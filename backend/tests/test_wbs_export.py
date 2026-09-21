"""WBS 的两个导出出口：Excel 表 与 调试框图。

盯住的是几条「看不出报错」的事：导出的表里分组行和叶子行混着，字号分不分层、
排除了几条有没有写出来、分组行的状态是不是被随手填了一个值；框图那边则是
版面只有一份（页面与 Excel 必须是同一个 spec 算出来的）。

**不在模块顶层 import 应用模块**（见 CLAUDE.md）：`conftest.py` 的 client 夹具靠
os.chdir 把 sqlite 指到临时目录，收集阶段的顶层 import 会赶在 chdir 之前把引擎
连上仓库里的 backend/app.db。
"""
import io

import pytest


@pytest.fixture(scope="module")
def special_id(client, admin_headers):
    r = client.post("/api/specials", json={"name": "导出测试专项"}, headers=admin_headers)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


@pytest.fixture()
def plan(client, admin_headers, special_id):
    """一份两层的 WBS：两个阶段，各挂两个叶子，其中一个标「已变更」。"""
    r = client.post("/api/wbs/plans",
                    json={"kind": "special", "special_id": special_id, "name": "导出用 WBS"},
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    for stage in ("调试准备", "功能验证"):
        d = client.post(f"/api/wbs/plans/{pid}/items", json={"name": stage},
                        headers=admin_headers).json()
        sid = [x for x in d["items"] if x["name"] == stage][0]["id"]
        for j, (nm, st, days) in enumerate((("子任务甲", "进行中", 3.0),
                                            ("子任务乙", "已变更", 5.0))):
            client.post(f"/api/wbs/plans/{pid}/items",
                        json={"parent_id": sid, "name": f"{stage}-{nm}",
                              "status": st, "man_days": days, "progress_pct": 40 * (j + 1)},
                        headers=admin_headers)
    return pid


# ─── 调试框图的版面 ─────────────────────────────────────────────────────────
def test_diagram_columns_are_the_top_level_rows(client, admin_headers, plan):
    """第 1 层＝一列。列数和阶段数对不上的话，图上就少了一整段活。"""
    spec = client.get(f"/api/wbs/plans/{plan}/diagram", headers=admin_headers).json()
    assert spec["stage_count"] == 2
    assert spec["box_count"] == 6            # 2 个阶段 + 4 个叶子
    # 相邻阶段之间一根箭头：n 个阶段 n-1 根
    assert len(spec["arrows"]) == 1


def test_diagram_font_size_steps_down_with_depth(client, admin_headers, plan):
    """各级字号必须真的分档——这正是「一目了然」要的那件事。

    盯的是「第 2 层比第 1 层小」，不是具体几号：阶梯改了这条仍然成立，
    而两级一样大（谁不小心把 wbs_level_font 改成常数）立刻红。
    """
    spec = client.get(f"/api/wbs/plans/{plan}/diagram", headers=admin_headers).json()
    by_depth = {}
    for b in spec["boxes"]:
        by_depth.setdefault(b["depth"], set()).add(b["font_px"])
    assert len(by_depth[1]) == 1 and len(by_depth[2]) == 1
    assert next(iter(by_depth[1])) > next(iter(by_depth[2]))


def test_diagram_keeps_changed_rows_and_greys_them(client, admin_headers, plan):
    """「已变更」的行照画、上灰底。剔掉的话，图上看不出这件事为什么没做。"""
    import brand

    spec = client.get(f"/api/wbs/plans/{plan}/diagram", headers=admin_headers).json()
    grey = [b for b in spec["boxes"] if b["fill"] == "#" + brand.STATUS_FILLS["已变更"]]
    assert len(grey) == 2
    assert {"label": "已变更", "fill": "#" + brand.STATUS_FILLS["已变更"]} in spec["legend"]


def test_diagram_legend_only_lists_status_words_actually_on_the_chart(client, admin_headers, plan):
    """图例只列图上真出现过的状态：全档铺出来会让人以为自己漏看了绿的那几个。"""
    spec = client.get(f"/api/wbs/plans/{plan}/diagram", headers=admin_headers).json()
    labels = {x["label"] for x in spec["legend"]}
    assert labels == {"进行中", "已变更"}


def test_diagram_reports_what_it_could_not_draw():
    """画不下的条数要如实报出来（同 nodeClipped / unassigned / match_rate）。"""
    import wbs_diagram

    rows = []
    for i in range(1, 60):
        rows.append({"code": str(i), "name": f"阶段{i}", "depth": 1, "is_leaf": False,
                     "leaf_count": 3, "days": 3.0, "pct": 0, "status": "", "owner": ""})
        for j in range(1, 6):
            rows.append({"code": f"{i}.{j}", "name": f"任务{j}", "depth": 2, "is_leaf": True,
                         "leaf_count": 1, "days": 1.0, "pct": 0, "status": "未开始", "owner": ""})
    spec = wbs_diagram.build_diagram(rows, "大树")
    assert spec["box_count"] < len(rows)
    assert spec["skipped"] == len(rows) - spec["box_count"]
    # 截断按**整段阶段**截：从一个阶段中间切开的话，图上那一列看着就是"这个阶段
    # 就这么多活"，而它其实还有一半没画
    codes = {b["code"].split(".")[0] for b in spec["boxes"]}
    for c in codes:
        assert sum(1 for b in spec["boxes"] if b["code"].split(".")[0] == c) == 6


def test_diagram_wraps_long_names_inside_the_box():
    """名字长到一行装不下要折行，不能戳出盒子——盒子看着还规规矩矩，字却在外面。"""
    import wbs_diagram

    long_name = "一个特别特别长的调试任务名字长到一行根本放不下必须折行才行"
    spec = wbs_diagram.build_diagram(
        [{"code": "1", "name": long_name, "depth": 1, "is_leaf": True,
          "leaf_count": 1, "days": 0, "pct": 0, "status": "", "owner": ""}], "折行")
    box = spec["boxes"][0]
    assert len(box["lines"]) > 1
    inner = box["w"] - 2 * wbs_diagram.BOX_PAD_X
    for ln in box["lines"]:
        assert wbs_diagram._text_w(ln, box["font_px"]) <= inner + 0.01


# ─── Excel 导出 ────────────────────────────────────────────────────────────
def _load(client, headers, plan_id):
    import openpyxl

    r = client.get(f"/api/wbs/plans/{plan_id}/export.xlsx", headers=headers)
    assert r.status_code == 200, r.text
    return openpyxl.load_workbook(io.BytesIO(r.content))


def test_export_has_every_row_including_the_changed_ones(client, admin_headers, plan):
    """导出**不剔**「已变更」的行：那是交付记录，也是"为什么没做"的唯一线索。"""
    wb = _load(client, admin_headers, plan)
    ws = wb["WBS"]
    names = [ws.cell(r, 2).value for r in range(2, 8)]
    assert len([n for n in names if n]) == 6
    assert any("子任务乙" in (n or "") for n in names)


def test_export_font_size_steps_down_with_depth(client, admin_headers, plan):
    """表里的字号也按层级分档，且与页面同一份阶梯（enums.wbs_level_font）。"""
    import enums

    wb = _load(client, admin_headers, plan)
    ws = wb["WBS"]
    sizes = {}
    for r in range(2, 8):
        code = str(ws.cell(r, 1).value or "")
        depth = code.count(".") + 1
        sizes.setdefault(depth, set()).add(ws.cell(r, 2).font.size)
    assert sizes[1] == {enums.wbs_level_font(1)["pt"]}
    assert sizes[2] == {enums.wbs_level_font(2)["pt"]}
    assert next(iter(sizes[1])) > next(iter(sizes[2]))


def test_export_leaves_group_status_blank(client, admin_headers, plan):
    """分组行的状态**留空**。随手填个「进行中」会被当成有人标过——
    而状态是叶子填的，分组没有状态（同「未指定领域」那行的采集问题单留空）。"""
    wb = _load(client, admin_headers, plan)
    ws = wb["WBS"]
    for r in range(2, 8):
        is_group = "分组" in str(ws.cell(r, 3).value or "")
        if is_group:
            assert not (ws.cell(r, 10).value or "")
        else:
            assert ws.cell(r, 10).value


def test_export_says_how_many_rows_it_excluded(client, admin_headers, plan):
    """只筛不报的数字比没有更糟：排除了几条、多少人天要写在表尾。"""
    wb = _load(client, admin_headers, plan)
    ws = wb["WBS"]
    tail = "\n".join(str(ws.cell(r, 1).value or "") for r in range(8, ws.max_row + 1))
    assert "已排除 2 条" in tail
    assert "10" in tail            # 两条各 5 人天
    assert "仍然留在表里" in tail


def test_export_carries_the_diagram_sheet(client, admin_headers, plan):
    """第 2 页是框图，且说明与版面是同一份 spec 算出来的。"""
    wb = _load(client, admin_headers, plan)
    assert "调试框图" in wb.sheetnames
    ws2 = wb["调试框图"]
    head = "\n".join(str(ws2.cell(r, 1).value or "") for r in range(1, 5))
    assert "调试框图" in head
    assert "2 个阶段" in head and "6 个方框" in head


def test_empty_plan_exports_without_blaming_the_font(client, admin_headers, special_id):
    """空 WBS 与「这台机器没中文字体」是两回事，混成一句会让人白装一遍字体。"""
    r = client.post("/api/wbs/plans",
                    json={"kind": "special", "special_id": special_id, "name": "空 WBS"},
                    headers=admin_headers)
    pid = r.json()["id"]
    wb = _load(client, admin_headers, pid)
    ws2 = wb["调试框图"]
    text = "\n".join(str(ws2.cell(i, 1).value or "") for i in range(1, 8))
    assert "还没有任何工作包" in text
    assert "字体" not in text
