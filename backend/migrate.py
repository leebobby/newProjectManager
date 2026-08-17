"""轻量自动迁移：检查并补齐缺失的列。

启动时调用一次，对老数据库平滑升级。仅支持 SQLite 的简单加列场景；
列重命名、类型变更等复杂迁移仍需借助 Alembic 或手动处理。
"""
from datetime import datetime

from sqlalchemy import inspect, text

from database import engine

_CUR_YEAR = datetime.utcnow().year

# (表名, 列名, SQLite 列定义)
_ADDITIONS = [
    (
        "customer_status",
        "attention_level",
        "INTEGER DEFAULT 0",
    ),
    (
        "customer_status",
        "field_version",
        "VARCHAR(128) DEFAULT ''",
    ),
    (
        "customer_status",
        "model",
        "VARCHAR(128) DEFAULT ''",
    ),
    (
        "customer_status",
        "issue_url",
        "VARCHAR(512) DEFAULT ''",
    ),
    (
        "iteration_requirements",
        "remark",
        "TEXT DEFAULT ''",
    ),
    # 路线图跨年支持：给已有的阶段/里程碑补年份列，默认当前年份。
    (
        "roadmap_phases",
        "start_year",
        f"INTEGER NOT NULL DEFAULT {_CUR_YEAR}",
    ),
    (
        "roadmap_phases",
        "end_year",
        f"INTEGER NOT NULL DEFAULT {_CUR_YEAR}",
    ),
    (
        "roadmap_milestones",
        "year",
        f"INTEGER NOT NULL DEFAULT {_CUR_YEAR}",
    ),
    # 乐观锁版本号
    ("customer_status", "version", "INTEGER NOT NULL DEFAULT 0"),
    ("iteration_requirements", "version", "INTEGER NOT NULL DEFAULT 0"),
    ("roadmap_phases", "version", "INTEGER NOT NULL DEFAULT 0"),

    # v0.14: 专项/攻关 拓展字段
    ("specials", "kind", "VARCHAR(16) NOT NULL DEFAULT 'special'"),
    ("specials", "email_to", "VARCHAR(512) NOT NULL DEFAULT ''"),
    ("specials", "email_cc", "VARCHAR(512) NOT NULL DEFAULT ''"),
    ("specials", "email_subject_tpl", "VARCHAR(256) NOT NULL DEFAULT ''"),
    ("special_tasks", "status", "VARCHAR(16) NOT NULL DEFAULT 'open'"),
    ("special_risks", "status", "VARCHAR(16) NOT NULL DEFAULT 'open'"),
    ("special_contents", "extra_grids_json", "TEXT NOT NULL DEFAULT '[]'"),

    # v0.15: 迭代需求增加责任人所属小组
    ("iteration_requirements", "owner_group", "VARCHAR(64) NOT NULL DEFAULT ''"),

    # v0.16: 客户主数据扩展字段
    # 注意：customers 表是 v0.16 才引入的。如果你在两次后端启动之间，先用了仅含基础列的
    # Customer 模型版本（早期 PR），后续才加这几列，那么 create_all 不会自动补列 —
    # 必须显式 ALTER。新库直接 create_all 时 has_table=False，这些 ALTER 会自动跳过。
    ("customers", "industry", "VARCHAR(128) NOT NULL DEFAULT ''"),
    ("customers", "intro", "TEXT NOT NULL DEFAULT ''"),
    ("customers", "key_focus", "TEXT NOT NULL DEFAULT ''"),

    # v0.18: User 表扩字段（资源组归属、工号、岗位、纯档案标记）
    ("users", "emp_no", "VARCHAR(64) NOT NULL DEFAULT ''"),
    ("users", "can_login", "BOOLEAN NOT NULL DEFAULT 1"),
    ("users", "group_id", "INTEGER"),
    ("users", "job_title", "VARCHAR(64) NOT NULL DEFAULT ''"),

    # v0.19: 客户主数据 FK 化（业务表挂 customer_id）
    ("customer_status", "customer_id", "INTEGER"),
    ("stakeholder_battlefields", "customer_id", "INTEGER"),
    # v0.19: 阵型成员挂到 User 主数据
    ("project_formation_members", "user_id", "INTEGER"),

    # v0.20: 业务表 owner / version 字符串 → FK
    ("annual_iterations", "owner_user_id", "INTEGER"),
    ("iteration_requirements", "owner_user_id", "INTEGER"),
    ("iteration_requirements", "group_id", "INTEGER"),
    ("iteration_requirements", "target_version_id", "INTEGER"),
    ("iteration_product_requirements", "target_version_id", "INTEGER"),
    ("iteration_product_requirements", "feature_fo_user_id", "INTEGER"),
    ("iteration_product_requirements", "feature_se_user_id", "INTEGER"),
    ("iteration_product_requirements", "feature_tfo_user_id", "INTEGER"),
    ("specials", "owner_user_id", "INTEGER"),
    ("special_tasks", "owner_user_id", "INTEGER"),
    ("special_risks", "owner_user_id", "INTEGER"),
    ("handbook_items", "owner_user_id", "INTEGER"),

    # v0.21: 领域需求版本质量统计
    ("iteration_requirements", "merge_links", "TEXT NOT NULL DEFAULT ''"),
    ("iteration_requirements", "code_volume", "INTEGER"),
    ("iteration_requirements", "self_test_case_count", "INTEGER"),
    ("iteration_requirements", "post_test_issue_count", "INTEGER"),

    # v0.22: 机台里程碑（自定义信息块走新表，由 create_all 建）
    ("customer_status", "milestones_json", "TEXT NOT NULL DEFAULT ''"),

    # v0.23: 专项「一句话进展&求助」拆分为「整体进展」+「求助」
    ("special_contents", "help_request", "TEXT NOT NULL DEFAULT ''"),

    # v0.24: 专项/攻关详情页「各自调整分段顺序」，对齐 Alembic 0003
    ("special_contents", "section_order_json", "TEXT NOT NULL DEFAULT '[]'"),
]


def ensure_schema():
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, column, definition in _ADDITIONS:
            if not inspector.has_table(table):
                continue  # 表都没有，留给 create_all 处理
            cols = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if column not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
