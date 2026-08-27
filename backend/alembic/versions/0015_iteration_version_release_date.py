"""迭代版本加「实际发布日期」

Revision ID: 0015_iteration_version_release_date
Revises: 0014_domain_task_owner_level
Create Date: 2026-08-27

「版本」这一层早就有 `actual_release_date`，构建这一层没有。加上之后，
迭代管理的「计划交付版本」下拉可以把发布完的构建收掉——否则可选项只增不减，
一年下来几百个构建里绝大多数是历史。

**老行一律留空**，不按 `planned_date` 回填：预计发布日期跟实际发布日期不是一回事，
拿计划当实际，会把一批其实还没发的构建从下拉里抹掉，而使用者只会觉得"这个版本怎么选不到了"，
不会想到是迁移替他填了个日期。留空＝「还没发布」，都还在下拉里，需要收哪个由人去填。

加列走裸 ADD COLUMN、不带约束，理由同 0011/0013/0014：batch 模式会整表重建。
"""
import sqlalchemy as sa
from alembic import op

revision = "0015_iteration_version_release_date"
down_revision = "0014_domain_task_owner_level"
branch_labels = None
depends_on = None

_TABLE = "iteration_versions"
_COL = "actual_release_date"


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
    op.add_column(_TABLE, sa.Column(_COL, sa.DateTime, nullable=True))


def downgrade():
    with op.batch_alter_table(_TABLE) as b:
        b.drop_column(_COL)
