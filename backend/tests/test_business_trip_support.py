"""客户面支撑：支撑项目 / 现场·线上 / 工作量（人天）。

人天是这次改动里最容易悄悄算错的东西，所以按口径逐条钉死：
填了 man_days 以它为准、没填按日历天数、跨区间按重叠比例分摊。
"""
import datetime as dt

import pytest


def _day(offset: int) -> str:
    return (dt.date.today() + dt.timedelta(days=offset)).isoformat() + "T00:00:00"


def _ymd(offset: int) -> str:
    return (dt.date.today() + dt.timedelta(days=offset)).isoformat()


@pytest.fixture(scope="module")
def project_id(client, admin_headers):
    resp = client.post("/api/roadmap/projects",
                       json={"name": "支撑口径测试项目", "granularity": "quarter"},
                       headers=admin_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


@pytest.fixture
def fresh_project(client, admin_headers, request):
    """每个统计用例一个专属项目：看板按 project_id 过滤，用例之间就不会互相污染。"""
    name = f"支撑口径-{request.node.name}"
    resp = client.post("/api/roadmap/projects", json={"name": name}, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    return {"id": resp.json()["id"], "name": name}


@pytest.fixture(scope="module")
def customer_id(client, admin_headers):
    resp = client.post("/api/customers", json={"code": "TRIPCUST"}, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _create(client, headers, **kw):
    body = {"start_date": _day(0), "end_date": _day(0)}
    body.update(kw)
    resp = client.post("/api/business-trips", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── 字段落库 ──────────────────────────────────────────────────────────────────
def test_create_carries_project_and_mode(client, admin_headers, project_id, customer_id):
    row = _create(client, admin_headers, project_id=project_id, customer_id=customer_id,
                  support_mode="线上支撑", purpose="远程调试")
    assert row["project_id"] == project_id
    assert row["project_name"] == "支撑口径测试项目"
    assert row["support_mode"] == "线上支撑"


def test_support_mode_defaults_to_onsite(client, admin_headers):
    """不传方式＝现场支撑：老数据与批量导入都落在这一档。"""
    assert _create(client, admin_headers)["support_mode"] == "现场支撑"


def test_bad_support_mode_rejected(client, admin_headers):
    resp = client.post("/api/business-trips",
                       json={"support_mode": "电话支撑", "start_date": _day(0)},
                       headers=admin_headers)
    assert resp.status_code == 422


def test_negative_man_days_rejected(client, admin_headers):
    resp = client.post("/api/business-trips",
                       json={"man_days": -1, "start_date": _day(0)}, headers=admin_headers)
    assert resp.status_code == 422


def test_update_keeps_mode_when_not_sent(client, admin_headers):
    row = _create(client, admin_headers, support_mode="线上支撑")
    resp = client.put(f"/api/business-trips/{row['id']}",
                      json={"version": row["version"], "purpose": "改个事由"},
                      headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["support_mode"] == "线上支撑"


def test_login_required_to_write(client):
    resp = client.post("/api/business-trips", json={"start_date": _day(0)})
    assert resp.status_code in (401, 403)


# ── 人天推导 ──────────────────────────────────────────────────────────────────
def test_calc_man_days_from_calendar_days(client, admin_headers):
    """没填 man_days：含头含尾的日历天数。"""
    row = _create(client, admin_headers, start_date=_day(0), end_date=_day(2))
    assert row["calc_man_days"] == 3


def test_calc_man_days_prefers_explicit(client, admin_headers):
    """填了 man_days 就以它为准——线上支撑五天各两小时不该算 5 人天。"""
    row = _create(client, admin_headers, start_date=_day(0), end_date=_day(4),
                  support_mode="线上支撑", man_days=1.5)
    assert row["calc_man_days"] == 1.5


def test_single_day_is_one_man_day(client, admin_headers):
    """只填了开始日期：按当天算一天，不是零天。"""
    row = _create(client, admin_headers, start_date=_day(0), end_date=None)
    assert row["calc_man_days"] == 1


# ── 看板统计 ──────────────────────────────────────────────────────────────────
def _dash(client, headers, **params):
    resp = client.get("/api/business-trips/dashboard", params=params, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_dashboard_sums_man_days_and_splits_by_mode(client, admin_headers, fresh_project):
    """同一项目里现场 3 天 + 线上 1.5 人天 → 合计 4.5，且按方式分开。"""
    pid = fresh_project["id"]
    _create(client, admin_headers, project_id=pid, start_date=_day(1), end_date=_day(3))
    _create(client, admin_headers, project_id=pid, start_date=_day(1), end_date=_day(5),
            support_mode="线上支撑", man_days=1.5)
    d = _dash(client, admin_headers, start=_ymd(-30), end=_ymd(30), project_id=pid)
    assert d["range_man_days"] == 4.5
    assert d["onsite_man_days"] == 3
    assert d["online_man_days"] == 1.5
    assert {m["name"]: m["man_days"] for m in d["by_mode"]} == {"现场支撑": 3, "线上支撑": 1.5}


def test_dashboard_prorates_across_range_boundary(client, admin_headers, fresh_project):
    """跨区间边界的记录按重叠天数分摊，不整段计入。

    10 天的支撑只有 4 天落在区间里 → 4 人天。别改成「有重叠就整段计入」：
    每个月都算一遍，各月看着都对，加起来比全年还多。
    """
    pid = fresh_project["id"]
    _create(client, admin_headers, project_id=pid, start_date=_day(0), end_date=_day(9))
    d = _dash(client, admin_headers, start=_ymd(0), end=_ymd(3), project_id=pid)
    assert d["range_man_days"] == 4
    assert d["range_total"] == 1


def test_dashboard_prorates_explicit_man_days(client, admin_headers, fresh_project):
    """手填的 10 人天摊在 10 天上，区间截 5 天 → 5 人天。"""
    pid = fresh_project["id"]
    _create(client, admin_headers, project_id=pid, start_date=_day(0), end_date=_day(9),
            man_days=10)
    d = _dash(client, admin_headers, start=_ymd(0), end=_ymd(4), project_id=pid)
    assert d["range_man_days"] == 5


def test_dashboard_project_filter_scopes_now_snapshot(client, admin_headers, fresh_project):
    """项目筛选同时收窄 now 快照：否则上面的「当前支撑中」和下面的分项对不上。"""
    pid = fresh_project["id"]
    _create(client, admin_headers, project_id=pid, start_date=_day(-1), end_date=_day(1))
    d = _dash(client, admin_headers, start=_ymd(-30), end=_ymd(30), project_id=pid)
    assert d["on_trip_now"] == 1
    assert [p["name"] for p in d["by_project"]] == [fresh_project["name"]]


def test_dashboard_mode_filter(client, admin_headers, fresh_project):
    pid = fresh_project["id"]
    _create(client, admin_headers, project_id=pid, start_date=_day(0), end_date=_day(1))
    _create(client, admin_headers, project_id=pid, start_date=_day(0), end_date=_day(1),
            support_mode="线上支撑", man_days=0.5)
    d = _dash(client, admin_headers, start=_ymd(-30), end=_ymd(30),
              project_id=pid, support_mode="线上支撑")
    assert d["range_total"] == 1
    assert d["range_man_days"] == 0.5


def test_cancelled_excluded_from_man_days(client, admin_headers, fresh_project):
    pid = fresh_project["id"]
    row = _create(client, admin_headers, project_id=pid, start_date=_day(0), end_date=_day(2))
    client.put(f"/api/business-trips/{row['id']}",
               json={"version": row["version"], "cancelled": True}, headers=admin_headers)
    d = _dash(client, admin_headers, start=_ymd(-30), end=_ymd(30), project_id=pid)
    assert d["range_man_days"] == 0
    assert d["range_total"] == 0


# ── 列表筛选 ──────────────────────────────────────────────────────────────────
def test_list_filters_by_project_and_mode(client, admin_headers, fresh_project):
    pid = fresh_project["id"]
    _create(client, admin_headers, project_id=pid, start_date=_day(0))
    _create(client, admin_headers, project_id=pid, start_date=_day(0), support_mode="线上支撑")
    rows = client.get("/api/business-trips",
                      params={"project_id": pid, "support_mode": "线上支撑"},
                      headers=admin_headers).json()
    assert len(rows) == 1 and rows[0]["support_mode"] == "线上支撑"


# ── 迁移 0011 ─────────────────────────────────────────────────────────────────
import sqlalchemy as sa  # noqa: E402


def _load_migration():
    import importlib.util
    import pathlib
    path = (pathlib.Path(__file__).resolve().parent.parent
            / "alembic" / "versions" / "0011_business_trip_support.py")
    spec = importlib.util.spec_from_file_location("mig0011", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def legacy_db(tmp_path):
    """改造前的 business_trips：只有出差那几列。"""
    engine = sa.create_engine(f"sqlite:///{tmp_path}/legacy.db")
    with engine.begin() as c:
        c.execute(sa.text("""CREATE TABLE business_trips (
            id INTEGER PRIMARY KEY, user_id INTEGER, customer_id INTEGER,
            location VARCHAR(128), purpose VARCHAR(256),
            start_date DATETIME, end_date DATETIME, cancelled BOOLEAN,
            remark TEXT, sort_order INTEGER, version INTEGER,
            created_at DATETIME, updated_at DATETIME)"""))
        c.execute(sa.text(
            "INSERT INTO business_trips (id, user_id, customer_id, purpose, version)"
            " VALUES (1, 3, 5, '现场交付', 0), (2, 4, 5, '客户会议', 0)"))
    return engine


def _run(engine, mod):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()


def test_migration_adds_columns_and_backfills_onsite(legacy_db):
    """老数据登记的就是出差，人确实到了现场——全部回填成现场支撑。"""
    _run(legacy_db, _load_migration())
    with legacy_db.connect() as c:
        cols = {r[1] for r in c.execute(sa.text("PRAGMA table_info(business_trips)"))}
        assert {"project_id", "support_mode", "man_days"} <= cols
        rows = c.execute(sa.text(
            "SELECT support_mode, project_id, man_days FROM business_trips ORDER BY id")).fetchall()
        # 项目与人天留空：当时支撑的是哪个项目、花了几天，猜一个比留空更糟
        assert rows == [("现场支撑", None, None), ("现场支撑", None, None)]


def test_migration_is_idempotent(legacy_db):
    """automigrate 会把整条链再走一遍，重跑必须无副作用。"""
    mod = _load_migration()
    _run(legacy_db, mod)
    with legacy_db.begin() as c:
        c.execute(sa.text("UPDATE business_trips SET support_mode = '线上支撑' WHERE id = 1"))
    _run(legacy_db, mod)
    with legacy_db.connect() as c:
        modes = [r[0] for r in c.execute(sa.text(
            "SELECT support_mode FROM business_trips ORDER BY id"))]
        assert modes == ["线上支撑", "现场支撑"], "重跑不该把已改过的方式冲回现场"
