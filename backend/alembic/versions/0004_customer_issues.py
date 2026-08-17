"""客户面问题/关键事务：从 JSON 清单提升为实体表 customer_issues

Revision ID: 0004_customer_issues
Revises: 0003_special_section_order
Create Date: 2026-07-19

原来 customer_status.key_issues / recent_focus 是两个 Text 列，里面存
JSON 清单 [{text, done}]。装不下责任人/紧急程度/时间，也无法跨战场汇总查询。
本迁移建 customer_issues 表，并把存量 JSON 逐条回填成行：

  text        → description
  done=true   → status=CLOSED，done=false → status=OPEN
  key_issues  → kind=issue，recent_focus  → kind=task
  customer_id → 取自所属机台（汇总页按战场分组靠它）

闭环时间(closed_at)一律留空：老数据没记过实际闭环日，编一个假日期比空值更坏。
旧的两个 Text 列**保留不删**，留一版回滚余地；回填后代码不再写它们。
"""
import json

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0004_customer_issues"
down_revision = "0003_special_section_order"
branch_labels = None
depends_on = None


def _parse_checklist(val):
    """兼容两种历史格式：JSON 数组 / 每行一条的纯文本。"""
    if not val or not str(val).strip():
        return []
    try:
        parsed = json.loads(val)
        if isinstance(parsed, list):
            return [
                {"text": str(i.get("text", "")).strip(), "done": bool(i.get("done"))}
                for i in parsed
                if isinstance(i, dict) and str(i.get("text", "")).strip()
            ]
    except (ValueError, TypeError):
        pass
    return [{"text": line.strip(), "done": False}
            for line in str(val).split("\n") if line.strip()]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # main.py 启动时的 create_all 很可能已经把表建好了（两者共存是本项目的既定策略）。
    # 那种情况下再 create_table 会直接报「table already exists」，所以这里先探测。
    # 同理，回填只在表为空时做一次，重复执行不会造出双份数据。
    if "customer_issues" not in inspector.get_table_names():
        _create_table()

    existing = conn.execute(sa.text("SELECT COUNT(*) FROM customer_issues")).scalar()
    if existing:
        print(f"customer_issues 已有 {existing} 行，跳过回填")
        return
    _backfill(conn)


def _create_table() -> None:
    op.create_table(
        "customer_issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("machine_status_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="issue"),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("issue_ref", sa.String(length=128), server_default=""),
        sa.Column("urgency", sa.String(length=16), server_default="一般"),
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
        sa.Column("owner_name", sa.String(length=64), server_default=""),
        sa.Column("raised_at", sa.String(length=10), server_default=""),
        sa.Column("due_date", sa.String(length=10), server_default=""),
        sa.Column("closed_at", sa.String(length=10), server_default=""),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="OPEN"),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["machine_status_id"], ["customer_status.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customer_issues_id", "customer_issues", ["id"])
    op.create_index("ix_customer_issues_machine_status_id", "customer_issues", ["machine_status_id"])
    op.create_index("ix_customer_issues_customer_id", "customer_issues", ["customer_id"])
    op.create_index("ix_customer_issues_kind", "customer_issues", ["kind"])
    op.create_index("ix_customer_issues_status", "customer_issues", ["status"])
    op.create_index("ix_customer_issues_owner_user_id", "customer_issues", ["owner_user_id"])


def _backfill(conn) -> None:
    """把 customer_status 的两个 JSON 清单列逐条搬进 customer_issues。"""
    machines = conn.execute(sa.text(
        "SELECT id, customer_id, recent_focus, key_issues FROM customer_status"
    )).fetchall()

    insert = sa.text(
        "INSERT INTO customer_issues "
        "(machine_status_id, customer_id, kind, description, issue_ref, urgency, "
        " owner_name, raised_at, due_date, closed_at, status, sort_order, version, "
        " created_at, updated_at) "
        "VALUES (:mid, :cid, :kind, :desc, '', :urgency, '', '', '', '', :status, :ord, 0, "
        " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )

    for m in machines:
        for field, kind in (("key_issues", "issue"), ("recent_focus", "task")):
            raw = m._mapping.get(field)
            for idx, entry in enumerate(_parse_checklist(raw), start=1):
                conn.execute(insert, {
                    "mid": m._mapping["id"],
                    "cid": m._mapping["customer_id"],
                    "kind": kind,
                    "desc": entry["text"],
                    # 老数据没有紧急程度，统一落默认值，由使用者后续按需调整
                    "urgency": "一般",
                    "status": "CLOSED" if entry["done"] else "OPEN",
                    "ord": idx,
                })


def downgrade() -> None:
    # 旧的 Text 列一直保留着，回滚只需丢掉新表（存量清单数据不会丢）
    op.drop_table("customer_issues")
