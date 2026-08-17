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
