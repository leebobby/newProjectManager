"""迭代需求的「所属项目」列，以及度量看板按项目切分。

项目挂在需求行上而不是迭代上（迭代是按年月排的，同一个月里排着多个项目的需求）。
这里钉住三件会静默出错的事：

1. 按项目筛时，**没填项目的行不算进任何一个项目**——混进去数字看着都合理，没人查得出来；
2. 作为补偿，响应里的 `unassigned` 要如实报出被排除的条数，页面据此提示去补；
3. 不传 project_id 时是全量口径，`unassigned` 恒为 0（没有"被排除"这回事）。
"""
import datetime

import pytest


@pytest.fixture(scope="module")
def iteration_id(client, admin_headers):
    rows = client.get("/api/annual-iterations", headers=admin_headers,
                      params={"year": datetime.date.today().year}).json()
    assert rows, "年度迭代应自动生成 12 条"
    return rows[0]["id"]


@pytest.fixture(scope="module")
def other_iteration_id(client, admin_headers):
    rows = client.get("/api/annual-iterations", headers=admin_headers,
                      params={"year": datetime.date.today().year}).json()
    return rows[1]["id"]


@pytest.fixture(scope="module")
def proj_a(client, admin_headers):
    r = client.post("/api/roadmap/projects", headers=admin_headers,
                    json={"name": "需求项目甲"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def proj_b(client, admin_headers):
    r = client.post("/api/roadmap/projects", headers=admin_headers,
                    json={"name": "需求项目乙"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _domain(client, headers, iteration_id, **kw):
    body = {"iteration_id": iteration_id, "title": "需求"}
    body.update(kw)
    r = client.post("/api/iteration-requirements", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _product(client, headers, iteration_id, **kw):
    body = {"iteration_id": iteration_id, "title": "产品需求"}
    body.update(kw)
    r = client.post("/api/iteration-product-requirements", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


# ─── 列本身 ────────────────────────────────────────────────────────────────
def test_domain_requirement_carries_project_and_name(client, admin_headers, iteration_id, proj_a):
    row = _domain(client, admin_headers, iteration_id, title="带项目的领域需求", project_id=proj_a)
    assert row["project_id"] == proj_a
    assert row["project_name"] == "需求项目甲", "名字要由后端回填，前端不该自己拼"


def test_product_requirement_carries_project_and_name(client, admin_headers, iteration_id, proj_a):
    row = _product(client, admin_headers, iteration_id, title="带项目的产品需求", project_id=proj_a)
    assert row["project_id"] == proj_a
    assert row["project_name"] == "需求项目甲"


def test_project_can_be_changed_and_cleared(client, admin_headers, iteration_id, proj_a, proj_b):
    row = _domain(client, admin_headers, iteration_id, title="会改项目的需求", project_id=proj_a)
    r = client.put(f"/api/iteration-requirements/{row['id']}", headers=admin_headers,
                   json={"version": row["version"], "project_id": proj_b})
    assert r.status_code == 200, r.text
    assert r.json()["project_id"] == proj_b
    assert r.json()["project_name"] == "需求项目乙"

    cur = r.json()
    r = client.put(f"/api/iteration-requirements/{cur['id']}", headers=admin_headers,
                   json={"version": cur["version"], "project_id": None})
    assert r.status_code == 200, r.text
    assert r.json()["project_id"] is None
    assert r.json()["project_name"] is None


def test_list_filters_by_project(client, admin_headers, other_iteration_id, proj_a, proj_b):
    _domain(client, admin_headers, other_iteration_id, title="甲项目的", project_id=proj_a)
    _domain(client, admin_headers, other_iteration_id, title="乙项目的", project_id=proj_b)
    _domain(client, admin_headers, other_iteration_id, title="没填项目的")

    rows = client.get("/api/iteration-requirements", headers=admin_headers,
                      params={"iteration_id": other_iteration_id, "project_id": proj_a}).json()
    assert {r["title"] for r in rows} == {"甲项目的"}

    # 不传 project_id ＝ 全量，含没填项目的行
    rows = client.get("/api/iteration-requirements", headers=admin_headers,
                      params={"iteration_id": other_iteration_id}).json()
    assert {"甲项目的", "乙项目的", "没填项目的"} <= {r["title"] for r in rows}


def test_product_list_filters_by_project(client, admin_headers, other_iteration_id, proj_a, proj_b):
    _product(client, admin_headers, other_iteration_id, title="甲项目的产品需求", project_id=proj_a)
    _product(client, admin_headers, other_iteration_id, title="乙项目的产品需求", project_id=proj_b)

    rows = client.get("/api/iteration-product-requirements", headers=admin_headers,
                      params={"iteration_id": other_iteration_id, "project_id": proj_b}).json()
    assert {r["title"] for r in rows} == {"乙项目的产品需求"}


# ─── 度量：按项目切分 ───────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def metric_setup(client, admin_headers, proj_a, proj_b):
    """一个专属迭代 + 一个专属版本，挂三条需求：甲、乙、没填项目。"""
    rows = client.get("/api/annual-iterations", headers=admin_headers,
                      params={"year": datetime.date.today().year}).json()
    it = rows[2]["id"]

    pr = client.post("/api/roadmap/projects", headers=admin_headers,
                     json={"name": "度量口径项目"}).json()["id"]
    mv = client.post("/api/major-versions", headers=admin_headers,
                     json={"version_no": "M10SPCP00", "project_id": pr}).json()
    rv = client.post("/api/release-versions", headers=admin_headers,
                     json={"version_no": "M10SPCP01", "major_version_id": mv["id"]}).json()
    iv = client.post("/api/iteration-versions", headers=admin_headers,
                     json={"version_no": "M10SPCP01B001", "release_version_id": rv["id"]}).json()

    done = {f: "已完成" for f in ("progress_walkthrough", "progress_reverse", "progress_stc",
                                  "progress_coding", "progress_bbit", "progress_clarify")}
    _domain(client, admin_headers, it, title="度量-甲", project_id=proj_a,
            target_version_id=iv["id"], code_volume=1000, self_test_case_count=10, **done)
    _domain(client, admin_headers, it, title="度量-乙", project_id=proj_b,
            target_version_id=iv["id"], code_volume=2000, self_test_case_count=20)
    _domain(client, admin_headers, it, title="度量-没填项目",
            target_version_id=iv["id"], code_volume=4000, self_test_case_count=40)
    return {"iteration_id": it, "release_version_id": rv["id"]}


def test_version_metric_scoped_to_project(client, admin_headers, metric_setup, proj_a):
    m = client.get(f"/api/metrics/version/{metric_setup['release_version_id']}",
                   headers=admin_headers, params={"project_id": proj_a}).json()
    assert {i["title"] for i in m["items"]} == {"度量-甲"}
    assert m["total_code_volume"] == 1000, "别的项目 / 没填项目的代码量不能混进来"
    assert m["unassigned"] == 1, "被排除的那条要如实报出来"


def test_version_metric_without_project_is_full_scope(client, admin_headers, metric_setup):
    m = client.get(f"/api/metrics/version/{metric_setup['release_version_id']}",
                   headers=admin_headers).json()
    assert {"度量-甲", "度量-乙", "度量-没填项目"} <= {i["title"] for i in m["items"]}
    assert m["unassigned"] == 0, "全量口径下没有「被排除」这回事"


def test_iteration_metric_scoped_to_project(client, admin_headers, metric_setup, proj_b):
    m = client.get(f"/api/metrics/iteration/{metric_setup['iteration_id']}",
                   headers=admin_headers, params={"project_id": proj_b}).json()
    assert m["total_domain"] == 1
    assert m["unassigned"] == 1

    full = client.get(f"/api/metrics/iteration/{metric_setup['iteration_id']}",
                      headers=admin_headers).json()
    assert full["total_domain"] == 3
    assert full["unassigned"] == 0


def test_iteration_quality_scoped_to_project(client, admin_headers, metric_setup, proj_a):
    year = datetime.date.today().year
    rows = client.get(f"/api/metrics/iteration-quality/{year}",
                      headers=admin_headers, params={"project_id": proj_a}).json()
    row = next(r for r in rows if r["iteration_id"] == metric_setup["iteration_id"])
    assert row["code_volume"] == 1000
    assert row["self_test_cases"] == 10
    assert row["self_test_case_density"] == 10.0, "密度要按筛后的分子分母算，不是筛分子不筛分母"

    full = client.get(f"/api/metrics/iteration-quality/{year}", headers=admin_headers).json()
    frow = next(r for r in full if r["iteration_id"] == metric_setup["iteration_id"])
    assert frow["code_volume"] == 7000


def test_group_metric_scoped_to_project(client, admin_headers, iteration_id, proj_a, proj_b):
    """组级负载也按项目切：别的项目的活不能算到这个组的负载里。"""
    dept = client.post("/api/resource-groups", headers=admin_headers,
                       json={"code": "PRJDEPT", "name": "项目度量部", "kind": "dept"})
    assert dept.status_code == 200, dept.text
    g = client.post("/api/resource-groups", headers=admin_headers,
                    json={"code": "PRJPL", "name": "项目度量组", "kind": "pl",
                          "parent_id": dept.json()["id"]})
    assert g.status_code == 200, g.text
    gid = g.json()["id"]

    u = client.post("/api/users", headers=admin_headers, json={
        "username": "prj_metric_user", "name": "项目度量员", "password": "test1234",
        "role": "normal", "can_login": True, "group_id": gid,
    })
    assert u.status_code == 200, u.text
    uid = u.json()["id"]

    _domain(client, admin_headers, iteration_id, title="组-甲项目",
            owner_user_id=uid, group_id=gid, project_id=proj_a)
    _domain(client, admin_headers, iteration_id, title="组-乙项目",
            owner_user_id=uid, group_id=gid, project_id=proj_b)
    _domain(client, admin_headers, iteration_id, title="组-没填项目",
            owner_user_id=uid, group_id=gid)

    m = client.get(f"/api/metrics/group/{gid}", headers=admin_headers,
                   params={"project_id": proj_a}).json()
    assert m["total_open"] == 1, "别的项目 / 没填项目的需求不能算进这个项目的负载"
    assert m["unassigned"] == 1

    full = client.get(f"/api/metrics/group/{gid}", headers=admin_headers).json()
    assert full["total_open"] == 3
    assert full["unassigned"] == 0


# ─── 导入：「项目」列反查不中要留空而不是报错 ────────────────────────────────
def test_import_resolves_project_by_name(client, admin_headers, iteration_id):
    from openpyxl import Workbook
    import io

    from routers.iteration_requirements import _IMPORT_COLUMNS

    client.post("/api/roadmap/projects", headers=admin_headers, json={"name": "导入命中项目"})

    headers = [c[0] for c in _IMPORT_COLUMNS]
    wb = Workbook()
    ws = wb.active
    ws.append(headers)

    def row(title, project):
        cells = [""] * len(headers)
        cells[headers.index("需求标题")] = title
        cells[headers.index("项目")] = project
        return cells

    ws.append(row("导入-命中", "导入命中项目"))
    ws.append(row("导入-对不上", "根本没有这个项目"))
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    r = client.post("/api/iteration-requirements/import", headers=admin_headers,
                    params={"iteration_id": iteration_id},
                    files={"file": ("req.xlsx", buf.getvalue(),
                                    "application/vnd.openxmlformats-officedocument."
                                    "spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 2
    assert not r.json()["errors"], "反查不中不该报错，留给页面事后补选"

    rows = client.get("/api/iteration-requirements", headers=admin_headers,
                      params={"iteration_id": iteration_id}).json()
    by_title = {x["title"]: x for x in rows}
    assert by_title["导入-命中"]["project_name"] == "导入命中项目"
    assert by_title["导入-对不上"]["project_id"] is None
