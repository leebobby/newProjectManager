"""自动迁移不能顺手把已有的 logger 关掉。

alembic 的 `fileConfig()` 默认 `disable_existing_loggers=True`：它会把「此刻已经
存在、但没写进 alembic.ini」的 logger 全部禁用。而 `automigrate` 是在 uvicorn 装好
自己的 logger 之后、于 `main.py` 导入期跑的——用默认值等于每次启动都顺手关掉
`uvicorn` / `uvicorn.error` / `uvicorn.access`。

后果不是报错，是**整个进程从此不打访问日志、500 也不打 traceback**：页面上只剩
一句「加载失败」，服务端一片安静，报上来的问题全都查不下去。而"日志没了"这件事
本身没有任何提示，没人会把它当成一个 bug 报上来。
"""


def test_automigrate_keeps_existing_loggers_alive(client, tmp_path):
    # client 夹具已把 cwd 切到临时目录：alembic.ini 里的 sqlite:///./app.db
    # 因此落在临时库上，不会去动仓库里的 backend/app.db
    import logging

    import automigrate
    from sqlalchemy import create_engine

    probe = logging.getLogger("uvicorn.error")
    probe.disabled = False

    engine = create_engine(f"sqlite:///{tmp_path / 'probe.db'}")
    automigrate.upgrade_to_head(engine)

    assert probe.disabled is False, (
        "自动迁移把 uvicorn 的 logger 关掉了——启动之后就再也看不到 traceback 了，"
        "见 alembic/env.py 里 fileConfig 的 disable_existing_loggers"
    )
