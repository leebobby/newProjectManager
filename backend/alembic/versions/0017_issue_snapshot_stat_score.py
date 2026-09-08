"""issue_snapshot_stats 加 DI 加权分列

问题单管理页要按小组 / 客户面看 DI（致命10 严重3 一般1 提示0.1），趋势也要能看 DI。
趋势**只读库里的数字、不碰明细文件**（见 models.IssueSnapshotStat 的说明），
所以 DI 必须和条数一样落库。

列**可空且不给默认值**：这一版之前采集的快照没算过 DI，NULL 是"算不出来"，
不是"0 分"。给 server_default="0" 的话，历史那一段在趋势图上会画成一条贴地的
直线，看着像那几天确实没缺陷——而这种错没人会当 bug 报。
历史回算走 scripts/backfill_issue_di.py（明细 JSON 还在就补得回来）。

Revision ID: 0017_issue_snapshot_stat_score
Revises: 0016_special_overview_light
"""
import sqlalchemy as sa
from alembic import op

revision = "0017_issue_snapshot_stat_score"
down_revision = "0016_special_overview_light"
branch_labels = None
depends_on = None

_TABLE = "issue_snapshot_stats"
_COL = "score"


def _has_column(bind) -> bool:
    insp = sa.inspect(bind)
    if _TABLE not in insp.get_table_names():
        return False          # 表还没建（新库由 create_all 建，已经带这一列）
    return _COL in {c["name"] for c in insp.get_columns(_TABLE)}


def upgrade() -> None:
    # 幂等守卫不能省：ensure_schema() 与 create_all() 都跑在 Alembic 之前，
    # 新库里这一列早就有了。漏守卫不是报错退出，而是 automigrate 把异常吞成一行
    # warning、**整条升级链停在这一版**，后续迁移全部静默不执行（0003 踩过）。
    bind = op.get_bind()
    if _has_column(bind):
        return
    with op.batch_alter_table(_TABLE) as batch:
        batch.add_column(sa.Column(_COL, sa.Float(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind):
        return
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_column(_COL)
