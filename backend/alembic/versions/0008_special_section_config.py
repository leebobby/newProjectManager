"""special_contents 增列 section_config_json（分段标题/启停 + 套用的模板）

Revision ID: 0008_special_section_config
Revises: 0007_hw_extra_fields
Create Date: 2026-08-17

专项详情页的分段原先只能排序（section_order_json），标题与「要不要这一段」写死在
前端。不同专项需要不同版式（如解决方案类专项要「测试详细进展和点灯」、不要「阵型」），
故增本列存每个分段的标题覆盖与启停，并记录套用过的模板名：

    {"template_id": 3, "template_name": "解决方案专项",
     "sections": {"goal": {"title": "解决方案专项目标"}, "plan": {"enabled": false}}}

空对象 = 全用默认标题、全部启用，即存量专项行为完全不变——所以本迁移**不做数据回填**。
解析规则见 special_layout.py。
"""
import sqlalchemy as sa
from alembic import op

revision = "0008_special_section_config"
down_revision = "0007_hw_extra_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    # create_all 可能已先把新库的表连列一起建好，故必须带幂等守卫
    if "special_contents" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("special_contents")}
    if "section_config_json" not in cols:
        with op.batch_alter_table("special_contents") as batch:
            batch.add_column(sa.Column("section_config_json", sa.Text(),
                                       server_default="{}"))


def downgrade() -> None:
    with op.batch_alter_table("special_contents") as batch:
        batch.drop_column("section_config_json")
