"""A 图（时间轴嵌套框图）：一根真日期横轴 + 大框套中框套小框。

盯住的是几条**坏了不报错、只是图不对**的事：
1. 嵌套是真的——父框纵向罩住它所有子孙行，子框画在父框**里面**；
2. 没填计划日期的行**照样占一行**（只是图区留白），且条数如实报出来；
3. 延期只数叶子（父子都数会把 4 条报成 8 条），图上是红框、天数在左栏；
4. 按整段阶段截断、折了几条挂在上级名字后面。

**模块顶层不 import 应用模块**（见 CLAUDE.md）：conftest 的 client 夹具靠 os.chdir
把 sqlite 指到临时目录，收集阶段的顶层 import 会赶在 chdir 之前连上仓库里的 app.db。
"""
from datetime import date, timedelta

import pytest


@pytest.fixture(scope="module")
def special_id(client, admin_headers):
    r = client.post("/api/specials", json={"name": "A 图测试专项"}, headers=admin_headers)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _add(client, headers, pid, parent_id=None, **kw):
    body = {"parent_id": parent_id, "name": kw.pop("name", "行")}
    body.update(kw)
    r = client.post(f"/api/wbs/plans/{pid}/items", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture()
def tree(client, admin_headers, special_id):
    """三层 + 日期：一条已过期没做完、一条按期、一条没填完成日、一条已变更。"""
    today = date.today()
    past = (today - timedelta(days=9)).isoformat()
    soon = (today + timedelta(days=20)).isoformat()
    r = client.post("/api/wbs/plans",
                    json={"kind": "special", "special_id": special_id, "name": "A 图 WBS"},
                    headers=admin_headers)
    pid = r.json()["id"]

    def sid(detail, name):
        return [x for x in detail["items"] if x["name"] == name][0]["id"]

    d = _add(client, admin_headers, pid, name="阶段一")
    s1 = sid(d, "阶段一")
    d = _add(client, admin_headers, pid, s1, name="中间层")
    mid = sid(d, "中间层")
    _add(client, admin_headers, pid, mid, name="拖了的活", status="进行中", man_days=3,
         progress_pct=40, planned_start=past, planned_end=past)
    _add(client, admin_headers, pid, mid, name="按期的活", status="未开始", man_days=2,
         planned_start=soon, planned_end=soon)
    d = _add(client, admin_headers, pid, s1, name="没填日期的活", status="未开始", man_days=1)
    d = _add(client, admin_headers, pid, name="阶段二")
    s2 = sid(d, "阶段二")
    _add(client, admin_headers, pid, s2, name="阶段二的活", status="未开始", man_days=1,
         planned_start=soon, planned_end=soon)
    _add(client, admin_headers, pid, s1, name="不做了的活", status="已变更", man_days=4)
    return pid


def _spec(client, headers, pid, **q):
    r = client.get(f"/api/wbs/plans/{pid}/timeline", headers=headers, params=q)
    assert r.status_code == 200, r.text
    return r.json()


def _row(spec, code):
    return [r for r in spec["rows"] if r["code"] == code][0]


def _box(spec, code):
    got = [b for b in spec["boxes"] if b["code"] == code]
    return got[0] if got else None


# ─── 嵌套：这就是这张图和一根甘特条的区别 ───────────────────────────────────
def test_parent_box_wraps_every_descendant_row(client, admin_headers, tree):
    """大框纵向罩住自己那一行 + 底下所有子孙行，子框在它**里面**。

    盯的是几何关系而不是具体像素：留白一调这条仍然成立，而"最后一个子框戳出
    父框半截"（上下用同一个留白就会这样）立刻红——而那种图看着还挺正常。
    """
    spec = _spec(client, admin_headers, tree)
    big, mid, leaf = _box(spec, "1"), _box(spec, "1.1"), _box(spec, "1.1.1")
    assert big and mid and leaf
    for inner, outer in ((mid, big), (leaf, mid), (leaf, big)):
        assert outer["y"] <= inner["y"], (inner["code"], outer["code"])
        assert inner["y"] + inner["h"] <= outer["y"] + outer["h"] + 0.01
        assert outer["x"] <= inner["x"] + 0.01
        assert inner["x"] + inner["w"] <= outer["x"] + outer["w"] + 0.01


def test_one_row_per_node_and_rows_never_overlap(client, admin_headers, tree):
    """一行一个节点，行与行首尾相接——行错开了，嵌套就看不出是"罩住"了。"""
    spec = _spec(client, admin_headers, tree)
    assert spec["row_count"] == 8          # 2 个阶段 + 中间层 + 5 个叶子
    rows = sorted(spec["rows"], key=lambda r: r["row_top"])
    for a, b in zip(rows, rows[1:]):
        assert abs(a["row_top"] + a["row_h"] - b["row_top"]) < 0.01


def test_deeper_rows_get_smaller_type(client, admin_headers, tree):
    """字号阶梯走 enums.wbs_level_font()，三层必须真的分得出来。"""
    spec = _spec(client, admin_headers, tree)
    px = {r["depth"]: r["font_px"] for r in spec["rows"]}
    assert px[1] > px[2] > px[3]


# ─── 排不上时间轴的行：留着，并如实报 ───────────────────────────────────────
def test_undated_rows_keep_a_box_and_get_counted(client, admin_headers, tree):
    """没填日期的任务也必须有框承载内容，不能因取消左栏而从 A 图消失。"""
    spec = _spec(client, admin_headers, tree)
    assert _box(spec, "1.2") is not None
    assert _row(spec, "1.2")["meta"] == "未填完成日"
    assert spec["undated"] == 1
    assert "1 行没填计划完成日" in " ".join(spec["note_lines"])


def test_changed_row_is_drawn_grey_and_not_called_undated(client, admin_headers, tree):
    """「已变更」是"不做了"，不是"没填日期"——混成一档会让那个待补录的数虚高。"""
    spec = _spec(client, admin_headers, tree)
    assert _row(spec, "1.3")["meta"] == "已变更"
    assert spec["undated"] == 1            # 只算 1.2 那一条


# ─── 延期：红框与框内天数，只数叶子 ─────────────────────────────────────────
def test_overdue_leaf_is_outlined_red_and_parents_follow(client, admin_headers, tree):
    """延期**改边框不改底色**：底色被状态占着，而"进行中"和"已延期"要同时看到。"""
    import wbs_diagram

    spec = _spec(client, admin_headers, tree)
    leaf = _box(spec, "1.1.1")
    assert leaf["stroke"] == wbs_diagram.LATE_STROKE
    assert leaf["fill"] != wbs_diagram.LATE_STROKE
    assert _box(spec, "1.1")["stroke"] == wbs_diagram.LATE_STROKE   # 父框跟着红
    assert _box(spec, "1")["stroke"] == wbs_diagram.LATE_STROKE


def test_overdue_count_only_counts_leaves(client, admin_headers, tree):
    """父子都数会把 1 条报成 3 条，而那个数看着还挺合理，没人会去核。"""
    spec = _spec(client, admin_headers, tree)
    assert spec["overdue"] == 1


def test_overdue_days_go_inside_the_box(client, admin_headers, tree):
    """取消左栏后，延期信息和任务名称都直接放在对应任务框中。"""
    spec = _spec(client, admin_headers, tree)
    assert _row(spec, "1.1.1")["meta"].startswith("延期 ")
    assert _box(spec, "1.1.1")["meta"].startswith("延期 ")


def test_box_contains_task_text_and_dependency_arrow(client, admin_headers, tree):
    detail = client.get(f"/api/wbs/plans/{tree}", headers=admin_headers).json()
    before = next(x for x in detail["items"] if x["name"] == "拖了的活")
    after = next(x for x in detail["items"] if x["name"] == "按期的活")
    r = client.put(f"/api/wbs/items/{after['id']}",
                   json={"predecessor_ids": [before["id"]], "version": after["version"]},
                   headers=admin_headers)
    assert r.status_code == 200, r.text
    spec = _spec(client, admin_headers, tree)
    target = _box(spec, "1.1.2")
    assert "按期的活" in target["label"] and target["label_x"] >= target["x"]
    assert any(a["from"] == "1.1.1" and a["to"] == "1.1.2" for a in spec["arrows"])


# ─── 裁剪与截断 ─────────────────────────────────────────────────────────────
def test_max_depth_folds_and_says_where(client, admin_headers, tree):
    """只画到第 N 层时，折了几条要报总数，**还要说清折在谁身上**（名字后的 +N）。"""
    spec = _spec(client, admin_headers, tree, max_depth=2)
    assert spec["row_count"] == 6          # 1 / 1.1 / 1.2 / 1.3 / 2 / 2.1
    assert spec["folded"] == 2
    assert _row(spec, "1.1")["fold"] == "+2"
    assert "另有 2 行折在上级框里" in " ".join(spec["note_lines"])


def test_totals_survive_the_clip(client, admin_headers, tree):
    """砍的是"画出来的层级"、不是"算进去的活"：父框的横向仍是整棵子树的汇总。"""
    full = _spec(client, admin_headers, tree)
    clipped = _spec(client, admin_headers, tree, max_depth=2)
    assert _box(full, "1")["x"] == _box(clipped, "1")["x"]
    assert _box(full, "1")["w"] == _box(clipped, "1")["w"]


def test_truncation_cuts_whole_stages(client):
    """截断按「整段阶段」截：从中间切开的话，图上那一段看着就是"这阶段就这么多活"。"""
    import wbs_diagram

    stages = [[{"depth": 1}] + [{"depth": 2}] * 4 for _ in range(3)]
    kept, skipped = wbs_diagram.cap_stages(stages, 7)
    assert [len(s) for s in kept] == [5]      # 第 2 段整段丢掉，不切一半
    assert skipped == 10


def test_orphan_rows_are_reported_not_dropped(client):
    """depth>1 却没有第 1 层的行画不出来，但**要计进 skipped**：
    直接丢掉会让人以为数据没了。"""
    import wbs_diagram

    stages, orphans = wbs_diagram.split_stages([{"depth": 2}, {"depth": 1}, {"depth": 2}])
    assert orphans == 1 and [len(s) for s in stages] == [2]


# ─── 轴与说明 ───────────────────────────────────────────────────────────────
def test_axis_labels_the_month_it_starts_in(client, admin_headers, tree):
    """轴的起点落在月中时，第一格也要有刻度——不然那一截看不出是几月。"""
    spec = _spec(client, admin_headers, tree)
    assert spec["ticks"], "一根刻度都没有"
    assert abs(spec["ticks"][0]["x"] - spec["plot_x"]) < 1.0
    assert "年" in spec["ticks"][0]["label"]


def test_today_line_sits_inside_the_plot(client, admin_headers, tree):
    """今天那根红线必须落在轴内：跑到左栏上去的话，看图的人会以为全都逾期了。"""
    spec = _spec(client, admin_headers, tree)
    assert spec["plot_x"] <= spec["today"]["x"] <= spec["plot_x"] + spec["plot_w"]


def test_note_says_which_wbs_and_as_of_when(client, admin_headers, tree):
    """这张图**不画标题**（现场要求），但导出的 PNG 被单独截走时得找得回出处。"""
    spec = _spec(client, admin_headers, tree)
    head = spec["note_lines"][0]
    assert "A 图 WBS" in head and date.today().isoformat() in head


def test_legend_only_lists_status_words_on_the_chart(client, admin_headers, tree):
    """图例只列真出现过的状态：全档铺出来会让人以为自己漏看了绿的那几个。"""
    spec = _spec(client, admin_headers, tree)
    labels = [x["label"] for x in spec["legend"]]
    assert "已完成" not in labels            # 这份里一条都没有
    assert any(x.startswith("进行中") for x in labels)
    assert any("已延期" in x for x in labels)


def test_empty_plan_draws_nothing_but_still_answers(client, admin_headers, special_id):
    """空 WBS 不是错：回一份空版面，由页面说明白，别 500。"""
    r = client.post("/api/wbs/plans",
                    json={"kind": "special", "special_id": special_id, "name": "空 A 图"},
                    headers=admin_headers)
    spec = _spec(client, admin_headers, r.json()["id"])
    assert spec["row_count"] == 0 and spec["box_count"] == 0
    assert spec["dated"] is False
    assert "一行计划日期都没填" in " ".join(spec["note_lines"])


def test_long_names_are_clipped_with_an_ellipsis(client):
    """左栏只有一行，放不下要**看得出来**被截了——悄悄截掉的话两行长得一模一样。"""
    import wbs_diagram

    out = wbs_diagram.clip_text("一二三四五六七八九十", 12, 40)
    assert out.endswith("…") and len(out) < 11
    assert wbs_diagram.clip_text("短", 12, 40) == "短"
