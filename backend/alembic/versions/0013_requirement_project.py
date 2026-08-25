"""迭代需求（领域 / 产品）加「所属项目」列

Revision ID: 0013_requirement_project
Revises: 0012_reattach_orphan_iterations
Create Date: 2026-08-25

迭代是按年月排的，本身**不属于任何项目**——同一个月的迭代里同时排着多个项目的需求。
度量看板要按项目切分，所以项目维度只能挂在需求行上，两张需求表各加一列 project_id。

老数据一律留空：迭代里没有任何字段能推出当时排的是哪个项目，
按「库里只有一个项目就全填它」这种规则回填看着很合理，但只要哪天有了第二个项目，
这批猜出来的归属就成了看板上无人察觉的偏差。留空反而是能被发现的——
度量看板会把「未指定项目」的条数单独显示出来，提示去补。

加列走裸 ADD COLUMN、不带 FK 约束，理由同 0011：batch 模式会整表重建。
"""
import sqlalchemy as sa
from alembic import op

revision = "0013_requirement_project"
down_revision = "0012_reattach_orphan_iterations"
branch_labels = None
depends_on = None

_TABLES = ("iteration_requirements", "iteration_product_requirements")


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    names = set(insp.get_table_names())
    for table in _TABLES:
        if table not in names:
            continue        # 全新库：create_all 已按新模型建好
        # ensure_schema() 与 create_all() 都跑在 Alembic 之前，列可能已经存在。
        # 漏了这个守卫不会报错退出，而是被 automigrate 吞成一行 warning，
        # 整条升级链停在这一版（见 CLAUDE.md「数据库结构变更」）。
        if "project_id" in {c["name"] for c in insp.get_columns(table)}:
            continue
        op.add_column(table, sa.Column("project_id", sa.Integer, nullable=True))
        op.create_index(f"ix_{table}_project_id", table, ["project_id"])


def downgrade():
    for table in _TABLES:
        with op.batch_alter_table(table) as b:
            b.drop_index(f"ix_{table}_project_id")
            b.drop_column("project_id")
