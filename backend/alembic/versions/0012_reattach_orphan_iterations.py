"""把没挂上「版本」的迭代版本重新接回去（0010 的自愈补丁）

Revision ID: 0012_reattach_orphan_iterations
Revises: 0011_business_trip_support
Create Date: 2026-08-20

0010 的数据回填有一道守卫：`release_versions` 非空就整段跳过。本意是重跑幂等，
但在**上一次迁移只跑了一半**的库上会反过来咬人——ADD COLUMN 已经落地、
一部分 release_versions 已经生成，于是重跑时直接跳过，剩下的 iteration_versions
永远停在 release_version_id IS NULL。

那些行在页面上完全不可见（版本页是 大版本 → 版本 → 迭代版本 三层嵌套渲染的），
现象就是「迁移完版本信息全丢了，只剩第一层」，但数据一直都在库里。

本迁移只做**挂接**，不删任何东西：
- 每条 release_version_id 为空的迭代行，按 0010 同一套 `B\\d+` 规则算出它的版本号，
  能对上已有版本就挂上去，对不上就补建一条版本；
- 一个版本都没有的大版本，补一条与大版本同号的版本顶着（与 0010 的兜底一致）。

「它本身其实是一个版本」的冗余行（C10SPC101 与 C10SPC101B001 同层那种）这里**不删**：
删除是不可逆的，留给人工用 scripts/repair_version_tiers.py 看过报告再决定。
它们会作为同号构建挂在自己的版本下，页面上看得见、可手工清理。

本迁移天然幂等：只处理 release_version_id IS NULL 的行，跑完就没有可处理的了。
"""
import re

import sqlalchemy as sa
from alembic import op

revision = "0012_reattach_orphan_iterations"
down_revision = "0011_business_trip_support"
branch_labels = None
depends_on = None

# 与 0010 的 _split 同一套规则。迁移之间不互相 import（改一版会牵动另一版的历史行为），
# 所以这里是有意的复制；两边要改一起改。
_BUILD_RE = re.compile(r"^(?P<base>.+?)B(?P<build>\d+)$", re.IGNORECASE)


def _split(version_no: str, major_no: str) -> str:
    """→ 这条迭代行应该挂在哪个版本号下。"""
    s = (version_no or "").strip()
    if not s:
        return (major_no or "").strip() or "未命名"
    m = _BUILD_RE.match(s)
    if m:
        base = m.group("base").strip().rstrip("-_.")
        return base or s
    return s


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    if not {"major_versions", "release_versions", "iteration_versions"} <= tables:
        return      # 全新库：create_all 已按新模型建好，没有可修的数据
    if "release_version_id" not in {c["name"] for c in insp.get_columns("iteration_versions")}:
        return      # 0010 没跑成，轮不到这一版来修

    majors = bind.execute(sa.text(
        "SELECT id, version_no FROM major_versions ORDER BY sort_order, id")).mappings().all()
    created = linked = 0

    for m in majors:
        rels = {r["version_no"]: r["id"] for r in bind.execute(sa.text(
            "SELECT id, version_no FROM release_versions WHERE major_version_id = :mid"
        ), {"mid": m["id"]}).mappings()}

        orphans = bind.execute(sa.text(
            "SELECT id, version_no FROM iteration_versions "
            "WHERE major_version_id = :mid AND release_version_id IS NULL "
            "ORDER BY sort_order, id"
        ), {"mid": m["id"]}).mappings().all()

        # 一个版本都没有的大版本补一条同号的顶着，页面上不至于是个空壳
        if not rels and not orphans:
            _insert_release(bind, m["id"], (m["version_no"] or "").strip() or "未命名", len(rels))
            created += 1
            continue

        for it in orphans:
            base = _split(it["version_no"], m["version_no"])
            rid = rels.get(base)
            if rid is None:
                rid = _insert_release(bind, m["id"], base, len(rels))
                rels[base] = rid
                created += 1
            bind.execute(sa.text(
                "UPDATE iteration_versions SET release_version_id = :rid WHERE id = :iid"
            ), {"rid": rid, "iid": it["id"]})
            linked += 1

    if created or linked:
        print(f"[0012] 补挂版本三层：新建版本 {created} 个，挂回迭代版本 {linked} 条")


def _insert_release(bind, major_id: int, version_no: str, sort_order: int) -> int:
    bind.execute(sa.text(
        "INSERT INTO release_versions (major_version_id, version_no, title, description, "
        " planned_date, actual_release_date, sort_order, created_at, updated_at) "
        "VALUES (:mid, :no, '', '', NULL, NULL, :sort, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    ), {"mid": major_id, "no": version_no, "sort": sort_order})
    return bind.execute(sa.text(
        "SELECT id FROM release_versions WHERE major_version_id = :mid AND version_no = :no "
        "ORDER BY id DESC LIMIT 1"
    ), {"mid": major_id, "no": version_no}).scalar()


def downgrade():
    # 只做过挂接与补建，回退没有意义：把 release_version_id 清回 NULL 只会
    # 让那些行重新变成页面上看不见的孤儿。
    pass
