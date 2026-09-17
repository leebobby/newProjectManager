"""需求的批量改版本 / 批量挪迭代，以及「已变更不进交付范围」。

四件会悄悄错掉的事：
1. 批量也要走**乐观锁**，撞了的那几条要逐条报出来——只报总数的话，人不知道该去改哪几条；
2. 挪迭代要**重判重**：目标迭代里可能已经手工补录过同一条，不判就两条并存；
3. 挪迭代要把 `seq` 重算成目标迭代的**末位**，带着原序号过去会插进中间；
4. 「已变更」的需求不进版本的交付范围，且**剔了几条要报出来**。
"""
import datetime

import pytest

_DOMAIN_PROGRESS = ("progress_walkthrough", "progress_reverse", "progress_stc",
                    "progress_coding", "progress_bbit", "progress_clarify")


@pytest.fixture(scope="module")
def iters(client, admin_headers):
    rows = client.get("/api/annual-iterations", headers=admin_headers,
                      params={"year": 2026}).json()
    by_month = {r["month"]: r["id"] for r in rows}
    return {"cur": by_month[4], "next": by_month[5], "dec": by_month[12]}


@pytest.fixture(scope="module")
def version_ids(client, admin_headers):
    pr = client.post("/api/roadmap/projects", headers=admin_headers,
                     json={"name": "批量用例项目"}).json()["id"]
    mv = client.post("/api/major-versions", headers=admin_headers,
                     json={"version_no": "K10SPC100", "project_id": pr}).json()
    rv = client.post("/api/release-versions", headers=admin_headers,
                     json={"version_no": "K10SPC101", "major_version_id": mv["id"]}).json()
    a = client.post("/api/iteration-versions", headers=admin_headers,
                    json={"version_no": "K10SPC101B001", "release_version_id": rv["id"]}).json()
    b = client.post("/api/iteration-versions", headers=admin_headers,
                    json={"version_no": "K10SPC101B002", "release_version_id": rv["id"]}).json()
    return {"a": a["id"], "b": b["id"], "a_no": a["version_no"], "b_no": b["version_no"]}


def _domain(client, headers, iteration_id, **kw):
    body = {"iteration_id": iteration_id, "title": "批量需求"}
    body.update(kw)
    r = client.post("/api/iteration-requirements", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _bulk(client, headers, body):
    r = client.post("/api/iteration-requirements/bulk", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _list(client, headers, iteration_id):
    return client.get("/api/iteration-requirements", headers=headers,
                      params={"iteration_id": iteration_id}).json()


def test_bulk_change_version(client, admin_headers, iters, version_ids):
    a = _domain(client, admin_headers, iters["cur"], title="批量-改版本A",
                req_no="BK-001", planned_version=version_ids["a_no"])
    b = _domain(client, admin_headers, iters["cur"], title="批量-改版本B",
                req_no="BK-002", planned_version=version_ids["a_no"])

    out = _bulk(client, admin_headers, {
        "items": [{"id": a["id"], "version": a["version"]},
                  {"id": b["id"], "version": b["version"]}],
        "planned_version": version_ids["b_no"],
    })
    assert out["updated"] == 2 and out["conflicts"] == []

    rows = {r["id"]: r for r in _list(client, admin_headers, iters["cur"])}
    for rid in (a["id"], b["id"]):
        assert rows[rid]["planned_version"] == version_ids["b_no"]
        # 版本号反查出来的 FK 也要跟着走，否则按版本统计时这几条落不到新版本上
        assert rows[rid]["target_version_id"] == version_ids["b"]


def test_stale_version_is_reported_not_silently_skipped(client, admin_headers, iters):
    """乐观锁撞了的那一条要指名道姓，别只给个总数。"""
    a = _domain(client, admin_headers, iters["cur"], title="批量-撞锁", req_no="BK-010")
    out = _bulk(client, admin_headers, {
        "items": [{"id": a["id"], "version": a["version"] + 5}],
        "planned_version": "X1",
    })
    assert out["updated"] == 0
    assert len(out["conflicts"]) == 1
    c = out["conflicts"][0]
    assert c["id"] == a["id"] and c["title"] == "批量-撞锁"
    assert "他人" in c["reason"]


def test_move_to_next_month(client, admin_headers, iters):
    a = _domain(client, admin_headers, iters["cur"], title="批量-挪走", req_no="BK-020")
    out = _bulk(client, admin_headers, {
        "items": [{"id": a["id"], "version": a["version"]}], "shift_months": 1,
    })
    assert out["updated"] == 1, out
    assert out["moved_to"] == ["2026-05"]

    assert a["id"] not in {r["id"] for r in _list(client, admin_headers, iters["cur"])}
    moved = {r["id"]: r for r in _list(client, admin_headers, iters["next"])}
    assert a["id"] in moved
    # seq 重算成目标迭代的末位，而不是带着原序号插进中间
    assert moved[a["id"]]["seq"] == len(moved)


def test_move_rejects_duplicate_in_target(client, admin_headers, iters):
    """目标迭代里已经手工补录过同一条时，不能再挪一条过去。"""
    _domain(client, admin_headers, iters["next"], title="批量-已存在", req_no="BK-030")
    a = _domain(client, admin_headers, iters["cur"], title="批量-已存在", req_no="BK-030")
    out = _bulk(client, admin_headers, {
        "items": [{"id": a["id"], "version": a["version"]}], "shift_months": 1,
    })
    assert out["updated"] == 0
    assert "2026-05" in out["conflicts"][0]["reason"]
    # 原地不动
    assert a["id"] in {r["id"] for r in _list(client, admin_headers, iters["cur"])}


def test_december_moves_into_next_year(client, admin_headers, iters):
    """12 月 +1 要跨年：就地取模会算出 13 月。"""
    a = _domain(client, admin_headers, iters["dec"], title="批量-跨年", req_no="BK-040")
    out = _bulk(client, admin_headers, {
        "items": [{"id": a["id"], "version": a["version"]}], "shift_months": 1,
    })
    assert out["updated"] == 1
    assert out["moved_to"] == ["2027-01"]


def test_version_and_move_are_mutually_exclusive(client, admin_headers, iters):
    a = _domain(client, admin_headers, iters["cur"], title="批量-互斥", req_no="BK-050")
    r = client.post("/api/iteration-requirements/bulk", headers=admin_headers, json={
        "items": [{"id": a["id"], "version": a["version"]}],
        "planned_version": "X", "shift_months": 1,
    })
    assert r.status_code == 400 and "分两次" in r.json()["detail"]


def test_changed_rows_are_out_of_the_delivery_scope(client, admin_headers, iters, version_ids):
    """已变更的需求不进版本交付范围，但剔了几条要如实报出来。"""
    done = {f: "已完成" for f in _DOMAIN_PROGRESS}
    _domain(client, admin_headers, iters["cur"], title="范围-正常", req_no="BK-060",
            target_version_id=version_ids["a"], **done)
    _domain(client, admin_headers, iters["cur"], title="范围-已变更", req_no="BK-061",
            target_version_id=version_ids["a"], **{**done, "progress_coding": "已变更"})

    r = client.get("/api/iteration-requirements/by-version", headers=admin_headers,
                   params={"version_id": version_ids["a"]})
    assert r.status_code == 200, r.text
    data = r.json()
    titles = [x["title"] for x in data["items"]]
    assert "范围-正常" in titles
    assert "范围-已变更" not in titles
    assert data["changed"] >= 1, "剔掉的条数要报出来，不能只剔不报"


def test_create_resolves_version_fk_like_edit_does(client, admin_headers, iters, version_ids):
    """**新建**填了版本号也要反查出 FK，不能只有编辑那条路能反查。

    两条路不一致时页面上完全看不出来（两边都显示着版本号），直到「版本管理 →
    合入需求」按 FK 查交付范围——新建的那批整片不出现，而没人会往反查上想。
    原因是新建用的是全量 model_dump()，`target_version_id` 以 None 出现在字典里，
    按「key 在不在」判的守卫就把反查整个跳过了。
    """
    made = _domain(client, admin_headers, iters["cur"], title="反查-新建", req_no="BK-070",
                   planned_version=version_ids["a_no"])
    assert made["target_version_id"] == version_ids["a"], "新建没反查出 FK"

    # 编辑那条路本来就对，一并钉住，免得将来只修一头
    edited = _domain(client, admin_headers, iters["cur"], title="反查-编辑", req_no="BK-071")
    r = client.put(f"/api/iteration-requirements/{edited['id']}", headers=admin_headers,
                   json={"version": edited["version"], "planned_version": version_ids["b_no"]})
    assert r.status_code == 200, r.text
    assert r.json()["target_version_id"] == version_ids["b"]


def test_clearing_the_version_still_clears_the_fk(client, admin_headers, iters, version_ids):
    """清空版本号要连 FK 一起清掉——不清的话行上没有版本号、却还挂在某个版本的交付范围里。"""
    made = _domain(client, admin_headers, iters["cur"], title="反查-清空", req_no="BK-072",
                   planned_version=version_ids["a_no"])
    assert made["target_version_id"] == version_ids["a"]
    r = client.put(f"/api/iteration-requirements/{made['id']}", headers=admin_headers,
                   json={"version": made["version"], "planned_version": "", "target_version_id": None})
    assert r.status_code == 200, r.text
    assert not r.json()["planned_version"]
    assert r.json()["target_version_id"] is None
