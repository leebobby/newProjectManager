"""版本体系从两层改三层：大版本 → 版本 → 迭代版本

Revision ID: 0010_version_three_tier
Revises: 0009_solution_template_test_sections
Create Date: 2026-08-20

老库里 major_versions 存的是号段（C10SPC100 / C10SPC110），而 iteration_versions
里**混着两级**：C10SPC101 这种其实是「版本」，C10SPC101B001 才是构建。所以这次迁移
的主体不是加表，是按 `B\\d+` 后缀把 iteration_versions 劈成两级。

劈分规则（`_split`）：
- `<base>B<数字>` → 构建，父版本号 = base
- 其余 → 它本身就是一个「版本」，同时也是自己的 base
- 版本号为空 → 挂到与大版本同号的版本下（兜底，不丢数据）

那些「本身就是版本」的行会被提升成 release_versions 的一条，**原行只有在没被
iteration_requirements / iteration_product_requirements 引用时才删掉**。被引用的留着
（页面上会看到版本与同号构建并存，人工确认后再删），这比 SET NULL 掉别人填了半年的
计划交付版本要好。

主干/分支：每个项目里版本号自然序最大的大版本归为主干，其余归为分支，
branched_at 一律留空——历史拉分支的时间无从考证，留空好过编一个看着合理的日期。

SQLite 的加列一律走裸 ADD COLUMN、不带 FK 约束（batch 模式会整表重建，
在刚出过 "database disk image is malformed" 的库上不值得冒这个险）。SQLite 默认不
强制外键，新库由 create_all 建表时是带约束的，两者行为一致。
"""
import re

import sqlalchemy as sa
from alembic import op

revision = "0010_version_three_tier"
down_revision = "0009_solution_template_test_sections"
branch_labels = None
depends_on = None

_BUILD_RE = re.compile(r"^(?P<base>.+?)B(?P<build>\d+)$", re.IGNORECASE)


def _split(version_no: str, major_no: str) -> tuple[str, bool]:
    """→ (所属版本号, 这条本身是不是一个「版本」)"""
    s = (version_no or "").strip()
    if not s:
        return (major_no or "").strip() or "未命名", False
    m = _BUILD_RE.match(s)
    if m:
        base = m.group("base").strip().rstrip("-_.")
        return base or s, False
    return s, True


def _natural_key(s: str):
    """C10SPC110 > C10SPC100：数字段按数值比，其余按字符串比。"""
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", (s or ""))]


def _colnames(insp, table):
    return {c["name"] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "major_versions" not in tables:
        return      # 全新库：create_all 已按新模型建好，没有可迁的数据

    # ── 1) release_versions ────────────────────────────────────────────────
    if "release_versions" not in tables:
        op.create_table(
            "release_versions",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("major_version_id", sa.Integer, nullable=False, index=True),
            sa.Column("version_no", sa.String(64), nullable=False),
            sa.Column("title", sa.String(256), server_default=""),
            sa.Column("description", sa.Text, server_default=""),
            sa.Column("planned_date", sa.DateTime, nullable=True),
            sa.Column("actual_release_date", sa.DateTime, nullable=True),
            sa.Column("sort_order", sa.Integer, server_default="0"),
            sa.Column("created_at", sa.DateTime, nullable=True),
            sa.Column("updated_at", sa.DateTime, nullable=True),
        )

    # ── 2) major_versions 的主干/分支列 ────────────────────────────────────
    mv_cols = _colnames(insp, "major_versions")
    for name, ddl in (
        ("line", sa.Column("line", sa.String(16), server_default="master")),
        ("branch_name", sa.Column("branch_name", sa.String(128), server_default="")),
        ("branched_at", sa.Column("branched_at", sa.DateTime, nullable=True)),
    ):
        if name not in mv_cols:
            op.add_column("major_versions", ddl)

    # ── 3) iteration_versions.release_version_id ───────────────────────────
    if "iteration_versions" not in tables:
        return
    if "release_version_id" not in _colnames(insp, "iteration_versions"):
        op.add_column("iteration_versions",
                      sa.Column("release_version_id", sa.Integer, nullable=True))

    # ── 4) 数据回填：只在 release_versions 还是空表时做，重跑幂等 ──────────
    if bind.execute(sa.text("SELECT COUNT(*) FROM release_versions")).scalar():
        return

    majors = bind.execute(sa.text(
        "SELECT id, project_id, version_no, title, actual_release_date "
        "FROM major_versions ORDER BY sort_order, id"
    )).mappings().all()

    ref_tables = [t for t in ("iteration_requirements", "iteration_product_requirements")
                  if t in tables]
    promoted = dropped = kept = 0

    for m in majors:
        iters = bind.execute(sa.text(
            "SELECT id, version_no, title, planned_date, sort_order "
            "FROM iteration_versions WHERE major_version_id = :mid ORDER BY sort_order, id"
        ), {"mid": m["id"]}).mappings().all()

        order: list[str] = []
        self_rows: dict[str, dict] = {}     # 版本号 → 那条「其实是版本」的迭代行
        parent_of: dict[int, str] = {}
        for it in iters:
            base, is_release = _split(it["version_no"], m["version_no"])
            parent_of[it["id"]] = base
            if base not in order:
                order.append(base)
            if is_release and base not in self_rows:
                self_rows[base] = it

        if not order:                       # 一个迭代都没有的大版本：建一条同号版本顶着
            order = [(m["version_no"] or "").strip() or "未命名"]

        rid_of: dict[str, int] = {}
        for idx, base in enumerate(order):
            src = self_rows.get(base)
            bind.execute(sa.text(
                "INSERT INTO release_versions "
                "(major_version_id, version_no, title, description, planned_date, "
                " actual_release_date, sort_order, created_at, updated_at) "
                "VALUES (:mid, :no, :title, '', :planned, :released, :sort, "
                "        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ), {
                "mid": m["id"], "no": base,
                "title": (src["title"] if src else "") or "",
                "planned": src["planned_date"] if src else None,
                # 两层时代大版本上的「实际发布」下沉到同号的版本
                "released": m["actual_release_date"] if base == m["version_no"] else None,
                "sort": idx,
            })
            rid_of[base] = bind.execute(sa.text(
                "SELECT id FROM release_versions WHERE major_version_id = :mid "
                "AND version_no = :no ORDER BY id DESC LIMIT 1"
            ), {"mid": m["id"], "no": base}).scalar()
            promoted += 1

        for it in iters:
            bind.execute(sa.text(
                "UPDATE iteration_versions SET release_version_id = :rid WHERE id = :iid"
            ), {"rid": rid_of[parent_of[it["id"]]], "iid": it["id"]})

        # 被提升成「版本」的那些行，没人引用就删掉；有人引用就留着让人工处理
        for base, src in self_rows.items():
            refs = sum(
                bind.execute(sa.text(
                    f"SELECT COUNT(*) FROM {t} WHERE target_version_id = :iid"
                ), {"iid": src["id"]}).scalar() or 0
                for t in ref_tables
            )
            if refs:
                kept += 1
            else:
                bind.execute(sa.text("DELETE FROM iteration_versions WHERE id = :iid"),
                             {"iid": src["id"]})
                dropped += 1

    # ── 5) 主干/分支的初值 ─────────────────────────────────────────────────
    bind.execute(sa.text("UPDATE major_versions SET line = 'branch' WHERE line IS NULL OR line = ''"))
    by_project: dict = {}
    for m in majors:
        by_project.setdefault(m["project_id"], []).append(m)
    for rows in by_project.values():
        top = max(rows, key=lambda r: _natural_key(r["version_no"]))
        for r in rows:
            is_master = r["id"] == top["id"]
            bind.execute(sa.text(
                "UPDATE major_versions SET line = :line, branch_name = :bn WHERE id = :id"
            ), {
                "line": "master" if is_master else "branch",
                "bn": "" if is_master else f"release/{r['version_no']}",
                "id": r["id"],
            })

    print(f"[0010] 版本三层迁移完成：生成版本 {promoted} 个，"
          f"删除被提升的冗余迭代行 {dropped} 条，因仍被需求引用而保留 {kept} 条")


def downgrade():
    # 回退只删新表：iteration_versions 里被提升后删掉的行无法复原，
    # 假装能回退比明说不能更危险。
    op.drop_table("release_versions")
