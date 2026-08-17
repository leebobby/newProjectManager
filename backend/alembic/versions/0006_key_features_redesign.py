"""关键特性重构：从机台级单表 → 全局特性目录 + 机台多对多引用

Revision ID: 0006_key_features_redesign
Revises: 0005_ci_domain_progress
Create Date: 2026-07-22

关键特性早期版本是"机台级"表（含 machine_status_id 列，实验性、未上库）。
现改为全局特性目录（key_features 新 schema：度量/责任人/简介/附件/关联问题单特性）
+ 机台多对多关联（machine_key_features）。

存量库若已 create_all 出旧 schema 的 key_features，本迁移把它丢弃；
新 schema 的 key_features 与 machine_key_features 由 main.py 的 create_all 重新建出
（与 hardware_issues 等新表同款策略）。旧表是实验数据，丢弃可接受。
"""
import sqlalchemy as sa
from alembic import op

revision = "0006_key_features_redesign"
down_revision = "0005_ci_domain_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "key_features" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("key_features")}
        if "machine_status_id" in cols:   # 旧 schema，丢弃让 create_all 按新模型重建
            op.drop_table("key_features")


def downgrade() -> None:
    # 不可逆（旧实验表不再恢复）
    pass
