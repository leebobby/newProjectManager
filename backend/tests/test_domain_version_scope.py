"""领域总览的「按版本」口径。

需求填的是**迭代版本**（构建号），人看的是**版本**——所以「这个版本上有哪些需求」
= 该版本名下所有构建 + 字符串回退。匹配规则收口在 `routers/_req_scope.py`，
度量看板的版本达成率走的是同一份：两处各写一份的表现是同一个版本在两个页面上
条数不一样，而两边看着都像对的。

这里钉住的是：
1. 按版本＝**跨迭代**，并且给了 release_version_id 就忽略 year/month（二选一，不叠加）；
2. 可选版本只列当前挂着需求的那些，条数与总览一致；
3. 下钻与总览同口径——分叉的表现是「格子里写 3 条、点进去 1 条」；
4. FK 为空但 planned_version 写了版本号的老行照样算进来；
5. 「已变更」在按版本口径下同样整行排除。
"""
import datetime

import pytest

_DOMAIN_PROGRESS = ("progress_walkthrough", "progress_reverse", "progress_stc",
                    "progress_coding", "progress_bbit", "progress_clarify")


@pytest.fixture(scope="module")
def env(client, admin_headers):
    """两个月的迭代 + 一个版本（两个构建），需求分散在两个月里。"""
    its = client.get("/api/annual-iterations", headers=admin_headers,
                     params={"year": datetime.date.today().year}).json()
    it_a, it_b = its[0], its[1]

    pr = client.post("/api/roadmap/projects", headers=admin_headers,
                     json={"name": "版本口径项目"}).json()["id"]
    mv = client.post("/api/major-versions", headers=admin_headers,
                     json={"version_no": "V10SPCV00", "project_id": pr}).json()
    rv = client.post("/api/release-versions", headers=admin_headers,
                     json={"version_no": "V10SPCV01", "major_version_id": mv["id"]}).json()
    rv2 = client.post("/api/release-versions", headers=admin_headers,
                      json={"version_no": "V10SPCV02", "major_version_id": mv["id"]}).json()
    iv1 = client.post("/api/iteration-versions", headers=admin_headers,
                      json={"version_no": "V10SPCV01B001", "release_version_id": rv["id"]}).json()
    iv2 = client.post("/api/iteration-versions", headers=admin_headers,
                      json={"version_no": "V10SPCV01B002", "release_version_id": rv["id"]}).json()

    dept = client.post("/api/resource-groups", headers=admin_headers,
                       json={"code": "VSCD", "name": "版本口径部", "kind": "dept"}).json()
    g = client.post("/api/resource-groups", headers=admin_headers,
                    json={"code": "VSCG", "name": "版本口径组", "kind": "pl",
                          "parent_id": dept["id"]}).json()

    def req(iteration, title, **kw):
        body = {"iteration_id": iteration["id"], "title": title, "group_id": g["id"]}
        body.update(kw)
        r = client.post("/api/iteration-requirements", headers=admin_headers, json=body)
        assert r.status_code == 200, r.text
        return r.json()

    # 同一个版本，需求分散在两个月：按迭代只能看到一半，按版本才是全貌
    req(it_a, "版本口径-A月", target_version_id=iv1["id"])
    req(it_b, "版本口径-B月", target_version_id=iv2["id"])
    # FK 没反查上、只留了字符串的老行
    req(it_b, "版本口径-字符串", planned_version="V10SPCV01")
    # 已变更：任何口径下都不进统计
    req(it_b, "版本口径-已变更", target_version_id=iv1["id"],
        **{f: "已变更" for f in _DOMAIN_PROGRESS})
    # 挂在另一个版本上，用来证明没有串台
    req(it_a, "版本口径-别的版本", planned_version="V10SPCV02")

    return {"group_id": g["id"], "release_id": rv["id"], "other_release_id": rv2["id"],
            "it_a": it_a, "it_b": it_b}


def _row(client, headers, env, **params):
    data = client.get("/api/domains", headers=headers, params=params).json()
    return data, next(r for r in data["rows"] if r["group_id"] == env["group_id"])


def test_version_scope_spans_iterations(client, admin_headers, env):
    """按版本＝跨迭代。按月份只看得到 A 月那两条（还混着别的版本的），按版本才是这个版本的全貌。"""
    _, by_month = _row(client, admin_headers, env,
                       year=env["it_a"]["year"], month=env["it_a"]["month"])
    assert by_month["req_summary"]["total"] == 2   # A月本版本 1 条 + A月别的版本 1 条

    _, by_ver = _row(client, admin_headers, env, release_version_id=env["release_id"])
    # A月1条 + B月1条 + 字符串回退1条；已变更那条整行排除
    assert by_ver["req_summary"]["total"] == 3
    assert by_ver["req_summary"]["changed"] == 1


def test_version_scope_ignores_month(client, admin_headers, env):
    """两个口径**不叠加**：给了版本就忽略 year/month，否则会得到一个既不是
    这个版本、也不是这个迭代的数，页面上看着像"这个版本怎么只有 1 条"。"""
    data, row = _row(client, admin_headers, env,
                     release_version_id=env["release_id"],
                     year=env["it_a"]["year"], month=env["it_a"]["month"])
    assert row["req_summary"]["total"] == 3
    assert data["selected_year"] is None and data["selected_month"] is None
    assert data["selected_release_version_id"] == env["release_id"]
    assert "V10SPCV01" in data["iteration_label"], "页头要明写当前是哪个版本的口径"


def test_version_options_only_list_versions_with_rows(client, admin_headers, env):
    data, _ = _row(client, admin_headers, env, release_version_id=env["release_id"])
    opts = {v["version_no"]: v for v in data["versions"]}
    assert opts["V10SPCV01"]["req_count"] == 4, "标签上的条数是挂着多少条（含已变更）"
    assert opts["V10SPCV02"]["req_count"] == 1
    assert all(v["req_count"] > 0 for v in data["versions"]), "空版本不该占一个标签"


def test_drilldown_matches_overview(client, admin_headers, env):
    """下钻与总览同口径——分叉的表现是「格子里写 3 条、点进去 1 条」。"""
    _, row = _row(client, admin_headers, env, release_version_id=env["release_id"])
    rows = client.get(f"/api/domains/{env['group_id']}/requirements", headers=admin_headers,
                      params={"release_version_id": env["release_id"]}).json()
    titles = {r["title"] for r in rows}
    assert titles == {"版本口径-A月", "版本口径-B月", "版本口径-字符串", "版本口径-已变更"}
    # 明细不藏已变更的行（置灰是前端的事），所以比 total 多一条
    assert len(rows) == row["req_summary"]["total"] + row["req_summary"]["changed"]


def test_other_version_not_mixed_in(client, admin_headers, env):
    _, row = _row(client, admin_headers, env, release_version_id=env["other_release_id"])
    assert row["req_summary"]["total"] == 1


def test_unknown_version_404(client, admin_headers):
    r = client.get("/api/domains", headers=admin_headers, params={"release_version_id": 999999})
    assert r.status_code == 404
