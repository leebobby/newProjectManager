from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./app.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    # 多用户并发：默认连接池偏小，请求多时会排队等连接。给足读连接的余量。
    pool_size=15,
    max_overflow=25,
    pool_recycle=1800,
)


@event.listens_for(engine, "connect")
def _init_sqlite_connection(dbapi_connection, _record):
    """每条连接的 SQLite PRAGMA 初始化。

    - foreign_keys=ON：SQLite 默认不强制外键，不开则 models 里所有
      ondelete=CASCADE/SET NULL 只是 DDL、不生效，裸 SQL 删除会留下悬空外键。
    - journal_mode=WAL：读写并发的关键。默认 rollback-journal 模式下读会阻塞写、
      写会阻塞读，并发一上来（如 ~50 用户）请求就互相串行，表现为操作卡顿。
      WAL 允许多读 + 单写并发，是 SQLite 多用户部署的标准做法（一次设置后持久化）。
    - busy_timeout=5000：拿不到写锁时等待 5s 再重试，而不是立刻抛「database is locked」。
    - synchronous=NORMAL：WAL 下安全（仅断电可能丢最后一个未落盘事务），比 FULL 少很多 fsync。
    （Alembic 用的是自建 engine，本监听器不影响其 batch 迁移。）
    """
    cur = dbapi_connection.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
