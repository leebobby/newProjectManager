"""WBS 调试框图：**只算版面，不画图**。

一份 WBS 拆出来的树，横着扫表格能看清每一行填了什么，却看不出"这件事分几步走、
每一步底下挂着哪些活、哪一步已经拖了"。框图答的就是这几个问题：
**第 1 层＝调试阶段，从左到右一列一列排开；从第 2 层开始，父任务框包住子任务框**。

每个方框只显示任务名称和责任人；状态底色、延期红框、阶段分列与层级字号保持原样。
图顶部是一根按月的全局日期参考轴，不按日期移动或拉长任务框，不作为精确排程。
默认跨度至少六个月，允许指定参考月份范围；裁剪显示层级不改变参考范围。

这个模块**只吐一份版面描述**（每个盒子的 x/y/w/h、已经折好行的文字、颜色），
两个出口各自照着画：

    页面   frontend/src/components/WbsDiagram.vue   → SVG
    Excel  routers/wbs.py 的 export.xlsx            → PIL 画成 PNG 贴进第二个工作表

**版面只有这一份实现**。两边各排一次的话，同一份 WBS 在页面上是 4 列、
在导出的图里是 5 列，或者同一个盒子里的文字折行位置不一样——而两边单独看都挺正常，
没人会当 bug 报上来（同专项总览的 PPT 导出「直接复用 overview() 的返回值」）。

配套的几条口径：

- **字号阶梯来自 `enums.wbs_level_font()`**，与页面表格、Excel 表格共用一份。
  在这儿另写一套 SIZE 常量的话，框图里第 2 层比第 3 层大一号、表格里一样大。
- **折行按显示宽度估，且宁可估宽**（`text_w`：全角 1.0 em、西文 0.55 em，同
  `pptx_utils` 的行高估算）。估窄了会算出"这一行装得下"，画出来的字戳出盒子。
  估的是宽度而不是拿真字体量，是因为**两个出口必须折在同一个位置**：PIL 那边有字体、
  浏览器那边没有，只有算出来的行数是两边都认的。
- **「已变更 / 不涉及」的行照画，上灰底**（同导出不剔这些行的规矩）：那是计划的一部分，
  也是别人回头看"为什么没做"的唯一线索。
- **画不下的行要如实报出来**（`skipped`）。树可以拆到几百行，全画出来每个盒子细得
  看不见；截断可以，但要说清楚少了几条（同 `nodeClipped` / `unassigned` / `match_rate`）。
- 阶段多到一行摆不下时**折到下一段**（`wrapped`），段与段之间不画箭头——
  跨段画一根从最右拉回最左的线，看着像"最后一步又回到第一步"。

甘特图那边额外的几条（`build_gantt`）：

- **延期与否由调用方算好传进来**（`overdue` / `overdue_days`），这个模块不判。
  判定只有一份实现：`routers/wbs.py` 的 `_is_overdue()`，页面上那条「待补录」提示
  （`_issues`）走的是同一个函数。两处各写一份的表现是**表格里写着延期、图上不红**，
  而两边单独看都对。
- **排不上时间轴的行要如实报**（`undated`）：计划完成日是选填的，没填就说不出"哪天该完"。
  猜一个日期摆上去比不画更糟——那条会在图上稳稳当当地显示成"按期"。
  **只填了完成日、没填开始日**的画成菱形里程碑，不是硬凑一根条。
- **今天那条线一定要在画幅内**：横轴范围取「计划区间 ∪ 今天」。掐掉今天的话，
  一份整体拖了两个月的计划看着仍然规规矩矩——而那正是最该一眼看到的事。
- **父行画细的汇总条**（子行的最早开始 → 最晚完成），与表格里那个汇总同一个口径。
"""
from datetime import date, timedelta
from math import floor
from typing import List, Optional, Tuple

import brand
import enums

# ─── 版面常量 ──────────────────────────────────────────────────────────────
PAD = 24                 # 画布四周留白
COL_W = 268              # 一个调试阶段占一列，列宽固定——按内容变宽的话，
                         # 名字长的那一列会把别人挤成窄条，而那一列并不更重要
COL_GAP = 52             # 列间距，箭头画在这段空里
BOX_GAP = 8
INDENT = 14              # 每深一层缩进多少
BOX_PAD_X = 10
BOX_PAD_Y = 7
META_PX = 10.5           # 盒子里第二行的责任人，不属于层级阶梯
TITLE_PX = 17.0          # 图头：这两个也不属于层级阶梯，它们不是任务
SUB_PX = 11.5
LEGEND_PX = 11.0
LINE_RATIO = 1.42
MAX_BAND_W = 1560        # 一段最宽多少；超了就折段
MAX_BOXES = 140          # 画不下的如实报，见模块说明
TITLE_MAX_LINES = 3      # 单个盒子里标题最多折几行，多的省略号收尾

STROKE = "#" + brand.BORDER
STAGE_FILL = "#" + brand.HEADER_BG
LEAF_FILL = "#FFFFFF"
ARROW = "#9AA4B2"
LATE_STROKE = "#F56C6C"   # 延期：改**边框**不改底色，底色已经被状态占了
LATE_TEXT = "#F56C6C"
DATE_TEXT = "#8A94A6"     # 没延期时日期那行的颜色：比正文淡，不跟标题抢
BAR_TRACK = "#EDF0F5"     # 盒子底部那条完成度细条
BAR_FILL = "#5B8FF9"
BAR_H = 3.0


def text_w(s: str, size: float) -> float:
    """显示宽度估算：全角 1.0 em、其余 0.55 em。**宁可估宽**，见模块说明。

    两张图（本模块与 [wbs_timeline.py](wbs_timeline.py)）共用这一份估算，
    前端那份在 `components/WbsDiagram.vue`。各写一份的表现是页面上的图例
    与导出的 PNG 错开一段，而两边单独看都正常。
    """
    w = 0.0
    for ch in str(s or ""):
        w += size if ord(ch) > 0x2E7F else size * 0.55
    return w


def _wrap(s: str, size: float, max_w: float, max_lines: int) -> List[str]:
    """按显示宽度折行。西文连成的一串不从中间拆（同 `xlsx_utils._wrap_by_width`）。"""
    text = " ".join(str(s or "").split())
    if not text:
        return [""]
    toks: List[str] = []
    cur = ""
    for ch in text:
        latin = ch.isascii() and (ch.isalnum() or ch in "._/'+-")
        if latin:
            cur += ch
        else:
            if cur:
                toks.append(cur)
                cur = ""
            toks.append(ch)
    if cur:
        toks.append(cur)

    lines: List[str] = []
    line = ""
    for tok in toks:
        cand = line + tok
        if line and text_w(cand, size) > max_w:
            lines.append(line)
            line = "" if tok == " " else tok
        else:
            line = cand
        # 单个词元本身就比一行宽（一长串型号/路径）时才从中间劈开：
        # 不劈的话它会直接戳出盒子，而盒子看着还是规规矩矩的
        while text_w(line, size) > max_w and len(line) > 1:
            k = len(line) - 1
            while k > 1 and text_w(line[:k], size) > max_w:
                k -= 1
            lines.append(line[:k])
            line = line[k:]
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:-1] + "…" if len(lines[-1]) > 1 else "…"
    return lines


def clip_text(s: str, size: float, max_w: float) -> str:
    """单行截断，收尾加省略号。折行放不下的场合（A 图的左栏只有一行）用它。

    截了要看得出来——省略号就是那个记号；**悄悄截掉**的表现是两个不同的工作包
    在图上长得一模一样，而两行单独看都正常。
    """
    text = " ".join(str(s or "").split())
    if max_w <= 0:
        return ""
    if text_w(text, size) <= max_w:
        return text
    out = ""
    for ch in text:
        if text_w(out + ch + "…", size) > max_w:
            break
        out += ch
    return (out + "…") if out else "…"


def split_stages(rows: List[dict]) -> Tuple[List[List[dict]], int]:
    """按第 1 层把拍平的行切成若干「阶段」。

    返回 (阶段列表, 孤儿数)。孤儿＝depth>1 却还没出现过第 1 层的行，那是树坏了，
    画不出来也要**计入 skipped**：直接丢掉会让人以为数据没了。
    两张图共用这一份切法，各写一份的表现是同一份 WBS 在两张图上截断的位置不一样。
    """
    stages: List[List[dict]] = []
    orphans = 0
    for r in rows:
        if int(r.get("depth") or 1) == 1:
            stages.append([r])
        elif stages:
            stages[-1].append(r)
        else:
            orphans += 1
    return stages, orphans


def cap_stages(stages: List[List[dict]], max_rows: int) -> Tuple[List[List[dict]], int]:
    """行数超了就整段丢，返回 (保留的段, 丢掉的行数)。

    **截断按「整段阶段」截**：从一个阶段中间切开的话，图上那一段看着就是
    "这个阶段就这么多活"，而它其实还有一半没画（同 A 图）。
    """
    kept: List[List[dict]] = []
    used = skipped = 0
    for st in stages:
        if used + len(st) > max_rows and kept:
            skipped += len(st)
            continue
        kept.append(st)
        used += len(st)
    return kept, skipped


def _md(v) -> str:
    """日期只留「月-日」：框图的盒子只有 250 来点宽，塞进两个完整年月日就换行了，
    而同一份 WBS 基本都在同一年里。年份在图的副标题与表格里都有。"""
    t = str(v or "")[:10]
    return t[5:] if len(t) == 10 else ""


def _date_text(row: dict) -> str:
    """盒子第三行：哪天该完、拖了没有。

    **没填计划完成日的如实写出来**，不留空：留空会被读成"没有交期要求"，
    而那批行正是最该被追着去补的（同 `overdue_unknown`）。
    「已变更 / 不涉及」的行不写这一行——那条本轮就不做了，交期无从谈起。
    """
    if (row.get("status") or "").strip() in enums.WBS_UNCOUNTED_STATUSES:
        return ""
    s0, s1 = _md(row.get("start")), _md(row.get("end"))
    if not s1:
        return "未填计划完成日"
    head = ("汇总 " if not row.get("is_leaf") else "计划 ")
    body = f"{s0} → {s1}" if s0 else f"完成 {s1}"
    late = int(row.get("overdue_days") or 0)
    return f"{head}{body}" + (f" · 已延期 {late} 天" if late else "")


def _fmt_num(v) -> str:
    """人天：整数就不拖一个 .0（"3.0 人天"读着像精确到小数的估算）。"""
    f = float(v or 0)
    return str(int(f)) if f == int(f) else f"{f:g}"


def _meta_text(row: dict) -> str:
    """盒子第二行的小字。**父行明写「汇总」**——不标的话，那个人天看着像它自己填的，
    而它其实是底下叶子加出来的（同表格里那个「汇总」角标）。"""
    parts: List[str] = []
    if row.get("owner"):
        parts.append(str(row["owner"]))
    days = float(row.get("days") or 0)
    if days:
        parts.append(("汇总 " if not row.get("is_leaf") else "") + _fmt_num(days) + " 人天")
    if row.get("pct"):
        parts.append(f"{int(row['pct'])}%")
    if row.get("is_leaf"):
        st = (row.get("status") or "").strip()
        if st:
            parts.append(st)
    elif row.get("leaf_count"):
        parts.append(f"{int(row['leaf_count'])} 个叶子")
    return " · ".join(parts)


def _colors(row: dict, depth: int):
    """(底色, 字色)。状态词**精确匹配**才点灯（同 `brand.status_style()`）——
    包含匹配会把「已完成三个模块联调」整格染绿，而它其实还在进行中。"""
    fill, text, _bold = brand.status_style(row.get("status") if row.get("is_leaf") else "")
    if fill:
        return "#" + fill, "#" + brand.STATUS_ON_FILL_TEXT
    if depth == 1:
        return STAGE_FILL, "#" + brand.HEADER_TEXT
    return LEAF_FILL, "#" + (text or enums.wbs_level_font(depth)["color"])


def reference_months(rows: List[dict], start: Optional[str] = None,
                     end: Optional[str] = None) -> Tuple[int, int]:
    """参考跨度来自整棵树；自定义月份必须成对给出，默认至少六个月。"""
    def number(v: str) -> int:
        import re
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}", v):
            raise ValueError("参考月份应为 YYYY-MM")
        d = date.fromisoformat(v + "-01")
        return d.year * 12 + d.month - 1

    if start is not None or end is not None:
        if start is None or end is None:
            raise ValueError("请同时指定参考开始和结束月份")
        first, last = number(start), number(end)
        if last < first:
            raise ValueError("参考结束月份不能早于开始月份")
        return first, last

    months = []
    for r in rows:
        if (r.get("status") or "").strip() in enums.WBS_UNCOUNTED_STATUSES:
            continue
        for key in ("start", "end"):
            if r.get(key):
                months.append(number(str(r[key])[:7]))
    today = date.today()
    first = min(months) if months else today.year * 12 + today.month - 1
    last = max(months) if months else first
    return first, min(9999 * 12 + 11, max(first + 5, last))


def _reference_axis(first: int, last: int, width: float, y: float) -> dict:
    """刻度按月；跨度很长时疏排刻度，所有标注仍保留年份和月份。"""
    count = last - first + 1
    capacity = max(2, int(width // 100))
    step = max(1, (count + capacity - 1) // capacity)
    ticks = []
    for offset in range(0, count, step):
        month = first + offset
        label = f"{month // 12}年{month % 12 + 1}月"
        x = PAD + offset / count * width
        label_x = min(x + 4, PAD + width - text_w(label, LEGEND_PX))
        ticks.append({"x": round(x, 1), "label_x": floor(label_x * 10) / 10,
                      "label": label})
    # 即使疏排刻度，最末月份仍明确显示，避免用户误判参考范围。
    end_label = f"{last // 12}年{last % 12 + 1}月"
    if ticks[-1]["label"] != end_label:
        label_x = PAD + width - text_w(end_label, LEGEND_PX)
        if label_x < ticks[-1]["label_x"] + text_w(ticks[-1]["label"], LEGEND_PX) + 12:
            ticks.pop()
        ticks.append({"x": round(PAD + width, 1), "label_x": floor(label_x * 10) / 10,
                      "label": end_label})
    return {"start": f"{first // 12:04d}-{first % 12 + 1:02d}",
            "end": f"{last // 12:04d}-{last % 12 + 1:02d}",
            "x1": PAD, "x2": round(PAD + width, 1), "y": round(y, 1),
            "label_y": round(y - 10, 1), "title_y": round(y - 32, 1),
            "ticks": ticks}


def build_diagram(rows: List[dict], title: str = "", subtitle: str = "",
                  reference_start: Optional[str] = None, reference_end: Optional[str] = None,
                  reference_rows: Optional[List[dict]] = None) -> dict:
    """把拍平的 WBS（按页面顺序、带 code/depth）排成框图版面。

    `rows` 是**纯字典**，不吃 ORM 对象：这个模块被 Excel 导出和接口两处调用，
    拖起 models 只会让它没法单独测（同 `timeutil.parse_plan_date` 放在 timeutil 的理由）。
    每行认这些键：code / name / depth / status / owner / days / pct / is_leaf / leaf_count。
    """
    # 切段与整段截断收口在 split_stages / cap_stages，A 图吃的是同一份
    first_month, last_month = reference_months(
        reference_rows if reference_rows is not None else rows, reference_start, reference_end)
    stages, skipped = split_stages(rows)
    stages, dropped = cap_stages(stages, MAX_BOXES)
    skipped += dropped

    cols_per_band = max(1, int((MAX_BAND_W - 2 * PAD + COL_GAP) // (COL_W + COL_GAP)))
    cols_per_band = min(cols_per_band, max(1, len(stages)))
    bands = [stages[i:i + cols_per_band] for i in range(0, len(stages), cols_per_band)]

    boxes: List[dict] = []
    arrows: List[dict] = []
    # 标题与图例**画进图里**，不是写在页面上：导出的那张图（PNG / SVG）经常被单独
    # 截进别的材料，落单的一张没有标题就找不回出处（同 `pptx_utils` 的页脚三件套、
    # 同 VersionTimeline 把图例画进 svg）。所以版面里给它们留位置，两个出口照着填。
    head_h = TITLE_PX * 1.5 + (SUB_PX * 1.6 if subtitle else 0) + 14
    axis_y = PAD + head_h + 34
    y_band = axis_y + 22
    used_status: List[str] = []

    for band in bands:
        band_h = 0.0
        stage_heads: List[dict] = []
        for ci, st in enumerate(band):
            x_col = PAD + ci * (COL_W + COL_GAP)
            y = y_band
            containers: List[dict] = []

            def close_containers(next_depth: int):
                nonlocal y
                while containers and containers[-1]["depth"] >= next_depth:
                    parent = containers.pop()
                    # 子任务之间留原来的间距，最末子任务与外框留底部内边距。
                    parent["h"] = round(y - BOX_GAP + BOX_PAD_Y - parent["y"], 1)
                    y = parent["y"] + parent["h"] + BOX_GAP

            for ri, r in enumerate(st):
                depth = max(1, int(r.get("depth") or 1))
                close_containers(depth)
                fs = enums.wbs_level_font(depth)
                size = float(fs["px"])
                indent = 0 if depth == 1 else (depth - 2) * INDENT
                x = x_col + indent
                w = COL_W - 2 * indent
                inner = w - 2 * BOX_PAD_X
                lines = _wrap(str(r.get("name") or "（未命名）"),
                              size, inner, TITLE_MAX_LINES)
                owner = str(r.get("owner") or "未指定").strip() or "未指定"
                owner_lines = _wrap(owner, META_PX, inner, 2)
                late_days = int(r.get("overdue_days") or 0)
                lh = round(size * LINE_RATIO, 1)
                mh = round(META_PX * LINE_RATIO, 1)
                pct_now = max(0, min(100, int(r.get("pct") or 0)))
                h = 2 * BOX_PAD_Y + len(lines) * lh + len(owner_lines) * mh
                fill, color = _colors(r, depth)
                st_word = (r.get("status") or "").strip()
                if r.get("is_leaf") and st_word and st_word not in used_status:
                    used_status.append(st_word)
                box = {
                    "x": round(x, 1), "y": round(y, 1), "w": round(w, 1), "h": round(h, 1),
                    "depth": depth, "code": r.get("code", ""),
                    "parent_code": containers[-1]["code"] if containers else (
                        st[0].get("code", "") if depth > 1 else ""),
                    "header_h": round(h, 1),
                    "container": depth >= 2 and ri + 1 < len(st)
                                 and int(st[ri + 1].get("depth") or 1) > depth,
                    "lines": lines, "name": str(r.get("name") or "（未命名）"),
                    "owner": owner, "owner_lines": owner_lines,
                    "meta": owner_lines[0], "date": "",
                    "font_px": size, "font_pt": float(fs["pt"]), "bold": bool(fs["bold"]),
                    "line_h": lh, "meta_h": mh, "meta_px": META_PX,
                    "fill": fill, "color": color,
                    # 延期保留红色粗边框，**底色照旧**：底色表达的是状态，
                    # 拿它表示延期就得在"进行中"和"已延期"里二选一，而那正是要同看的两件事
                    "stroke": LATE_STROKE if late_days else STROKE,
                    "stroke_w": 2.0 if late_days else 1.0,
                    "date_color": LATE_TEXT if late_days else DATE_TEXT,
                    "overdue": bool(late_days), "overdue_days": late_days,
                    "is_leaf": bool(r.get("is_leaf")),
                    "pct": pct_now,
                    "bar": None,
                }
                boxes.append(box)
                if depth == 1:
                    stage_heads.append(box)
                if box["container"]:
                    containers.append(box)
                    y += h
                else:
                    y += h + BOX_GAP
            close_containers(1)
            band_h = max(band_h, y - y_band)
        # 阶段之间画箭头：只在**同一段内**相邻的两列之间，跨段不画（见模块说明）
        for a, b in zip(stage_heads, stage_heads[1:]):
            ay = a["y"] + a["h"] / 2
            arrows.append({"x1": round(a["x"] + a["w"], 1), "y1": round(ay, 1),
                           "x2": round(b["x"], 1), "y2": round(b["y"] + b["h"] / 2, 1)})
        y_band += band_h + 30

    width = PAD * 2 + (cols_per_band * COL_W + max(0, cols_per_band - 1) * COL_GAP)
    legend = [{"label": s, "fill": "#" + brand.STATUS_FILLS[s]}
              for s in used_status if s in brand.STATUS_FILLS]
    overdue_n = sum(1 for b in boxes if b["overdue"] and b["is_leaf"])
    undated_n = sum(1 for r in rows if _date_text(r) == "未填计划完成日")
    reference_axis = _reference_axis(first_month, last_month, width - 2 * PAD, axis_y)
    if any(b["overdue"] for b in boxes):
        # 「已延期」是**边框**不是底色，图例里也画成一个空心红框才对得上
        legend.append({"label": "已延期（红框）", "fill": "#FFFFFF", "stroke": LATE_STROKE})
    legend_y = y_band - 30 + 10
    # 底注**不截断**（给一个够大的行数上限）：截掉的恰恰是「另有 N 行没填计划完成日」
    # 这种必须说清楚的话，而一个"…"结尾的说明看着还挺正常，没人会去核
    note_lines = _wrap(diagram_note(overdue_n, undated_n, len(bands) > 1, max(0, skipped)),
                       LEGEND_PX, width - 2 * PAD, 12)
    note_y = legend_y + LEGEND_PX * 1.9
    height = int(note_y + len(note_lines) * LEGEND_PX * 1.5 + PAD)

    return {
        "title": title, "subtitle": subtitle,
        "head_h": round(head_h, 1), "title_px": TITLE_PX, "sub_px": SUB_PX,
        "legend_px": LEGEND_PX, "legend_y": round(legend_y, 1), "pad": PAD,
        "note_lines": note_lines, "note_y": round(note_y, 1),
        "width": int(width), "height": int(height),
        "boxes": boxes, "arrows": arrows, "legend": legend,
        "reference_axis": reference_axis,
        "stage_count": len(stages), "box_count": len(boxes),
        # 只筛不报的数字比没有更糟：这两个都要摆到页面和图上
        # （overdue **只数叶子**：父行跟着红是推上来的，父子都数会把 4 条报成 8 条）
        "overdue": overdue_n, "undated": undated_n,
        "cols_per_band": cols_per_band, "wrapped": len(bands) > 1,
        # 只筛不报的数字比没有更糟：画不下的条数要摆到页面和图上
        "skipped": max(0, skipped),
        "arrow_color": ARROW,
    }


def render_png(spec: dict, scale: float = 2.0) -> Optional[bytes]:
    """把版面画成 PNG（贴进 Excel 用）。**找不到中文字体返回 None**，由调用方
    退回文字说明——绝不回退 PIL 默认字体，那不含汉字，画出来是一排方块
    （同 `xlsx_utils._render_milestone_image` 的退回规则）。
    """
    import io as _io

    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    from xlsx_utils import _load_pil_font

    if not spec.get("boxes"):
        return None
    if _load_pil_font(12) is None:
        return None

    W = int(spec["width"] * scale)
    H = int(spec["height"] * scale)
    img = Image.new("RGB", (max(W, 1), max(H, 1)), "#FFFFFF")
    d = ImageDraw.Draw(img)

    def S(v):
        return int(round(float(v) * scale))

    for a in spec.get("arrows", []):
        y = S(a["y1"])
        x1, x2 = S(a["x1"]) + 6, S(a["x2"]) - 6
        d.line([(x1, y), (x2, y)], fill=spec.get("arrow_color", ARROW), width=max(1, S(1.6)))
        head = max(4, S(5))
        d.polygon([(x2, y), (x2 - head, y - head * 0.7), (x2 - head, y + head * 0.7)],
                  fill=spec.get("arrow_color", ARROW))

    f_title = _load_pil_font(max(9, S(spec["title_px"] * 0.78)), bold=True)
    f_sub = _load_pil_font(max(8, S(spec["sub_px"] * 0.78)))
    if f_title is None:
        return None
    d.text((S(spec["pad"]), S(spec["pad"])), spec.get("title") or "WBS 调试框图",
           font=f_title, fill="#" + brand.BRAND)
    if spec.get("subtitle") and f_sub is not None:
        d.text((S(spec["pad"]), S(spec["pad"] + spec["title_px"] * 1.5)),
               spec["subtitle"], font=f_sub, fill="#" + brand.MUTED)

    axis = spec["reference_axis"]
    f_axis = _load_pil_font(max(7, S(LEGEND_PX * 0.78)))
    if f_axis is not None:
        d.text((S(PAD), S(axis["title_y"] - LEGEND_PX)), "全局日期参考（按月）",
               font=f_axis, fill=DATE_TEXT)
        d.line([(S(axis["x1"]), S(axis["y"])), (S(axis["x2"]), S(axis["y"]))],
               fill=STROKE, width=max(1, S(1)))
        for tick in axis["ticks"]:
            d.line([(S(tick["x"]), S(axis["y"] - 5)), (S(tick["x"]), S(axis["y"]))],
                   fill=STROKE, width=max(1, S(1)))
            d.text((S(tick["label_x"]), S(axis["label_y"] - LEGEND_PX)),
                   tick["label"], font=f_axis, fill=DATE_TEXT)

    for b in spec["boxes"]:
        x0, y0 = S(b["x"]), S(b["y"])
        x1, y1 = S(b["x"] + b["w"]), S(b["y"] + b["h"])
        d.rectangle([x0, y0, x1, y1], fill=b["fill"], outline=b["stroke"],
                    width=max(1, S(b.get("stroke_w", 1.0))))
        f = _load_pil_font(max(8, S(b["font_px"] * 0.78)), bold=b["bold"])
        fm = _load_pil_font(max(7, S(b["meta_px"] * 0.78)))
        if f is None:
            return None
        ty = y0 + S(BOX_PAD_Y)
        for ln in b["lines"]:
            d.text((x0 + S(BOX_PAD_X), ty), ln, font=f, fill=b["color"])
            ty += S(b["line_h"])
        if fm is not None:
            for line in b["owner_lines"]:
                d.text((x0 + S(BOX_PAD_X), ty), line, font=fm, fill="#" + brand.MUTED)
                ty += S(b["meta_h"])

    # 图例：只列图上真的出现过的状态。全档铺出来的话，一份全是「未开始」的 WBS
    # 底下挂着四种颜色的说明，看图的人会以为自己漏看了绿的那几个
    f_leg = _load_pil_font(max(7, S(spec["legend_px"] * 0.78)))
    if f_leg is not None:
        lx = S(spec["pad"])
        ly = S(spec["legend_y"])
        sq = S(spec["legend_px"])
        for item in spec.get("legend", []):
            d.rectangle([lx, ly, lx + sq, ly + sq], fill=item["fill"],
                        outline=item.get("stroke") or STROKE,
                        width=max(1, S(2 if item.get("stroke") else 0.8)))
            d.text((lx + sq + S(5), ly - S(1)), item["label"], font=f_leg, fill="#" + brand.TEXT)
            lx += sq + S(6) + int(text_w(item["label"], spec["legend_px"]) * scale) + S(16)
        ny = ly + sq + S(6)
        for line in spec.get("note_lines", []):
            d.text((S(spec["pad"]), ny), line, font=f_leg, fill="#" + brand.MUTED)
            ny += S(spec["legend_px"] * 1.5)

    buf = _io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()



def diagram_note(overdue: int, undated: int, wrapped: bool, skipped: int) -> str:
    """图底那段说明。**被标记/被排除的数都要写出来**——只筛不报的数字比没有更糟
    （同 `unassigned` / `overdue_unknown` / `match_rate`）。页面与 PNG 共用这一份，
    各写一份的表现是同一张图在页面上说"另有 3 行"、导出的图里说"另有 5 行"。
    """
    parts = ["第 1 层＝调试阶段，箭头是推进顺序；从第 2 层开始，父任务框包住子任务框，越深一层字越小。"
             "方框只显示任务名称和责任人；顶部月份仅作全局参考，不与阶段列精确对应。"]
    if overdue:
        parts.append(f"红框＝已过计划完成日、状态还不是「已完成」，共 {overdue} 个工作包"
                     f"（只数叶子；上级方框跟着红，不另计）。")
    if undated:
        parts.append(f"另有 {undated} 个任务没填计划完成日，详细日期请查看表格。")
    if wrapped:
        parts.append("阶段一行摆不下，折到了下一段（段与段之间不画箭头）。")
    if skipped:
        parts.append(f"另有 {skipped} 行没画进图里。")
    return " ".join(parts)
