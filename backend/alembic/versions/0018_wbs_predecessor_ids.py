"""wbs_items 加 predecessor_ids：前置关联从「手填编号」改成「选任务」

原来那一列 `predecessor` 存的是人手敲的编号串（"1.2, 2.3"）。编号（1.2.3）是按
parent_id + sort_order **现算**的、不入库（见 models.WbsItem），所以上移一行、
加一个子项之后，存着的那个编号就指到另一件活上去了，而两行单独看都合法。
新列存 **id**，页面上改成从同一份 WBS 的任务里选，并能顺着它跳过去。

**老值不迁移、也不清空**：编号在改口径的这一刻可能已经漂了，照着它反猜一个 id
是在替人做主，而猜错了没人看得出来。老值原样留在 `predecessor` 里，页面上标成
「老写法」摆给人看，由填的人自己改成关联（同"认不出来的一律算没填"）。

Revision ID: 0018_wbs_predecessor_ids
Revises: 0017_issue_snapshot_stat_score
"""
import sqlalchemy as sa
from alembic import op

revision = "0018_wbs_predecessor_ids"
down_revision = "0017_issue_snapshot_stat_score"
branch_labels = None
depends_on = None

_TABLE = "wbs_items"
_COL = "predecessor_ids"


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
        batch.add_column(sa.Column(_COL, sa.String(length=400), nullable=True,
                                   server_default=""))


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind):
        return
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_column(_COL)
