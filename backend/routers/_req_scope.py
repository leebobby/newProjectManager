"""需求的**版本口径**：一处实现，度量看板与领域总览共用。

需求填的是**迭代版本**（构建号 C10SPC101B001），而人看的是**版本**（C10SPC101）——
所以「这个版本上有哪些需求」= 把该版本下所有构建的 id 收齐再匹配，
另外还得带上字符串回退：不少需求当年直接把版本号本身写进了 `planned_version`，
FK 还没反查上。两条规则少一条，同一个版本在两个页面上会给出不同的条数，
而两边看着都像对的（见 CLAUDE.md「版本：三层与主干/分支」）。
"""
from typing import Set

from sqlalchemy import false, or_

import models


def build_no_set(rv: models.ReleaseVersion) -> Set[str]:
    """该版本可能被写成的字符串：名下每个构建号，外加版本号本身。"""
    nos = {iv.version_no for iv in rv.iteration_versions if iv.version_no}
    if rv.version_no:
        nos.add(rv.version_no)
    return nos


def version_clause(model, rv: models.ReleaseVersion):
    """`model`（领域需求 / 产品需求）里命中版本 `rv` 的过滤条件。

    FK 命中优先；FK 为空时才看字符串，避免「FK 指到别的版本、字符串又恰好同名」
    的行被两个版本各算一次。
    """
    iv_ids = [iv.id for iv in rv.iteration_versions]
    nos = build_no_set(rv)
    return or_(
        model.target_version_id.in_(iv_ids) if iv_ids else false(),
        (model.target_version_id.is_(None)) &
        (model.planned_version.in_(nos) if nos else false()),
    )
