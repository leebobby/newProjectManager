"""需求的**进展口径**：一处实现，度量看板与「产品需求 ↔ 领域需求」拆解汇总共用。

领域需求 6 个进展子项、产品需求 7 个，字段名不同但判法是同一套：哪些取值算做完、
哪一行算「已变更」整行剔掉、加权完成度怎么算。两处各写一份的表现是同一条需求
在度量看板里算完成、在产品需求的拆解汇总里算没完成，而两边看着都对。

`routers/metrics.py` 以私有别名再导出这几个名字（`_WEIGHT` / `_is_done` …），
既有调用点与文档引用因此不变。
"""
import enums

#: 领域需求（iteration_requirements）的 6 个进展子项
DOMAIN_PROGRESS_FIELDS = [
    "progress_walkthrough", "progress_reverse", "progress_stc",
    "progress_coding", "progress_bbit", "progress_clarify",
]
#: 产品需求（iteration_product_requirements）的 7 个进展子项
PRODUCT_PROGRESS_FIELDS = [
    "progress_walkthrough", "progress_reverse", "progress_domain",
    "progress_coding", "progress_joint_debug", "progress_clarify",
    "progress_test_result",
]

WEIGHT = {
    "已完成": 1.0,
    "进行中": 0.5,
    "已延期": 0.0,
    "未开始": 0.0,
    # "不涉及" 不计入分母
    # "已变更" 不在表里是有意的：带它的行在 split_changed() 就整行被剔掉了，
    # 到不了这里。别再给它加权重——那等于把一条已经不做的需求重新算进平均完成度。
}


def completion_score(values: list) -> tuple:
    """返回 (得分, 计入分母的项数)。"""
    score = 0.0
    cnt = 0
    for v in values:
        if not v or v == "不涉及":
            continue
        cnt += 1
        score += WEIGHT.get(v, 0.0)
    return score, cnt


def row_completion(row, progress_fields: list) -> float:
    vals = [getattr(row, f, None) for f in progress_fields]
    score, cnt = completion_score(vals)
    return (score / cnt) if cnt else 0.0


def is_done(row, progress_fields: list) -> bool:
    """全部进展项 ∈ {已完成, 不涉及}。"""
    for f in progress_fields:
        v = getattr(row, f, None)
        if v == "不涉及" or v is None or v == "":
            continue
        if v != "已完成":
            return False
    return True


def is_delayed(row, progress_fields: list) -> bool:
    return any(getattr(row, f, None) == "已延期" for f in progress_fields)


def split_changed(rows: list, progress_fields: list) -> tuple:
    """剔掉「已变更」的行，返回 (计入统计的行, 被剔掉的条数)。

    先剔已变更、再按项目切（见各接口）：反过来的话 `unassigned` 里会混进
    本来就不该统计的已变更行，页面提示「有 N 条没填项目」，去补了却发现数字纹丝不动。
    """
    kept = [r for r in rows if not enums.is_changed_row(r, progress_fields)]
    return kept, len(rows) - len(kept)
