"""WBS 当前进展与问题风险条目。"""
import sqlalchemy as sa
from alembic import op

revision = "0020_wbs_progress_risks"
down_revision = "0019_wbs_tree_version"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if "wbs_items" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("wbs_items")}
    for name, default in (("current_progress", ""), ("issues_risks_json", "[]")):
        if name not in columns:
            op.add_column("wbs_items", sa.Column(name, sa.Text(), nullable=False, server_default=default))


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if "wbs_items" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("wbs_items")}
        with op.batch_alter_table("wbs_items") as batch:
            for name in ("issues_risks_json", "current_progress"):
                if name in columns:
                    batch.drop_column(name)
