"""Alembic 运行环境。

要点：
- 把 backend/ 加入 sys.path，便于直接 import database / models；
- 数据库 URL 不写在 alembic.ini，而是从 database.py 注入，保证与应用单一来源；
- render_as_batch=True：SQLite 不支持原生 ALTER（改名 / 删列 / 改类型 / 加约束），
  batch 模式用「建新表 → 拷数据 → 换名」实现，这正是引入 Alembic 的核心目的。
"""
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# backend/ 根目录入 path（env.py 在 backend/alembic/ 下）
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from database import Base, SQLALCHEMY_DATABASE_URL  # noqa: E402
import models  # noqa: E402,F401  导入即把所有表注册到 Base.metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 用应用里的 URL 覆盖 ini 中的空值
config.set_main_option("sqlalchemy.url", SQLALCHEMY_DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
