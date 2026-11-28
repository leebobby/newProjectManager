"""客户 License 授权信息和不可变的文件版本，保留老文件原路径。"""
import json

import sqlalchemy as sa
from alembic import op

revision = '0022_customer_license'
down_revision = '0021_issue_version_workload_ar'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    machine_columns = {c['name'] for c in inspector.get_columns('customer_status')}
    if 'created_at' not in machine_columns:
        op.add_column('customer_status', sa.Column('created_at', sa.DateTime()))
    # 型号修订历史以建行时间为下界，避免删除后 SQLite 复用 id 串入上一台历史。
    timestamp = 'COALESCE(updated_at, CURRENT_TIMESTAMP)' if 'updated_at' in machine_columns else 'CURRENT_TIMESTAMP'
    bind.execute(sa.text(f'UPDATE customer_status SET created_at={timestamp} WHERE created_at IS NULL'))
    if 'machine_license_files' not in inspector.get_table_names():
        op.create_table(
            'machine_license_files',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('license_id', sa.Integer(), sa.ForeignKey('machine_licenses.id', ondelete='CASCADE'), nullable=False),
            sa.Column('file_version', sa.Integer(), nullable=False),
            sa.Column('file_name', sa.String(256), nullable=False),
            sa.Column('file_path', sa.String(512), nullable=False),
            sa.Column('file_size', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('snapshot_json', sa.Text(), nullable=False, server_default='{}'),
            sa.Column('note', sa.Text(), server_default=''),
            sa.Column('uploaded_by', sa.String(64), server_default=''),
            sa.Column('uploaded_at', sa.DateTime()),
            sa.UniqueConstraint('license_id', 'file_version', name='uq_license_file_version'),
        )
        op.create_index('ix_machine_license_files_license_id', 'machine_license_files', ['license_id'])
    columns = {c['name'] for c in sa.inspect(bind).get_columns('machine_licenses')}
    additions = [sa.Column('created_at', sa.DateTime()),
                 sa.Column('tool_id', sa.String(256), nullable=False, server_default=''),
                 sa.Column('uuid', sa.String(256), nullable=False, server_default=''),
                 sa.Column('throughput_package', sa.String(128), nullable=False, server_default=''),
                 sa.Column('algorithm', sa.String(128), nullable=False, server_default=''),
                 sa.Column('optional_features_json', sa.Text(), nullable=False, server_default='[]'),
                 sa.Column('version', sa.Integer(), nullable=False, server_default='0'),
                 sa.Column('file_version', sa.Integer(), nullable=False, server_default='0')]
    for column in additions:
        if column.name not in columns:
            op.add_column('machine_licenses', column)
    bind.execute(sa.text('UPDATE machine_licenses SET created_at = COALESCE(uploaded_at, CURRENT_TIMESTAMP) WHERE created_at IS NULL'))
    # 不拷贝/删除文件；V1 指向现有文件。重复执行也不重复插入。
    rows = bind.execute(sa.text('''SELECT l.*, c.model FROM machine_licenses l
        LEFT JOIN customer_status c ON c.id=l.machine_status_id
        WHERE l.file_path != '' AND NOT EXISTS
        (SELECT 1 FROM machine_license_files f WHERE f.license_id=l.id)''')).mappings()
    for row in list(rows):
        snapshot = {k: row[k] or '' for k in ('model', 'tool_id', 'uuid', 'throughput_package', 'algorithm', 'remark')}
        snapshot['optional_features'] = json.loads(row['optional_features_json'] or '[]')
        bind.execute(sa.text('''INSERT INTO machine_license_files
            (license_id,file_version,file_name,file_path,file_size,snapshot_json,note,uploaded_by,uploaded_at)
            VALUES (:id,1,:file_name,:file_path,:file_size,:snapshot_json,'历史文件迁入',:uploaded_by,:uploaded_at)'''),
            dict(row, snapshot_json=json.dumps(snapshot, ensure_ascii=False)))
        bind.execute(sa.text('UPDATE machine_licenses SET file_version=1 WHERE id=:id'), {'id': row['id']})


def downgrade():
    op.drop_table('machine_license_files')
    with op.batch_alter_table('machine_licenses') as batch:
        for name in ('created_at', 'tool_id', 'uuid', 'throughput_package', 'algorithm', 'optional_features_json', 'version', 'file_version'):
            batch.drop_column(name)
    with op.batch_alter_table('customer_status') as batch:
        batch.drop_column('created_at')
