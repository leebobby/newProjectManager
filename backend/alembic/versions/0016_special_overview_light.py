"""专项总览：风险点灯的手工覆盖列

Revision ID: 0016_special_overview_light
Revises: 0015_iteration_version_release_date
Create Date: 2026-09-01

专项总览表里的「风险」一列默认由风险和问题分段推出来（见 specials._auto_light），
但点灯本质是管理判断，规则算不出「这一项其实很危险，只是还没人登记风险行」。
所以留一个覆盖列：填了就以它为准，清空回到自动。

**老行一律留空**，不按当前风险行回填成一个固定值：回填等于把"自动推出来的那个灯"
凝固成"人拍的板"，此后风险闭环了灯也不会变，而页面上看不出这个灯是死的。
留空＝还没人覆盖过，每天跟着风险行走。

加列走裸 ADD COLUMN、不带约束，理由同 0011/0013/0014/0015：batch 模式会整表重建。
"""
import sqlalchemy as sa
from alembic import op

revision = "0016_special_overview_light"
down_revision = "0015_iteration_version_release_date"
branch_labels = None
depends_on = None

_TABLE = "special_contents"
_COL = "overview_light"


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if _TABLE not in set(insp.get_table_names()):
        return          # 全新库：create_all 已按新模型建好
    # ensure_schema() 与 create_all() 都跑在 Alembic 之前，列可能已经存在。
    # 漏了这个守卫不会报错退出，而是被 automigrate 吞成一行 warning，
    # 整条升级链停在这一版（见 CLAUDE.md「数据库结构变更」）。
    if _COL in {c["name"] for c in insp.get_columns(_TABLE)}:
        return
    op.add_column(_TABLE, sa.Column(_COL, sa.String(16), nullable=True,
                                    server_default=""))


def downgrade():
    with op.batch_alter_table(_TABLE) as b:
        b.drop_column(_COL)
