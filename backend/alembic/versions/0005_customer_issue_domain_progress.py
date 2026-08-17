"""customer_issues 增列：责任领域 / 问题进展 / 分类专项 + 重要程度词表迁移

Revision ID: 0005_ci_domain_progress
Revises: 0004_customer_issues
Create Date: 2026-07-21

问题跟踪表按新口径重构，新增四列：
  group_id      责任领域（PL 组 FK → resource_groups）
  owner_group   责任领域自由文本快照（导入兜底）
  progress_note 问题进展（多行文本）
  category      分类 / 专项

并把重要程度旧值「紧急」统一迁移为「重要」（词表 重要紧急 / 重要 / 一般）。

新库靠 main.py 的 create_all 直接带出这些列；存量库跑本迁移补列。
create_all 不会给已存在的表补列，所以两者共存策略下，老库必须 upgrade 一次。
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0005_ci_domain_progress"
down_revision = "0004_customer_issues"
branch_labels = None
depends_on = None

_NEW_COLS = [
    ("group_id", sa.Integer()),
    ("owner_group", sa.String(length=64)),
    ("progress_note", sa.Text()),
    ("category", sa.String(length=64)),
]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {c["name"] for c in inspector.get_columns("customer_issues")}

    with op.batch_alter_table("customer_issues") as batch:
        for name, col_type in _NEW_COLS:
            if name not in existing:
                default = "" if not isinstance(col_type, sa.Integer) else None
                batch.add_column(sa.Column(name, col_type, nullable=True,
                                           server_default=default))
    if "ix_customer_issues_group_id" not in {i["name"] for i in inspector.get_indexes("customer_issues")}:
        op.create_index("ix_customer_issues_group_id", "customer_issues", ["group_id"])

    # 重要程度词表迁移：紧急 → 重要
    conn.execute(sa.text(
        "UPDATE customer_issues SET urgency = '重要' WHERE urgency = '紧急'"
    ))


def downgrade() -> None:
    with op.batch_alter_table("customer_issues") as batch:
        for name, _ in _NEW_COLS:
            batch.drop_column(name)
