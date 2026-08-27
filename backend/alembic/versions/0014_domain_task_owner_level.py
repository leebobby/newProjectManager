"""领域事务/风险加「责任人 + 风险等级」，遗留问题加「当前进展」

Revision ID: 0014_domain_task_owner_level
Revises: 0013_requirement_project
Create Date: 2026-08-27

三列都是纯新增，没有回填规则可言：

- `domain_risks.owner_id`：原来只到「责任领域」这一层，而领域是个组，
  组不会去闭环一条风险。老行留空——从领域反推一个人（比如取组长）看着很合理，
  但那是替别人认领工作，错了以后没人会发现是系统填的。
- `domain_risks.risk_level`：与优先级是两个口径（见 enums.DOMAIN_RISK_LEVELS），
  所以**不能**拿 priority 回填。老行一律空串＝「还没评过等级」，
  和「评过是中」在页面上必须能分开。
- `domain_legacy_issues.progress`：富文本，老行空串。

加列走裸 ADD COLUMN、不带 FK 约束，理由同 0011/0013：batch 模式会整表重建。
server_default 只为了让老行落到空串而不是 NULL（SQLite 的 ADD COLUMN 没有
第二次机会），模型侧不声明它。
"""
import sqlalchemy as sa
from alembic import op

revision = "0014_domain_task_owner_level"
down_revision = "0013_requirement_project"
branch_labels = None
depends_on = None

# (表名, 列名, 列类型, 是否建索引)
_ADDITIONS = (
    ("domain_risks", "owner_id", sa.Integer(), True),
    ("domain_risks", "risk_level", sa.String(16), False),
    ("domain_legacy_issues", "progress", sa.Text(), False),
)


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    names = set(insp.get_table_names())
    for table, col, coltype, indexed in _ADDITIONS:
        if table not in names:
            continue        # 全新库：create_all 已按新模型建好
        # ensure_schema() 与 create_all() 都跑在 Alembic 之前，列可能已经存在。
        # 漏了这个守卫不会报错退出，而是被 automigrate 吞成一行 warning，
        # 整条升级链停在这一版（见 CLAUDE.md「数据库结构变更」）。
        if col in {c["name"] for c in insp.get_columns(table)}:
            continue
        default = None if isinstance(coltype, sa.Integer) else ""
        op.add_column(table, sa.Column(col, coltype, nullable=True,
                                       server_default=default))
        if indexed:
            op.create_index(f"ix_{table}_{col}", table, [col])


def downgrade():
    for table, col, _coltype, indexed in reversed(_ADDITIONS):
        with op.batch_alter_table(table) as b:
            if indexed:
                b.drop_index(f"ix_{table}_{col}")
            b.drop_column(col)
