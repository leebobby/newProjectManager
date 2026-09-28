"""wbs_plans 增加独立的树结构版本号

Revision ID: 0019_wbs_tree_version
Revises: 0018_wbs_predecessor_ids
"""
import sqlalchemy as sa
from alembic import op

revision = "0019_wbs_tree_version"
down_revision = "0018_wbs_predecessor_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "wbs_plans" not in insp.get_table_names():
        return
    if "tree_version" not in {c["name"] for c in insp.get_columns("wbs_plans")}:
        op.add_column("wbs_plans", sa.Column("tree_version", sa.Integer(),
                                             nullable=False, server_default="0"))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if ("wbs_plans" in insp.get_table_names() and
            "tree_version" in {c["name"] for c in insp.get_columns("wbs_plans")}):
        with op.batch_alter_table("wbs_plans") as batch:
            batch.drop_column("tree_version")
