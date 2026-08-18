"""专项内容新增分段顺序字段 section_order_json

Revision ID: 0003_special_section_order
Revises: 0002_unify_product_priority
Create Date: 2026-06-08

专项详情页的分段顺序改为逐专项可调，顺序存本列（空数组＝按默认顺序）。

本迁移的幂等守卫不是可选项：`migrate.py` 的 `_ADDITIONS` 里也有同名列，而启动顺序是
ensure_schema() → create_all() → alembic upgrade，所以轮到 Alembic 时这列往往已经存在。
没有守卫时这里会抛 `duplicate column name: section_order_json`，而 automigrate 把异常
吞成一行 warning —— 表现为**整条升级链卡死在 0002，后续迁移全部静默不执行**。
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_special_section_order"
down_revision = "0002_unify_product_priority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "special_contents" not in insp.get_table_names():
        return  # 新库还没建这表，create_all 会带出新列
    cols = {c["name"] for c in insp.get_columns("special_contents")}
    if "section_order_json" in cols:
        return  # migrate.py / create_all 已先补上
    with op.batch_alter_table("special_contents") as batch_op:
        batch_op.add_column(
            sa.Column("section_order_json", sa.Text(),
                      nullable=False, server_default="[]")
        )


def downgrade() -> None:
    with op.batch_alter_table("special_contents") as batch_op:
        batch_op.drop_column("section_order_json")
