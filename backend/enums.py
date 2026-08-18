"""集中管理业务枚举（状态 / 优先级）的单一来源。

历史上这些取值以「注释文档化的自由字符串」散落在各 router 与前端，造成：
- 两张需求表优先级口径不一致（领域需求 P0-P3 vs 产品需求 高/中/低）；
- 模型注释与前端实际可选值漂移（如进展状态漏写「已变更」）；
- 聚合按精确字符串匹配，错字静默漏算且无人发现。

这里把权威词表收口到一处：Pydantic 层用 norm_* 校验/规范化输入，
导入路径复用同一份常量。**前端下拉值需与本文件保持一致。**
"""
from typing import Optional

# ── 交付进展状态（领域需求 / 产品需求共用，6 值）──────────────────────────────
PROGRESS_STATUSES = ("未开始", "进行中", "已完成", "已延期", "已变更", "不涉及")
PROGRESS_DEFAULT = "未开始"

# ── 需求优先级（统一口径：P0-P3）──────────────────────────────────────────────
PRIORITIES = ("P0", "P1", "P2", "P3")
PRIORITY_DEFAULT = "P2"
# 产品需求历史用「高/中/低」，统一时按此映射到 P 级（导入 / 数据迁移复用）
PRIORITY_LEGACY_MAP = {"高": "P1", "中": "P2", "低": "P3"}

# ── 事务 / 风险条目状态 ───────────────────────────────────────────────────────
TASK_STATUSES = ("open", "closed")

# ── 年度迭代状态 ─────────────────────────────────────────────────────────────
ITERATION_STATUSES = ("planning", "in_progress", "done")

# ── 客户面问题 / 关键事务 / 需求（customer_issues）───────────────────────────
# kind：一张表装三类。issue/demand 用全套字段（demand＝客户需求，录入时以
# 「需求:」前缀区分，与问题同栏展示）；task 只用 描述 + 预计时间 + 状态。
CUSTOMER_ISSUE_KINDS = ("issue", "task", "demand")
CUSTOMER_ISSUE_KIND_DEFAULT = "issue"
# 状态词表与 domain_risks 对齐，避免同一概念两套口径
CUSTOMER_ISSUE_STATUSES = ("OPEN", "CLOSED", "挂起")
CUSTOMER_ISSUE_STATUS_DEFAULT = "OPEN"
# 重要程度口径：重要紧急 / 重要 / 一般（旧词表用「紧急」，统一迁移为「重要」）
CUSTOMER_ISSUE_URGENCIES = ("重要紧急", "重要", "一般")
CUSTOMER_ISSUE_URGENCY_DEFAULT = "一般"
CUSTOMER_ISSUE_URGENCY_LEGACY = {"紧急": "重要"}
# 汇总页默认排序用：越紧急越靠前
CUSTOMER_ISSUE_URGENCY_RANK = {"重要紧急": 0, "重要": 1, "一般": 2}


def _is_blank(v) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


def norm_priority(v, *, partial: bool = False) -> Optional[str]:
    """规范化优先级：去空白、旧「高/中/低」自动转 P 级、校验白名单。

    - 空值：partial（Update 语义＝「不修改」）原样返回 None；否则落默认 P2。
    - 非法值：抛 ValueError（FastAPI 自动转 422）。
    """
    if _is_blank(v):
        return None if partial else PRIORITY_DEFAULT
    s = str(v).strip()
    s = PRIORITY_LEGACY_MAP.get(s, s).upper()
    if s in PRIORITIES:
        return s
    raise ValueError(
        f"优先级「{v}」非法，应为 {'/'.join(PRIORITIES)}（旧「高/中/低」会自动转 P1/P2/P3）"
    )


def norm_progress(v, *, partial: bool = False) -> Optional[str]:
    """规范化交付进展状态：去空白、校验白名单。空值规则同 norm_priority。"""
    if _is_blank(v):
        return None if partial else PROGRESS_DEFAULT
    s = str(v).strip()
    if s in PROGRESS_STATUSES:
        return s
    raise ValueError(f"进展状态「{v}」非法，应为 {'/'.join(PROGRESS_STATUSES)} 之一")


def _norm_choice(v, choices, default, label, *, partial=False, upper=False):
    """通用白名单规范化：空值按 partial 决定 None / 默认值，非法值抛 ValueError。"""
    if _is_blank(v):
        return None if partial else default
    s = str(v).strip()
    if upper:
        s = s.upper()
    if s in choices:
        return s
    raise ValueError(f"{label}「{v}」非法，应为 {'/'.join(choices)} 之一")


def norm_issue_kind(v, *, partial: bool = False) -> Optional[str]:
    return _norm_choice(v, CUSTOMER_ISSUE_KINDS, CUSTOMER_ISSUE_KIND_DEFAULT, "条目类型",
                        partial=partial)


def norm_issue_status(v, *, partial: bool = False) -> Optional[str]:
    """OPEN/CLOSED 大小写不敏感；「挂起」原样匹配。"""
    if _is_blank(v):
        return None if partial else CUSTOMER_ISSUE_STATUS_DEFAULT
    s = str(v).strip()
    if s in CUSTOMER_ISSUE_STATUSES:
        return s
    up = s.upper()
    if up in CUSTOMER_ISSUE_STATUSES:
        return up
    raise ValueError(f"状态「{v}」非法，应为 {'/'.join(CUSTOMER_ISSUE_STATUSES)} 之一")


def norm_issue_urgency(v, *, partial: bool = False) -> Optional[str]:
    """重要程度：旧「紧急」自动归一为「重要」，再走白名单校验。"""
    if _is_blank(v):
        return None if partial else CUSTOMER_ISSUE_URGENCY_DEFAULT
    s = CUSTOMER_ISSUE_URGENCY_LEGACY.get(str(v).strip(), str(v).strip())
    if s in CUSTOMER_ISSUE_URGENCIES:
        return s
    raise ValueError(f"重要程度「{v}」非法，应为 {'/'.join(CUSTOMER_ISSUE_URGENCIES)} 之一")


# ── 关键特性交付状态（key_features）───────────────────────────────────────────
# 从"最成熟"到"最早期"排序；前端点灯颜色须与本顺序一致。
KEY_FEATURE_STATUSES = ("可商用", "beta验证", "测试", "开发", "设计", "分析")
KEY_FEATURE_STATUS_DEFAULT = "分析"


def norm_key_feature_status(v, *, partial: bool = False) -> Optional[str]:
    return _norm_choice(v, KEY_FEATURE_STATUSES, KEY_FEATURE_STATUS_DEFAULT,
                        "交付状态", partial=partial)


# ── 专项详情页的内置分段（版式模板 / 分段配置的单一来源）───────────────────────
# 专项详情页 = 若干「分段」拼起来：这 8 个内置分段（各有专属交互，见
# SpecialDetail.vue）+ 任意个自定义分段（表格/文本框/图片，存 extra_grids_json）。
# 内置分段的标题可被 section_config_json 覆盖、可整段停用，顺序由
# section_order_json 决定——所以下面的 label 只是**默认**标题。
# {label} 运行时替换为「专项」或「攻关」。
# kind 决定导出/周报怎么渲染这一段，不要与自定义分段的 kind 混淆：
#   text=富文本单字段 / milestones=里程碑 / image=单图 / items=事务风险表 / grid=阵型
# 顺序即默认显示顺序，须与前端 FIXED_KEYS 一致。
SPECIAL_SECTIONS = (
    {"key": "goal", "label": "{label}目标", "kind": "text"},
    {"key": "plan", "label": "{label}计划", "kind": "milestones"},
    {"key": "progress", "label": "整体进展", "kind": "text"},
    {"key": "help", "label": "求助", "kind": "text"},
    {"key": "panorama", "label": "{label}全景图", "kind": "image"},
    {"key": "risks", "label": "风险和问题", "kind": "items"},
    {"key": "tasks", "label": "{label}事务", "kind": "items"},
    {"key": "formation", "label": "{label}阵型", "kind": "grid"},
)
SPECIAL_SECTION_KEYS = tuple(s["key"] for s in SPECIAL_SECTIONS)

# 自定义分段的形态。RichGrid 的列格式（colTypes）另有一套：text/select/date/light
# milestones＝时间轴分段，块内自带 [{name,date,status}]，与内置「计划」分段互不影响
SPECIAL_BLOCK_KINDS = ("grid", "text", "images", "milestones")
# RichGrid 列格式。light=点灯：取值同 select，但渲染成红黄绿色块
GRID_COL_TYPES = ("text", "select", "date", "light")
# 点灯取值 → 颜色档位。键为单元格文本（去空白后精确匹配），未命中不着色
GRID_LIGHT_COLORS = {
    "红": "red", "黄": "yellow", "绿": "green",
    "红灯": "red", "黄灯": "yellow", "绿灯": "green",
    "R": "red", "Y": "yellow", "G": "green",
}
GRID_LIGHT_DEFAULT_OPTIONS = ("绿", "黄", "红")

# 单元格 / 富文本的字体：**存 key 不存 CSS 串**。
# 页面要 CSS font-family、周报 HTML 要 CSS、Excel 要一个字体名，三处口径不同；
# 存成 CSS 串会逼着 Excel 端去反解析 font-family 列表（"'Microsoft YaHei', 微软雅黑,
# sans-serif" → 微软雅黑），一旦有人手改了串就静默丢字体。存 key 则三处各查各的表。
# 前端同名表在 frontend/src/utils/gridFormat.js，**两边必须同步**——
# 前端漏一项的后果与 GRID_COL_TYPES 一样：该字体每次加载被静默清成默认值。
GRID_FONTS = {
    "yahei": {"label": "微软雅黑", "css": "'Microsoft YaHei', 微软雅黑, sans-serif", "xlsx": "微软雅黑"},
    "simsun": {"label": "宋体", "css": "SimSun, 宋体, serif", "xlsx": "宋体"},
    "simhei": {"label": "黑体", "css": "SimHei, 黑体, sans-serif", "xlsx": "黑体"},
    "kaiti": {"label": "楷体", "css": "KaiTi, 楷体, serif", "xlsx": "楷体"},
    "fangsong": {"label": "仿宋", "css": "FangSong, 仿宋, serif", "xlsx": "仿宋"},
    "arial": {"label": "Arial", "css": "Arial, Helvetica, sans-serif", "xlsx": "Arial"},
    "times": {"label": "Times New Roman", "css": "'Times New Roman', Times, serif",
              "xlsx": "Times New Roman"},
}
# 字号（px）。Excel 的磅值≈px×0.75，换算在 xlsx_utils 里做
GRID_FONT_SIZES = (12, 13, 14, 16, 18, 22)
# 单元格底色候选（点灯列的着色优先于它）
GRID_CELL_BG = ("", "#FFF7E6", "#FEF0F0", "#F0F9EB", "#ECF5FF", "#F4F4F5")
