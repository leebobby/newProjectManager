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

# 「已变更」＝这条需求本轮不做了（范围变更 / 挪出迭代），是行级语义而不只是某个子项的状态。
# 统计口径：整行**排除**在度量之外，不按「变更后仍在做，算一半」加权——
# 后者会让一条已经不做的需求继续把平均完成度往下拽，看着像团队没干活。
PROGRESS_CHANGED = "已变更"


def is_changed_row(row, progress_fields) -> bool:
    """任一进展子项标了「已变更」就算整行已变更。

    判定放这里是因为 metrics（度量看板）与 domains（领域总览）两处统计都要用，
    各写一份迟早分叉——一个看板把它算进去、另一个不算，两边对不上却都不报错。
    取「任一」而不是「全部」：改口径只需动这一行。
    """
    return any(getattr(row, f, None) == PROGRESS_CHANGED for f in progress_fields)

# ── 需求优先级（统一口径：P0-P3）──────────────────────────────────────────────
PRIORITIES = ("P0", "P1", "P2", "P3")
PRIORITY_DEFAULT = "P2"
# 产品需求历史用「高/中/低」，统一时按此映射到 P 级（导入 / 数据迁移复用）
PRIORITY_LEGACY_MAP = {"高": "P1", "中": "P2", "低": "P3"}

# ── 事务 / 风险条目状态 ───────────────────────────────────────────────────────
TASK_STATUSES = ("open", "closed")

# ── 领域管理 · 遗留问题（事务/风险的状态词表与客户面问题共用，见下方 CUSTOMER_ISSUE_STATUSES）──
# 遗留问题（domain_legacy_issues）：pending 是业务方指定的写法，不要"顺手"改成挂起——
# 页面、导出、筛选三处按同一字面量比对，任何一处大小写不同都会静默漏算
DOMAIN_LEGACY_STATUSES = ("OPEN", "CLOSED", "pending")
DOMAIN_LEGACY_STATUS_DEFAULT = "OPEN"
# 这两张表沿用「高/中/低」而非 P0-P3：它们是跟踪事项不是需求，与需求优先级不同口径
DOMAIN_TASK_PRIORITIES = ("高", "中", "低")
DOMAIN_TASK_PRIORITY_DEFAULT = "中"
# 事务与风险跟踪的「风险等级」：与优先级同词表但**不是同一个口径**——
# 优先级答的是"先处理哪个"，等级答的是"真砸下来有多疼"。一条低优先级的高等级风险
# （短期不动、但爆了很惨）是常态，合成一列就再也表达不出来。
# 没有默认值：这张表里事务行和风险行混着，事务本来就没有风险等级，
# 默认成「中」会让半屏事务行挂上一个凭空捏的等级，而没人会当 bug 报。
DOMAIN_RISK_LEVELS = ("高", "中", "低")

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



def norm_domain_legacy_status(v, *, partial: bool = False) -> Optional[str]:
    """遗留问题状态：大小写不敏感输入，一律归一到 DOMAIN_LEGACY_STATUSES 的字面量。

    归一而不是直接收原串，是因为 "Pending"/"pending"/"PENDING" 落库后按字面量分组统计
    会变成三档；出口只有一种写法，前端下拉才和统计对得上。
    """
    if _is_blank(v):
        return None if partial else DOMAIN_LEGACY_STATUS_DEFAULT
    s = str(v).strip()
    for c in DOMAIN_LEGACY_STATUSES:
        if s.lower() == c.lower():
            return c
    raise ValueError(f"状态「{v}」非法，应为 {'/'.join(DOMAIN_LEGACY_STATUSES)} 之一")


def norm_domain_priority(v, *, partial: bool = False) -> Optional[str]:
    """领域跟踪事项优先级：高/中/低（与需求的 P0-P3 是两套口径，不互转）。"""
    return _norm_choice(v, DOMAIN_TASK_PRIORITIES, DOMAIN_TASK_PRIORITY_DEFAULT,
                        "优先级", partial=partial)


def norm_domain_risk_level(v, *, partial: bool = False) -> str:
    """风险等级：高/中/低，**空是合法取值**（事务行没有等级）。

    不走 _norm_choice：那一套把空值当"不修改"（partial）或"落默认值"，
    而这里空既不是不修改也不该有默认——留空就是留空，一律归一成空串，
    这样"清掉等级"和"没填过等级"在库里是同一个值，统计时不用分两种情况判。
    """
    if _is_blank(v):
        return ""
    s = str(v).strip()
    if s in DOMAIN_RISK_LEVELS:
        return s
    raise ValueError(f"风险等级「{v}」非法，应为 {'/'.join(DOMAIN_RISK_LEVELS)} 之一或留空")

# ── 问题单跟踪：合入状态（issue_tracks）──────────────────────────────────────
# 问题单本身的状态来自 DTS（采集回来的「进展」列），这里这一档是**我们自己的**
# 合入节奏：从"看过了"到"代码进版本了"。两者答的是两个问题，不要合并——
# DTS 说这单还开着，不等于我们这边已经安排了合入。
# 「不合入」是显式的一档（评估后决定本版本不合），与「未开始」不是一回事：
# 前者是结论，后者是还没看；合并掉的话，看板上分不出"没人管"和"决定不做"。
ISSUE_MERGE_STATUSES = ("未开始", "分析中", "开发中", "已合入", "不合入")
ISSUE_MERGE_STATUS_DEFAULT = "未开始"


def norm_issue_merge_status(v, *, partial: bool = False) -> Optional[str]:
    return _norm_choice(v, ISSUE_MERGE_STATUSES, ISSUE_MERGE_STATUS_DEFAULT,
                        "合入状态", partial=partial)


# ── 关键特性交付状态（key_features）───────────────────────────────────────────
# 从"最成熟"到"最早期"排序；前端点灯颜色须与本顺序一致。
KEY_FEATURE_STATUSES = ("可商用", "beta验证", "测试", "开发", "设计", "分析")
KEY_FEATURE_STATUS_DEFAULT = "分析"


# ── 版本管理 · 主干 / 分支 ────────────────────────────────────────────────────
# 版本体系是三层：大版本（C10SPC100，号段）→ 版本（C10SPC101，真正发布的一级）
# → 迭代版本（C10SPC101B001，构建）。主干/分支是**大版本**的属性：
# C10SPC100 在 C10SPC110 还没出版本时跑在主干上，C110 一开始发版，C100 就被拉成分支。
# 不变量「同一项目同一时刻只有一个大版本在主干」由服务端保证（见 routers/major_versions.py
# 的 set_master），不要做成两个各自独立的开关——手点必然出现两个主干或零个主干，
# 而这种错没人会当 bug 报。
VERSION_LINES = ("master", "branch")
VERSION_LINE_DEFAULT = "master"
VERSION_LINE_LABELS = {"master": "主干", "branch": "分支"}


def norm_version_line(v, *, partial: bool = False) -> Optional[str]:
    """大版本的主干/分支状态。"""
    return _norm_choice(v, VERSION_LINES, VERSION_LINE_DEFAULT, "主干/分支", partial=partial)


# ── 客户面支撑方式 ────────────────────────────────────────────────────────────
# 现场支撑＝人到战场（原来的「出差」就是这一档，历史数据全部按它回填）；
# 线上支撑＝远程接入 / 电话会议，人没动地方。两者的工作量口径不同：现场按日历天
# 连续投入，线上往往是一天里的几小时，所以人天要允许手填（见 models.BusinessTrip
# 的 man_days），不要一律按天数推。
SUPPORT_MODES = ("现场支撑", "线上支撑")
SUPPORT_MODE_DEFAULT = "现场支撑"


def norm_support_mode(v, *, partial: bool = False) -> Optional[str]:
    """支撑方式：现场 / 线上。"""
    return _norm_choice(v, SUPPORT_MODES, SUPPORT_MODE_DEFAULT, "支撑方式", partial=partial)


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

# ─── 专项总览：风险点灯 ─────────────────────────────────────────────────────
# 总览表里每个专项一盏灯。**四档，但只有三档能手工指定**：
#   red / yellow / green  —— 人可以指定，也可以由 _auto_light 推出来
#   gray（未评估）        —— 只可能是自动推出来的：这个专项一条风险行都没登记
# 「一条风险都没登记」不能算绿：那是"还没人评过"，不是"评过、没风险"。
# 记成绿的话，最该被追着去填风险的那几个专项，在总览上看着比谁都干净
# （同 domains 的「超期未知」vs「无超期」：算不出来要如实说算不出来）。
SPECIAL_OVERVIEW_LIGHTS = ("red", "yellow", "green")
SPECIAL_OVERVIEW_LIGHT_AUTO = "gray"
SPECIAL_OVERVIEW_LIGHT_LABELS = {
    "red": "红", "yellow": "黄", "green": "绿", "gray": "未评估",
}
# 手工填灯时认的写法。前端下拉只给 red/yellow/green 三个 key，这张表是给
# 将来可能的导入/接口直填留的余地——不要在这里加 gray。
_LIGHT_ALIASES = {
    "红": "red", "红灯": "red", "R": "red",
    "黄": "yellow", "黄灯": "yellow", "Y": "yellow",
    "绿": "green", "绿灯": "green", "G": "green",
}


def norm_special_light(v) -> str:
    """总览点灯的手工覆盖值。**空是合法取值**，含义是「回到自动」。

    因此不走 `_norm_choice`：后者把空当作"不修改"或"落默认值"，
    而这里空既不是不修改、也不该有默认——清空就是清空
    （同 `norm_domain_risk_level()` 的取舍）。
    """
    if v is None:
        return ""
    s = str(v).strip()
    if not s:
        return ""
    if s in SPECIAL_OVERVIEW_LIGHTS:
        return s
    key = _LIGHT_ALIASES.get(s) or _LIGHT_ALIASES.get(s.upper())
    if key:
        return key
    raise ValueError(
        f"点灯「{v}」非法，应为 {'/'.join(SPECIAL_OVERVIEW_LIGHTS)} 之一，或留空＝自动")


# 导出侧：一格点灯文字 → 颜色档位 key（颜色表在 brand.LIGHT_FILLS / LIGHT_TEXTS）。
# 自由表格的点灯列与专项总览的风险灯**共用这一份**——两处各写一份的表现是
# 同一盏灯在 Excel 里是绿的、在 PPT 里没颜色，而两份文件单独看都挺正常。
_LIGHT_TEXT_TO_KEY = dict(GRID_LIGHT_COLORS)
_LIGHT_TEXT_TO_KEY.update({v: k for k, v in SPECIAL_OVERVIEW_LIGHT_LABELS.items()})


def light_key_of(text) -> str:
    """点灯文字 → red/yellow/green/gray；认不出返回 ""（那一格不着色）。"""
    return _LIGHT_TEXT_TO_KEY.get(str(text or "").strip(), "")
