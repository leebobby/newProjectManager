"""hardware_issues 增列 extra_fields_json（硬件清零自定义列的值）

Revision ID: 0007_hw_extra_fields
Revises: 0006_key_features_redesign
Create Date: 2026-07-22

硬件清零表支持配置驱动的自定义列（列定义存 config.hw_extra_columns），
每行的自定义列取值集中存 extra_fields_json：{列key: 值}。

hardware_issues 原本由 create_all 建出（无迁移），这里给存量库补该列；
新库靠 create_all 直接带出。create_all 不给已存在的表补列，故老库需 upgrade。
"""
import sqlalchemy as sa
from alembic import op

revision = "0007_hw_extra_fields"
down_revision = "0006_key_features_redesign"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "hardware_issues" not in insp.get_table_names():
        return  # 新库还没建这表，create_all 会带出新列
    cols = {c["name"] for c in insp.get_columns("hardware_issues")}
    if "extra_fields_json" not in cols:
        with op.batch_alter_table("hardware_issues") as batch:
            batch.add_column(sa.Column("extra_fields_json", sa.Text(), server_default="{}"))


def downgrade() -> None:
    with op.batch_alter_table("hardware_issues") as batch:
        batch.drop_column("extra_fields_json")
