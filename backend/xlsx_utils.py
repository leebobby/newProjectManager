"""Excel 导出工具：专项/攻关导出为美观、整洁、可直接使用的单页表格（华为红风格）。

依赖：openpyxl

设计要点（解决"导出很乱"）：
- 全表统一 6 列（A–F）网格，列宽固定且合理；
- 标题 / 章节 / 叙述段落统一横跨 A–F 合并，表格按"逻辑列→物理列合并"对齐；
- 里程碑这种窄表通过合并映射到 6 列，避免落在过窄的列里串味；
- 单元格统一自动换行 + 按内容估算行高，长文本不再溢出/挤压。
"""
import io
import math
import os
import pathlib
import re
from datetime import datetime
from typing import Optional

import enums
import special_layout
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# 华为红主题
_BRAND = "C7000B"
_BRAND_DARK = "9E0009"
_SECTION = "FBEAEA"      # 章节标题底色（浅红）
_ZEBRA = "FBF4F4"        # 斑马底色
_BORDER_RGB = "E3C9CB"

_FONT = "微软雅黑"

# 6 列网格列宽（字符单位）
_COL_WIDTHS = [6, 36, 30, 12, 14, 10]
_NCOL = len(_COL_WIDTHS)

_MS_STATUS_LABEL = {
    "planning": "未开始", "in_progress": "进行中", "done": "已完成", "delayed": "已延期",
}
_STATUS_FONT = {
    "已完成": "2E7D32", "进行中": "1565C0", "已延期": "C62828",
    "已变更": "B96A00", "未开始": "909399", "已闭环": "2E7D32",
}
_STATUS_FILL = {
    "已闭环": "EAF6EA", "已完成": "EAF6EA",
}

_thin = Side(style="thin", color=_BORDER_RGB)
_BORDER = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)

# 点灯列的底色/字色，与前端 RichGrid 及周报 HTML 的三档保持一致
_LIGHT_FILL = {"red": "FEF0F0", "yellow": "FDF6EC", "green": "F0F9EB"}
_LIGHT_FONT = {"red": "F56C6C", "yellow": "E6A23C", "green": "67C23A"}

# 分段图片 / 全景图的落盘根目录（与 routers/specials.py 的 UPLOAD_ROOT 同一处）
UPLOAD_ROOT = pathlib.Path(__file__).resolve().parent / "uploads" / "specials"


def _strip_html(s: str) -> str:
    if not s:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    text = re.sub(r"</\s*(p|div|h\d|li|tr)\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _kind_label(kind: str) -> str:
    return "攻关" if kind == "assault" else "专项"


def _disp_w(s: str) -> int:
    """显示宽度：CJK 记 2，其余记 1。"""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in s)


def _cell_lines(text: str, capacity: int) -> int:
    cap = max(capacity, 4)
    lines = 0
    for seg in str(text or "").split("\n"):
        lines += max(1, math.ceil(_disp_w(seg) / cap))
    return max(1, lines)


def _hex_to_rgb6(color: str, default: str = "262626") -> str:
    """'#C7000B' / 'C7000B' → 'C7000B'；空 / 非法 → default。"""
    s = (color or "").strip().lstrip("#")
    if len(s) == 6 and all(c in "0123456789abcdefABCDEF" for c in s):
        return s.upper()
    return default


# ─── 里程碑「图片」渲染（PIL）─────────────────────────────────────
# 里程碑导出为时间轴图片而非表格。字体在 Windows / Linux 上自动发现；
# 找不到能渲染中文的字体时整体放弃图片、退回表格形式（避免方块乱码）。
# 可用环境变量 APP_CJK_FONT 指定字体文件路径（部署机字体装在非常规目录时）。

_MS_DOT_RGB = {
    "planning": (192, 196, 204), "in_progress": (64, 158, 255),
    "done": (103, 194, 58), "delayed": (245, 108, 108),
}
_MS_LEGEND = [("planning", "未开始"), ("in_progress", "进行中"),
              ("done", "已完成"), ("delayed", "已延期")]

_FONT_CANDIDATES_REGULAR = [
    "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyh.ttf",
    "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simsun.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/System/Library/Fonts/PingFang.ttc",
]
_FONT_CANDIDATES_BOLD = [
    "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/simhei.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Bold.otf",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
]


# 常规目录下按文件名模式补充发现 CJK 字体（候选清单没命中时的兜底）
_FONT_SCAN_DIRS = [
    "C:/Windows/Fonts",
    "/usr/share/fonts", "/usr/local/share/fonts",
    "/System/Library/Fonts",
]
_FONT_SCAN_PATTERNS = (
    "msyh", "simhei", "simsun", "notosanscjk", "notoserifcjk",
    "sourcehansans", "wqy", "droidsansfallback", "pingfang", "harmonyos",
)


def _discover_cjk_font() -> Optional[str]:
    for d in _FONT_SCAN_DIRS:
        if not os.path.isdir(d):
            continue
        try:
            for root, _dirs, files in os.walk(d):
                for f in files:
                    low = f.lower()
                    if low.endswith((".ttf", ".ttc", ".otf")) and any(p in low for p in _FONT_SCAN_PATTERNS):
                        return os.path.join(root, f)
        except OSError:
            continue
    return None


def _can_render_cjk(font) -> bool:
    """字体是否真的带汉字字形（拿「中」探测；缺字形的字体 getmask 全空）。"""
    try:
        mask = font.getmask("中")
        return mask.getbbox() is not None
    except Exception:
        return False


def _load_pil_font(size: int, bold: bool = False):
    """按候选清单→环境变量→目录扫描找中文字体；全部落空返回 None（调用方退回表格），
    绝不回退 PIL 默认字体——它不含中文，画出来是方块。"""
    from PIL import ImageFont
    cands = ([os.environ.get("APP_CJK_FONT")] if os.environ.get("APP_CJK_FONT") else []) \
        + (_FONT_CANDIDATES_BOLD if bold else []) + _FONT_CANDIDATES_REGULAR
    for path in cands:
        if path and os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                if _can_render_cjk(font):
                    return font
            except OSError:
                continue
    found = _discover_cjk_font()
    if found:
        try:
            font = ImageFont.truetype(found, size)
            if _can_render_cjk(font):
                return font
        except OSError:
            pass
    return None


def _text_wh(draw, text: str, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def _wrap_by_width(draw, text: str, font, max_w: int):
    lines, cur = [], ""
    for ch in str(text or ""):
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        w, _ = _text_wh(draw, cur + ch, font)
        if w > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines or [""]


def _render_milestone_image(milestones):
    """把里程碑画成横向时间轴 PNG，返回 PIL.Image；PIL 不可用/出错时返回 None（调用方退回表格）。"""
    if not milestones:
        return None
    try:
        from PIL import Image, ImageDraw

        n = len(milestones)
        margin = 90
        spacing = 175
        width = max(760, margin * 2 + (n - 1) * spacing)
        height = 250
        baseline_y = 78
        node_w = min(spacing - 16, 160)

        f_name = _load_pil_font(16, bold=True)
        f_date = _load_pil_font(13)
        f_legend = _load_pil_font(13)
        if not (f_name and f_date and f_legend):
            return None  # 没有可用中文字体 → 退回表格，避免方块乱码

        img = Image.new("RGB", (width, height), "white")
        d = ImageDraw.Draw(img)

        # 轴线
        d.line([(margin, baseline_y), (width - margin, baseline_y)], fill=(220, 223, 230), width=3)

        def node_x(i):
            if n == 1:
                return width // 2
            return margin + i * spacing

        for i, m in enumerate(milestones):
            x = node_x(i)
            status = m.get("status", "planning")
            rgb = _MS_DOT_RGB.get(status, _MS_DOT_RGB["planning"])
            # 名称（轴线上方，自动换行，加粗）
            name_lines = _wrap_by_width(d, m.get("name", ""), f_name, node_w)
            ny = baseline_y - 18
            for ln in reversed(name_lines):
                w, h = _text_wh(d, ln, f_name)
                d.text((x - w / 2, ny - h), ln, font=f_name, fill=(48, 49, 51))
                ny -= h + 3
            # 节点圆点（外圈白 + 彩色实心）
            r = 9
            d.ellipse([x - r - 2, baseline_y - r - 2, x + r + 2, baseline_y + r + 2], fill=(255, 255, 255))
            d.ellipse([x - r, baseline_y - r, x + r, baseline_y + r], fill=rgb)
            # 日期（轴线下方）
            date = m.get("date", "") or "未定"
            w, h = _text_wh(d, date, f_date)
            d.text((x - w / 2, baseline_y + 16), date, font=f_date, fill=(144, 147, 153))

        # 图例
        lx = margin
        ly = height - 34
        for status, label in _MS_LEGEND:
            rgb = _MS_DOT_RGB[status]
            d.ellipse([lx, ly + 3, lx + 11, ly + 14], fill=rgb)
            d.text((lx + 16, ly), label, font=f_legend, fill=(96, 98, 102))
            tw, _ = _text_wh(d, label, f_legend)
            lx += 16 + tw + 26

        return img
    except Exception:
        return None


# ─── 附加自由表格（RichGrid）→ 独立工作表 ──────────────────────────

def _safe_sheet_name(name: str, used: set) -> str:
    base = re.sub(r"[\[\]\:\*\?\/\\]", " ", str(name or "")).strip() or "附加表格"
    base = base[:28]
    cand = base
    k = 2
    while cand in used or not cand:
        cand = f"{base[:25]}-{k}"
        k += 1
    used.add(cand)
    return cand


def build_special_xlsx(special) -> io.BytesIO:
    """传入 Special ORM（含 content/tasks/risks），返回美观 xlsx 的 BytesIO。"""
    label = _kind_label(special.kind)
    content = special.content
    wb = Workbook()
    ws = wb.active
    ws.title = label
    ws.sheet_view.showGridLines = False

    for i, w in enumerate(_COL_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # pending＝已经排到但还没落笔的章节标题，见 _flush_section
    state = {"row": 1, "pending": None}

    def _fill(r, c1, c2, color):
        for c in range(c1, c2 + 1):
            ws.cell(row=r, column=c).fill = PatternFill("solid", fgColor=color)

    def band(text, *, fill=None, font_color="262626", bold=False, size=11,
             align="left", height=20, italic=False, wrap=True):
        r = state["row"]
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=_NCOL)
        c = ws.cell(row=r, column=1, value=text)
        c.font = Font(name=_FONT, bold=bold, size=size, color=font_color, italic=italic)
        c.alignment = Alignment(horizontal=align, vertical="center", wrap_text=wrap)
        if fill:
            _fill(r, 1, _NCOL, fill)
        ws.row_dimensions[r].height = height
        state["row"] += 1

    def section(title):
        """把章节标题挂起，等真有内容落笔时再写（见 _flush_section）。"""
        state["pending"] = title

    def _flush_section():
        """写正文前补上待写的章节标题。

        「空分段不占章节编号」是页面 / 周报 / 导出三处共同的口径，可标题必须写在
        内容之前——所以先挂起、等第一笔内容落笔时再补。原先是先写标题、发现空了
        再补一行「—」，于是模板里多一个空分段，Excel 的章节号就和周报对不上，
        而这种错没人会当成 bug 去查。
        """
        title = state.get("pending")
        if not title:
            return
        state["pending"] = None
        band(title, fill=_SECTION, font_color=_BRAND_DARK, bold=True, size=12, height=22)

    def narrative(text):
        _flush_section()
        r = state["row"]
        text = text or "—"
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=_NCOL)
        c = ws.cell(row=r, column=1, value=text)
        c.font = Font(name=_FONT, size=11, color="262626")
        c.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
        c.border = _BORDER
        cap = sum(_COL_WIDTHS) - 2
        ws.row_dimensions[r].height = max(20, min(260, _cell_lines(text, cap) * 16 + 4))
        state["row"] += 1

    def gap():
        state["row"] += 1

    def table(col_specs, headers, rows, status_col=None, center_cols=None):
        """col_specs: [(c1,c2), ...] 每个逻辑列在 6 列网格中的物理列区间。
        status_col: 逻辑列下标（从 0 起），该列文字按状态着色 + 整行变浅绿。
        center_cols: 需要居中的逻辑列下标集合（默认 status / 第 0 列居中）。"""
        _flush_section()
        center = set(center_cols or [])
        # 列容量（字符单位）
        caps = [sum(_COL_WIDTHS[c1 - 1:c2]) for (c1, c2) in col_specs]

        # 表头
        r = state["row"]
        for j, (c1, c2) in enumerate(col_specs):
            if c2 > c1:
                ws.merge_cells(start_row=r, start_column=c1, end_row=r, end_column=c2)
            for cc in range(c1, c2 + 1):
                cell = ws.cell(row=r, column=cc, value=headers[j] if cc == c1 else None)
                cell.fill = PatternFill("solid", fgColor=_BRAND)
                cell.font = Font(name=_FONT, bold=True, color="FFFFFF", size=10)
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                cell.border = _BORDER
        ws.row_dimensions[r].height = 20
        state["row"] += 1

        # 数据行
        for i, dr in enumerate(rows):
            r = state["row"]
            status_txt = ""
            if status_col is not None and status_col < len(dr):
                status_txt = str(dr[status_col] or "").strip()
            zebra = (i % 2 == 1)
            row_fill = _STATUS_FILL.get(status_txt) or (_ZEBRA if zebra else None)
            max_lines = 1
            for j, (c1, c2) in enumerate(col_specs):
                if c2 > c1:
                    ws.merge_cells(start_row=r, start_column=c1, end_row=r, end_column=c2)
                val = "" if j >= len(dr) or dr[j] is None else str(dr[j])
                max_lines = max(max_lines, _cell_lines(val, caps[j]))
                is_status = (status_col is not None and j == status_col)
                fcolor = _STATUS_FONT.get(val.strip(), "262626") if is_status else "262626"
                halign = "center" if (j in center or is_status) else "left"
                for cc in range(c1, c2 + 1):
                    cell = ws.cell(row=r, column=cc, value=val if cc == c1 else None)
                    cell.font = Font(name=_FONT, size=10, color=fcolor, bold=is_status)
                    cell.alignment = Alignment(horizontal=halign, vertical="center", wrap_text=True)
                    cell.border = _BORDER
                    if row_fill:
                        cell.fill = PatternFill("solid", fgColor=row_fill)
            ws.row_dimensions[r].height = max(18, min(160, max_lines * 15 + 3))
            state["row"] += 1

    # ===== 标题条 =====
    band(f"【{label}周报】{special.name or ''}", fill=_BRAND_DARK,
         font_color="FFFFFF", bold=True, size=16, align="center", height=30)
    band(f"责任人：{special.owner or '-'}      导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
         fill=_BRAND, font_color="FFFFFF", size=10, align="center", height=20)
    gap()

    kept_images = []  # 持有 BytesIO 引用直到 wb.save，避免被 GC
    # 6 列等分映射（序号/内容/进展/责任人/闭环/状态）
    six = [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6)]

    def render_milestones(milestones=None):
        """内置「计划」与自定义里程碑分段共用：两者只是取数不同，画法必须一样。"""
        if milestones is None:
            milestones = special_layout.loads(getattr(content, "milestones_json", None), [])
        milestones = [m for m in milestones if isinstance(m, dict)]
        if not milestones:
            return False
        _flush_section()
        ms_img = _render_milestone_image(milestones)
        if ms_img is not None:
            r = state["row"]
            bio = io.BytesIO()
            ms_img.save(bio, format="PNG")
            bio.seek(0)
            ws.add_image(XLImage(bio), f"A{r}")
            kept_images.append(bio)
            # 预留行高（默认行高约 18px），让后续章节不与图片重叠
            state["row"] += max(8, math.ceil(ms_img.height / 18) + 2)
        else:
            # PIL 不可用：退回表格形式
            rows = [[m.get("name", ""), m.get("date", ""),
                     _MS_STATUS_LABEL.get(m.get("status", "planning"), m.get("status", ""))]
                    for m in milestones]
            table([(1, 3), (4, 4), (5, 6)], ["里程碑", "日期", "状态"], rows,
                  status_col=2, center_cols={1, 2})
        return True

    def render_items(rows_src, content_header):
        if not rows_src:
            return False
        rows = []
        for idx, it in enumerate(rows_src, 1):
            st = "已闭环" if (it.status or "open") == "closed" else "进行中"
            rows.append([idx, _strip_html(it.content), _strip_html(it.progress),
                         it.owner or "", it.planned_close_date or "", st])
        table(six, ["序号", content_header, "当前进展", "责任人", "计划闭环", "状态"],
              rows, status_col=5, center_cols={0, 3, 4})
        return True

    def render_formation():
        obj = special_layout.loads(getattr(content, "formation_json", None), {})
        headers = [str(h) for h in (obj.get("headers") or [])]
        rows = [[_cell_str(c) for c in (r or [])] for r in (obj.get("rows") or [])]
        rows = [r for r in rows if any(x.strip() for x in r)]
        if not rows:
            return False
        ncol = max(len(headers), max(len(r) for r in rows))
        table(_partition_cols(ncol), headers or [""] * ncol, rows)
        return True

    def render_block_images(block):
        items = [i for i in (block.get("items") or [])
                 if isinstance(i, dict) and i.get("file")]
        if not items:
            return False
        _flush_section()
        drawn = 0
        for im in items:
            if _place_image(ws, state, UPLOAD_ROOT / str(special.id) / str(im["file"])):
                drawn += 1
        if items and not drawn:
            # SVG 等 openpyxl 塞不进去的格式：说清楚，别让人以为图丢了
            narrative(f"（{len(items)} 张图片，Excel 无法内嵌，请见系统页面）")
        return bool(items)

    # ===== 各分段按「版式」顺序输出 =====
    # 标题与顺序全部来自 special_layout；自定义表格因列宽差异过大仍走独立工作表，
    # 但页签按分段序号命名，主表在对应位置留一行指引，顺序不丢。
    used_names = {ws.title}
    grid_sheets = []          # [(序号, 标题, grid)] 主表遍历完再建，保证页签顺序
    n = 0
    for sec in special_layout.resolve_sections(special):
        n += 1
        title = f"{_cn_index(n)}、{sec.title}"
        if sec.is_custom and sec.kind == "grid":
            headers, rows = _grid_cells(sec.block)
            if not rows:
                n -= 1
                continue
            sheet_name = _safe_sheet_name(f"{n}.{sec.title}", used_names)
            grid_sheets.append((sheet_name, sec.title, sec.block))
            section(title)
            narrative(f"→ 见工作表「{sheet_name}」（{len(rows)} 行）")
            gap()
            continue

        section(title)
        ok = True
        if sec.is_custom and sec.kind == "text":
            body = _strip_html(sec.block.get("html") or "")
            ok = bool(body.strip())
            if ok:
                narrative(body)
        elif sec.is_custom and sec.kind == "milestones":
            ok = render_milestones(sec.block.get("milestones") or [])
        elif sec.is_custom:
            ok = render_block_images(sec.block)
        elif sec.key in _TEXT_FIELD:
            body = _strip_html(getattr(content, _TEXT_FIELD[sec.key], "") or "") if content else ""
            ok = bool(body.strip())
            if ok:
                narrative(body)
        elif sec.key == "plan":
            ok = render_milestones()
        elif sec.key == "panorama":
            path = getattr(content, "panorama_image_path", "") if content else ""
            ok = bool(path)
            if ok:
                _flush_section()
            if ok and not _place_image(ws, state, UPLOAD_ROOT.parent / path):
                narrative(f"（{getattr(content, 'panorama_image_name', '') or '全景图'}："
                          f"Excel 无法内嵌该格式，请见系统页面）")
        elif sec.key == "risks":
            ok = render_items(special.risks or [], "问题内容")
        elif sec.key == "tasks":
            ok = render_items(sorted(special.tasks or [],
                                     key=lambda t: (t.sort_order or 0, t.id)), "事务内容")
        elif sec.key == "formation":
            ok = render_formation()
        else:
            ok = False
        if not ok:
            # 标题还挂着没落笔，撤回即可；编号让给下一段，与周报保持同一套章节号
            state["pending"] = None
            n -= 1
            continue
        gap()

    for sheet_name, sec_title, grid in grid_sheets:
        _render_extra_grid_sheet(wb, grid, sheet_name, sec_title)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# 内置文本类分段 -> content 上的列（与 routers/specials.py 的同名表一致）
_TEXT_FIELD = {"goal": "goal", "progress": "progress_summary", "help": "help_request"}
_CN_DIGITS = "零一二三四五六七八九"


def _cn_index(n: int) -> str:
    if n <= 0:
        return str(n)
    if n < 10:
        return _CN_DIGITS[n]
    if n < 20:
        return "十" + (_CN_DIGITS[n - 10] if n > 10 else "")
    tens, ones = divmod(n, 10)
    return _CN_DIGITS[tens] + "十" + (_CN_DIGITS[ones] if ones else "")


def _cell_str(c) -> str:
    if isinstance(c, dict):
        return str(c.get("text") or "")
    return "" if c is None else str(c)


def _grid_cells(block: dict):
    """自定义表格 → (表头名, 非空数据行)。判断"这段有没有内容"用。"""
    headers = []
    for h in (block.get("headers") or []):
        if isinstance(h, dict):
            headers.extend([str(h.get("text") or "")] * max(1, int(h.get("colspan") or 1)))
        else:
            headers.append(str(h or ""))
    rows = [[_cell_str(c) for c in (r or [])] for r in (block.get("rows") or [])]
    return headers, [r for r in rows if any(x.strip() for x in r)]


def _partition_cols(ncol: int):
    """ncol 个逻辑列摊到主表的 6 个物理列上；超过 6 列则 1:1 直接展开。"""
    if ncol >= _NCOL:
        return [(i + 1, i + 1) for i in range(ncol)]
    base, extra = divmod(_NCOL, ncol)
    spans, c = [], 1
    for i in range(ncol):
        w = base + (1 if i < extra else 0)
        spans.append((c, c + w - 1))
        c += w
    return spans


def _place_image(ws, state, path) -> bool:
    """把磁盘上的图片放到当前行并预留行高；放不进去（SVG/缺 PIL/文件丢失）返回 False。"""
    try:
        p = pathlib.Path(path).resolve()
        if not p.exists() or p.suffix.lower() == ".svg":
            return False
        img = XLImage(str(p))
    except Exception:
        return False
    try:
        max_w = 700.0
        if img.width and img.width > max_w:
            ratio = max_w / float(img.width)
            img.width = int(img.width * ratio)
            img.height = int(img.height * ratio)
        r = state["row"]
        ws.add_image(img, f"A{r}")
        state["row"] += max(6, math.ceil((img.height or 200) / 18) + 2)
        return True
    except Exception:
        return False


def _cell_font_spec(cell: dict) -> dict:
    """单元格格式 → openpyxl 的 Font/Fill 参数。

    与 routers/specials._fmt_css、前端 utils/gridFormat.js 是同一张表的三种出口：
    页面要 CSS、周报要 CSS、Excel 要字体名 + 磅值。白名单外的值退回默认，
    因为 openpyxl 对非法字号会直接抛，而一次导出失败比丢个字号严重得多。
    """
    font_key = str(cell.get("font") or "")
    name = enums.GRID_FONTS.get(font_key, {}).get("xlsx") or _FONT
    try:
        px = int(cell.get("size") or 0)
    except (TypeError, ValueError):
        px = 0
    # px → 磅：Excel 用磅（1px ≈ 0.75pt）。默认 10 磅是本表原有的正文字号
    size = round(px * 0.75, 1) if px in enums.GRID_FONT_SIZES else 10
    bg = str(cell.get("bg") or "")
    return {
        "name": name,
        "size": size,
        "color": _hex_to_rgb6(cell.get("color", "")),
        "bold": bool(cell.get("bold")),
        "italic": bool(cell.get("italic")),
        "underline": "single" if cell.get("underline") else None,
        "bg": _hex_to_rgb6(bg, "") if bg in enums.GRID_CELL_BG and bg else "",
    }


def _render_extra_grid_sheet(wb, grid, sheet_name, title):
    """把一个 RichGrid（{title, headers, rows, colWidths}）渲染成独立工作表。

    - 表头按 colspan 合并、**加粗**、华为红底白字；
    - 正文单元格保留对齐（left/center）与字体颜色；点灯列（colTypes=light）按取值上底色；
    - 列宽来自 colWidths（px → Excel 字符宽，约 px/7）。
    兼容旧格式：headers 为 str[]、rows 为 str[][]。

    独立工作表而非内联进主表：主表列宽是为叙述段和 6 列事务表定的
    （[6,36,30,12,14,10]），把一张 5~8 列、列宽各异的自由表格塞进去必然被压变形。
    页签名由调用方按分段序号给出，故工作表顺序与页面分段顺序一致。
    """
    raw_headers = grid.get("headers") or []
    rows = grid.get("rows") or []
    col_types = grid.get("colTypes") or []

    hdrs = []
    for h in raw_headers:
        if isinstance(h, dict):
            hdrs.append({
                **h,
                "text": str(h.get("text", "")),
                "colspan": max(1, int(h.get("colspan", 1) or 1)),
                "align": h.get("align") or "center",
            })
        else:
            hdrs.append({"text": str(h), "colspan": 1, "align": "center"})

    body_cols = sum(h["colspan"] for h in hdrs)
    if body_cols <= 0:
        body_cols = max((len(r) for r in rows if isinstance(r, list)), default=1)
        hdrs = [{"text": f"列{i + 1}", "colspan": 1, "align": "center"} for i in range(body_cols)]

    ws = wb.create_sheet(title=sheet_name)
    ws.sheet_view.showGridLines = False

    col_widths = grid.get("colWidths") or []

    def _px(i, default=130):
        if i < len(col_widths):
            try:
                return float(col_widths[i])
            except (TypeError, ValueError):
                return default
        return default

    for c in range(1, body_cols + 1):
        ws.column_dimensions[get_column_letter(c)].width = max(6, round(_px(c - 1) / 7.0, 1))

    r = 1
    # 标题条
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=body_cols)
    tc = ws.cell(row=r, column=1, value=title)
    tc.font = Font(name=_FONT, bold=True, size=13, color="FFFFFF")
    tc.alignment = Alignment(horizontal="left", vertical="center")
    for cc in range(1, body_cols + 1):
        ws.cell(row=r, column=cc).fill = PatternFill("solid", fgColor=_BRAND_DARK)
    ws.row_dimensions[r].height = 24
    r += 1

    # 表头（按 colspan 合并、加粗）
    col = 1
    for h in hdrs:
        c1, c2 = col, col + h["colspan"] - 1
        if c2 > c1:
            ws.merge_cells(start_row=r, start_column=c1, end_row=r, end_column=c2)
        for cc in range(c1, c2 + 1):
            cell = ws.cell(row=r, column=cc, value=h["text"] if cc == c1 else None)
            cell.fill = PatternFill("solid", fgColor=_BRAND)
            # 表头恒为品牌红底白字粗体：只让它跟随字体与字号，字色/底色不跟
            hf = _cell_font_spec(h)
            cell.font = Font(name=hf["name"], bold=True, color="FFFFFF", size=hf["size"],
                             italic=hf["italic"], underline=hf["underline"])
            cell.alignment = Alignment(horizontal=h["align"], vertical="center", wrap_text=True)
            cell.border = _BORDER
        col = c2 + 1
    ws.row_dimensions[r].height = 20
    r += 1

    # 数据行
    for i, row in enumerate(rows):
        cells = row if isinstance(row, list) else []
        zebra = (i % 2 == 1)
        max_lines = 1
        for c in range(1, body_cols + 1):
            cd = cells[c - 1] if c - 1 < len(cells) else None
            if isinstance(cd, dict):
                text = str(cd.get("text", ""))
                align = cd.get("align") or "left"
            else:
                text = "" if cd is None else str(cd)
                align = "left"
                cd = {}
            fmt = _cell_font_spec(cd)
            cap = max(4, int(_px(c - 1) / 7))
            max_lines = max(max_lines, _cell_lines(text, cap))
            # 点灯列：取值命中红/黄/绿则整格上底色 + 同色粗体，与页面和周报一致
            light = None
            if c - 1 < len(col_types) and col_types[c - 1] == "light":
                light = enums.GRID_LIGHT_COLORS.get(text.strip())
            cell = ws.cell(row=r, column=c, value=text)
            cell.font = Font(name=fmt["name"], size=fmt["size"],
                             color=_LIGHT_FONT[light] if light else fmt["color"],
                             bold=bool(light) or fmt["bold"],
                             italic=fmt["italic"], underline=fmt["underline"])
            cell.alignment = Alignment(horizontal="center" if light else align,
                                       vertical="center", wrap_text=True)
            cell.border = _BORDER
            if light:
                cell.fill = PatternFill("solid", fgColor=_LIGHT_FILL[light])
            elif fmt["bg"]:
                cell.fill = PatternFill("solid", fgColor=fmt["bg"])
            elif zebra:
                cell.fill = PatternFill("solid", fgColor=_ZEBRA)
        ws.row_dimensions[r].height = max(18, min(180, max_lines * 15 + 3))
        r += 1
