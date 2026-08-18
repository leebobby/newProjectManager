"""「解决方案专项」模板补三段：验收标准 / 总体测试策略 / 专项测试计划

Revision ID: 0009_solution_template_test_sections
Revises: 0008_special_section_config
Create Date: 2026-08-18

模板是 seed_initial_data 注入的，而那段代码只在 **模板表为空** 时跑一次——
改了 main.py 里的种子，只有全新部署能拿到新分段，已经在跑的库永远等不到。
所以补分段必须走迁移。

认领哪一行：按 layout_json 里的 tkey 指纹（含 "test-lights"）而不是模板名，
因为模板名是 admin 可改的；已经手工加过同名分段的（tkey 已存在）整行跳过。
**只增不删**，与 special_layout.apply_template 同口径：既有分段、既有列定义一律不动，
只把缺的三段插进 blocks 并在 order 里排到「测试详细进展和点灯」之前。

已经套用过旧版模板的专项不受影响——套模板时版式就写进了 special_contents，
与模板脱钩。要让它们也拿到新分段，得在专项页重新套一次模板（套用是幂等的）。
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "0009_solution_template_test_sections"
down_revision = "0008_special_section_config"
branch_labels = None
depends_on = None

_SIGNATURE_TKEY = "test-lights"     # 认出「解决方案专项」这份种子版式
_NEW_TKEYS = ("acceptance", "test-strategy", "test-plan")


def _cols(*names):
    return [{"text": n, "colspan": 1, "align": "center"} for n in names]


def _new_blocks():
    return [
        {"tkey": "acceptance", "kind": "grid", "title": "解决方案验收标准",
         "headers": _cols("验收项", "验收标准", "验收方式", "责任人", "达成情况"),
         "colTypes": ["text", "text", "text", "text", "light"],
         "colWidths": [160, 300, 140, 90, 90], "row_count": 3},
        {"tkey": "test-strategy", "kind": "text", "title": "总体测试策略"},
        {"tkey": "test-plan", "kind": "grid", "title": "专项测试计划",
         "headers": _cols("测试阶段", "测试范围", "计划开始", "计划完成", "责任人", "状态"),
         "colTypes": ["text", "text", "date", "date", "text", "light"],
         "colWidths": [140, 280, 110, 110, 90, 80], "row_count": 3},
    ]


def _patched(layout: dict):
    """给一份 layout 补上缺的三段；无需改动时返回 None。"""
    blocks = [b for b in (layout.get("blocks") or []) if isinstance(b, dict)]
    have = {str(b.get("tkey") or "") for b in blocks}
    missing = [b for b in _new_blocks() if b["tkey"] not in have]
    if not missing:
        return None

    blocks.extend(missing)
    order = [k for k in (layout.get("order") or []) if isinstance(k, str)]
    new_keys = [f"tpl:{b['tkey']}" for b in missing]
    anchor = f"tpl:{_SIGNATURE_TKEY}"
    at = order.index(anchor) if anchor in order else len(order)
    order = order[:at] + new_keys + order[at:]

    return {**layout, "order": order, "blocks": blocks}


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    # 新库由 create_all + seed_initial_data 直接种出带三段的版式，这里没得可补
    if "special_templates" not in insp.get_table_names():
        return

    rows = conn.execute(sa.text(
        "SELECT id, layout_json FROM special_templates")).fetchall()
    for tid, raw in rows:
        try:
            layout = json.loads(raw or "{}")
        except (ValueError, TypeError):
            continue        # 脏行留给 admin 在页面上修，不在迁移里猜
        if not isinstance(layout, dict):
            continue
        tkeys = {str(b.get("tkey") or "") for b in (layout.get("blocks") or [])
                 if isinstance(b, dict)}
        if _SIGNATURE_TKEY not in tkeys:
            continue
        patched = _patched(layout)
        if patched is None:
            continue
        conn.execute(
            sa.text("UPDATE special_templates SET layout_json = :j WHERE id = :i"),
            {"j": json.dumps(patched, ensure_ascii=False), "i": tid},
        )


def downgrade() -> None:
    """把补进去的三段摘掉。已经套到具体专项上的分段不动——那是数据不是配置。"""
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "special_templates" not in insp.get_table_names():
        return
    rows = conn.execute(sa.text(
        "SELECT id, layout_json FROM special_templates")).fetchall()
    for tid, raw in rows:
        try:
            layout = json.loads(raw or "{}")
        except (ValueError, TypeError):
            continue
        if not isinstance(layout, dict):
            continue
        blocks = [b for b in (layout.get("blocks") or [])
                  if not (isinstance(b, dict) and b.get("tkey") in _NEW_TKEYS)]
        order = [k for k in (layout.get("order") or [])
                 if k not in {f"tpl:{t}" for t in _NEW_TKEYS}]
        conn.execute(
            sa.text("UPDATE special_templates SET layout_json = :j WHERE id = :i"),
            {"j": json.dumps({**layout, "order": order, "blocks": blocks},
                             ensure_ascii=False), "i": tid},
        )
