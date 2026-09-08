"""产品需求 ↔ 领域需求的拆解关联。

覆盖四件会悄悄错掉的事：
1. 一条领域需求可以承接多条产品需求——做成单外键的话第二条看着就是"没拆"；
2. 同一对只能挂一次，重复挂返回 400（撞唯一约束的话是 500，页面上看不出原因）；
3. **跨迭代关联允许、但要标出来**——限定同迭代会让产品需求下个月凭空变成"未拆解"；
4. 进展汇总（done / changed / completion）与度量看板吃同一份口径，
   `已变更` 的行标出来而不是悄悄剔掉。
"""
import datetime

import pytest


@pytest.fixture(scope="module")
def iterations(client, admin_headers):
    """借两个没被别的用例占用的迭代（本月一个、下月一个），用来验跨迭代关联。"""
    rows = client.get("/api/annual-iterations", headers=admin_headers,
                      params={"year": datetime.date.today().year}).json()
    assert len(rows) >= 12, "年度迭代应自动生成 12 条"
    return {"a": rows[8]["id"], "b": rows[9]["id"]}


def _product(client, headers, iteration_id, **kw):
    body = {"iteration_id": iteration_id, "title": "产品需求"}
    body.update(kw)
    r = client.post("/api/iteration-product-requirements", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _domain(client, headers, iteration_id, **kw):
    body = {"iteration_id": iteration_id, "title": "领域需求"}
    body.update(kw)
    r = client.post("/api/iteration-requirements", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _link(client, headers, product_id, domain_id, remark=""):
    return client.post("/api/iteration-req-links", headers=headers, json={
        "product_req_id": product_id, "domain_req_id": domain_id, "remark": remark,
    })


def _links(client, headers, iteration_id):
    r = client.get("/api/iteration-req-links", headers=headers,
                   params={"iteration_id": iteration_id})
    assert r.status_code == 200, r.text
    return r.json()


def test_one_domain_req_can_serve_several_product_reqs(client, admin_headers, iterations):
    """公共模块的一条领域需求同时承接两条产品需求——这正是不做成单外键的理由。"""
    it = iterations["a"]
    p1 = _product(client, admin_headers, it, title="多挂-产品A")
    p2 = _product(client, admin_headers, it, title="多挂-产品B")
    d = _domain(client, admin_headers, it, title="多挂-公共领域需求")

    assert _link(client, admin_headers, p1["id"], d["id"]).status_code == 200
    assert _link(client, admin_headers, p2["id"], d["id"]).status_code == 200

    rows = [x for x in _links(client, admin_headers, it) if x["domain_req_id"] == d["id"]]
    assert {x["product_req_id"] for x in rows} == {p1["id"], p2["id"]}
    # 两条都不是跨迭代，也不该报版本不一致（两边都没填版本，推不出来就别说）
    assert all(x["cross_iteration"] is False for x in rows)
    assert all(x["version_mismatch"] is False for x in rows)


def test_same_pair_twice_is_400_not_500(client, admin_headers, iterations):
    """重复挂接给的是一条看得懂的 400，不是唯一约束撞出来的 500。"""
    it = iterations["a"]
    p = _product(client, admin_headers, it, title="重复挂-产品")
    d = _domain(client, admin_headers, it, title="重复挂-领域")
    assert _link(client, admin_headers, p["id"], d["id"]).status_code == 200

    again = _link(client, admin_headers, p["id"], d["id"])
    assert again.status_code == 400, again.text
    assert "关联" in again.json()["detail"]


def test_cross_iteration_link_is_allowed_and_flagged(client, admin_headers, iterations):
    """本轮没做完、下个月接着排：关联要能跨迭代，且两边都看得见、被标出来。"""
    p = _product(client, admin_headers, iterations["a"], title="跨迭代-产品")
    d = _domain(client, admin_headers, iterations["b"], title="跨迭代-领域")
    assert _link(client, admin_headers, p["id"], d["id"]).status_code == 200

    def _find(iteration_id):
        return [x for x in _links(client, admin_headers, iteration_id)
                if x["product_req_id"] == p["id"] and x["domain_req_id"] == d["id"]]

    # 产品需求所在的迭代看得见
    here = _find(iterations["a"])
    assert len(here) == 1 and here[0]["cross_iteration"] is True
    # 领域需求所在的迭代也看得见——只查自己那一侧的话，同一条关联会在一个 Tab
    # 里有、另一个 Tab 里没有，而两边看着都对
    there = _find(iterations["b"])
    assert len(there) == 1
    assert there[0]["domain"]["iteration_label"] != there[0]["product"]["iteration_label"]


def test_progress_summary_follows_the_metrics_rules(client, admin_headers, iterations):
    """done / changed / completion 用的是度量看板那一份口径（_req_progress）。"""
    it = iterations["a"]
    p = _product(client, admin_headers, it, title="汇总-产品")
    done_fields = {f: "已完成" for f in ("progress_walkthrough", "progress_reverse",
                                         "progress_stc", "progress_coding",
                                         "progress_bbit", "progress_clarify")}
    d_done = _domain(client, admin_headers, it, title="汇总-已完成", **done_fields)
    d_changed = _domain(client, admin_headers, it, title="汇总-已变更",
                        **{**done_fields, "progress_coding": "已变更"})
    _link(client, admin_headers, p["id"], d_done["id"])
    _link(client, admin_headers, p["id"], d_changed["id"])

    rows = {x["domain_req_id"]: x for x in _links(client, admin_headers, it)
            if x["product_req_id"] == p["id"]}
    assert rows[d_done["id"]]["domain"]["done"] is True
    assert rows[d_done["id"]]["domain"]["changed"] is False
    assert rows[d_done["id"]]["domain"]["completion"] == 1.0
    # 已变更的行照样返回、并标出来——服务端藏起来的话，误标的那行连同"改回来"
    # 的入口一起消失
    assert rows[d_changed["id"]]["domain"]["changed"] is True


def test_unlink_removes_only_the_link(client, admin_headers, iterations):
    """解挂删的是关联行，两条需求一行不动。"""
    it = iterations["a"]
    p = _product(client, admin_headers, it, title="解挂-产品")
    d = _domain(client, admin_headers, it, title="解挂-领域")
    link_id = _link(client, admin_headers, p["id"], d["id"]).json()["id"]

    assert client.delete(f"/api/iteration-req-links/{link_id}",
                         headers=admin_headers).status_code == 200
    assert not [x for x in _links(client, admin_headers, it) if x["id"] == link_id]
    # 需求本身还在
    assert client.get("/api/iteration-product-requirements", headers=admin_headers,
                      params={"iteration_id": it}).status_code == 200
    assert any(r["id"] == d["id"] for r in
               client.get("/api/iteration-requirements", headers=admin_headers,
                          params={"iteration_id": it}).json())


def test_candidates_default_to_this_iteration(client, admin_headers, iterations):
    """候选默认只在本迭代里找；要挂别的迭代得显式勾选。"""
    _domain(client, admin_headers, iterations["b"], title="候选-只在B迭代")

    def _search(all_iterations):
        r = client.get("/api/iteration-req-links/candidates", headers=admin_headers,
                       params={"side": "domain", "iteration_id": iterations["a"],
                               "q": "候选-只在B迭代", "all_iterations": all_iterations})
        assert r.status_code == 200, r.text
        return r.json()

    assert _search(False) == []
    assert [x["title"] for x in _search(True)] == ["候选-只在B迭代"]


def test_missing_requirement_is_404(client, admin_headers, iterations):
    p = _product(client, admin_headers, iterations["a"], title="404-产品")
    r = _link(client, admin_headers, p["id"], 99999999)
    assert r.status_code == 404, r.text
