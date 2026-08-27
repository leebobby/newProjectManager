"""度量看板的两个质量维度：版本质量（整个版本）与领域质量（按迭代）。

这两个维度的口径是**不一样的**，而且必须不一样：
- 领域按月排活，问「这个月各领域干得怎么样」才有意义 → 口径＝一个迭代；
- 版本跨月，按月截一刀会得到一个既不是这个版本、也不是这个月的数 → 口径＝整个版本。

这里钉住的是：
1. 按领域分行只列**确实挂着需求**的领域，没填 PL 组的归到「未指定领域」并排最后；
2. 合计＝各行相加（前端不用自己加一遍，两端各加一次迟早对不上）；
3. 版本口径的 total 含产品需求、by_domain 各行只数领域需求——两个数对不上是正常的；
4. 密度分子分母来自同一批行（只筛分子会得到量纲对、数值错的密度）；
5. 采集问题单按「版本信息」**精确匹配**，命中率如实报，没命中的取值也报出来；
6. 「未指定领域」那行的快照问题单留空而不是记 0——0 会被读成"这个领域没问题单"。
"""
import datetime
import json

import pytest

_DOMAIN_PROGRESS = ("progress_walkthrough", "progress_reverse", "progress_stc",
                    "progress_coding", "progress_bbit", "progress_clarify")
_ALL_DONE = {f: "已完成" for f in _DOMAIN_PROGRESS}
_PROJECT = "QUALMETRIC"


@pytest.fixture(scope="module")
def env(client, admin_headers, tmp_path_factory):
    """一个迭代 + 一个版本（两个构建）+ 两个领域，外加一份问题单快照。"""
    import models
    from database import SessionLocal
    import routers.issues as ri

    year = datetime.date.today().year
    it = client.get("/api/annual-iterations", headers=admin_headers,
                    params={"year": year}).json()[0]

    mv = client.post("/api/major-versions", headers=admin_headers,
                     json={"version_no": "Q10SPCV00"}).json()
    rv = client.post("/api/release-versions", headers=admin_headers,
                     json={"version_no": "Q10SPCV01", "major_version_id": mv["id"]}).json()
    iv = client.post("/api/iteration-versions", headers=admin_headers,
                     json={"version_no": "Q10SPCV01B001", "release_version_id": rv["id"]}).json()

    dept = client.post("/api/resource-groups", headers=admin_headers,
                       json={"code": "QMD", "name": "质量度量部", "kind": "dept"}).json()
    g1 = client.post("/api/resource-groups", headers=admin_headers,
                     json={"code": "QMA", "name": "质量度量甲组", "kind": "pl",
                           "parent_id": dept["id"]}).json()
    g2 = client.post("/api/resource-groups", headers=admin_headers,
                     json={"code": "QMB", "name": "质量度量乙组", "kind": "pl",
                           "parent_id": dept["id"]}).json()

    def req(title, **kw):
        body = {"iteration_id": it["id"], "title": title, "target_version_id": iv["id"]}
        body.update(kw)
        r = client.post("/api/iteration-requirements", headers=admin_headers, json=body)
        assert r.status_code == 200, r.text
        return r.json()

    # 甲组：2 条，代码量 20000 行、用例 60 个、转测后问题单 4 个
    req("质量-甲1", group_id=g1["id"], code_volume=12000,
        self_test_case_count=40, post_test_issue_count=3, **_ALL_DONE)
    req("质量-甲2", group_id=g1["id"], code_volume=8000,
        self_test_case_count=20, post_test_issue_count=1)
    # 乙组：1 条
    req("质量-乙1", group_id=g2["id"], code_volume=5000,
        self_test_case_count=25, post_test_issue_count=2)
    # 没填 PL 组：该进「未指定领域」，不能藏起来
    req("质量-无组", code_volume=1000, self_test_case_count=2, post_test_issue_count=1)
    # 已变更：任何口径下都整行剔除，代码量也不能算进去
    req("质量-已变更", group_id=g1["id"], code_volume=999999,
        self_test_case_count=999, post_test_issue_count=999,
        **{f: "已变更" for f in _DOMAIN_PROGRESS})

    # 产品需求：进版本口径的 total，但不进 by_domain（没有 PL 组，也没有质量字段）
    r = client.post("/api/iteration-product-requirements", headers=admin_headers,
                    json={"iteration_id": it["id"], "title": "质量-产品1",
                          "target_version_id": iv["id"]})
    assert r.status_code == 200, r.text

    # 问题单快照：3 条命中构建号（甲2 乙1），2 条挂在别的版本串上
    root = tmp_path_factory.mktemp("qual_snapshots")
    ri._snapshot_root = lambda: root
    rel = f"{_PROJECT}/2026-05-06.json"
    fp = root / rel
    fp.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"issue_id": "S1", "severity": "致命", "group": "质量度量甲组", "version": "Q10SPCV01B001"},
        {"issue_id": "S2", "severity": "一般", "group": "质量度量甲组", "version": "Q10SPCV01"},
        {"issue_id": "S3", "severity": "严重", "group": "质量度量乙组", "version": "Q10SPCV01B001"},
        {"issue_id": "S4", "severity": "一般", "group": "质量度量甲组", "version": "别的版本"},
        {"issue_id": "S5", "severity": "一般", "group": "质量度量甲组", "version": ""},
    ]
    fp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    db = SessionLocal()
    db.add(models.IssueSnapshot(project=_PROJECT, snapshot_date="2026-05-06",
                                total=len(rows), data_file=rel, source="api"))
    db.commit()
    db.close()

    return {"iteration": it, "release_id": rv["id"],
            "g1": g1["id"], "g2": g2["id"], "root": root}


def _patch_root(env):
    """快照根目录是模块级可变状态，别的测试模块也会改它——每次用前重新指回来。"""
    import routers.issues as ri
    ri._snapshot_root = lambda: env["root"]


def _domain_quality(client, headers, env, **params):
    r = client.get(f"/api/metrics/domain-quality/{env['iteration']['id']}",
                   headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _version(client, headers, env, **params):
    r = client.get(f"/api/metrics/version/{env['release_id']}", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


# ─── 领域质量（按迭代）─────────────────────────────────────────────────────
def test_domain_quality_rows_and_total(client, admin_headers, env):
    d = _domain_quality(client, admin_headers, env)
    rows = {r["group_name"]: r for r in d["rows"]}
    assert rows["质量度量甲组"]["total"] == 2
    assert rows["质量度量甲组"]["code_volume"] == 20000
    assert rows["质量度量乙组"]["total"] == 1

    # 合计＝各行相加：两端各加一次迟早对不上，所以后端把合计一起给出来
    assert d["total"] == sum(r["total"] for r in d["rows"])
    assert d["code_volume"] == sum(r["code_volume"] for r in d["rows"])
    assert d["self_test_cases"] == sum(r["self_test_cases"] for r in d["rows"])


def test_unassigned_domain_is_its_own_row_and_sorts_last(client, admin_headers, env):
    """没填 PL 组的行正是最该被捞出来补录的那批，藏起来就永远没人去补。"""
    d = _domain_quality(client, admin_headers, env)
    assert d["rows"][-1]["group_name"] == "未指定领域"
    assert d["rows"][-1]["group_id"] is None
    assert d["rows"][-1]["total"] == 1


def test_changed_rows_do_not_leak_into_quality(client, admin_headers, env):
    """已变更那条带着 999999 行代码——漏剔一次，密度会离谱到没法用。"""
    d = _domain_quality(client, admin_headers, env)
    assert d["changed"] == 1
    assert d["code_volume"] == 26000        # 12000+8000+5000+1000，不含 999999
    assert all(r["code_volume"] < 999999 for r in d["rows"])


def test_density_shares_numerator_and_denominator(client, admin_headers, env):
    """密度＝该行自己的用例数 ÷ 该行自己的代码量。分子分母来自不同批行的话，量纲对、数值错。"""
    d = _domain_quality(client, admin_headers, env)
    jia = next(r for r in d["rows"] if r["group_name"] == "质量度量甲组")
    assert jia["self_test_case_density"] == pytest.approx(60 / 20.0)   # 60 个 / 20 kloc
    assert jia["post_test_issue_density"] == pytest.approx(4 / 20.0)


def test_domain_quality_unknown_iteration_404(client, admin_headers):
    assert client.get("/api/metrics/domain-quality/999999",
                      headers=admin_headers).status_code == 404


# ─── 版本质量（整个版本）───────────────────────────────────────────────────
def test_version_total_includes_product_but_by_domain_does_not(client, admin_headers, env):
    """版本的 total 把产品需求也算进来（进度要看全），但质量字段只有领域需求有，
    所以 by_domain 各行相加会比 total 少——这不是 bug，表头要写明白。"""
    d = _version(client, admin_headers, env)
    assert d["total"] == 5                                   # 领域 4 + 产品 1
    assert sum(r["total"] for r in d["by_domain"]) == 4       # 只数领域需求
    assert d["changed"] == 1


def test_version_totals_carry_density(client, admin_headers, env):
    d = _version(client, admin_headers, env)
    assert d["total_code_volume"] == 26000
    assert d["total_self_test_case_density"] == round(87 / 26.0, 2)   # 87 个 / 26 kloc


def test_version_issue_match_rate_is_reported(client, admin_headers, env):
    """快照的「版本信息」是 DTS 的自由串，对不上是常态。命中多少要如实报，
    没命中的取值也要报出来——否则「这个版本怎么一个问题单都没有」没人说得清。"""
    _patch_root(env)
    d = _version(client, admin_headers, env, issue_project=_PROJECT)
    st = d["issues"]
    assert st["available"] is True
    assert st["total"] == 5 and st["matched"] == 3
    assert st["match_rate"] == pytest.approx(0.6)
    joined = " ".join(st["unmatched_top"])
    assert "别的版本" in joined and "版本信息为空" in joined


def test_matched_issues_split_by_domain(client, admin_headers, env):
    """命中的单按「责任人所属小组」落到各领域行；未指定领域那行留空而不是记 0，
    0 会被读成"这个领域没问题单"，留空才是"这一格算不出来"。"""
    _patch_root(env)
    d = _version(client, admin_headers, env, issue_project=_PROJECT)
    rows = {r["group_name"]: r for r in d["by_domain"]}
    assert rows["质量度量甲组"]["snapshot_issues"] == 2          # S1 致命 + S2 一般
    assert rows["质量度量甲组"]["snapshot_score"] == pytest.approx(11.0)
    assert rows["质量度量乙组"]["snapshot_issues"] == 1
    assert rows["未指定领域"]["snapshot_issues"] is None


def test_unknown_issue_project_says_so_instead_of_swapping(client, admin_headers, env):
    """指定的项目没有快照时如实返回不可用，绝不静默换成别的项目的数字。"""
    _patch_root(env)
    d = _version(client, admin_headers, env, issue_project="根本没有这个项目")
    assert d["issues"]["available"] is False
    assert d["issues"]["note"]
