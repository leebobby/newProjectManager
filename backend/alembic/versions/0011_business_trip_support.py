"""客户面支撑：加支撑项目、支撑方式、工作量（人天）三列

Revision ID: 0011_business_trip_support
Revises: 0010_version_three_tier
Create Date: 2026-08-20

business_trips 原本只是「成员出差」——去哪个战场、哪段时间。看板要按项目分、
按现场/线上分，并直接给出工作量，于是加三列：

- project_id     支撑项目 FK（roadmap_projects）。老数据一律留空，
                 因为无从判断当时支撑的是哪个项目，猜一个比留空更糟。
- support_mode   现场支撑 / 线上支撑。老数据**全部回填成「现场支撑」**——
                 这张表在改造前登记的就是出差，人确实到了现场。
- man_days       工作量（人天）。老数据留空，看板按日历天数推导
                 （见 routers/business_trips.py 的 _man_days_in）。
                 不在这里批量算一遍写死：推导值随口径变，写死了以后改口径就要再迁一次。

加列走裸 ADD COLUMN、不带 FK 约束，理由同 0010：batch 模式会整表重建。
SQLite 默认不强制外键，新库由 create_all 建表时是带约束的，两者行为一致。
"""
import sqlalchemy as sa
from alembic import op

revision = "0011_business_trip_support"
down_revision = "0010_version_three_tier"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "business_trips" not in set(insp.get_table_names()):
        return      # 全新库：create_all 已按新模型建好

    # ensure_schema() 与 create_all() 都跑在 Alembic 之前，列可能已经存在。
    # 漏了这个守卫不会报错退出，而是被 automigrate 吞成一行 warning，
    # 整条升级链停在这一版（见 CLAUDE.md「数据库结构变更」）。
    cols = {c["name"] for c in insp.get_columns("business_trips")}
    for name, ddl in (
        ("project_id", sa.Column("project_id", sa.Integer, nullable=True)),
        ("support_mode", sa.Column("support_mode", sa.String(16), server_default="现场支撑")),
        ("man_days", sa.Column("man_days", sa.Float, nullable=True)),
    ):
        if name not in cols:
            op.add_column("business_trips", ddl)

    # 回填：老行的 support_mode 为空（刚加的列 / 历史 NULL）时按现场支撑算
    bind.execute(sa.text(
        "UPDATE business_trips SET support_mode = '现场支撑' "
        "WHERE support_mode IS NULL OR TRIM(support_mode) = ''"
    ))


def downgrade():
    # 三列都是新增的纯附加列，回退直接删。SQLite 下 drop column 需要 batch 重建，
    # 只在真要回退时才付这个代价。
    with op.batch_alter_table("business_trips") as b:
        for name in ("man_days", "support_mode", "project_id"):
            b.drop_column(name)
