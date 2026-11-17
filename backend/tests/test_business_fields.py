"""客户合入大版本、事务工作量、领域 SR/AR 的完整写入与兼容性。"""
import importlib.util
import io
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def business(client, admin_headers, machine_id):
    key = uuid4().hex[:10]
    def post(path, data):
        response = client.post('/api' + path, headers=admin_headers, json=data)
        assert response.status_code == 200, response.text
        return response.json()
    project = post('/roadmap/projects', {'name': '业务字段项目-' + key})
    major = post('/major-versions', {'version_no': 'MAJOR-' + key, 'title': '合入大版本', 'project_id': project['id']})
    special = post('/specials', {'name': '工作量专项-' + key})
    iterations = client.get('/api/annual-iterations', params={'year': 2062}, headers=admin_headers).json()
    return {'post': post, 'major': major, 'special': special, 'iterations': iterations, 'key': key, 'machine': machine_id}


def test_customer_issue_major_version_roundtrip_clear_validation_and_export(client, admin_headers, business):
    major = business['major']
    item = business['post']('/customer-issues', {'machine_status_id': business['machine'],
           'description': '合入验证', 'merge_major_version_id': major['id']})
    assert item['merge_major_version_id'] == major['id']
    assert major['version_no'] in item['merge_major_version']
    catalog = client.get('/api/major-versions/all', headers=admin_headers).json()
    assert any(version['id'] == major['id'] and '业务字段项目' in version['label'] for version in catalog)
    rows = client.get('/api/customer-issues', headers=admin_headers).json()
    assert next(row for row in rows if row['id'] == item['id'])['merge_major_version_id'] == major['id']
    result = client.put(f"/api/customer-issues/{item['id']}", headers=admin_headers,
                        json={'version': item['version'], 'merge_major_version_id': 99999999})
    assert result.status_code == 400
    from openpyxl import load_workbook
    export = client.get('/api/customer-issues/export.xlsx', headers=admin_headers)
    sheet = load_workbook(io.BytesIO(export.content)).active
    headers = [cell.value for cell in sheet[1]]
    assert headers[-1] == '合入版本'
    assert any(major['version_no'] in str(row[-1].value) for row in list(sheet)[1:])
    cleared = client.put(f"/api/customer-issues/{item['id']}", headers=admin_headers,
                         json={'version': item['version'], 'merge_major_version_id': None})
    assert cleared.status_code == 200
    assert cleared.json()['merge_major_version_id'] is None


def test_optional_task_workload_including_zero_and_negative(client, admin_headers, business):
    sid = business['special']['id']
    row = business['post'](f'/specials/{sid}/tasks', {'content': '事务工作量', 'workload': 1.75})
    assert row['workload'] == 1.75
    detail = client.get(f'/api/specials/{sid}', headers=admin_headers).json()
    assert detail['tasks'][0]['workload'] == 1.75
    for value in (0, None):
        response = client.put(f"/api/specials/tasks/{row['id']}", headers=admin_headers, json={'workload': value})
        assert response.status_code == 200, response.text
        assert response.json()['workload'] == value
    rejected = client.put(f"/api/specials/tasks/{row['id']}", headers=admin_headers, json={'workload': -1})
    assert rejected.status_code == 422
    # 风险与事务共用表单时不会因额外的空工作量创建失败。
    risk = business['post'](f'/specials/{sid}/risks', {'content': '风险', 'workload': None})
    assert risk['workload'] is None


def test_workload_is_in_excel_and_weekly_html(client, admin_headers, business):
    sid = business['special']['id']
    business['post'](f'/specials/{sid}/tasks', {'content': '导出事务', 'workload': 2.5})
    from openpyxl import load_workbook
    response = client.get(f'/api/specials/{sid}/export.xlsx', headers=admin_headers)
    assert response.status_code == 200, response.text
    workbook = load_workbook(io.BytesIO(response.content))
    values = [str(cell.value) for sheet in workbook for row in sheet for cell in row if cell.value is not None]
    assert '工作量（人天）' in values and '2.5' in values
    from email import policy
    from email.parser import BytesParser
    report = client.post(f'/api/specials/{sid}/report.eml', headers=admin_headers, json={})
    assert report.status_code == 200, report.text
    message = BytesParser(policy=policy.default).parsebytes(report.content)
    html = next(part for part in message.walk() if part.get_content_type() == 'text/html').get_content()
    assert '工作量（人天）' in html and '2.5' in html


def test_sr_repeats_but_ar_is_globally_unique_and_nullable(client, admin_headers, business):
    post = business['post']
    first, second = [iteration['id'] for iteration in business['iterations'][:2]]
    ar = 'AR-' + business['key']
    a = post('/iteration-requirements', {'iteration_id': first, 'req_no': 'SR-重复', 'ar_no': ar, 'title': '共同标题'})
    b = post('/iteration-requirements', {'iteration_id': first, 'req_no': 'SR-重复', 'ar_no': ar + '-B', 'title': '共同标题'})
    assert a['req_no'] == b['req_no'] and a['ar_no'] != b['ar_no']
    duplicate = client.post('/api/iteration-requirements', headers=admin_headers,
                            json={'iteration_id': second, 'ar_no': ' ' + ar.lower() + ' ', 'title': '别的迭代'})
    assert duplicate.status_code == 409 and 'AR' in duplicate.json()['detail']
    for _ in range(2):
        post('/iteration-requirements', {'iteration_id': first, 'req_no': 'SR-重复', 'ar_no': '', 'title': '共同标题'})
    update = client.put(f"/api/iteration-requirements/{b['id']}", headers=admin_headers,
                        json={'version': b['version'], 'ar_no': ar})
    assert update.status_code == 409
    clear = client.put(f"/api/iteration-requirements/{a['id']}", headers=admin_headers,
                       json={'version': a['version'], 'ar_no': None})
    assert clear.status_code == 200 and clear.json()['ar_no'] is None
    post('/iteration-requirements', {'iteration_id': second, 'ar_no': ar, 'title': '释放后复用'})


def test_ar_database_constraint_and_link_candidates(client, admin_headers, business):
    from database import SessionLocal
    from sqlalchemy.exc import IntegrityError
    import models
    iteration = business['iterations'][0]['id']
    ar = 'AR-KEY-' + business['key']
    row = business['post']('/iteration-requirements', {'iteration_id': iteration, 'ar_no': ar, 'title': '按 AR 查找'})
    with SessionLocal() as db:
        db.add(models.IterationRequirement(iteration_id=iteration, ar_no=ar.lower(), title='并发重复'))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    candidates = client.get('/api/iteration-req-links/candidates', headers=admin_headers,
                            params={'side': 'domain', 'iteration_id': iteration, 'q': ar})
    assert candidates.status_code == 200, candidates.text
    assert any(item['id'] == row['id'] and item['ar_no'] == ar for item in candidates.json())


def test_legacy_schema_upgrade_keeps_sr_and_optional_values(tmp_path):
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    source = Path(__file__).resolve().parents[1] / 'alembic/versions/0021_issue_version_workload_ar.py'
    spec = importlib.util.spec_from_file_location('business_migration', source)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine('sqlite:///' + str(tmp_path / 'legacy.db'))
    with engine.begin() as connection:
        for statement in ('CREATE TABLE major_versions (id INTEGER PRIMARY KEY)',
                          'CREATE TABLE customer_issues (id INTEGER PRIMARY KEY, description TEXT)',
                          'CREATE TABLE special_tasks (id INTEGER PRIMARY KEY, content TEXT)',
                          'CREATE TABLE iteration_requirements (id INTEGER PRIMARY KEY, req_no TEXT)'):
            connection.exec_driver_sql(statement)
        connection.exec_driver_sql("INSERT INTO iteration_requirements VALUES (1, '旧SR'), (2, '旧SR')")
        connection.exec_driver_sql("INSERT INTO customer_issues VALUES (1, '旧问题')")
        connection.exec_driver_sql("INSERT INTO special_tasks VALUES (1, '旧事务')")
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()
        assert connection.exec_driver_sql('SELECT req_no, ar_no, ar_key FROM iteration_requirements').all() == [('旧SR', None, None)] * 2
        assert connection.exec_driver_sql('SELECT description, merge_major_version_id FROM customer_issues').one() == ('旧问题', None)
        assert connection.exec_driver_sql('SELECT content, workload FROM special_tasks').one() == ('旧事务', None)
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert connection.exec_driver_sql('SELECT req_no FROM iteration_requirements').all() == [('旧SR',)] * 2
        assert connection.exec_driver_sql('SELECT content FROM special_tasks').one() == ('旧事务',)


def test_domain_import_accepts_legacy_sr_and_rejects_duplicate_ar(client, admin_headers, business):
    from openpyxl import Workbook
    def upload(headers, rows):
        book = Workbook()
        sheet = book.active
        sheet.append(headers)
        for row in rows:
            sheet.append(row)
        blob = io.BytesIO()
        book.save(blob)
        response = client.post('/api/iteration-requirements/import', headers=admin_headers,
                               params={'iteration_id': business['iterations'][0]['id']},
                               files={'file': ('requirements.xlsx', blob.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
        assert response.status_code == 200, response.text
        return response.json()
    sr = 'LEGACY-' + business['key']
    legacy = upload(['需求编号', '需求标题'], [[sr, '旧表甲'], [sr, '旧表乙']])
    assert legacy['created'] == 2 and legacy['errors'] == []
    ar = 'IMPORT-' + business['key']
    imported = upload(['需求编号(SR)', '需求编号AR', '需求标题'],
                      [[sr, ar, '新表甲'], [sr, ar + '-B', '新表乙'], [sr, ar.lower(), '重复 AR']])
    assert imported['created'] == 2 and imported['skipped'] == 1
    repeated = upload(['需求编号AR', '需求标题'], [[ar, '跨次导入重复']])
    assert repeated['created'] == 0 and repeated['skipped'] == 1


def test_customer_import_resolves_exported_major_version_label(client, admin_headers, business):
    from openpyxl import Workbook
    machine = next(row for row in client.get('/api/customer-status', headers=admin_headers).json() if row['id'] == business['machine'])
    major = business['major']
    label = next(row['label'] for row in client.get('/api/major-versions/all', headers=admin_headers).json() if row['id'] == major['id'])
    book = Workbook()
    sheet = book.active
    sheet.append(['机台编号', '关键问题描述', '合入版本'])
    sheet.append([machine['machine_id'], '导入合入版本-' + business['key'], label])
    blob = io.BytesIO()
    book.save(blob)
    response = client.post('/api/customer-issues/import', headers=admin_headers,
                           files={'file': ('issues.xlsx', blob.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    assert response.status_code == 200, response.text
    assert response.json()['created'] == 1
    rows = client.get('/api/customer-issues', headers=admin_headers).json()
    saved = next(row for row in rows if row['description'] == '导入合入版本-' + business['key'])
    assert saved['merge_major_version_id'] == major['id']


def test_cleanup_script_preserves_allowed_repeated_sr(client, tmp_path):
    import subprocess
    import sys
    import sqlalchemy as sa
    from sqlalchemy.orm import Session
    import models

    path = tmp_path / 'cleanup.db'
    engine = sa.create_engine('sqlite:///' + str(path))
    models.Base.metadata.create_all(engine)
    with Session(engine) as db:
        iteration = models.AnnualIteration(year=2070, month=1)
        db.add(iteration)
        db.flush()
        db.add_all([models.IterationRequirement(iteration_id=iteration.id, req_no='允许重复SR', title='同名')
                    for _ in range(2)])
        db.commit()
    script = Path(__file__).resolve().parents[1] / 'scripts/find_duplicate_requirements.py'
    result = subprocess.run([sys.executable, str(script), '--db', str(path), '--apply'],
                            cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    with Session(engine) as db:
        assert db.query(models.IterationRequirement).count() == 2


def test_archives_keep_workload_and_merge_version_snapshot(client, admin_headers, business):
    post = business['post']
    sid = business['special']['id']
    task = post(f'/specials/{sid}/tasks', {'content': '存档事务', 'workload': 2.5})
    snapshot = post('/archives', {'kind': 'special', 'ref_id': sid})
    client.put(f"/api/specials/tasks/{task['id']}", headers=admin_headers, json={'workload': 0})
    saved = client.get(f"/api/archives/{snapshot['id']}", headers=admin_headers).json()
    assert saved['payload']['tasks'][0]['workload'] == 2.5
    html = client.get(f"/api/archives/{snapshot['id']}/view", headers=admin_headers).text
    assert '工作量（人天）' in html and '2.5' in html
    customer = post('/customers', {'code': 'C' + business['key'], 'display_name': '存档客户'})
    machine = archived = None
    try:
        # 客户面通过客户编码或别名绑定客户，而不是 display_name。
        machine = post('/customer-status', {'machine_id': 'M' + business['key'],
                                           'battlefield': customer['code'], 'current_stage': '验证', 'customer_status': '跟进'})
        assert machine['customer_id'] == customer['id']
        issue = post('/customer-issues', {'machine_status_id': machine['id'], 'description': '存档问题',
                                         'merge_major_version_id': business['major']['id']})
        archived = post('/archives', {'kind': 'customer', 'ref_id': customer['id']})
        client.put(f"/api/customer-issues/{issue['id']}", headers=admin_headers,
                   json={'version': issue['version'], 'merge_major_version_id': None})
        rendered = client.get(f"/api/archives/{archived['id']}/view", headers=admin_headers).text
        assert business['major']['version_no'] in rendered and '合入版本' in rendered
    finally:
        if archived:
            client.delete(f"/api/archives/{archived['id']}", headers=admin_headers)
        if machine:
            client.delete(f"/api/customer-status/{machine['id']}", headers=admin_headers)
        client.delete(f"/api/customers/{customer['id']}", headers=admin_headers)
