"""专项内容新增分段顺序字段 section_order_json

Revision ID: 0003_special_section_order
Revises: 0002_unify_product_priority
Create Date: 2026-07-06

专项/攻关详情页支持「每个专项各自调整分段顺序」（求助↔全景图互换等），
需要给 special_contents 增加一列存放分段 key 的有序数组。空数组＝按默认顺序。
新列 NOT NULL + server_default='[]'，存量行自动回填为 '[]'。
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003_special_section_order"
down_revision = "0002_unify_product_priority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("special_contents") as batch_op:
        batch_op.add_column(
            sa.Column("section_order_json", sa.Text(),
                      nullable=False, server_default="[]")
        )


def downgrade() -> None:
    with op.batch_alter_table("special_contents") as batch_op:
        batch_op.drop_column("section_order_json")
