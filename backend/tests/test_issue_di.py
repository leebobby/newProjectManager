"""问题单 DI（缺陷加权分）：权重口径、按维度分组、趋势里「没算过 ≠ 0 分」。

DI = 致命10 + 严重3 + 一般1 + 提示0.1，权重表在 routers/_issue_source.SEVERITY_WEIGHTS，
领域总览 / 度量看板 / 问题单管理三处共用同一份。

**模块顶层不 import 应用模块**（见 CLAUDE.md）：conftest 的 client 夹具靠 os.chdir
把 sqlite:///./app.db 指到临时目录，收集阶段的顶层 import 会赶在 chdir 之前把引擎
连上仓库里的 backend/app.db，之后整个会话都跑在那个老库上。
"""
import json

import pytest


@pytest.fixture(scope="module", autouse=True)
def snap_root(client, tmp_path_factory):
    """快照明细写到临时目录，别落进仓库的 backend/data。

    `_snapshot_root()` 是按 `__file__` 算的**绝对路径**，conftest 那个 os.chdir
    管不到它——不改这里的话，每跑一次测试仓库里就多出几个项目目录
    （同 test_issue_flow.py 的做法）。
    """
    import routers.issues as ri
    root = tmp_path_factory.mktemp("snapshots")
    ri._snapshot_root = lambda: root
    return root


def _rows():
    """一批覆盖所有分支的明细行：四档齐全 + 认不出的级别 + 没有客户面的行。"""
    return [
        {"issue_id": "A1", "severity": "致命", "group": "控制组", "customer": "西安1号机"},
        {"issue_id": "A2", "severity": "严重", "group": "控制组", "customer": "西安1号机"},
        {"issue_id": "A3", "severity": "一般", "group": "视觉组", "customer": "合肥2号机"},
        {"issue_id": "A4", "severity": "提示", "group": "视觉组", "customer": ""},
        {"issue_id": "A5", "severity": "看不懂的级别", "group": "视觉组", "customer": ""},
    ]


def test_weights_are_the_ones_business_asked_for(client):
    from routers._issue_source import SEVERITY_WEIGHTS
    assert SEVERITY_WEIGHTS == {"致命": 10.0, "严重": 3.0, "一般": 1.0, "提示": 0.1}


def test_unknown_severity_scores_zero_but_still_counts(client):
    """认不出的级别记 0 分——但那一条仍然算进条数。

    丢掉的话条数和 DI 会对不上，而两个数单独看都正常；记 0 则表现为
    「条数涨了 DI 没涨」，一眼看得出是词表没对上。
    """
    from routers._issue_source import row_score, weighted_score
    rows = _rows()
    assert row_score(rows[4]) == 0.0
    assert weighted_score(rows) == 14.1          # 10 + 3 + 1 + 0.1
    assert len(rows) == 5                        # 那一条没被丢掉


def test_score_by_groups_exactly_like_count_by(client):
    """DI 的分组口径必须和条数一模一样：取值为空的行两边都整条跳过。

    分法差一点，同一张表里条数按一种分法、DI 按另一种，两列加起来都还对，
    只有分到哪一行不一样——没人会去核。
    """
    from routers._issue_source import score_by
    from routers.issues import _count_by
    rows = _rows()

    assert score_by(rows, "group") == {"控制组": 13.0, "视觉组": 1.1}
    assert _count_by(rows, "group") == {"控制组": 2, "视觉组": 3}

    # 客户面为空的行：条数那边跳过，DI 这边也必须跳过（不能落进「未标注」桶）
    assert set(score_by(rows, "customer")) == set(_count_by(rows, "customer"))
    assert score_by(rows, "customer") == {"西安1号机": 13.0, "合肥2号机": 1.0}


def test_severity_di_sums_to_total_di(client):
    """按严重程度加总 ＝ 整份的 DI。趋势接口的合计 DI 就是这么算的。

    级别为空的行会被跳过，但那种行的 DI 本来就是 0（不在权重表里），所以一分不差。
    换成按客户面加总就不成立——标题匹配不到客户的单整条不进那一维。
    """
    from routers._issue_source import score_by, weighted_score
    rows = _rows()
    assert round(sum(score_by(rows, "severity").values()), 1) == weighted_score(rows)


def _seed_snapshot(client, project, date, rows, with_di):
    """直接往库里塞一份快照（绕开真实采集，采集要连 DTS）。

    with_di=False 模拟「DI 这一列还没加进来的那天采的快照」——score 留 NULL。
    """
    import models
    from database import SessionLocal
    from routers._issue_source import score_by
    from routers.issues import _count_by, _snapshot_root

    db = SessionLocal()
    try:
        snap = models.IssueSnapshot(project=project, snapshot_date=date,
                                    total=len(rows), data_file=f"{project}/{date}.json")
        db.add(snap)
        db.flush()
        for dim in ("group", "customer", "severity"):
            di = score_by(rows, dim)
            for key, cnt in _count_by(rows, dim).items():
                db.add(models.IssueSnapshotStat(
                    snapshot_id=snap.id, dimension=dim, dim_key=key, count=cnt,
                    score=(di.get(key, 0.0) if with_di else None),
                ))
        db.commit()
        fp = _snapshot_root() / f"{project}/{date}.json"
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        return snap.id
    finally:
        db.close()


def test_snapshot_detail_reports_di_by_group_and_customer(client, admin_headers):
    """明细接口按小组、按客户面都给 DI，权重表也一并发下去（前端不另存一份）。"""
    _seed_snapshot(client, "DIPROJ", "2026-09-01", _rows(), with_di=True)
    d = client.get("/api/issues/snapshot-detail",
                   params={"project": "DIPROJ", "date": "2026-09-01"},
                   headers=admin_headers).json()
    assert d["exists"] is True
    assert d["di_total"] == 14.1
    assert d["di_by_group"] == {"控制组": 13.0, "视觉组": 1.1}
    assert d["di_by_customer"] == {"西安1号机": 13.0, "合肥2号机": 1.0}
    assert d["di_weights"]["致命"] == 10.0


def test_trend_returns_di_alongside_counts(client, admin_headers):
    """条数和 DI 一次全返回：前端切指标不重新请求。"""
    t = client.get("/api/issues/snapshot-trend",
                   params={"project": "DIPROJ", "dimension": "group"},
                   headers=admin_headers).json()
    assert t["dates"] == ["2026-09-01"]
    assert t["total"] == [5]
    assert t["total_di"] == [14.1]
    by_name = {s["name"]: s for s in t["series"]}
    assert by_name["控制组"]["data"] == [2]
    assert by_name["控制组"]["di"] == [13.0]
    assert t["di_missing_dates"] == []


def test_snapshot_without_di_reports_null_not_zero(client, admin_headers):
    """DI 这一列是后加的：之前采的快照没算过分。

    那几天必须回 null 并列进 di_missing_dates，**不能记 0**——记 0 的话趋势图上
    那一段是一条贴地的直线，看着像那几天确实没缺陷，而这种错没人会当 bug 报。
    """
    _seed_snapshot(client, "OLDPROJ", "2026-08-01", _rows(), with_di=False)
    _seed_snapshot(client, "OLDPROJ", "2026-08-02", _rows(), with_di=True)
    t = client.get("/api/issues/snapshot-trend",
                   params={"project": "OLDPROJ", "dimension": "group"},
                   headers=admin_headers).json()
    assert t["dates"] == ["2026-08-01", "2026-08-02"]
    assert t["total"] == [5, 5]                      # 条数两天都在
    assert t["total_di"] == [None, 14.1]             # 没算过的那天是 None，不是 0
    assert t["di_missing_dates"] == ["2026-08-01"]
    ctrl = next(s for s in t["series"] if s["name"] == "控制组")
    assert ctrl["di"] == [None, 13.0]                # 分维度的线同样断在那一天


def test_backfill_fills_in_the_missing_day(client, admin_headers):
    """回算脚本把 NULL 补上；补完之后 di_missing_dates 就空了。"""
    import models
    from database import SessionLocal
    from routers._issue_source import score_by
    from routers.issues import _snapshot_root

    db = SessionLocal()
    try:
        snap = (db.query(models.IssueSnapshot)
                .filter(models.IssueSnapshot.project == "OLDPROJ",
                        models.IssueSnapshot.snapshot_date == "2026-08-01").one())
        raw = json.loads((_snapshot_root() / snap.data_file).read_text(encoding="utf-8"))
        di_by_dim = {d: score_by(raw, d) for d in ("group", "customer", "severity")}
        stats = (db.query(models.IssueSnapshotStat)
                 .filter(models.IssueSnapshotStat.snapshot_id == snap.id).all())
        assert all(st.score is None for st in stats), "前置条件：这份快照还没有 DI"
        for st in stats:
            st.score = di_by_dim.get(st.dimension, {}).get(st.dim_key, 0.0)
        db.commit()
    finally:
        db.close()

    t = client.get("/api/issues/snapshot-trend",
                   params={"project": "OLDPROJ", "dimension": "group"},
                   headers=admin_headers).json()
    assert t["di_missing_dates"] == []
    assert t["total_di"] == [14.1, 14.1]


def test_empty_snapshot_is_zero_not_missing(client, admin_headers):
    """一条单都没有的快照没有任何维度行，那不是「没算过」，它的 DI 就是 0。

    不特判的话，每个空快照都会被报成待回算，页面上顶着一条永远消不掉的黄条。
    """
    _seed_snapshot(client, "EMPTYPROJ", "2026-08-05", [], with_di=True)
    t = client.get("/api/issues/snapshot-trend",
                   params={"project": "EMPTYPROJ", "dimension": "group"},
                   headers=admin_headers).json()
    assert t["total"] == [0]
    assert t["total_di"] == [0.0]
    assert t["di_missing_dates"] == []
