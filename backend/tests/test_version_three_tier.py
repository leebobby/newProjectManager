"""版本三层（大版本 → 版本 → 迭代版本）+ 主干/分支 + 0010 迁移的劈分。

重点不是 CRUD 通不通，是三件会静默出错的事：
1. 迭代版本的 major_version_id 是冗余列，必须始终跟着父版本走；
2. 主干只能有一个，切换时旧主干必须同时被降级；
3. 0010 迁移要把老库里混在一层的「版本」和「构建」按 B 后缀劈开，且不能
   把还被需求引用的行删掉。
"""
import pytest
import sqlalchemy as sa


@pytest.fixture(scope="module")
def project_id(client, admin_headers):
    r = client.post("/api/roadmap/projects", headers=admin_headers,
                    json={"name": "版本三层测试项目"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def iteration_id(client, admin_headers):
    """需求必须挂在某个年度迭代下，这里借第一条用。"""
    import datetime
    rows = client.get("/api/annual-iterations", headers=admin_headers,
                      params={"year": datetime.date.today().year}).json()
    assert rows, "年度迭代应自动生成 12 条"
    return rows[0]["id"]


@pytest.fixture(scope="module")
def normal_headers(client, admin_headers):
    client.post("/api/users", headers=admin_headers, json={
        "username": "ver_tester", "name": "版本测试", "password": "test1234",
        "role": "normal", "can_login": True,
    })
    tok = client.post("/api/auth/login",
                      json={"username": "ver_tester", "password": "test1234"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _major(client, headers, project_id, no):
    r = client.post("/api/major-versions", headers=headers,
                    json={"version_no": no, "project_id": project_id})
    assert r.status_code == 200, r.text
    return r.json()


def _release(client, headers, major_id, no, **kw):
    r = client.post("/api/release-versions", headers=headers,
                    json={"version_no": no, "major_version_id": major_id, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def _iter(client, headers, release_id, no, **kw):
    r = client.post("/api/iteration-versions", headers=headers,
                    json={"version_no": no, "release_version_id": release_id, **kw})
    assert r.status_code == 200, r.text
    return r.json()


# ─── 结构 ───────────────────────────────────────────────────────────────────
def test_three_levels_nest_and_major_id_is_derived(client, admin_headers, project_id):
    mv = _major(client, admin_headers, project_id, "T10SPC100")
    rv = _release(client, admin_headers, mv["id"], "T10SPC101")
    iv = _iter(client, admin_headers, rv["id"], "T10SPC101B001")

    # 冗余列由服务端从父版本推导
    assert iv["major_version_id"] == mv["id"]
    assert iv["release_version_id"] == rv["id"]

    rows = client.get("/api/major-versions", headers=admin_headers,
                      params={"project_id": project_id}).json()
    got = next(m for m in rows if m["id"] == mv["id"])
    assert [r["version_no"] for r in got["release_versions"]] == ["T10SPC101"]
    assert [i["version_no"] for i in got["release_versions"][0]["iteration_versions"]] \
        == ["T10SPC101B001"]


def test_client_cannot_forge_major_version_id(client, admin_headers, project_id):
    """迭代版本上传 major_version_id 一律忽略，否则冗余列会和父版本对不上。"""
    other = _major(client, admin_headers, project_id, "T10SPC900")
    mv = _major(client, admin_headers, project_id, "T10SPC200")
    rv = _release(client, admin_headers, mv["id"], "T10SPC201")
    r = client.post("/api/iteration-versions", headers=admin_headers, json={
        "version_no": "T10SPC201B001", "release_version_id": rv["id"],
        "major_version_id": other["id"],          # 伪造
    })
    assert r.status_code == 200, r.text
    assert r.json()["major_version_id"] == mv["id"]


def test_moving_release_repoints_children(client, admin_headers, project_id):
    a = _major(client, admin_headers, project_id, "T10SPC300")
    b = _major(client, admin_headers, project_id, "T10SPC310")
    rv = _release(client, admin_headers, a["id"], "T10SPC301")
    iv = _iter(client, admin_headers, rv["id"], "T10SPC301B001")
    assert iv["major_version_id"] == a["id"]

    r = client.put(f"/api/release-versions/{rv['id']}", headers=admin_headers,
                   json={"major_version_id": b["id"]})
    assert r.status_code == 200, r.text

    flat = client.get("/api/iteration-versions/all", headers=admin_headers).json()
    moved = next(x for x in flat if x["id"] == iv["id"])
    assert moved["major_version_id"] == b["id"], "改挂父级后构建仍算在旧大版本下，指标会串"
    assert moved["major_version_no"] == "T10SPC310"


def test_deleting_release_takes_its_builds(client, admin_headers, project_id):
    mv = _major(client, admin_headers, project_id, "T10SPC400")
    rv = _release(client, admin_headers, mv["id"], "T10SPC401")
    iv = _iter(client, admin_headers, rv["id"], "T10SPC401B001")
    assert client.delete(f"/api/release-versions/{rv['id']}", headers=admin_headers).status_code == 200
    flat = client.get("/api/iteration-versions/all", headers=admin_headers).json()
    assert all(x["id"] != iv["id"] for x in flat)


# ─── 主干 / 分支 ────────────────────────────────────────────────────────────
def test_new_major_is_branch_by_default(client, admin_headers, project_id):
    mv = _major(client, admin_headers, project_id, "T10SPC500")
    assert mv["line"] == "branch", "新建就自动成主干的话，同项目会冒出第二个主干"


def test_set_master_demotes_the_previous_one(client, admin_headers, project_id):
    old = _major(client, admin_headers, project_id, "T10SPC600")
    new = _major(client, admin_headers, project_id, "T10SPC610")
    assert client.post(f"/api/major-versions/{old['id']}/set-master",
                       headers=admin_headers).status_code == 200

    r = client.post(f"/api/major-versions/{new['id']}/set-master", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["line"] == "master"
    assert r.json()["branched_at"] is None

    rows = {m["id"]: m for m in client.get("/api/major-versions", headers=admin_headers,
                                           params={"project_id": project_id}).json()}
    demoted = rows[old["id"]]
    assert demoted["line"] == "branch"
    assert demoted["branched_at"], "被拉走主干要盖时间戳，否则时间轴不知道从哪拉枝"
    assert demoted["branch_name"] == "release/T10SPC600"

    # 同一项目里任何时刻只有一个主干
    masters = [m for m in rows.values() if m["line"] == "master"]
    assert len(masters) == 1 and masters[0]["id"] == new["id"]


def test_set_master_on_current_master_is_noop(client, admin_headers, project_id):
    rows = client.get("/api/major-versions", headers=admin_headers,
                      params={"project_id": project_id}).json()
    cur = next(m for m in rows if m["line"] == "master")
    r = client.post(f"/api/major-versions/{cur['id']}/set-master", headers=admin_headers)
    assert r.status_code == 200 and r.json()["line"] == "master"
    after = client.get("/api/major-versions", headers=admin_headers,
                       params={"project_id": project_id}).json()
    assert len([m for m in after if m["line"] == "master"]) == 1


def test_line_cannot_be_set_through_plain_update(client, admin_headers, project_id):
    """line 不在 MajorVersionUpdate 里：普通 PUT 改不动主干状态。"""
    mv = _major(client, admin_headers, project_id, "T10SPC700")
    r = client.put(f"/api/major-versions/{mv['id']}", headers=admin_headers,
                   json={"line": "master", "title": "顺便改个标题"})
    assert r.status_code == 200, r.text
    assert r.json()["line"] == "branch"
    assert r.json()["title"] == "顺便改个标题"


def test_writes_are_admin_only(client, normal_headers, admin_headers, project_id):
    mv = _major(client, admin_headers, project_id, "T10SPC800")
    assert client.post("/api/major-versions", headers=normal_headers,
                       json={"version_no": "X", "project_id": project_id}).status_code == 403
    assert client.post("/api/release-versions", headers=normal_headers,
                       json={"version_no": "X", "major_version_id": mv["id"]}).status_code == 403
    assert client.post(f"/api/major-versions/{mv['id']}/set-master",
                       headers=normal_headers).status_code == 403
    # 读对所有登录用户开放（各页面的版本下拉都要用）
    assert client.get("/api/release-versions/all", headers=normal_headers).status_code == 200


# ─── 扁平列表：哪一层给谁用 ─────────────────────────────────────────────────
def test_flat_lists_carry_parent_info(client, admin_headers, project_id):
    mv = _major(client, admin_headers, project_id, "T10SPCA00")
    rv = _release(client, admin_headers, mv["id"], "T10SPCA01", title="首发")
    _iter(client, admin_headers, rv["id"], "T10SPCA01B001")

    rels = client.get("/api/release-versions/all", headers=admin_headers).json()
    got = next(x for x in rels if x["id"] == rv["id"])
    assert got["major_version_no"] == "T10SPCA00"
    assert got["project_name"] == "版本三层测试项目"

    iters = client.get("/api/iteration-versions/all", headers=admin_headers).json()
    it = next(x for x in iters if x["version_no"] == "T10SPCA01B001")
    assert it["release_version_no"] == "T10SPCA01"
    assert it["major_version_no"] == "T10SPCA00"


# ─── 反查：由细到粗 ─────────────────────────────────────────────────────────
def test_version_lookup_falls_back_level_by_level(client, admin_headers, project_id):
    from database import SessionLocal
    from routers._lookups import resolve_iteration_version_id

    mv = _major(client, admin_headers, project_id, "T10SPCB00")
    rv = _release(client, admin_headers, mv["id"], "T10SPCB01")
    first = _iter(client, admin_headers, rv["id"], "T10SPCB01B001", sort_order=0)
    _iter(client, admin_headers, rv["id"], "T10SPCB01B002", sort_order=1)

    db = SessionLocal()
    try:
        assert resolve_iteration_version_id(db, "T10SPCB01B002") != first["id"]
        # 版本号 / 大版本号都落到该层下序号最小的构建
        assert resolve_iteration_version_id(db, "T10SPCB01") == first["id"]
        assert resolve_iteration_version_id(db, "T10SPCB00") == first["id"]
        assert resolve_iteration_version_id(db, "根本没有这个版本") is None
    finally:
        db.close()


def test_release_without_builds_resolves_to_none(client, admin_headers, project_id):
    """版本下还没有构建时反查返回 None，留给数据对账页补，不要瞎猜一个。"""
    from database import SessionLocal
    from routers._lookups import resolve_iteration_version_id

    mv = _major(client, admin_headers, project_id, "T10SPCC00")
    _release(client, admin_headers, mv["id"], "T10SPCC01")
    db = SessionLocal()
    try:
        assert resolve_iteration_version_id(db, "T10SPCC01") is None
    finally:
        db.close()


# ─── 达成率看「版本」这一层 ─────────────────────────────────────────────────
def test_version_metric_is_scoped_to_one_release(client, admin_headers, project_id, iteration_id):
    mv = _major(client, admin_headers, project_id, "T10SPCD00")
    r1 = _release(client, admin_headers, mv["id"], "T10SPCD01")
    r2 = _release(client, admin_headers, mv["id"], "T10SPCD02")
    i1 = _iter(client, admin_headers, r1["id"], "T10SPCD01B001")
    i2 = _iter(client, admin_headers, r2["id"], "T10SPCD02B001")

    for title, ivid in (("需求甲", i1["id"]), ("需求乙", i2["id"])):
        resp = client.post("/api/iteration-requirements", headers=admin_headers, json={
            "title": title, "target_version_id": ivid, "iteration_id": iteration_id,
        })
        assert resp.status_code == 200, resp.text

    m1 = client.get(f"/api/metrics/version/{r1['id']}", headers=admin_headers).json()
    assert m1["version_no"] == "T10SPCD01"
    assert m1["major_version_no"] == "T10SPCD00"
    titles = {i["title"] for i in m1["items"]}
    assert "需求甲" in titles and "需求乙" not in titles, "达成率串到了同大版本的另一个版本"


def test_version_metric_matches_requirements_that_wrote_the_release_no(client, admin_headers, project_id, iteration_id):
    """不少需求直接写「C10SPC101」而不是构建号，字符串回退要认这一层。"""
    mv = _major(client, admin_headers, project_id, "T10SPCE00")
    rv = _release(client, admin_headers, mv["id"], "T10SPCE01")
    resp = client.post("/api/iteration-requirements", headers=admin_headers, json={
        "title": "只写了版本号的需求", "planned_version": "T10SPCE01",
        "iteration_id": iteration_id,
    })
    assert resp.status_code == 200, resp.text
    m = client.get(f"/api/metrics/version/{rv['id']}", headers=admin_headers).json()
    assert "只写了版本号的需求" in {i["title"] for i in m["items"]}


# ─── 0010 迁移：把混在一层的两级劈开 ────────────────────────────────────────
def _load_migration():
    import importlib.util
    import pathlib
    path = (pathlib.Path(__file__).resolve().parent.parent
            / "alembic" / "versions" / "0010_version_three_tier.py")
    spec = importlib.util.spec_from_file_location("mig0010", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_split_rule():
    mod = _load_migration()
    assert mod._split("C10SPC101B001", "C10SPC100") == ("C10SPC101", False)
    assert mod._split("C10SPC100B012", "C10SPC100") == ("C10SPC100", False)
    assert mod._split("C10SPC101", "C10SPC100") == ("C10SPC101", True)
    # 版本号为空的构建挂到与大版本同号的版本下，不丢
    assert mod._split("", "C10SPC100") == ("C10SPC100", False)
    # B 后面不是数字的不算构建（BETA 是版本名的一部分）
    assert mod._split("C10SPC101BETA", "C10SPC100") == ("C10SPC101BETA", True)


def test_natural_key_orders_number_segments_numerically():
    mod = _load_migration()
    assert sorted(["C10SPC100", "C10SPC110", "C10SPC20"], key=mod._natural_key) \
        == ["C10SPC20", "C10SPC100", "C10SPC110"]


@pytest.fixture
def legacy_db(tmp_path):
    """造一个两层时代的老库：iteration_versions 里混着「版本」和「构建」。"""
    engine = sa.create_engine(f"sqlite:///{tmp_path}/legacy.db")
    with engine.begin() as c:
        c.execute(sa.text("""CREATE TABLE major_versions (
            id INTEGER PRIMARY KEY, project_id INTEGER, version_no VARCHAR(64),
            title VARCHAR(256), description TEXT, range_start DATETIME, range_end DATETIME,
            actual_release_date DATETIME, sort_order INTEGER, created_at DATETIME,
            updated_at DATETIME)"""))
        c.execute(sa.text("""CREATE TABLE iteration_versions (
            id INTEGER PRIMARY KEY, major_version_id INTEGER, version_no VARCHAR(64),
            title VARCHAR(256), planned_date DATETIME, sort_order INTEGER, created_at DATETIME)"""))
        for t in ("iteration_requirements", "iteration_product_requirements"):
            c.execute(sa.text(f"CREATE TABLE {t} (id INTEGER PRIMARY KEY, target_version_id INTEGER)"))
        c.execute(sa.text(
            "INSERT INTO major_versions (id, project_id, version_no, sort_order, actual_release_date)"
            " VALUES (1, 7, 'C10SPC100', 0, '2026-03-01 00:00:00'), (2, 7, 'C10SPC110', 1, NULL)"))
        rows = [
            (1, 1, "C10SPC100B001", 0),   # 大版本同号的构建
            (2, 1, "C10SPC101", 1),       # 其实是「版本」——没人引用，迁移后删掉
            (3, 1, "C10SPC101B001", 2),
            (4, 1, "C10SPC101B002", 3),
            (5, 1, "C10SPC102", 4),       # 其实是「版本」——被需求引用，保留
            (6, 2, "C10SPC111B001", 0),
        ]
        for rid, mid, no, so in rows:
            c.execute(sa.text("INSERT INTO iteration_versions (id, major_version_id, version_no,"
                              " title, sort_order) VALUES (:i,:m,:n,'',:s)"),
                      {"i": rid, "m": mid, "n": no, "s": so})
        c.execute(sa.text("INSERT INTO iteration_requirements (id, target_version_id) VALUES (1, 5)"))
    return engine


def test_migration_splits_mixed_levels(legacy_db):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    mod = _load_migration()
    with legacy_db.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()

    with legacy_db.connect() as c:
        rels = c.execute(sa.text(
            "SELECT major_version_id, version_no, actual_release_date FROM release_versions"
            " ORDER BY major_version_id, sort_order")).fetchall()
        assert [(r[0], r[1]) for r in rels] == [
            (1, "C10SPC100"), (1, "C10SPC101"), (1, "C10SPC102"), (2, "C10SPC111"),
        ]
        # 大版本上的实际发布日下沉到同号的版本，其余版本不认领它
        assert rels[0][2] is not None
        assert rels[1][2] is None

        # 构建各自挂到自己的版本下
        pairs = dict(c.execute(sa.text(
            "SELECT iv.version_no, rv.version_no FROM iteration_versions iv"
            " JOIN release_versions rv ON rv.id = iv.release_version_id")).fetchall())
        assert pairs["C10SPC100B001"] == "C10SPC100"
        assert pairs["C10SPC101B001"] == "C10SPC101"
        assert pairs["C10SPC101B002"] == "C10SPC101"
        assert pairs["C10SPC111B001"] == "C10SPC111"

        left = {r[0] for r in c.execute(sa.text("SELECT version_no FROM iteration_versions"))}
        assert "C10SPC101" not in left, "没人引用的冗余行应被删掉"
        assert "C10SPC102" in left, "还被需求引用的行必须留着，不能 SET NULL 掉别人填的计划版本"

        lines = dict(c.execute(sa.text("SELECT version_no, line FROM major_versions")).fetchall())
        assert lines == {"C10SPC100": "branch", "C10SPC110": "master"}
        bn = dict(c.execute(sa.text("SELECT version_no, branch_name FROM major_versions")).fetchall())
        assert bn["C10SPC100"] == "release/C10SPC100" and bn["C10SPC110"] == ""
        # 历史拉分支时间无从考证，留空好过编一个
        assert c.execute(sa.text(
            "SELECT branched_at FROM major_versions WHERE version_no='C10SPC100'")).scalar() is None


def test_migration_is_idempotent(legacy_db):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    mod = _load_migration()
    for _ in range(2):
        with legacy_db.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                mod.upgrade()
    with legacy_db.connect() as c:
        n = c.execute(sa.text("SELECT COUNT(*) FROM release_versions")).scalar()
    assert n == 4, "重跑不能把版本翻倍——automigrate 会把整条升级链再走一遍"
