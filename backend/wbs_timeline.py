"""A 图：一根真日期横轴 + 大框套中框套小框。

与 [wbs_diagram.py](wbs_diagram.py) 是**两张图、两份版面，刻意不合并**：

| | 答的问题 | 横轴 |
| --- | --- | --- |
| 调试框图（`wbs_diagram`） | 这件事分几步走、每步底下挂着哪些活 | 无，按阶段分列 |
| **A 图（本模块）** | 每个事项**哪天**该完、今天看有没有拖 | **真日期** |

框图那张图把一个阶段的活摞成一列，读得出拆解结构，读不出"9 月底该完的是哪几件"；
A 图把同一棵树摊到一根日期轴上，代价是阶段之间会留出大片空白（那正是"这段时间
没安排活"的事实）。两张都留着，因为它们答的不是同一个问题——合成一张的话，
两个问题里必然有一个答不出来，而图看着还挺正常。

**版面只算不画**（同 `wbs_diagram`）：页面用 SVG 画、Excel 用 PIL 画 PNG，
两个出口吃同一份坐标。前端自己再排一次的话，同一份 WBS 在页面上和导出的图里
框的位置不一样，而两边单独看都正常。

嵌套是这么出来的：**一行一个节点**，父节点的框**纵向罩住自己那一行 + 它底下所有
子孙行**、横向铺它汇总出来的计划起止。于是第 1 层是大框，第 2 层的框画在它里面，
第 3 层的再画在第 2 层里面——嵌套关系与时间位置同时看得见。

**框里不写字，名字全在左边那一栏**：短活的框只有十来个像素宽，字写在框里必然
戳出去（第一版就是这么坏的：「6 交付与固化」被裁成一半）。左栏定宽、按层级缩进、
字号走 `enums.wbs_level_font()` 那一份阶梯，右端再对齐一小列「人天 · 完成度」，
可以竖着扫。**延期天数写在左栏这一列、不写在图上**：图上父子各印一遍会堆成三行
压在框上，而红边已经把"哪个框延期了"说清楚了。

**这张图不画标题**（现场原话："有这样的图后坐标的标题就不需要了"）——日期轴自己
就说明了这是什么图。但底注第一行仍然写明这是哪一份 WBS、截至哪天：导出的 PNG
经常被单独截进别的材料，落单的一张连出处都没有就找不回来了（同 `pptx_utils`
的页脚三件套）。
"""
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import brand
import enums
# 「按整段阶段截」与宽度估算两张图共用一份实现，放在 wbs_diagram 那边
# （它层级更低、不依赖本模块）。各写一份的表现是同一份 WBS 在两张图上
# 截断的位置不一样，而两张单独看都正常。
from wbs_diagram import (BAR_FILL, BAR_TRACK, LATE_STROKE, STROKE, cap_stages,
                         clip_text, split_stages, text_w)

PAD = 22
NAME_W = 348              # 左栏定宽。按内容变宽的话，换一份 WBS 整张图就左右跳，
                          # 两份图没法并排看
GUT = 18                  # 左栏与时间轴之间的沟，竖分隔线画在这中间
AXIS_H = 44               # 顶上留给月份刻度与「今天」胶囊的高度
INDENT = 16               # 左栏每深一层缩进
META_PX = 10.5            # 右端那一小列的字号（不属于层级阶梯，它不是任务名）
META_W = 82               # 那一列占的宽度
ROW_RATIO = 2.3           # 行高 = 本层字号 × 这个数。行高跟着字号走而不是另写一张
                          # 表：字号阶梯一调，行高就跟着对，不会出现"字变大了、行没变"
ROW_MIN = 22.0
BOX_PAD_TOP = 4.0         # 框在自己那一行里的上留白（父框多留一点，见下）
BOX_PAD_BOT = 5.0         # 叶子框的下留白
BOX_NEST_PAD = 2.0        # **每往上一层，下沿就多探出这么多**：父框的下沿必须在
                          # 最后一个子孙的下沿**外面**，不然最底下那个子框会戳出
                          # 父框半截，而"框里套框"正是这张图要表达的东西
BOX_INSET = 4.0           # 父框横向比子框各外扩这么多
MIN_BOX_W = 9.0           # 一天的活也要看得见
BAR_H = 2.5               # 叶子框底部那条完成度细条
DAY_PX = 11.0             # 一天多宽（会被 PLOT_MIN/MAX 夹住）
PLOT_MIN, PLOT_MAX = 660.0, 1180.0
MAX_ROWS = 150            # 画不下的如实报（`skipped`），且**按整段阶段**截
LEGEND_PX = 11.0
TODAY_PILL_W = 78.0
TODAY_PILL_H = 17.0

L1_FILL = "#" + brand.HEADER_BG     # 大框：浅蓝灰（与表头同一档，蓝分层）
L2_FILL = "#" + brand.ZEBRA         # 中框：更淡一档
LEAF_FILL = "#" + brand.WHITE
UNCOUNTED_FILL = "#" + brand.SECTION_BG   # 「已变更 / 不涉及」＝不进统计，灰
BAND_FILL = "#" + brand.ZEBRA       # 左栏的斑马（只上在左栏，图区上了会和中框同色）
AXIS_LINE = "#" + brand.BORDER
GRID_LINE = "#EDF0F5"
TICK_TEXT = "#" + brand.MUTED
META_TEXT = "#909399"
LATE_TEXT = LATE_STROKE
TODAY_COLOR = "#" + brand.BRAND     # 整张图唯一一处红（红定位，见 brand.py）


# ─── 树形：一行一个节点，父框罩住自己 + 全部子孙 ────────────────────────────
def _as_date(v) -> Optional[date]:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    t = str(v or "")[:10]
    try:
        return date.fromisoformat(t)
    except ValueError:
        return None


def _fmt_num(v) -> str:
    f = float(v or 0)
    return str(int(f)) if f == int(f) else f"{f:g}"


def _meta_text(row: dict) -> Tuple[str, str]:
    """左栏右端那一小列：(文字, 颜色)。

    优先级是刻意的：**延期天数压过一切**——那是这张图最该被看见的一件事。
    其次是「不做了」与「没填完成日」：这两种行在图区里是**空白**的，
    不在这儿写明原因的话，那一行看着像数据丢了（同 `overdue_unknown`）。
    """
    late = int(row.get("overdue_days") or 0)
    if late:
        return f"延期 {late} 天", LATE_TEXT
    st = (row.get("status") or "").strip()
    if row.get("is_leaf") and st in enums.WBS_UNCOUNTED_STATUSES:
        return st, META_TEXT
    if row.get("is_leaf") and not row.get("end"):
        return "未填完成日", META_TEXT
    if not row.get("is_leaf") and not row.get("end"):
        return "子行都没填日期", META_TEXT
    return f"{_fmt_num(row.get('days'))}天 · {int(row.get('pct') or 0)}%", META_TEXT


def _box_style(row: dict, depth: int) -> Tuple[str, str, float]:
    """(底色, 边框色, 边框粗细)。

    **延期改边框不改底色**：底色已经被状态占了（绿＝已完成、黄＝进行中），
    再拿它表示延期就得二选一，而"进行中"和"已延期"恰恰是要同时看到的两件事
    （同 `wbs_diagram`，两张图的这条口径必须一样）。
    状态词**精确匹配**才点灯，配色只认 `brand.STATUS_FILLS` 那一份。
    """
    late = int(row.get("overdue_days") or 0)
    if not row.get("is_leaf"):
        fill = L1_FILL if depth == 1 else L2_FILL
        return fill, (LATE_STROKE if late else AXIS_LINE), (1.8 if late else 1.0)
    st = (row.get("status") or "").strip()
    if st in enums.WBS_UNCOUNTED_STATUSES:
        return UNCOUNTED_FILL, AXIS_LINE, 1.0
    f, _t, _b = brand.status_style(st)
    fill = ("#" + f) if f else LEAF_FILL
    return fill, (LATE_STROKE if late else STROKE), (1.8 if late else 1.0)


def _tip(row: dict) -> str:
    """悬停给全的那一份：框上一个字都没写，不给 tooltip 就只能靠左栏猜。"""
    bits = [f"{row.get('code', '')} {row.get('name') or '（未命名）'}".strip()]
    if row.get("owner"):
        bits.append(str(row["owner"]))
    if float(row.get("days") or 0):
        bits.append(("汇总 " if not row.get("is_leaf") else "") + _fmt_num(row["days"]) + " 人天")
    bits.append(f"{int(row.get('pct') or 0)}%")
    if row.get("is_leaf") and (row.get("status") or "").strip():
        bits.append(row["status"])
    s0, s1 = _as_date(row.get("start")), _as_date(row.get("end"))
    if s0 or s1:
        head = "计划 " if row.get("is_leaf") else "汇总 "
        bits.append(head + f"{s0 or '?'} → {s1 or '?'}")
    else:
        bits.append("未填计划日期")
    late = int(row.get("overdue_days") or 0)
    if late:
        bits.append(f"已过计划完成日 {late} 天，状态还不是「已完成」")
    return " · ".join(bits)


def _month_starts(d0: date, d1: date) -> List[date]:
    out = []
    cur = date(d0.year, d0.month, 1)
    while cur <= d1:
        if cur >= d0:
            out.append(cur)
        cur = date(cur.year + 1, 1, 1) if cur.month == 12 else date(cur.year, cur.month + 1, 1)
    return out


def build_timeline(rows: List[dict], subtitle: str = "", today: Optional[date] = None,
                   max_depth: Optional[int] = None, folded: int = 0) -> dict:
    """把拍平的 WBS（按页面顺序、带 code/depth/start/end/overdue_days）排成 A 图版面。

    `rows` 是**纯字典**、不吃 ORM 对象（同 `wbs_diagram.build_diagram`）：这个模块
    被接口和 Excel 导出两处调用，拖起 models 只会让它没法单独测。
    每行认这些键：code / name / depth / status / owner / days / pct / is_leaf /
    start / end / overdue_days / folded。
    """
    today = today or date.today()
    stages, skipped = split_stages(rows)
    stages, dropped = cap_stages(stages, MAX_ROWS)
    skipped += dropped
    kept: List[dict] = [r for st in stages for r in st]

    # ── 行：一行一个节点，行高跟着本层字号走 ────────────────────────────
    depths = [max(1, int(r.get("depth") or 1)) for r in kept]
    fonts = [enums.wbs_level_font(d) for d in depths]
    row_h = [max(ROW_MIN, round(float(f["px"]) * ROW_RATIO, 1)) for f in fonts]
    top = PAD + AXIS_H
    row_top: List[float] = []
    y = top
    for h in row_h:
        row_top.append(y)
        y += h
    bottom = y

    # 父框的下沿 = 它**最后一个子孙**那一行的下沿。行是按树的顺序排的，
    # 所以"子孙"＝后面连续一串 depth 更大的行，不必再查一次 parent_id
    def last_row(i: int) -> int:
        j = i
        k = i + 1
        while k < len(kept) and depths[k] > depths[i]:
            j = k
            k += 1
        return j

    # ── 时间轴：起止取图上所有行的计划日期，再把「今天」也裹进来 ──────────
    ds = [d for d in (_as_date(r.get("start")) for r in kept) if d]
    de = [d for d in (_as_date(r.get("end")) for r in kept) if d]
    dated = bool(ds or de)
    d0 = (min(ds + de + [today]) if dated else today) - timedelta(days=5)
    d1 = (max(ds + de + [today]) if dated else today) + timedelta(days=5)
    span = max(1, (d1 - d0).days)
    plot_w = max(PLOT_MIN, min(PLOT_MAX, span * DAY_PX))
    plot_x = PAD + NAME_W + GUT
    width = int(plot_x + plot_w + PAD)

    def X(d: date) -> float:
        return plot_x + (d - d0).days / span * plot_w

    # ── 斑马：只给第 1 层的**整段**上，且只上在左栏 ──────────────────────
    # 一行一条会把嵌套关系切碎；铺到图区则会和中框同色，中框就看不见了
    bands: List[dict] = []
    stage_i = 0
    for i, r in enumerate(kept):
        if depths[i] != 1:
            continue
        stage_i += 1
        if stage_i % 2 == 0:
            j = last_row(i)
            bands.append({"x": round(PAD - 6, 1), "y": round(row_top[i], 1),
                          "w": round(NAME_W + 6, 1),
                          "h": round(row_top[j] + row_h[j] - row_top[i], 1),
                          "fill": BAND_FILL})

    # ── 左栏 + 框 ───────────────────────────────────────────────────────
    out_rows: List[dict] = []
    boxes: List[dict] = []
    used_status: List[str] = []
    undated = 0
    for i, r in enumerate(kept):
        depth, f = depths[i], fonts[i]
        size = float(f["px"])
        baseline = row_top[i] + row_h[i] / 2 + size * 0.35
        code = str(r.get("code") or "")
        tx = PAD + (depth - 1) * INDENT
        code_w = text_w(code, size) + 7
        avail = NAME_W - (tx - PAD) - code_w - META_W
        meta, meta_color = _meta_text(r)
        out_rows.append({
            "y": round(baseline, 1), "row_top": round(row_top[i], 1),
            "row_h": round(row_h[i], 1), "depth": depth,
            "code": code, "code_x": round(tx, 1),
            "name": clip_text(r.get("name") or "（未命名）", size, avail),
            "name_x": round(tx + code_w, 1),
            "font_px": size, "font_pt": float(f["pt"]),
            "bold": bool(f["bold"]), "color": "#" + f["color"],
            "meta": meta, "meta_x": round(PAD + NAME_W - 4, 1),
            "meta_px": META_PX, "meta_color": meta_color,
            # 折叠掉的子孙数就挂在名字后面：只筛不报的表现是「这几行怎么没了」
            "fold": f"+{int(r['folded'])}" if int(r.get("folded") or 0) else "",
            "fold_x": round(tx + code_w + text_w(clip_text(r.get("name") or "", size, avail), size) + 6, 1),
        })

        s0, s1 = _as_date(r.get("start")), _as_date(r.get("end"))
        st_word = (r.get("status") or "").strip()
        if r.get("is_leaf") and st_word and st_word not in used_status:
            used_status.append(st_word)
        if not (s0 and s1):
            # 没填计划日期的**行照样占着**（左栏写明原因），图区留白。
            # 藏起来的话，那批最该被追着去补日期的行就从图上消失了
            if r.get("is_leaf") and st_word not in enums.WBS_UNCOUNTED_STATUSES:
                undated += 1
            continue
        leaf = bool(r.get("is_leaf"))
        j = last_row(i)
        # 下沿按「底下还有几层」往外探：叶子探 0，父框每多罩一层多探一档。
        # 上下用同一个留白的话，最后一个子框的下沿正好和父框的下沿重合，
        # 看上去就是子框戳出了父框（第一版就是这么坏的）
        levels = depths[j] - depths[i]
        by0 = row_top[i] + BOX_PAD_TOP + (0.0 if leaf else 1.5)
        by1 = row_top[j] + row_h[j] - max(1.0, BOX_PAD_BOT - BOX_NEST_PAD * levels)
        inset = 0.0 if leaf else BOX_INSET
        bx = X(s0) - inset
        # 结束日**算整天**：条走到 s1 那天的末尾，不然"9-10 到 9-10"是一根零宽的线
        bw = max(MIN_BOX_W, X(s1 + timedelta(days=1)) - X(s0) + inset * 2)
        fill, stroke, sw = _box_style(r, depth)
        pct = max(0, min(100, int(r.get("pct") or 0)))
        # 完成度细条只给**还没做完、且算进统计**的叶子画：100% 的框已经是整块绿的，
        # 再压一条满格的条上去看着像多了一道边；0% 画一条空槽出来也只是噪声
        show_bar = leaf and st_word not in enums.WBS_UNCOUNTED_STATUSES and 0 < pct < 100
        boxes.append({
            "x": round(bx, 1), "y": round(by0, 1),
            "w": round(bw, 1), "h": round(max(4.0, by1 - by0), 1),
            "rx": 5.0 if depth == 1 else 4.0,
            "fill": fill, "stroke": stroke, "stroke_w": sw,
            "depth": depth, "is_leaf": leaf, "code": code,
            "overdue": bool(int(r.get("overdue_days") or 0)),
            "overdue_days": int(r.get("overdue_days") or 0),
            "tip": _tip(r),
            "bar": ({"x": round(bx + 1.5, 1), "y": round(by1 - BAR_H - 1.5, 1),
                     "w": round(max(0.0, (bw - 3) * pct / 100.0), 1),
                     "h": BAR_H, "fill": LATE_STROKE if int(r.get("overdue_days") or 0)
                     else BAR_FILL, "track": BAR_TRACK,
                     "track_w": round(bw - 3, 1)} if show_bar else None),
        })

    # ── 刻度与分隔线 ────────────────────────────────────────────────────
    ticks: List[dict] = []
    if dated:
        months = _month_starts(d0, d1)
        # 轴的起点落在月中时，第一个整月之前那一截没有任何刻度——一眼看不出
        # 那是几月。补一个落在起点上的刻度（带年份），而不是让它空着
        if not months or months[0] > d0:
            months = [d0] + months
        # 一格太窄时隔月标一次：每月一格在宽窗口下会糊成一片（同 VersionTimeline）
        stride = 1 if not months or plot_w / max(1, len(months)) >= 62 else 2
        for k, m in enumerate(months):
            if k % stride:
                continue
            ticks.append({
                "x": round(X(m), 1),
                "label": (f"{m.year}年{m.month}月" if k == 0 or m.month == 1 else f"{m.month}月"),
                "label_x": round(X(m) + 5, 1),
            })
    axis_y = top - 14
    lines = [
        {"x1": round(plot_x, 1), "y1": round(axis_y, 1),
         "x2": round(plot_x + plot_w, 1), "y2": round(axis_y, 1),
         "color": AXIS_LINE, "w": 1.0},
        {"x1": round(plot_x - GUT / 2, 1), "y1": round(axis_y - 12, 1),
         "x2": round(plot_x - GUT / 2, 1), "y2": round(bottom, 1),
         "color": AXIS_LINE, "w": 1.0},
    ]
    grid = [{"x": t["x"], "y1": round(axis_y, 1), "y2": round(bottom, 1),
             "color": GRID_LINE} for t in ticks]

    tx_today = X(today)
    todaym = {
        "x": round(tx_today, 1), "y1": round(PAD + 13, 1), "y2": round(bottom, 1),
        "label": f"今天 {today.month}-{today.day:02d}", "color": TODAY_COLOR,
        "pill_x": round(tx_today - TODAY_PILL_W / 2, 1), "pill_y": round(PAD - 4, 1),
        "pill_w": TODAY_PILL_W, "pill_h": TODAY_PILL_H, "pill_px": 10.5,
        "text_y": round(PAD + 8.5, 1),
    }

    # ── 图例：只列图上真出现过的状态 ────────────────────────────────────
    # 全档铺出来的话，一份全是「未开始」的 WBS 底下挂着四种颜色的说明，
    # 看图的人会以为自己漏看了绿的那几个
    legend: List[dict] = []
    for s in used_status:
        if s in brand.STATUS_FILLS:
            legend.append({"label": s, "fill": "#" + brand.STATUS_FILLS[s]})
        elif s in enums.WBS_UNCOUNTED_STATUSES:
            legend.append({"label": s + "（不进统计）", "fill": UNCOUNTED_FILL})
        else:
            legend.append({"label": s, "fill": LEAF_FILL})
    if any(b["overdue"] for b in boxes):
        # 「已延期」是**边框**不是底色，图例里也画成一个空心红框才对得上
        legend.append({"label": "已延期（红框）", "fill": "#" + brand.WHITE,
                       "stroke": LATE_STROKE})
    legend.append({"label": "大框＝第 1 层，框里套的是它的子任务", "fill": L1_FILL})
    lx = float(PAD)
    for it in legend:
        it["x"] = round(lx, 1)
        lx += LEGEND_PX + 6 + text_w(it["label"], LEGEND_PX) + 16
    legend_y = bottom + 14

    overdue_n = sum(1 for r in kept if r.get("is_leaf") and int(r.get("overdue_days") or 0))
    note = timeline_note(subtitle=subtitle, today=today, overdue=overdue_n,
                         undated=undated, folded=folded, skipped=skipped,
                         max_depth=max_depth, dated=dated)
    # 底注**不截断**（行数上限给够）：截掉的恰恰是「另有 N 行没填计划完成日」
    # 这种必须说清楚的话，而一个"…"结尾的说明看着还挺正常
    note_lines = _wrap_note(note, width - 2 * PAD)
    # 图例与底注之间留够一行：贴太近的话两段文字糊成一块，扫过去以为是一段
    note_y = legend_y + LEGEND_PX * 2.8
    height = int(note_y + len(note_lines) * LEGEND_PX * 1.6 + PAD)

    return {
        "pad": PAD, "name_w": NAME_W, "gut": GUT, "axis_h": AXIS_H,
        "plot_x": round(plot_x, 1), "plot_w": round(plot_w, 1),
        "top": round(top, 1), "bottom": round(bottom, 1),
        "width": width, "height": height,
        "date_start": d0.isoformat(), "date_end": d1.isoformat(), "dated": dated,
        "rows": out_rows, "boxes": boxes, "bands": bands,
        "ticks": ticks, "grid": grid, "lines": lines, "today": todaym,
        "legend": legend, "legend_y": round(legend_y, 1), "legend_px": LEGEND_PX,
        "note_lines": note_lines, "note_y": round(note_y, 1),
        "row_count": len(out_rows), "box_count": len(boxes),
        # 只筛不报的数字比没有更糟：这几个都要摆到页面和图上
        # （overdue **只数叶子**：父框跟着红是推上来的，父子都数会把 4 条报成 8 条）
        "overdue": overdue_n, "undated": undated,
        "folded": folded, "skipped": skipped, "max_depth": max_depth or 0,
        "subtitle": subtitle,
    }


def _wrap_note(text: str, max_w: float) -> List[str]:
    """底注折行。**不截断**（行数上限给够）：截掉的恰恰是「另有 N 行没填计划完成日」
    这种必须说清楚的话，而一个"…"结尾的说明看着还挺正常。

    折完把**孤零零掉到下一行的收尾标点收回去**：宽度是估出来的（宁可估宽），
    经常差一个字，于是图底多出一行只写着「。」，看着像哪儿画坏了。
    """
    from wbs_diagram import _wrap

    lines = _wrap(text, LEGEND_PX, max_w, 12)
    while len(lines) > 1 and lines[-1].strip() and all(c in "。，、；：）」" for c in lines[-1]):
        tail = lines.pop()       # 先 pop 再写回，不能写成 lines[-2] += lines.pop()
        lines[-1] += tail
    return lines


def timeline_note(subtitle: str = "", today: Optional[date] = None, overdue: int = 0,
                  undated: int = 0, folded: int = 0, skipped: int = 0,
                  max_depth: Optional[int] = None, dated: bool = True) -> str:
    """图底那段说明。页面与 PNG 共用这一份，各写一份的表现是同一张图在页面上说
    「另有 3 行」、导出的图里说「另有 5 行」。

    第一行带上是哪份 WBS、截至哪天：这张图不画标题（现场要求），但导出的 PNG
    被单独截进别的材料时总得找得回出处。
    """
    today = today or date.today()
    head = f"{subtitle} · 截至 {today.isoformat()}" if subtitle else f"截至 {today.isoformat()}"
    parts = [head + "。横轴是真日期；大框纵向罩住它底下所有子行、横向铺它汇总出来的"
                    "计划起止，框里套的就是下一层。红竖线是今天。"]
    if overdue:
        parts.append(f"红框＝已过计划完成日、状态还不是「已完成」，共 {overdue} 个工作包"
                     f"（只数叶子；上级框跟着红，不另计）。延期天数写在左栏右端那一列。")
    if undated:
        parts.append(f"另有 {undated} 行没填计划完成日，排不上时间轴——它们在图区里是空白的，"
                     f"左栏写明了原因，行照样占着。")
    if not dated:
        parts.append("这份 WBS 一行计划日期都没填，横轴只剩「今天」这一根线。")
    if folded:
        parts.append(f"只画到第 {max_depth or 0} 层，另有 {folded} 行折在上级框里"
                     f"（名字后面的 +N）；它们的工期仍然算在上级框的汇总里。")
    if skipped:
        parts.append(f"另有 {skipped} 行没画进图里（整份 WBS 太大，全画出来每一行细得看不见），"
                     f"按整段阶段截的。表是全量的。")
    return " ".join(parts)


def render_png(spec: dict, scale: float = 2.0) -> Optional[bytes]:
    """把版面画成 PNG（贴进 Excel 用）。**找不到中文字体返回 None**，由调用方
    退回文字说明——绝不回退 PIL 默认字体，那不含汉字，画出来是一排方块
    （同 `wbs_diagram.render_png` / `xlsx_utils._render_milestone_image`）。
    """
    import io as _io

    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    from xlsx_utils import _load_pil_font

    if not spec.get("rows"):
        return None
    if _load_pil_font(12) is None:
        return None

    W = max(1, int(spec["width"] * scale))
    H = max(1, int(spec["height"] * scale))
    img = Image.new("RGB", (W, H), "#FFFFFF")
    d = ImageDraw.Draw(img)

    def S(v) -> int:
        return int(round(float(v) * scale))

    def font(px: float, bold: bool = False):
        # PIL 吃的是磅值，页面吃像素——0.78 这个换算与 wbs_diagram 同一份，
        # 不一样的话导出的图会比页面上的大半号
        return _load_pil_font(max(7, S(px * 0.78)), bold=bold)

    for b in spec.get("bands", []):
        d.rectangle([S(b["x"]), S(b["y"]), S(b["x"] + b["w"]), S(b["y"] + b["h"])],
                    fill=b["fill"])
    for g in spec.get("grid", []):
        d.line([(S(g["x"]), S(g["y1"])), (S(g["x"]), S(g["y2"]))], fill=g["color"],
               width=max(1, S(1)))
    for ln in spec.get("lines", []):
        d.line([(S(ln["x1"]), S(ln["y1"])), (S(ln["x2"]), S(ln["y2"]))],
               fill=ln["color"], width=max(1, S(ln["w"])))

    f_tick = font(11)
    if f_tick is None:
        return None
    for t in spec.get("ticks", []):
        d.text((S(t["label_x"]), S(spec["top"] - 30)), t["label"], font=f_tick, fill=TICK_TEXT)

    # 框按行的顺序画：父框先画、子框压在上面，这就是"框里套框"看得见的原因
    for b in spec.get("boxes", []):
        x0, y0 = S(b["x"]), S(b["y"])
        x1, y1 = S(b["x"] + b["w"]), S(b["y"] + b["h"])
        d.rounded_rectangle([x0, y0, max(x1, x0 + 1), max(y1, y0 + 1)],
                            radius=max(1, S(b["rx"])), fill=b["fill"],
                            outline=b["stroke"], width=max(1, S(b["stroke_w"])))
        bar = b.get("bar")
        if bar:
            bx, by = S(bar["x"]), S(bar["y"])
            d.rectangle([bx, by, bx + S(bar["track_w"]), by + S(bar["h"])], fill=bar["track"])
            if bar["w"] > 0.5:
                d.rectangle([bx, by, bx + S(bar["w"]), by + S(bar["h"])], fill=bar["fill"])

    f_meta = font(spec["rows"][0]["meta_px"]) if spec["rows"] else None
    for r in spec["rows"]:
        f = font(r["font_px"], bold=r["bold"])
        if f is None:
            return None
        ty = S(r["y"] - r["font_px"])
        d.text((S(r["code_x"]), ty), r["code"], font=f, fill=r["color"])
        d.text((S(r["name_x"]), ty), r["name"], font=f, fill=r["color"])
        if f_meta is not None:
            if r["meta"]:
                w = int(text_w(r["meta"], r["meta_px"]) * scale)
                d.text((S(r["meta_x"]) - w, S(r["y"] - r["meta_px"])), r["meta"],
                       font=f_meta, fill=r["meta_color"])
            if r["fold"]:
                d.text((S(r["fold_x"]), S(r["y"] - r["meta_px"])), r["fold"],
                       font=f_meta, fill=META_TEXT)

    t = spec["today"]
    d.line([(S(t["x"]), S(t["y1"])), (S(t["x"]), S(t["y2"]))], fill=t["color"],
           width=max(1, S(1.5)))
    d.rounded_rectangle([S(t["pill_x"]), S(t["pill_y"]),
                         S(t["pill_x"] + t["pill_w"]), S(t["pill_y"] + t["pill_h"])],
                        radius=S(t["pill_h"] / 2), fill=t["color"])
    f_pill = font(t["pill_px"], bold=True)
    if f_pill is not None:
        w = int(text_w(t["label"], t["pill_px"]) * scale)
        d.text((S(t["x"]) - w // 2, S(t["pill_y"] + 3)), t["label"], font=f_pill, fill="#FFFFFF")

    f_leg = font(spec["legend_px"])
    if f_leg is not None:
        sq = S(spec["legend_px"])
        ly = S(spec["legend_y"])
        for it in spec.get("legend", []):
            lx = S(it["x"])
            d.rectangle([lx, ly, lx + sq, ly + sq], fill=it["fill"],
                        outline=it.get("stroke") or STROKE,
                        width=max(1, S(2 if it.get("stroke") else 0.8)))
            d.text((lx + sq + S(5), ly - S(1)), it["label"], font=f_leg, fill="#" + brand.TEXT)
        ny = S(spec["note_y"])
        for line in spec.get("note_lines", []):
            d.text((S(spec["pad"]), ny), line, font=f_leg, fill="#" + brand.MUTED)
            ny += S(spec["legend_px"] * 1.6)

    buf = _io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()
