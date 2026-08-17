"""启动时自动把 Alembic 迁移追平到 head，替代手工 `alembic upgrade head`。

在 main.py 里于 ensure_schema() + create_all() 之后调用：
- 库还没被 Alembic 跟踪（无 alembic_version 表）→ 先 `stamp 0001_baseline`
  （表结构此刻已由 create_all 补齐到当前模型），再 upgrade head 补数据迁移；
- 已跟踪 → 直接 upgrade head（没有新迁移时是空操作，毫秒级）。

失败只记日志不阻塞启动（延续 create_all 的零风险原则）——结构缺失最终会在
业务请求上暴露，届时按日志手工执行 `alembic upgrade head` 排查。
0002+ 的迁移都带 inspector 幂等守卫，与 create_all 先建表并存安全。
"""
import logging
from pathlib import Path

log = logging.getLogger("automigrate")


def upgrade_to_head(engine) -> None:
    try:
        import sqlalchemy as sa
        from alembic import command
        from alembic.config import Config

        base_dir = Path(__file__).resolve().parent
        cfg = Config(str(base_dir / "alembic.ini"))
        cfg.set_main_option("script_location", str(base_dir / "alembic"))

        insp = sa.inspect(engine)
        tables = insp.get_table_names()
        if "alembic_version" not in tables:
            command.stamp(cfg, "0001_baseline")
            log.info("Alembic 首次接管：已 stamp 0001_baseline")
        command.upgrade(cfg, "head")
        log.info("Alembic 迁移已追平 head")
    except Exception as exc:
        log.warning("自动迁移失败（不阻塞启动，请手工执行 alembic upgrade head）：%s", exc)
