"""每日新增 / 解决：相邻快照差分。

快照只存"当天还开着的单"，新增与解决全靠集合求差，容易错的是边界：
1. 首次快照是基线，整份存量不能算成"新增"（否则第一天冒出一根柱子）；
2. 明细文件丢了的那天要整天跳过，不能当成"0 条"——那会凭空产生一批"解决"；
3. 中途补采一天后，后一天的比对基准要跟着改（prev_date 变了就得重算）。
"""
import json

import pytest


@pytest.fixture(scope="module")
def flow_env(client, admin_headers, tmp_path_factory):
    """在临时目录里造 3 天快照：day1 基线，day2 增 2 减 1，day3 增 1 减 2。"""
    import models
    from database import SessionLocal
    import routers.issues as ri

    root = tmp_path_factory.mktemp("snapshots")
    ri._snapshot_root = lambda: root          # 绕开 config，别写到仓库的 backend/data

    project = "FLOWTEST"
    days = {
        "2026-03-01": ["SDTS20260101001", "SDTS20260201002", "SDTS20260228003"],
        "2026-03-02": ["SDTS20260201002", "SDTS20260228003", "SDTS20260302004", "SDTS20260302005"],
        "2026-03-03": ["SDTS20260228003", "SDTS20260303006"],
    }
    db = SessionLocal()
    for date, ids in days.items():
        rel = f"{project}/{date}.json"
        fp = root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps([
            {"issue_id": i, "title": f"标题 {i}", "severity": "一般", "group": "SE"} for i in ids
        ], ensure_ascii=False), encoding="utf-8")
        db.add(models.IssueSnapshot(project=project, snapshot_date=date,
                                    total=len(ids), data_file=rel, source="api"))
    db.commit()
    db.close()
    return project


def test_baseline_day_is_not_counted_as_new(client, admin_headers, flow_env):
    r = client.get("/api/issues/snapshot-flow", params={"project": flow_env}, headers=admin_headers)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["baseline_date"] == "2026-03-01"
    assert d["by_snapshot"]["dates"] == ["2026-03-02", "2026-03-03"]


def test_created_and_resolved_counts(client, admin_headers, flow_env):
    d = client.get("/api/issues/snapshot-flow", params={"project": flow_env},
                   headers=admin_headers).json()["by_snapshot"]
    # 03-02：新增 004/005，解决 101001；03-03：新增 006，解决 201002 与 302004/005 中的两条
    assert d["created"] == [2, 1]
    assert d["resolved"] == [1, 3]
    assert d["net"] == [1, -2]
    assert d["open"] == [4, 2]


def test_by_issue_no_reaches_before_first_snapshot(client, admin_headers, flow_env):
    """编号里带创建日，所以能看到开始采集（03-01）之前的每日新增。"""
    d = client.get("/api/issues/snapshot-flow", params={"project": flow_env},
                   headers=admin_headers).json()
    hist = dict(zip(d["by_issue_no"]["dates"], d["by_issue_no"]["created"]))
    assert hist["2026-01-01"] == 1          # 基线那天的单也计入，且日期取自编号
    assert hist["2026-03-02"] == 2
    assert d["unknown_no"] == 0


def test_flow_detail_reads_previous_file_for_resolved(client, admin_headers, flow_env):
    """解决的单当天已经不在快照里了，明细必须回上一天的文件取，否则永远是空。"""
    r = client.get("/api/issues/flow-detail",
                   params={"project": flow_env, "date": "2026-03-02", "kind": "resolved"},
                   headers=admin_headers).json()
    assert r["source_date"] == "2026-03-01"
    assert [x["issue_id"] for x in r["rows"]] == ["SDTS20260101001"]

    r2 = client.get("/api/issues/flow-detail",
                    params={"project": flow_env, "date": "2026-03-02", "kind": "created"},
                    headers=admin_headers).json()
    assert sorted(x["issue_id"] for x in r2["rows"]) == ["SDTS20260302004", "SDTS20260302005"]


def test_missing_detail_file_skips_the_day(client, admin_headers, flow_env, tmp_path_factory):
    """明细文件丢了的一天整天跳过：不能把它当成 0 条，否则前一天的单会被误判为全部解决。"""
    import models
    from database import SessionLocal
    import routers.issues as ri

    db = SessionLocal()
    db.add(models.IssueSnapshot(project=flow_env, snapshot_date="2026-03-04",
                                total=99, data_file=f"{flow_env}/2026-03-04.json", source="api"))
    db.commit()
    db.close()

    d = client.get("/api/issues/snapshot-flow", params={"project": flow_env},
                   headers=admin_headers).json()["by_snapshot"]
    assert "2026-03-04" not in d["dates"]
    assert d["resolved"] == [1, 3]      # 没有凭空多出 2 条"解决"
