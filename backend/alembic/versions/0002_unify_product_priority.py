"""统一产品需求优先级口径：高/中/低 → P1/P2/P3

Revision ID: 0002_unify_product_priority
Revises: 0001_baseline
Create Date: 2026-06-07

iteration_product_requirements.priority 历史用「高/中/低」，现与领域需求统一为
P0-P3。本迁移把存量数据按 高→P1 / 中→P2 / 低→P3 映射；空值或已是 P 级的行不动。
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002_unify_product_priority"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

_MAP = {"高": "P1", "中": "P2", "低": "P3"}


def upgrade() -> None:
    conn = op.get_bind()
    for old, new in _MAP.items():
        conn.execute(
            sa.text(
                "UPDATE iteration_product_requirements SET priority=:new WHERE priority=:old"
            ),
            {"new": new, "old": old},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for old, new in _MAP.items():
        conn.execute(
            sa.text(
                "UPDATE iteration_product_requirements SET priority=:old WHERE priority=:new"
            ),
            {"old": old, "new": new},
        )
