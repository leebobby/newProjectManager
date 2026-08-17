"""baseline：既有库 stamp 此版本，新库由 create_all 建全表

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-07

项目此前无 Alembic，schema 由 models.py + create_all 维护。本基线把
「当前模型即真相」固化为迁移起点：
- 全新库：`alembic upgrade head` 会按当前模型建好所有表（含全部唯一约束/索引）；
- 既有库：执行一次 `alembic stamp 0001_baseline`（表已存在，无需重建）。
此后所有结构变更（改名/删列/类型/约束/回填）都写成新的 revision。
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 复用应用的声明式 metadata，一次性建齐当前全部表。
    from database import Base
    import models  # noqa: F401  触发所有表注册到 Base.metadata
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    from database import Base
    import models  # noqa: F401
    Base.metadata.drop_all(bind=op.get_bind())
