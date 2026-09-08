"""整页存档的回归：那一周长什么样，得能原样翻回来。

这套测试防的是两类看不出报错的坏法：
- 存档跟着页面一起变（存的是引用而不是当时的数据）——回看时看到的是今天的内容；
- 存档页头写着今天的日期（渲染时取了 now）——三个月前的档看着像刚出的报告。

注意：不要在模块顶层 import 应用模块（见 CLAUDE.md）。
"""
import pytest


@pytest.fixture(scope="module")
def archived_special(client, admin_headers):
    """一个填了内容的专项，返回 (sid, 存档 id)。"""
    sid = client.post("/api/specials", json={"name": "存档专项", "kind": "special",
                                             "owner": "张三"},
                      headers=admin_headers).json()["id"]
    cur = client.get(f"/api/specials/{sid}", headers=admin_headers).json()["content"]
    r = client.put(f"/api/specials/{sid}/content",
                   json={"goal": "打通端到端链路", "progress_summary": "存档那一周的进展",
                         "version": cur["version"]}, headers=admin_headers)
    assert r.status_code == 200, r.text
    client.post(f"/api/specials/{sid}/tasks",
                json={"content": "联调", "progress": "存档那一周的事务进展"},
                headers=admin_headers)
    snap = client.post("/api/archives", json={"kind": "special", "ref_id": sid},
                       headers=admin_headers)
    assert snap.status_code == 200, snap.text
    return sid, snap.json()["id"]


def test_archive_keeps_what_the_page_said_back_then(client, admin_headers, archived_special):
    """存档之后再改页面，存档里还是当时那份——这就是这张表存在的理由。"""
    sid, snap_id = archived_special
    cur = client.get(f"/api/specials/{sid}", headers=admin_headers).json()["content"]
    client.put(f"/api/specials/{sid}/content",
               json={"progress_summary": "改过之后的进展", "version": cur["version"]},
               headers=admin_headers)

    payload = client.get(f"/api/archives/{snap_id}", headers=admin_headers).json()["payload"]
    assert payload["content"]["progress_summary"] == "存档那一周的进展"
    assert payload["tasks"][0]["progress"] == "存档那一周的事务进展"
    # 页面确实已经变了，两者不是同一份数据
    now = client.get(f"/api/specials/{sid}", headers=admin_headers).json()["content"]
    assert now["progress_summary"] == "改过之后的进展"


def test_special_archive_is_rendered_by_the_weekly_report_renderer(
        client, admin_headers, archived_special):
    """专项存档用周报那一份渲染：分段与标题都得在，且日期是**存档日**不是今天。"""
    sid, snap_id = archived_special
    meta = client.get(f"/api/archives/{snap_id}", headers=admin_headers).json()
    html = client.get(f"/api/archives/{snap_id}/view", headers=admin_headers).text

    assert "打通端到端链路" in html          # 目标分段
    assert "存档那一周的进展" in html        # 整体进展（存档时那一版）
    assert "存档那一周的事务进展" in html    # 事务表
    assert "改过之后的进展" not in html
    assert "存档】" in html                  # 页头写的是「存档」，不是周报
    assert meta["label"] in html             # 日期＝存档日
    assert "cid:" not in html                # 图片引用要内联，浏览器不认 cid:


def test_same_day_archive_overwrites_instead_of_piling_up(client, admin_headers,
                                                          archived_special):
    """同一天再存一次是覆盖：不然点两下按钮就多两份，列表很快就没法看了。"""
    sid, snap_id = archived_special
    again = client.post("/api/archives", json={"kind": "special", "ref_id": sid},
                        headers=admin_headers)
    assert again.status_code == 200
    assert again.json()["id"] == snap_id
    rows = client.get("/api/archives", params={"kind": "special", "ref_id": sid},
                      headers=admin_headers).json()
    assert len([r for r in rows if r["label"] == again.json()["label"]]) == 1
    # 覆盖之后内容跟着刷新成当前的
    payload = client.get(f"/api/archives/{snap_id}", headers=admin_headers).json()["payload"]
    assert payload["content"]["progress_summary"] == "改过之后的进展"


def test_targets_and_kinds_come_from_the_backend(client, admin_headers, archived_special):
    kinds = {k["kind"]: k["label"] for k in
             client.get("/api/archives/kinds", headers=admin_headers).json()}
    assert kinds["special"] == "专项" and kinds["hardware"] == "硬件清零"
    # /kinds 与 /targets 必须排在 /{snap_id} 前面，否则会被当成 id 解析成 422
    targets = client.get("/api/archives/targets", params={"kind": "special"},
                         headers=admin_headers).json()
    assert any(t["ref_id"] == archived_special[0] and t["count"] >= 1 for t in targets)


def test_weekly_run_covers_every_page_kind(client, admin_headers, machine_id):
    """每周那一轮要把四类页面都存到；漏一类不会报错，只是那一页没有存档。"""
    from database import SessionLocal
    import archives

    cid = client.post("/api/customers", json={"code": "ARCH", "name": "存档战场", "display_name": "存档战场"},
                      headers=admin_headers)
    assert cid.status_code == 200, cid.text
    r = client.post("/api/customer-issues",
                    json={"machine_status_id": machine_id, "kind": "issue",
                          "description": "存档用问题"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        counts = archives.run_weekly(db)
    finally:
        db.close()
    assert set(counts) == {"special", "domain", "customer", "hardware"}
    assert counts["special"] >= 1 and counts["hardware"] == 1

    for kind in ("customer", "hardware"):
        rows = client.get("/api/archives", params={"kind": kind}, headers=admin_headers).json()
        assert rows, f"{kind} 没有存档"
        html = client.get(f"/api/archives/{rows[0]['id']}/view", headers=admin_headers).text
        assert "存档】" in html


def test_deleting_an_archive_is_admin_only(client, admin_headers, archived_special):
    """删存档＝仅 admin：这是别人回溯要用的历史，误删了补不回来。"""
    sid, _ = archived_special
    snap = client.post("/api/archives", json={"kind": "special", "ref_id": sid},
                       headers=admin_headers).json()
    r = client.post("/api/users", json={"username": "archive_reader", "password": "pw123456",
                                        "role": "normal"}, headers=admin_headers)
    assert r.status_code in (200, 201), r.text
    tok = client.post("/api/auth/login",
                      json={"username": "archive_reader", "password": "pw123456"}).json()
    hdr = {"Authorization": f"Bearer {tok['access_token']}"}

    assert client.get(f"/api/archives/{snap['id']}", headers=hdr).status_code == 200
    assert client.delete(f"/api/archives/{snap['id']}", headers=hdr).status_code == 403
    assert client.delete(f"/api/archives/{snap['id']}", headers=admin_headers).status_code == 200


def test_unknown_kind_is_rejected(client, admin_headers):
    r = client.post("/api/archives", json={"kind": "nope", "ref_id": 1}, headers=admin_headers)
    assert r.status_code == 400
