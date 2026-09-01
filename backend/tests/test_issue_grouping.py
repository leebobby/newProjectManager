"""责任人归组：归不到组的人**留下来**，并被报出去。

历史上归不到组的行是直接丢的，而「解决」＝这一单从快照里消失（差分从不读状态），
于是「问题单从定位转到实施修改、顺手转给了名单外的人」会表现成一笔假解决——
数字看着完全正常，没人会当 bug 报。这里钉住三件事：

1. 名单外的人不丢行，归到「未归组」；
2. 部门过滤照旧丢行（部门答的是"这单归不归我们管"，是另一个问题）；
3. 转给名单外的人之后，差分里不再出现这笔假「解决」。
"""
import json

import pytest


@pytest.fixture(scope="module")
def ri(client):
    """routers.issues。**必须依赖 client 之后再 import**：conftest 的 client 夹具
    先 os.chdir 到临时库目录，模块顶层 import 会赶在 chdir 之前把引擎连上仓库里的
    backend/app.db，之后整个会话都跑在那个老库上——表现是别的测试文件成片报
    「no such column」，而单跑这个文件一切正常。
    """
    import routers.issues as ri
    return ri


def _rows(*specs):
    """specs: (issue_id, owner, dept, progress)"""
    return [{"issue_id": i, "owner": o, "department": d, "dept_path": d,
             "progress": p, "title": f"标题 {i}", "severity": "一般"}
            for i, o, d, p in specs]


@pytest.fixture
def cfg(monkeypatch, ri):
    """让 _enrich_rows 读到我们给的配置，不碰仓库里的 config.json。"""
    store = {}

    def _set(**kw):
        store.clear()
        store.update(kw)
        monkeypatch.setattr(ri, "_load_config", lambda: dict(store))
        # 客户面匹配要查库，这里不测它
        monkeypatch.setattr(ri, "_load_customer_matchers", lambda db: [])
    return _set


# ── ① 名单外的人不丢行 ──────────────────────────────────────────────────────

def test_unlisted_owner_is_kept_as_ungrouped(cfg, ri):
    cfg(issue_groups=[{"name": "SE组", "members": "张三;李四"}])
    out = ri._enrich_rows(None, _rows(
        ("A1", "张三", "量检测软件部", "定位"),
        ("A2", "王五", "量检测软件部", "实施修改"),   # 名单里没有王五
    ))
    assert [r["issue_id"] for r in out] == ["A1", "A2"], "名单外的人不该被丢掉"
    assert out[0]["group"] == "SE组"
    assert out[1]["group"] == ri.UNGROUPED_GROUP


def test_no_groups_configured_means_no_grouping(cfg, ri):
    """一个小组都没配＝不做归组，也就没有「未归组」这回事。"""
    cfg(issue_groups=[])
    out = ri._enrich_rows(None, _rows(("A1", "王五", "部门", "定位")))
    assert len(out) == 1
    assert out[0].get("group", "") != ri.UNGROUPED_GROUP


# ── ② 另外两道过滤没被顺手改掉 ──────────────────────────────────────────────

def test_department_filter_still_drops(cfg, ri):
    """部门答的是"这单归不归我们管"——答否就该出统计，这一条不变。"""
    cfg(issue_stat_departments=["量检测软件部"],
        issue_groups=[{"name": "SE组", "members": "张三"}])
    out = ri._enrich_rows(None, _rows(
        ("A1", "张三", "量检测软件部", "定位"),
        ("A2", "王五", "别的产品线", "定位"),
    ))
    assert [r["issue_id"] for r in out] == ["A1"]


def test_closed_status_still_dropped(cfg, ri):
    cfg(issue_groups=[{"name": "SE组", "members": "张三"}])
    out = ri._enrich_rows(None, _rows(
        ("A1", "张三", "部门", "定位"),
        ("A2", "张三", "部门", "关闭"),
    ))
    assert [r["issue_id"] for r in out] == ["A1"]


# ── ③ 待办清单 ─────────────────────────────────────────────────────────────

def test_ungrouped_owners_aggregates_by_person(cfg, ri):
    cfg(issue_groups=[{"name": "SE组", "members": "张三"}])
    out = ri._enrich_rows(None, _rows(
        ("A1", "张三", "甲部门", "定位"),
        ("A2", "王五", "乙部门", "定位"),
        ("A3", "王五", "乙部门", "实施修改"),
        ("A4", "赵六", "丙部门", "定位"),
    ))
    ung = ri._ungrouped_owners(out)
    assert [(u["owner"], u["count"]) for u in ung] == [("王五", 2), ("赵六", 1)], "按条数降序"
    assert ung[0]["dept"] == "乙部门", "带上部门，好判断该往哪个组里加"
    assert all(u["owner"] != "张三" for u in ung), "已归组的人不该出现在待办里"


def test_ungrouped_endpoint_reads_latest_snapshot(client, admin_headers, tmp_path, monkeypatch, ri):
    import models
    from database import SessionLocal

    monkeypatch.setattr(ri, "_snapshot_root", lambda: tmp_path)
    project = "UNGTEST"
    db = SessionLocal()
    for date, rows in (
        ("2026-04-01", [{"issue_id": "B1", "owner": "老王", "department": "甲", "group": ri.UNGROUPED_GROUP}]),
        ("2026-04-02", [{"issue_id": "B1", "owner": "老王", "department": "甲", "group": ri.UNGROUPED_GROUP},
                        {"issue_id": "B2", "owner": "小李", "department": "乙", "group": ri.UNGROUPED_GROUP},
                        {"issue_id": "B3", "owner": "张三", "department": "甲", "group": "SE组"}]),
    ):
        rel = f"{project}/{date}.json"
        fp = tmp_path / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        db.add(models.IssueSnapshot(project=project, snapshot_date=date,
                                    total=len(rows), data_file=rel, source="api"))
    db.commit()
    db.close()

    d = client.get("/api/issues/ungrouped", params={"project": project},
                   headers=admin_headers).json()
    assert d["date"] == "2026-04-02", "默认取最新一次快照"
    assert d["count"] == 2 and d["issues"] == 2
    assert {r["owner"] for r in d["rows"]} == {"老王", "小李"}


def test_ungrouped_endpoint_no_snapshot_is_empty_not_error(client, admin_headers):
    r = client.get("/api/issues/ungrouped", params={"project": "NOSUCHPROJ"}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["rows"] == []


# ── ④ 真正要防的回归：转手不再变成假「解决」 ────────────────────────────────

def test_transfer_to_unlisted_owner_is_not_resolved(client, admin_headers, tmp_path, monkeypatch, cfg, ri):
    """同一单第二天转给名单外的人：它仍在快照里，所以差分里不能出现「解决」。"""
    import models
    from database import SessionLocal

    monkeypatch.setattr(ri, "_snapshot_root", lambda: tmp_path)
    cfg(issue_groups=[{"name": "SE组", "members": "张三"}])
    project = "XFERTEST"

    day1 = ri._enrich_rows(None, _rows(("C1", "张三", "部门", "定位")))
    day2 = ri._enrich_rows(None, _rows(("C1", "王五", "部门", "实施修改")))   # 转给名单外的人
    assert len(day2) == 1, "前提：转手之后这一单还在"

    db = SessionLocal()
    for date, rows in (("2026-05-01", day1), ("2026-05-02", day2)):
        rel = f"{project}/{date}.json"
        fp = tmp_path / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        db.add(models.IssueSnapshot(project=project, snapshot_date=date,
                                    total=len(rows), data_file=rel, source="api"))
    db.commit()
    db.close()

    d = client.get("/api/issues/snapshot-flow", params={"project": project},
                   headers=admin_headers).json()["by_snapshot"]
    assert d["dates"] == ["2026-05-02"]
    assert d["resolved"] == [0], "转手不是解决"
    assert d["created"] == [0]


# ── ⑤ 归组的模糊匹配不许把一个更长的名字从中间切开 ──────────────────────────

@pytest.mark.parametrize("owner, expected", [
    ("张伟", "SE组"),                     # 名单里就是这么写的
    ("张伟 00123456", "SE组"),            # DTS 常见：姓名 + 工号
    ("张伟(zhangwei)", "SE组"),           # 姓名 + 英文名
    ("张伟明", ""),                       # **不是张伟**：名单里没有他，就该报未归组
    ("李伟", ""),
])
def test_group_match_does_not_cut_a_longer_name(ri, owner, expected):
    """朴素子串包含会让「张伟」认走「张伟明」的单——名单里没有张伟明，他的单却被
    安安静静记到张伟所在的组，组级负载和交叉表都偏一点，而两边看着都对。
    """
    assert ri._match_group(owner, [("SE组", ["张伟"])]) == expected


def test_longer_name_still_matches_its_own_group(ri):
    """两个名字互为前缀且各在一个组：各归各的，与名单顺序无关。"""
    groups = [("SE组", ["张伟"]), ("测试组", ["张伟明"])]
    assert ri._match_group("张伟明", groups) == "测试组"
    assert ri._match_group("张伟", groups) == "SE组"
    assert ri._match_group("张伟明", list(reversed(groups))) == "测试组"


def test_group_match_is_still_two_way_and_case_insensitive(ri):
    """名单可能写得比 DTS 长（带备注），也可能更短（DTS 带工号）——两个方向都要认。"""
    assert ri._match_group("张伟", [("SE组", ["张伟(SE)"])]) == "SE组"
    assert ri._match_group("ZhangWei 张伟", [("SE组", ["zhangwei"])]) == "SE组"


def test_latin_account_is_not_cut_either(ri):
    """西文同理：zhangwei 不能认走 zhangwei01——那多半是另一个人的账号。"""
    assert ri._match_group("zhangwei01", [("SE组", ["zhangwei"])]) == ""
    assert ri._match_group("zhangwei", [("SE组", ["zhangwei"])]) == "SE组"


def test_near_miss_owner_shows_up_in_the_todo_list(cfg, ri):
    """认不上就归「未归组」并进待办——名单不全是配置问题，不该表现成数据问题。"""
    cfg(issue_groups=[{"name": "SE组", "members": "张伟"}])
    out = ri._enrich_rows(None, _rows(("D1", "张伟明", "量检测软件部", "定位")))
    assert len(out) == 1, "认不上也不能丢行（丢了就是下一次差分里的一笔假解决）"
    assert out[0]["group"] == ri.UNGROUPED_GROUP
    assert [u["owner"] for u in ri._ungrouped_owners(out)] == ["张伟明"]
