"""客户问题合入大版本、专项事务工作量、领域需求 AR 唯一编号。"""
import sqlalchemy as sa
from alembic import op

revision = '0021_issue_version_workload_ar'
down_revision = '0020_wbs_progress_risks'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if 'customer_issues' in tables:
        columns = {c['name'] for c in inspector.get_columns('customer_issues')}
        if 'merge_major_version_id' not in columns:
            with op.batch_alter_table('customer_issues') as batch:
                batch.add_column(sa.Column('merge_major_version_id', sa.Integer(), nullable=True))
                batch.create_foreign_key('fk_customer_issue_merge_major', 'major_versions',
                                         ['merge_major_version_id'], ['id'], ondelete='SET NULL')
                batch.create_index('ix_customer_issues_merge_major_version_id', ['merge_major_version_id'])
    if 'special_tasks' in tables and 'workload' not in {c['name'] for c in inspector.get_columns('special_tasks')}:
        op.add_column('special_tasks', sa.Column('workload', sa.Float(), nullable=True))
    if 'iteration_requirements' in tables:
        columns = {c['name'] for c in inspector.get_columns('iteration_requirements')}
        for name in ('ar_no', 'ar_key'):
            if name not in columns:
                op.add_column('iteration_requirements', sa.Column(name, sa.String(64), nullable=True))
        indexes = {i['name'] for i in sa.inspect(op.get_bind()).get_indexes('iteration_requirements')}
        if 'ix_iteration_requirements_ar_key' not in indexes:
            op.create_index('ix_iteration_requirements_ar_key', 'iteration_requirements', ['ar_key'], unique=True)


def downgrade():
    with op.batch_alter_table('iteration_requirements') as batch:
        batch.drop_index('ix_iteration_requirements_ar_key')
        batch.drop_column('ar_key')
        batch.drop_column('ar_no')
    with op.batch_alter_table('special_tasks') as batch:
        batch.drop_column('workload')
    foreign_key = next(fk for fk in sa.inspect(op.get_bind()).get_foreign_keys('customer_issues')
                       if fk['constrained_columns'] == ['merge_major_version_id'])
    convention = {'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s'}
    constraint_name = foreign_key['name'] or 'fk_customer_issues_merge_major_version_id_major_versions'
    with op.batch_alter_table('customer_issues', naming_convention=convention) as batch:
        batch.drop_index('ix_customer_issues_merge_major_version_id')
        batch.drop_constraint(constraint_name, type_='foreignkey')
        batch.drop_column('merge_major_version_id')
