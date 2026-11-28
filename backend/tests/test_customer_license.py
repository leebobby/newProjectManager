"""授权信息、真实文件历史、配置联动、权限、并发与老库迁移。"""
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def license_setup(client, admin_headers, tmp_path, monkeypatch):
    from routers import config, licenses
    monkeypatch.setattr(config, 'CONFIG_PATH', tmp_path / 'config.json')
    monkeypatch.setattr(licenses, 'UPLOAD_ROOT', tmp_path / 'uploads/licenses')
    settings = {'customer_machine_models': ['YLS3000', 'YLS5000', 'YLS3000Y', 'YLS5000Y'],
                'license_throughput_packages': ['标准包', '高产包'], 'license_algorithms': ['高精度'],
                'license_optional_features': ['远程诊断', '报表']}
    assert client.put('/api/config', headers=admin_headers, json=settings).status_code == 200
    customer = client.post('/api/customers', headers=admin_headers, json={'code': 'LC-' + uuid4().hex[:8]}).json()
    machine = client.post('/api/customer-status', headers=admin_headers, json={
        'machine_id': 'LC-' + uuid4().hex[:8], 'battlefield': customer['code'], 'model': 'YLS3000',
        'current_stage': '验证', 'customer_status': '联调'}).json()
    assert 'id' in machine, machine
    def create(metadata=None, file=None):
        response = client.post('/api/licenses', headers=admin_headers,
            data={'machine_status_id': machine['id'], 'metadata': json.dumps(metadata or {}, ensure_ascii=False)},
            files={'file': ('license.lic', file, 'application/octet-stream')} if file is not None else None)
        assert response.status_code == 200, response.text
        return response.json()
    yield {'machine': machine, 'customer': customer, 'settings': settings, 'create': create,
           'root': licenses.UPLOAD_ROOT, 'config': config}
    client.delete(f"/api/customer-status/{machine['id']}", headers=admin_headers)
    client.delete(f"/api/customers/{customer['id']}", headers=admin_headers)


def test_metadata_and_file_versions_keep_bytes_and_authorization_snapshots(client, admin_headers, license_setup):
    setup = license_setup
    item = setup['create']({'tool_id': 'NE-01', 'uuid': 'uuid-first', 'throughput_package': '标准包',
                           'algorithm': '高精度', 'optional_features': ['远程诊断', '报表']}, b'\x00first\xff')
    lid = item['id']
    assert item['file_version'] == 1 and item['uploaded_at'].endswith('+08:00')
    assert 'file_path' not in item
    edit = client.put(f'/api/licenses/{lid}', headers=admin_headers, json={
        'version': item['version'], 'tool_id': 'NE-02', 'uuid': '', 'throughput_package': '', 'optional_features': []})
    assert edit.status_code == 200, edit.text
    current = edit.json()
    assert current['file_version'] == 1 and current['uuid'] == '' and current['optional_features'] == []
    upload = client.post(f'/api/licenses/{lid}/files', headers=admin_headers,
        data={'version': current['version'], 'note': '升级'}, files={'file': ('new.bin', b'\xffsecond\x00')})
    assert upload.status_code == 200, upload.text
    current = upload.json()
    assert current['file_version'] == 2
    history = client.get(f'/api/licenses/{lid}/files', headers=admin_headers).json()
    assert [f['file_version'] for f in history] == [2, 1]
    assert history[1]['snapshot']['uuid'] == 'uuid-first'
    assert history[1]['snapshot']['optional_features'] == ['远程诊断', '报表']
    assert history[0]['snapshot']['tool_id'] == 'NE-02'
    for file, content in zip(history, [b'\xffsecond\x00', b'\x00first\xff']):
        response = client.get(f"/api/licenses/{lid}/files/{file['id']}/download", headers=admin_headers)
        assert response.status_code == 200 and response.content == content
    assert client.get(f'/api/licenses/{lid}/download', headers=admin_headers).content == b'\xffsecond\x00'
    changes = client.get('/api/history', headers=admin_headers, params={'entity': 'machine_license', 'entity_id': lid}).json()
    assert any(r['field'] == 'tool_id' and r['old_value'] == 'NE-01' and r['new_value'] == 'NE-02' for r in changes['items'])
    assert len(list(setup['root'].rglob('*.*'))) == 2


def test_model_is_shared_with_overview_but_historical_snapshot_is_frozen(client, admin_headers, license_setup):
    setup = license_setup
    first = setup['create'](file=b'v1')
    second = setup['create']()
    machine = setup['machine']
    response = client.put(f"/api/customer-status/{machine['id']}", headers=admin_headers,
                          json={'version': machine['version'], 'model': 'YLS5000Y'})
    assert response.status_code == 200, response.text
    overview = client.get('/api/customer-status', headers=admin_headers).json()
    assert next(m for m in overview if m['id'] == machine['id'])['model'] == 'YLS5000Y'
    detail = client.get(f"/api/customers/{setup['customer']['id']}/machines", headers=admin_headers).json()
    assert detail[0]['model'] == 'YLS5000Y'
    rows = client.get('/api/licenses', headers=admin_headers, params={'machine_status_id': machine['id']}).json()
    assert {r['model'] for r in rows} == {'YLS5000Y'} and len(rows) == 2
    changes = client.get('/api/history', headers=admin_headers,
        params={'entity': 'customer_machine', 'entity_id': machine['id']}).json()
    assert changes['total'] == 1  # 即使 SQLite 复用已删机台的 id，也只认这一台的修订。
    history = client.get(f"/api/licenses/{first['id']}/files", headers=admin_headers).json()
    assert history[0]['snapshot']['model'] == 'YLS3000'
    assert second['file_version'] == 0
    stale = client.put(f"/api/customer-status/{machine['id']}", headers=admin_headers,
                       json={'version': machine['version'], 'model': 'YLS3000Y'})
    assert stale.status_code == 409


def test_configuration_is_shared_validated_and_in_use_options_are_kept(client, admin_headers, license_setup):
    setup = license_setup
    setup['create']({'throughput_package': '标准包'})
    for key, value in [('license_throughput_packages', ['高产包']), ('customer_machine_models', ['YLS5000'])]:
        assert client.put('/api/config', headers=admin_headers, json={key: value}).status_code == 400
    for invalid in [None, 'wrong', [123], [' '], ['x' * 129]]:
        assert client.put('/api/config', headers=admin_headers, json={'license_algorithms': invalid}).status_code == 400
    rejected = client.post('/api/licenses', headers=admin_headers, data={
        'machine_status_id': setup['machine']['id'], 'metadata': json.dumps({'algorithm': '未配置'})})
    assert rejected.status_code == 400
    good = client.put('/api/config', headers=admin_headers, json={'license_algorithms': ['高精度', ' 新算法 ', '新算法']})
    assert good.status_code == 200 and good.json()['license_algorithms'] == ['高精度', '新算法']
    assert good.json()['customer_machine_models'] == setup['settings']['customer_machine_models']
    assert setup['create']({'algorithm': '新算法'})['algorithm'] == '新算法'


def test_concurrent_uploads_conflict_and_failure_cleans_new_file(client, admin_headers, license_setup, monkeypatch):
    from routers import licenses
    setup = license_setup
    item = setup['create'](file=b'initial')
    lid = item['id']
    def upload(number):
        return client.post(f'/api/licenses/{lid}/files', headers=admin_headers,
            data={'version': item['version']}, files={'file': (f'{number}.lic', str(number).encode())})
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(upload, [1, 2]))
    assert sorted(r.status_code for r in results) == [200, 409]
    current = next(r.json() for r in results if r.status_code == 200)
    count = len(list(setup['root'].rglob('*.*')))
    def fail(*args, **kwargs):
        raise RuntimeError('history failure')
    monkeypatch.setattr(licenses.revisions, 'record', fail)
    with pytest.raises(RuntimeError, match='history failure'):
        client.post(f'/api/licenses/{lid}/files', headers=admin_headers,
            data={'version': current['version']}, files={'file': ('rollback.lic', b'rollback')})
    assert len(list(setup['root'].rglob('*.*'))) == count
    history = client.get(f'/api/licenses/{lid}/files', headers=admin_headers).json()
    assert len(history) == 2
    stale = client.put(f'/api/licenses/{lid}', headers=admin_headers, json={'version': 0, 'tool_id': 'overwrite'})
    assert stale.status_code == 409


def test_read_and_write_permissions_and_cross_license_download(client, admin_headers, license_setup):
    setup = license_setup
    first = setup['create'](file=b'first')
    second = setup['create']()
    user = 'license-' + uuid4().hex[:8]
    client.post('/api/users', headers=admin_headers, json={'username': user, 'password': 'test123', 'role': 'normal', 'can_login': True})
    login = client.post('/api/auth/login', json={'username': user, 'password': 'test123'})
    headers = {'Authorization': 'Bearer ' + login.json()['access_token']}
    lid = first['id']
    assert client.get('/api/licenses', params={'machine_status_id': setup['machine']['id']}).status_code == 401
    assert client.get(f'/api/licenses/{lid}/files', headers=headers).status_code == 200
    assert client.get(f'/api/licenses/{lid}/download', headers=headers).content == b'first'
    assert client.post('/api/licenses', headers=headers, data={'machine_status_id': setup['machine']['id']}).status_code == 403
    assert client.put(f'/api/licenses/{lid}', headers=headers, json={'version': 0, 'tool_id': 'forbidden'}).status_code == 403
    assert client.delete(f'/api/licenses/{lid}', headers=headers).status_code == 403
    assert client.post(f'/api/licenses/{lid}/files', headers=headers, data={'version': 0}, files={'file': ('no.lic', b'no')}).status_code == 403
    machine = setup['machine']
    assert client.put(f"/api/customer-status/{machine['id']}", headers=headers, json={'version': machine['version'], 'model': 'YLS5000'}).status_code == 403
    assert client.put('/api/config', headers=headers, json={'license_algorithms': []}).status_code == 403
    history = client.get(f'/api/licenses/{lid}/files', headers=headers).json()
    assert client.get(f"/api/licenses/{second['id']}/files/{history[0]['id']}/download", headers=headers).status_code == 404
    assert client.delete(f'/api/licenses/{lid}', headers=admin_headers).status_code == 200
    assert client.get(f'/api/licenses/{lid}/download', headers=headers).status_code == 404
    assert not list(setup['root'].rglob('*.*'))


def test_legacy_files_upgrade_idempotently_without_changing_paths_or_metadata(tmp_path):
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    source = Path(__file__).resolve().parents[1] / 'alembic/versions/0022_customer_license.py'
    spec = importlib.util.spec_from_file_location('license_migration', source)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine('sqlite:///' + str(tmp_path / 'legacy.db'))
    file = tmp_path / 'original.lic'
    file.write_bytes(b'\xffold\x00')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE customer_status (id INTEGER PRIMARY KEY, model TEXT)')
        connection.exec_driver_sql("INSERT INTO customer_status VALUES (1, '旧型号')")
        connection.exec_driver_sql('''CREATE TABLE machine_licenses (id INTEGER PRIMARY KEY,
            machine_status_id INTEGER, file_name TEXT NOT NULL, file_path TEXT NOT NULL, file_size INTEGER,
            remark TEXT, uploaded_by TEXT, uploaded_at DATETIME)''')
        connection.exec_driver_sql("""INSERT INTO machine_licenses VALUES
            (1,1,'original.lic','licenses/1/original.lic',5,'原备注','old-admin','2026-01-01 02:00:00')""")
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()
        files = connection.exec_driver_sql('SELECT * FROM machine_license_files').mappings().all()
        assert len(files) == 1 and files[0]['file_path'] == 'licenses/1/original.lic'
        assert files[0]['uploaded_by'] == 'old-admin'
        assert json.loads(files[0]['snapshot_json'])['model'] == '旧型号'
        assert json.loads(files[0]['snapshot_json'])['remark'] == '原备注'
        assert connection.exec_driver_sql('SELECT file_version,version,created_at FROM machine_licenses').one() == (1, 0, '2026-01-01 02:00:00')
    assert file.read_bytes() == b'\xffold\x00'
