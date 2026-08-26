"""标了「已变更」的需求整行不进统计。

「已变更」是 6/7 个进展子项的取值之一，不是行级字段——判定收口在
`enums.is_changed_row`（任一子项标了就算整行已变更）。这里钉住的是口径本身：

1. 度量看板四个接口一律不统计它，并如实报出被排除的条数（`changed`）；
2. 领域总览的需求统计同口径——两处分叉的表现是「一个看板算进去、另一个不算」，
   两边都不报错，对不上却查不出来；
3. **先剔已变更、再按项目切**：反过来的话没填项目的已变更行会混进 `unassigned`，
   页面提示「有 N 条没填项目」，去补了数字却纹丝不动；
4. 列表接口照常返回它——置灰/隐藏是前端的事，服务端把它藏起来就没法改回去了。
"""
import datetime

import pytest

_DOMAIN_PROGRESS = ("progress_walkthrough", "progress_reverse", "progress_stc",
                    "progress_coding", "progress_bbit", "progress_clarify")


@pytest.fixture(scope="module")
def iteration_id(client, admin_headers):
    """借一个没被别的用例占用的迭代，避免统计互相污染。"""
    rows = client.get("/api/annual-iterations", headers=admin_headers,
                      params={"year": datetime.date.today().year}).json()
    assert len(rows) >= 12, "年度迭代应自动生成 12 条"
    return rows[5]["id"]


@pytest.fixture(scope="module")
def version_ids(client, admin_headers):
    pr = client.post("/api/roadmap/projects", headers=admin_headers,
                     json={"name": "已变更口径项目"}).json()["id"]
    mv = client.post("/api/major-versions", headers=admin_headers,
                     json={"version_no": "G10SPCC00", "project_id": pr}).json()
    rv = client.post("/api/release-versions", headers=admin_headers,
                     json={"version_no": "G10SPCC01", "major_version_id": mv["id"]}).json()
    iv = client.post("/api/iteration-versions", headers=admin_headers,
                     json={"version_no": "G10SPCC01B001", "release_version_id": rv["id"]}).json()
    return {"release_id": rv["id"], "iter_version_id": iv["id"]}


def _domain(client, headers, iteration_id, **kw):
    body = {"iteration_id": iteration_id, "title": "需求"}
    body.update(kw)
    r = client.post("/api/iteration-requirements", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _all_done():
    return {f: "已完成" for f in _DOMAIN_PROGRESS}


@pytest.fixture(scope="module")
def seeded(client, admin_headers, iteration_id, version_ids):
    """三条领域需求：正常一条、整行已变更一条、只有一个子项已变更一条。"""
    ivid = version_ids["iter_version_id"]
    _domain(client, admin_headers, iteration_id, title="变更-正常", target_version_id=ivid,
            code_volume=1000, self_test_case_count=10, post_test_issue_count=2, **_all_done())
    _domain(client, admin_headers, iteration_id, title="变更-整行变更", target_version_id=ivid,
            code_volume=5000, self_test_case_count=50, post_test_issue_count=30,
            **{f: "已变更" for f in _DOMAIN_PROGRESS})
    one = dict(_all_done())
    one["progress_coding"] = "已变更"
    _domain(client, admin_headers, iteration_id, title="变更-单项变更", target_version_id=ivid,
            code_volume=3000, self_test_case_count=30, post_test_issue_count=20, **one)
    return version_ids


# ─── 度量看板 ───────────────────────────────────────────────────────────────
def test_version_metric_excludes_changed(client, admin_headers, seeded):
    m = client.get(f"/api/metrics/version/{seeded['release_id']}", headers=admin_headers).json()
    assert {i["title"] for i in m["items"]} == {"变更-正常"}
    assert m["changed"] == 2, "整行变更与单项变更都要算进 changed"
    assert m["total_code_volume"] == 1000, "被排除的行不能把代码量带进来"
    assert m["avg_completion"] == 1.0, "已变更的行不该继续把平均完成度往下拽"


def test_iteration_metric_excludes_changed(client, admin_headers, seeded, iteration_id):
    m = client.get(f"/api/metrics/iteration/{iteration_id}", headers=admin_headers).json()
    assert m["total_domain"] == 1
    assert m["changed"] == 2
    assert sum(m["by_priority"].values()) == 1, "优先级分布也得是剔除后的口径"


def test_iteration_quality_excludes_changed(client, admin_headers, seeded, iteration_id):
    year = datetime.date.today().year
    rows = client.get(f"/api/metrics/iteration-quality/{year}", headers=admin_headers).json()
    row = next(r for r in rows if r["iteration_id"] == iteration_id)
    assert row["code_volume"] == 1000
    assert row["self_test_cases"] == 10
    assert row["changed"] == 2
    assert row["self_test_case_density"] == 10.0, "分子分母要一起剔，只剔分子会得到量纲对数值错的密度"


def test_changed_is_split_before_project(client, admin_headers, version_ids):
    """先剔已变更、再按项目切：没填项目的已变更行不该混进 unassigned。"""
    rows = client.get("/api/annual-iterations", headers=admin_headers,
                      params={"year": datetime.date.today().year}).json()
    it = rows[6]["id"]
    pid = client.post("/api/roadmap/projects", headers=admin_headers,
                      json={"name": "变更与项目交叉"}).json()["id"]
    mv = client.post("/api/major-versions", headers=admin_headers,
                     json={"version_no": "G10SPCX00", "project_id": pid}).json()
    rv = client.post("/api/release-versions", headers=admin_headers,
                     json={"version_no": "G10SPCX01", "major_version_id": mv["id"]}).json()
    iv = client.post("/api/iteration-versions", headers=admin_headers,
                     json={"version_no": "G10SPCX01B001", "release_version_id": rv["id"]}).json()

    _domain(client, admin_headers, it, title="交叉-有项目", project_id=pid,
            target_version_id=iv["id"], **_all_done())
    # 没填项目 **而且** 已变更：它已经因为变更被剔掉了，不该再被算成"待补录项目"
    _domain(client, admin_headers, it, title="交叉-无项目且已变更", target_version_id=iv["id"],
            **{f: "已变更" for f in _DOMAIN_PROGRESS})

    m = client.get(f"/api/metrics/version/{rv['id']}", headers=admin_headers,
                   params={"project_id": pid}).json()
    assert m["changed"] == 1
    assert m["unassigned"] == 0, "已变更的行不该再冒充「没填项目」催人去补"
    assert {i["title"] for i in m["items"]} == {"交叉-有项目"}


def test_group_load_excludes_changed(client, admin_headers):
    rows = client.get("/api/annual-iterations", headers=admin_headers,
                      params={"year": datetime.date.today().year}).json()
    it = rows[7]["id"]
    dept = client.post("/api/resource-groups", headers=admin_headers,
                       json={"code": "CHGDEPT", "name": "变更口径部", "kind": "dept"}).json()
    g = client.post("/api/resource-groups", headers=admin_headers,
                    json={"code": "CHGPL", "name": "变更口径组", "kind": "pl",
                          "parent_id": dept["id"]})
    assert g.status_code == 200, g.text
    gid = g.json()["id"]
    u = client.post("/api/users", headers=admin_headers, json={
        "username": "chg_metric_user", "name": "变更度量员", "password": "test1234",
        "role": "normal", "can_login": True, "group_id": gid,
    })
    assert u.status_code == 200, u.text
    uid = u.json()["id"]

    _domain(client, admin_headers, it, title="组-在做", owner_user_id=uid, group_id=gid)
    _domain(client, admin_headers, it, title="组-已变更", owner_user_id=uid, group_id=gid,
            **{f: "已变更" for f in _DOMAIN_PROGRESS})

    m = client.get(f"/api/metrics/group/{gid}", headers=admin_headers).json()
    assert m["total_open"] == 1, "已变更的需求不该继续挂在别人的负载上"
    assert m["changed"] == 1


# ─── 领域总览与度量看板同口径 ────────────────────────────────────────────────
def test_domain_summary_excludes_changed(client, admin_headers):
    rows = client.get("/api/annual-iterations", headers=admin_headers,
                      params={"year": datetime.date.today().year}).json()
    it = rows[8]
    dept = client.post("/api/resource-groups", headers=admin_headers,
                       json={"code": "DOMCHGD", "name": "领域变更部", "kind": "dept"}).json()
    g = client.post("/api/resource-groups", headers=admin_headers,
                    json={"code": "DOMCHG", "name": "领域变更组", "kind": "pl",
                          "parent_id": dept["id"]}).json()

    _domain(client, admin_headers, it["id"], title="领域-在做", group_id=g["id"])
    _domain(client, admin_headers, it["id"], title="领域-已变更", group_id=g["id"],
            **{f: "已变更" for f in _DOMAIN_PROGRESS})

    data = client.get("/api/domains", headers=admin_headers,
                      params={"year": it["year"], "month": it["month"]}).json()
    row = next(r for r in data["rows"] if r["group_id"] == g["id"])
    assert row["req_summary"]["total"] == 1, "领域总览要和度量看板同口径"
    assert row["req_summary"]["changed"] == 1


# ─── 服务端不藏行 ───────────────────────────────────────────────────────────
def test_changed_rows_are_still_listed(client, admin_headers, seeded, iteration_id):
    """置灰/隐藏是前端的事。服务端把它过滤掉的话，误标的行就再也改不回来了。"""
    rows = client.get("/api/iteration-requirements", headers=admin_headers,
                      params={"iteration_id": iteration_id}).json()
    assert "变更-整行变更" in {r["title"] for r in rows}
