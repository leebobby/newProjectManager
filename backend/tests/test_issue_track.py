"""问题单跟踪：进展 + 合入计划。

最要紧的一条是**跨快照存活**：问题单每天采集一次，明细落文件、只有数字入库。
跟踪记录要是跟着某一天的快照走，第二天重采就等于全丢了——页面上只表现成
「昨天填的怎么没了」，看着像丢数据。所以它按「项目 + 缺陷编号」独立存。

合入计划两层各记一个：计划挂**版本**（C10SPC101），实际落**迭代版本/构建**
（C10SPC101B001）。填反了的表现是下拉里选的和存的不是一回事，而页面上看着都对。
"""
import json

import pytest

TRACKS = "/api/issue-tracks"
PROJECT = "TRACKTEST"


@pytest.fixture(scope="module")
def versions(client, admin_headers):
    """建一套三层版本：大版本 → 版本 C10SPC101 → 构建 C10SPC101B001。"""
    mv = client.post("/api/major-versions", headers=admin_headers,
                     json={"version_no": "C10SPC100"}).json()
    rv = client.post("/api/release-versions", headers=admin_headers,
                     json={"major_version_id": mv["id"], "version_no": "C10SPC101"}).json()
    iv = client.post("/api/iteration-versions", headers=admin_headers,
                     json={"release_version_id": rv["id"], "version_no": "C10SPC101B001"}).json()
    return rv, iv


def _put(client, headers, **kw):
    body = {"project": PROJECT, "issue_id": "DTS2026010001"}
    body.update(kw)
    return client.put(TRACKS, headers=headers, json=body)


def test_first_write_creates_the_record(client, admin_headers):
    """问题单不是我们建的，第一次填进展时不该让页面先查一次再决定调哪个接口。"""
    r = _put(client, admin_headers, merge_status="分析中", progress="已定位到驱动层")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["merge_status"] == "分析中" and d["progress"] == "已定位到驱动层"
    assert d["version"] == 1 and d["updated_by"], "要记下是谁填的"


def test_plan_goes_to_release_tier_and_actual_to_build_tier(client, admin_headers, versions):
    rv, iv = versions
    d = _put(client, admin_headers, plan_version="C10SPC101",
             merged_build="C10SPC101B001").json()
    assert d["plan_version_id"] == rv["id"], "计划合入版本要落到「版本」这一层"
    assert d["merged_build_id"] == iv["id"], "实际合入要落到「构建」这一层"


def test_build_number_in_the_plan_field_maps_up_to_its_release(client, admin_headers, versions):
    """老数据里把构建号填进"计划合入版本"的不少——挂到它所属的版本上，不是猜。"""
    rv, _ = versions
    d = _put(client, admin_headers, plan_version="C10SPC101B001").json()
    assert d["plan_version_id"] == rv["id"]
    assert d["plan_version"] == "C10SPC101B001", "字符串快照原样留着，别替人改写"


def test_unknown_version_string_is_kept_not_rejected(client, admin_headers):
    """反查不中留空、不报错，交给「数据对账」事后补（见 CLAUDE.md 主数据与 FK 反查）。"""
    d = _put(client, admin_headers, plan_version="谁也不认识的版本号").json()
    assert d["plan_version"] == "谁也不认识的版本号"
    assert d["plan_version_id"] is None


def test_second_write_updates_in_place(client, admin_headers):
    before = _put(client, admin_headers, progress="第一版").json()
    after = _put(client, admin_headers, progress="第二版", version=before["version"]).json()
    assert after["id"] == before["id"], "同一条单只该有一条跟踪记录"
    assert after["progress"] == "第二版" and after["version"] == before["version"] + 1


def test_stale_version_is_rejected(client, admin_headers):
    cur = _put(client, admin_headers, progress="占位").json()
    r = _put(client, admin_headers, progress="别人的改动", version=cur["version"] - 1)
    assert r.status_code == 409


def test_partial_update_does_not_wipe_other_fields(client, admin_headers):
    """只传进展时不能把合入计划清掉——"没传"和"传了空"是两件事。"""
    base = _put(client, admin_headers, merge_status="开发中",
                plan_version="C10SPC101", progress="旧").json()
    after = _put(client, admin_headers, progress="新", version=base["version"]).json()
    assert after["merge_status"] == "开发中"
    assert after["plan_version"] == "C10SPC101"


def test_bad_merge_status_is_rejected(client, admin_headers):
    r = _put(client, admin_headers, merge_status="随便写的")
    assert r.status_code == 422


def test_track_survives_the_next_days_snapshot(client, admin_headers, tmp_path, monkeypatch):
    """**这是这张表存在的理由**：今天填的进展，明天的快照里照样看得到。

    跟踪记录要是挂在某一天的快照行上，第二天重采就全丢了，而页面上只表现成
    「昨天填的怎么没了」。这里模拟连续两天的快照：同一条单还在（没关闭/撤销），
    跟踪记录必须还认得上。
    """
    import models
    import routers.issues as ri
    from database import SessionLocal

    monkeypatch.setattr(ri, "_snapshot_root", lambda: tmp_path)
    issue_id = "DTS2026010777"
    _put(client, admin_headers, issue_id=issue_id,
         merge_status="开发中", progress="等 B002 合入", plan_version="C10SPC101")

    db = SessionLocal()
    for date in ("2026-01-01", "2026-01-02"):
        rows = [{"issue_id": issue_id, "title": "偶发复位", "owner": "张三",
                 "group": "SE组", "severity": "严重", "progress": "实施修改"}]
        rel = f"{PROJECT}/{date}.json"
        fp = tmp_path / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        db.add(models.IssueSnapshot(project=PROJECT, snapshot_date=date,
                                    total=1, data_file=rel, source="api"))
    db.commit()
    db.close()

    # 第二天的快照里这条单还在
    detail = client.get("/api/issues/snapshot-detail", headers=admin_headers,
                        params={"project": PROJECT}).json()
    assert detail["date"] == "2026-01-02"
    assert [r["issue_id"] for r in detail["raw"]] == [issue_id]

    # 跟踪记录跟着缺陷编号走，一个字都没丢
    tracks = client.get(TRACKS, headers=admin_headers, params={"project": PROJECT}).json()
    hit = next(t for t in tracks if t["issue_id"] == issue_id)
    assert hit["merge_status"] == "开发中"
    assert hit["progress"] == "等 B002 合入"
    assert hit["plan_version"] == "C10SPC101"


def test_tracks_are_scoped_by_project(client, admin_headers):
    """两个项目里可能有同号的单，别串台。"""
    _put(client, admin_headers, project="OTHERPROJ", issue_id="DTS2026010001",
         progress="另一个项目的")
    mine = client.get(TRACKS, headers=admin_headers, params={"project": PROJECT}).json()
    assert all(t["project"] == PROJECT for t in mine)


def test_requires_login(client):
    r = client.put(TRACKS, json={"project": PROJECT, "issue_id": "X", "progress": "x"})
    assert r.status_code in (401, 403)
