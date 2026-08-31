"""领域管理：超过「预计闭环时间」还没处理的问题单数量。

「没处理」不用读状态：快照里本来就只有当天还开着的单（关闭/撤销在采集时就剔掉了），
在快照里 ＝ 还没处理。这与「解决＝从快照里消失」是同一套口径，两处必须一致，
否则会出现"已闭环的单还挂在超期数里"。

第二件要钉住的事：**没填预计闭环时间的条数要一起报**。DTS 那一列是选填的，
没接上时全库都是空，此时「超期 0」会被读成"一条都没超期"，而实际是算不出来。
"""
import datetime
import json

import pytest

TODAY = datetime.date.today()
PAST = (TODAY - datetime.timedelta(days=10)).strftime("%Y-%m-%d")
PAST2 = (TODAY - datetime.timedelta(days=1)).strftime("%Y/%m/%d")   # 另一种写法
FUTURE = (TODAY + datetime.timedelta(days=10)).strftime("%Y-%m-%d")


@pytest.fixture(scope="module")
def env(client, admin_headers, tmp_path_factory):
    import models
    from database import SessionLocal
    import routers.issues as ri

    root = tmp_path_factory.mktemp("overdue_snapshots")
    ri._snapshot_root = lambda: root

    dept = client.post("/api/resource-groups", headers=admin_headers,
                       json={"code": "ODDEPT", "name": "超期测试部", "kind": "dept"}).json()
    g = client.post("/api/resource-groups", headers=admin_headers,
                    json={"code": "ODG", "name": "超期测试组", "kind": "pl",
                          "parent_id": dept["id"]}).json()
    g2 = client.post("/api/resource-groups", headers=admin_headers,
                     json={"code": "ODG2", "name": "超期测试组乙", "kind": "pl",
                           "parent_id": dept["id"]}).json()

    rows = [
        # 超期：预计闭环时间已经过了，单还在快照里
        {"issue_id": "O1", "severity": "严重", "group": "超期测试组", "estimated_close": PAST},
        {"issue_id": "O2", "severity": "一般", "group": "超期测试组", "estimated_close": PAST2},
        # 没超期
        {"issue_id": "O3", "severity": "一般", "group": "超期测试组", "estimated_close": FUTURE},
        # 今天到期不算超期（"超过"才算）
        {"issue_id": "O4", "severity": "提示", "group": "超期测试组",
         "estimated_close": TODAY.strftime("%Y-%m-%d")},
        # 没填 / 填了看不懂的
        {"issue_id": "O5", "severity": "一般", "group": "超期测试组", "estimated_close": ""},
        {"issue_id": "O6", "severity": "一般", "group": "超期测试组", "estimated_close": "待定"},
        # 另一个组：一条都没填日期
        {"issue_id": "O7", "severity": "一般", "group": "超期测试组乙"},
    ]
    db = SessionLocal()
    rel = "ODPROJ/2026-04-01.json"
    fp = root / rel
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    db.add(models.IssueSnapshot(project="ODPROJ", snapshot_date="2026-04-01",
                                total=len(rows), data_file=rel, source="api"))
    db.commit()
    db.close()
    return {"g": g["id"], "g2": g2["id"]}


def _summary(client, headers, group_id):
    d = client.get("/api/domains", headers=headers, params={"project": "ODPROJ"}).json()
    return next(r for r in d["rows"] if r["group_id"] == group_id)["issue_summary"]


def test_overdue_counts_only_past_due_rows(client, admin_headers, env):
    s = _summary(client, admin_headers, env["g"])
    assert s["total"] == 6
    assert s["overdue"] == 2, "只有预计闭环时间已经过去的那两条算超期"


def test_due_today_is_not_overdue(client, admin_headers, env):
    """「超过」计划时间才算——当天到期的还在期限内，记成超期会让人白紧张一天。"""
    d = client.get("/api/domains/%d/issues" % env["g"], headers=admin_headers,
                   params={"project": "ODPROJ", "overdue": True}).json()
    assert {r["issue_id"] for r in d["rows"]} == {"O1", "O2"}


def test_rows_without_a_plan_date_are_reported_not_counted(client, admin_headers, env):
    """没填的既不算超期也不算达标，单独报出来。"""
    s = _summary(client, admin_headers, env["g"])
    assert s["overdue_unknown"] == 2, "空串与看不懂的写法都算「没填」"


def test_all_missing_is_distinguishable_from_none_overdue(client, admin_headers, env):
    """整组都没填日期时 overdue=0，但 overdue_unknown==total——页面据此说「算不出」
    而不是「没有超期的」。两者混为一谈会让一个没接上的字段看起来像达标。"""
    s = _summary(client, admin_headers, env["g2"])
    assert s["total"] == 1 and s["overdue"] == 0 and s["overdue_unknown"] == 1


def test_drilldown_without_the_flag_returns_everything(client, admin_headers, env):
    d = client.get("/api/domains/%d/issues" % env["g"], headers=admin_headers,
                   params={"project": "ODPROJ"}).json()
    assert len(d["rows"]) == 6


@pytest.mark.parametrize("value, expected", [
    ("2026-09-15", datetime.date(2026, 9, 15)),
    ("2026/9/15", datetime.date(2026, 9, 15)),
    ("2026.09.15", datetime.date(2026, 9, 15)),
    ("2026-09-15 00:00:00", datetime.date(2026, 9, 15)),
    ("2026年9月15日", datetime.date(2026, 9, 15)),
    ("", None),
    (None, None),
    ("待定", None),
    ("2026-13-45", None),
])
def test_plan_date_parsing_is_tolerant_but_never_guesses(client, value, expected):
    """认不出来的一律算「没填」而不是算「没超期」——后者会把一批读不懂的日期
    悄悄记成达标，数字看着还挺好。"""
    from routers._issue_source import parse_plan_date
    assert parse_plan_date(value) == expected


# ─── 度量看板：各领域横向对比 ────────────────────────────────────────────────

def test_dashboard_ranks_domains_by_overdue(client, admin_headers, env):
    """看板与领域总览走同一份数据源和同一份口径——两处各写一份的表现是
    同一个组在两个页面上超期数不一样，而两边看着都像对的。"""
    d = client.get("/api/metrics/issue-overdue", headers=admin_headers,
                   params={"project": "ODPROJ"}).json()
    assert d["available"] and d["project"] == "ODPROJ"
    assert d["total"] == 7 and d["overdue"] == 2 and d["overdue_unknown"] == 3

    names = [r["group_name"] for r in d["rows"]]
    assert names[0] == "超期测试组", "超期多的排最前面"
    row = d["rows"][0]
    assert row["overdue"] == 2 and row["total"] == 6
    # 分母是"填了预计闭环时间的条数"（6-2=4），不是 total：按 total 算的话，
    # 一个压根没填日期的组会显示成 0%，看着比谁都干净
    assert row["overdue_rate"] == 0.5
    assert row["oldest_overdue_days"] == 10


def test_group_with_no_dates_shows_zero_rate_not_a_clean_bill(client, admin_headers, env):
    g2 = next(r for r in client.get("/api/metrics/issue-overdue", headers=admin_headers,
                                    params={"project": "ODPROJ"}).json()["rows"]
              if r["group_name"] == "超期测试组乙")
    assert g2["overdue"] == 0 and g2["overdue_unknown"] == g2["total"]
    assert g2["overdue_rate"] == 0.0, "没有可比的基数时是 0，页面据此显示「算不出」"


def test_unknown_project_is_reported_not_silently_swapped(client, admin_headers, env):
    """指定了没有快照的项目时如实说明，绝不静默换成别的项目的数字。"""
    d = client.get("/api/metrics/issue-overdue", headers=admin_headers,
                   params={"project": "NOSUCHPROJ"}).json()
    assert d["available"] is False and d["note"]
    assert d["rows"] == []
    assert any(p["project"] == "ODPROJ" for p in d["projects"]), "可选项目仍要给出来"
