from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base


class Customer(Base):
    """客户主数据：以缩写英文名 code 作为业务主键，配合多个别名做模糊匹配。

    其他业务模块（客户面状态、战场沟通矩阵、版本、迭代、专项 …）后续都会
    引用 customers.id；本表是单一来源（single source of truth）。
    """
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(64), nullable=False, unique=True, index=True,
                  comment="缩写英文名 / 业务主键 / 默认展示名称")
    display_name = Column(String(256), default="", comment="完整名称（可选，未填则展示 code）")
    region = Column(String(64), default="", comment="区域，如华东/华南/华北")
    industry = Column(String(128), default="", comment="所属行业 / 业务领域")
    intro = Column(Text, default="", comment="客户档案 / 背景介绍（富文本）")
    key_focus = Column(Text, default="", comment="近期重点关注事项（富文本）")
    remark = Column(Text, default="", comment="备注")
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    version = Column(Integer, nullable=False, default=0, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    aliases = relationship(
        "CustomerAlias", back_populates="customer",
        cascade="all, delete-orphan", order_by="CustomerAlias.id",
    )


class CustomerAlias(Base):
    """客户别名：同一客户可有多个写法（中文全称、历史叫法、产品线绰号等）。

    alias 全局唯一，保证按名称反查时不歧义。
    """
    __tablename__ = "customer_aliases"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    alias = Column(String(256), nullable=False, index=True)

    customer = relationship("Customer", back_populates="aliases")

    __table_args__ = (UniqueConstraint("alias", name="uq_customer_aliases_alias"),)


class CustomerStatus(Base):
    __tablename__ = "customer_status"

    id = Column(Integer, primary_key=True, index=True)
    machine_id = Column(String(64), nullable=False, comment="机台编号")
    battlefield = Column(String(128), nullable=False, comment="客户名（展示快照）")
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="SET NULL"),
                         nullable=True, index=True,
                         comment="客户主数据 FK；为空表示未匹配/未对账")
    model = Column(String(128), default="", comment="型号")
    current_stage = Column(String(128), nullable=False, comment="当前阶段")
    field_version = Column(String(128), default="", comment="现场版本")
    attention_level = Column(Integer, default=0, comment="近期关注度: 0 未评估 / 1-5 星")
    customer_status = Column(String(256), nullable=False, comment="当前进展")
    recent_focus = Column(Text, default="", comment="近期现场关键诉求")
    key_issues = Column(Text, default="", comment="软件类风险和问题")
    issue_url = Column(String(512), default="", comment="问题单链接")
    milestones_json = Column(Text, default="", comment="机台里程碑 JSON：[{name,date,status}]")
    version = Column(Integer, nullable=False, default=0, comment="乐观锁版本号")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sow_rows = relationship(
        "SowRow", back_populates="machine_status",
        cascade="all, delete-orphan", order_by="SowRow.sort_order",
    )
    licenses = relationship(
        "MachineLicense", back_populates="machine_status",
        cascade="all, delete-orphan", order_by="MachineLicense.id",
    )
    issues = relationship(
        "CustomerIssue", back_populates="machine_status",
        cascade="all, delete-orphan", order_by="CustomerIssue.sort_order",
    )


class CustomerIssue(Base):
    """客户面「软件类风险和问题」/「现场关键事务」的单条记录。

    原来这两栏是 customer_status.key_issues / recent_focus 两个 Text 列里的
    JSON 清单 [{text, done}]：装不下责任人/时间/紧急程度，也无法跨战场汇总查询
    （只能把所有机台拉下来在前端拆 JSON）。这里提升为一行一条的实体表。

    一表两类，靠 kind 区分（同 specials 的 专项/攻关 套路）：
      - issue（软件类问题）：用全套字段
      - task （现场关键事务）：只用 description + due_date + status，其余留空
    customer_id 是从所属机台冗余下来的，汇总页按战场过滤/分组全靠它。
    """
    __tablename__ = "customer_issues"

    id = Column(Integer, primary_key=True, index=True)
    machine_status_id = Column(
        Integer, ForeignKey("customer_status.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="所属机台（customer_status 行）",
    )
    customer_id = Column(
        Integer, ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True, index=True, comment="所属客户/战场；随机台冗余，供汇总过滤",
    )
    kind = Column(String(16), nullable=False, default="issue", index=True,
                  comment="issue 软件类问题 / task 现场关键事务")
    description = Column(Text, default="", comment="问题描述 / 任务内容")
    issue_ref = Column(String(128), default="", comment="关联问题单编号（可为空）")
    urgency = Column(String(16), default="一般", comment="重要紧急 / 紧急 / 一般")
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                           nullable=True, index=True, comment="责任人（系统用户）")
    owner_name = Column(String(64), default="", comment="责任人自由文本（非系统用户时兜底）")
    group_id = Column(Integer, ForeignKey("resource_groups.id", ondelete="SET NULL"),
                      nullable=True, index=True, comment="责任领域（PL 组 FK）")
    owner_group = Column(String(64), default="", comment="责任领域自由文本快照（导入兜底）")
    progress_note = Column(Text, default="", comment="问题进展（多行文本）")
    category = Column(String(64), default="", comment="分类 / 专项")
    raised_at = Column(String(10), default="", comment="提出时间 YYYY-MM-DD")
    due_date = Column(String(10), default="", comment="计划解决时间 YYYY-MM-DD（逾期提醒基准）")
    closed_at = Column(String(10), default="", comment="实际闭环时间 YYYY-MM-DD")
    status = Column(String(16), nullable=False, default="OPEN", index=True,
                    comment="OPEN / CLOSED / 挂起")
    sort_order = Column(Integer, default=0, comment="同机台内的展示顺序")
    version = Column(Integer, nullable=False, default=0, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    machine_status = relationship("CustomerStatus", back_populates="issues")
    owner = relationship("User", foreign_keys=[owner_user_id])
    group = relationship("ResourceGroup", foreign_keys=[group_id])


class HardwareIssue(Base):
    """硬件问题清零：一行一条硬件问题，尾部按机台展开跟踪清零状态。

    固定列描述问题本身（来源/问题单号/简述/更换部件/责任/CCB结论/进展/SOP）；
    尾部每台机台一列，单元格存该机台的清零状态（下拉，选项在 config.json 维护）。
    per-machine 值集中存 machine_cells_json：{machine_status_id: 状态字符串}，
    机台增删不改表结构（同 SowRow.data 的套路）。协作编辑域；删除限 admin。
    """
    __tablename__ = "hardware_issues"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(128), default="", comment="来源")
    issue_ref = Column(String(128), default="", comment="问题单号")
    summary = Column(Text, default="", comment="问题简述")
    replaced_part = Column(String(256), default="", comment="更换部件")
    issue_source = Column(String(64), default="", comment="问题来源（config 下拉）")
    group_id = Column(Integer, ForeignKey("resource_groups.id", ondelete="SET NULL"),
                      nullable=True, index=True, comment="责任领域（PL 组 FK）")
    owner_group = Column(String(64), default="", comment="责任领域文本快照")
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                           nullable=True, index=True, comment="责任人（系统用户）")
    owner_name = Column(String(64), default="", comment="责任人自由文本兜底")
    ccb_conclusion = Column(Text, default="", comment="CCB 清零结论")
    ship_clear_from = Column(String(64), default="", comment="从 #N 开始发货清零（机台编号）")
    clear_progress = Column(Text, default="", comment="清零进展")
    sop_status = Column(Text, default="", comment="SOP 情况")
    machine_cells_json = Column(Text, default="{}", comment="{machine_status_id: 清零状态}")
    extra_fields_json = Column(Text, default="{}", comment="自定义列的值 {列key: 值}；列定义在 config.hw_extra_columns")
    sort_order = Column(Integer, default=0, comment="展示顺序")
    version = Column(Integer, nullable=False, default=0, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", foreign_keys=[owner_user_id])
    group = relationship("ResourceGroup", foreign_keys=[group_id])


class KeyFeature(Base):
    """关键特性目录（全局），机台通过 machine_key_features 多对多引用。

    交付状态六档（enums.KEY_FEATURE_STATUSES）＝点灯。需求度量三数（总SR/已验收/
    已转测）、责任人（FO/特性SE）、简介、附件（attachments_json）、关联问题单特性
    （issue_feature，用于"客户面关键问题"跳到问题单管理按 feature 过滤）。
    表由 create_all 自动建；协作编辑域，删除限 admin。
    """
    __tablename__ = "key_features"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False, default="", comment="关键特性名称")
    status = Column(String(16), nullable=False, default="分析", comment="交付状态（六档）＝点灯")
    # 需求度量
    total_sr = Column(Integer, default=0, comment="总 SR 数量")
    accepted_sr = Column(Integer, default=0, comment="已验收数量")
    to_test_sr = Column(Integer, default=0, comment="已转测数量")
    # 责任人
    fo = Column(String(64), default="", comment="FO 责任人")
    se = Column(String(64), default="", comment="特性 SE")
    # 内容
    intro = Column(Text, default="", comment="特性简介")
    attachments_json = Column(Text, default="[]", comment="附件/链接 [{id,kind,name,stored|url,size}]")
    issue_feature = Column(String(128), default="", comment="关联问题单特性名（客户面关键问题）")
    sort_order = Column(Integer, default=0)
    version = Column(Integer, nullable=False, default=0, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MachineKeyFeature(Base):
    """机台 ↔ 关键特性 多对多关联。客户面状态页每台机台勾选适用特性，总览据此点灯。"""
    __tablename__ = "machine_key_features"

    id = Column(Integer, primary_key=True, index=True)
    machine_status_id = Column(
        Integer, ForeignKey("customer_status.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    feature_id = Column(
        Integer, ForeignKey("key_features.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    __table_args__ = (
        UniqueConstraint("machine_status_id", "feature_id", name="uq_machine_feature"),
    )


class IssueReportDaily(Base):
    """问题单"历史数据"报表的按天聚合缓存（趋势图数据源）。

    历史数据 tab 原来每次画趋势都要把报表目录下所有 xlsx 重新用 openpyxl
    解析一遍（O(文件数)）。这里把每天的聚合"数字"落库：趋势直接读库，
    只有新增/变更（file_mtime 变化）的那一天才重新解析文件。明细仍按天在
    钻取时从本地 xlsx 现读，不进库。表由 create_all 自动建。
    """
    __tablename__ = "issue_report_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(String(10), nullable=False, unique=True, index=True, comment="YYYY-MM-DD")
    file_name = Column(String(256), default="", comment="该天取用的 xlsx 文件名")
    file_mtime = Column(String(40), default="", comment="文件 mtime（变更检测）")
    total = Column(Integer, default=0)
    by_group_json = Column(Text, default="{}", comment="{小组: 数量}")
    by_severity_json = Column(Text, default="{}", comment="{严重程度: 数量}")
    ingested_at = Column(DateTime, default=datetime.utcnow)


class SowFieldDef(Base):
    """SOW 表格列定义（全局共享一份）。
    所有客户、所有机台共用同一套列；admin 在 客户管理 → SOW 字段配置 里维护。
    """
    __tablename__ = "sow_field_defs"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(64), nullable=False, unique=True, comment="列 key（内部 ID）")
    label = Column(String(128), nullable=False, comment="表头显示文本")
    field_type = Column(String(16), nullable=False, default="text",
                        comment="text / date / select")
    options = Column(Text, default="[]", comment="select 列的候选项 JSON 数组")
    required = Column(Boolean, default=False, comment="是否必填")
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SowRow(Base):
    """单台机台下的一行 SOW 数据。data 字段以 JSON 形式存 {field_key: value}。"""
    __tablename__ = "sow_rows"

    id = Column(Integer, primary_key=True, index=True)
    machine_status_id = Column(
        Integer, ForeignKey("customer_status.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    data = Column(Text, default="{}", comment="JSON 字典: {field_key: value}")
    sort_order = Column(Integer, default=0)
    version = Column(Integer, nullable=False, default=0, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    machine_status = relationship("CustomerStatus", back_populates="sow_rows")


class MachineLicense(Base):
    """机台 license 文件。一台机台可以上传多个 license。"""
    __tablename__ = "machine_licenses"

    id = Column(Integer, primary_key=True, index=True)
    machine_status_id = Column(
        Integer, ForeignKey("customer_status.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    file_name = Column(String(256), nullable=False, comment="原始文件名")
    file_path = Column(String(512), nullable=False, comment="uploads/ 下的相对路径")
    file_size = Column(Integer, default=0)
    remark = Column(Text, default="", comment="备注")
    uploaded_by = Column(String(64), default="", comment="上传人 username")
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    machine_status = relationship("CustomerStatus", back_populates="licenses")


class CustomerExtraField(Base):
    """机台自定义信息块定义（全局共享一份）。

    管理员在 客户管理 → 自定义信息块 里维护。每个块在机台详情里渲染为
    "一段文本 + 一个附件/图片" 的卡片（如 MPH 状态）。
    """
    __tablename__ = "customer_extra_fields"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(64), nullable=False, unique=True, comment="块 key（内部 ID）")
    label = Column(String(128), nullable=False, comment="块标题，如 MPH状态")
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CustomerExtraValue(Base):
    """单台机台下某个自定义信息块的值：文本 + 单个附件。"""
    __tablename__ = "customer_extra_values"

    id = Column(Integer, primary_key=True, index=True)
    machine_status_id = Column(
        Integer, ForeignKey("customer_status.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    field_id = Column(
        Integer, ForeignKey("customer_extra_fields.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    text = Column(Text, default="", comment="文本内容")
    file_name = Column(String(256), default="", comment="附件原始文件名")
    file_path = Column(String(512), default="", comment="uploads/ 下的相对路径")
    file_size = Column(Integer, default=0)
    version = Column(Integer, nullable=False, default=0, comment="乐观锁版本号")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CustomerCustomReq(Base):
    """客户定制化需求（客户级，非机台级）。客户详情页"问题单情况"上方的表格。"""
    __tablename__ = "customer_custom_reqs"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    seq = Column(Integer, default=0, comment="序号")
    description = Column(Text, default="", comment="需求描述")
    customer_value = Column(Text, default="", comment="对客户价值")
    domain = Column(String(128), default="", comment="领域")
    designer = Column(String(64), default="", comment="设计人员")
    involves_other = Column(String(16), default="", comment="是否涉及其他项目")
    planned_version = Column(String(64), default="", comment="预计合入版本")
    remark = Column(Text, default="", comment="备注")
    version = Column(Integer, nullable=False, default=0, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Version(Base):
    __tablename__ = "versions"

    id = Column(Integer, primary_key=True, index=True)
    version_no = Column(String(64), nullable=False, comment="版本号")
    title = Column(String(256), nullable=False, comment="标题")
    description = Column(Text, default="", comment="版本说明")
    release_url = Column(String(512), default="", comment="跳转链接")
    released_at = Column(DateTime, default=datetime.utcnow, comment="发布时间")


class Iteration(Base):
    """旧版迭代表 —— 保留兼容，新业务请用 AnnualIteration。"""
    __tablename__ = "iterations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False, comment="迭代名称")
    goal = Column(Text, default="", comment="迭代目标")
    start_date = Column(DateTime, nullable=True, comment="开始时间")
    end_date = Column(DateTime, nullable=True, comment="结束时间")
    status = Column(String(32), default="planning", comment="状态")
    owner = Column(String(64), default="", comment="负责人")


class AnnualIteration(Base):
    """按年度规划的迭代：每年 12 个，每月一个。"""
    __tablename__ = "annual_iterations"
    __table_args__ = (UniqueConstraint("year", "month", name="uq_year_month"),)

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False, index=True, comment="年份")
    month = Column(Integer, nullable=False, comment="月份 1-12")
    name = Column(String(128), default="", comment="迭代名称")
    owner = Column(String(64), default="", comment="负责人（展示快照）")
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                           nullable=True, index=True, comment="负责人 FK")
    status = Column(String(32), default="planning", comment="状态: planning/in_progress/done")
    goal = Column(Text, default="", comment="迭代目标/备注")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    requirements = relationship(
        "IterationRequirement",
        back_populates="iteration",
        cascade="all, delete-orphan",
        order_by="IterationRequirement.seq",
    )
    product_requirements = relationship(
        "IterationProductRequirement",
        back_populates="iteration",
        cascade="all, delete-orphan",
        order_by="IterationProductRequirement.seq",
    )


class IterationProductRequirement(Base):
    """迭代下的"产品需求"：与 IterationRequirement（领域需求）并列的另一类清单。

    列结构与领域需求差异较大，单独建表，避免在同一行里塞大量空字段。
    """
    __tablename__ = "iteration_product_requirements"

    id = Column(Integer, primary_key=True, index=True)
    iteration_id = Column(Integer, ForeignKey("annual_iterations.id", ondelete="CASCADE"), nullable=False, index=True)
    seq = Column(Integer, default=0, comment="序号（排序用）")
    req_no = Column(String(64), default="", comment="需求编号")
    req_url = Column(String(512), default="", comment="需求超链接")
    title = Column(String(256), default="", comment="需求标题")
    planned_version = Column(String(64), default="", comment="计划交付版本（展示快照）")
    target_version_id = Column(Integer, ForeignKey("iteration_versions.id", ondelete="SET NULL"),
                               nullable=True, index=True, comment="计划交付迭代版本 FK")
    priority = Column(String(8), default="P2", comment="优先级 P0/P1/P2/P3（旧高/中/低已统一）")
    feature = Column(String(128), default="", comment="所属特性")
    feature_fo = Column(String(64), default="", comment="特性FO（展示快照）")
    feature_fo_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                                nullable=True, index=True, comment="特性FO FK")
    feature_se = Column(String(64), default="", comment="特性SE（展示快照）")
    feature_se_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                                nullable=True, index=True, comment="特性SE FK")
    feature_tfo = Column(String(64), default="", comment="特性TFO（展示快照）")
    feature_tfo_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                                 nullable=True, index=True, comment="特性TFO FK")
    code_areas = Column(Text, default="", comment="涉及代码领域")

    # 交付进展跟踪 ─── 进度子项，枚举：未开始/进行中/已完成/已延期/已变更/不涉及
    progress_walkthrough = Column(String(16), default="未开始", comment="需求串讲")
    progress_reverse = Column(String(16), default="未开始", comment="反串讲")
    progress_domain = Column(String(16), default="未开始", comment="领域串讲")
    progress_coding = Column(String(16), default="未开始", comment="编码")
    progress_joint_debug = Column(String(16), default="未开始", comment="联调验证")
    progress_clarify = Column(String(16), default="未开始", comment="转测澄清")
    progress_test_result = Column(String(16), default="未开始", comment="测试结论")

    # 数据/风险类自由字段
    estimated_loc = Column(String(32), default="", comment="预估代码量")
    actual_loc = Column(String(32), default="", comment="实际代码量")
    actual_effort = Column(String(32), default="", comment="实际工作量")
    key_risks = Column(Text, default="", comment="关键风险")

    version = Column(Integer, nullable=False, default=0, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    iteration = relationship("AnnualIteration", back_populates="product_requirements")


class IterationRequirement(Base):
    """迭代下的需求条目，含 6 个交付进展子状态。"""
    __tablename__ = "iteration_requirements"

    id = Column(Integer, primary_key=True, index=True)
    iteration_id = Column(Integer, ForeignKey("annual_iterations.id", ondelete="CASCADE"), nullable=False, index=True)
    seq = Column(Integer, default=0, comment="序号（排序用）")
    req_no = Column(String(64), default="", comment="需求编号")
    req_url = Column(String(512), default="", comment="需求超链接")
    title = Column(String(256), default="", comment="需求标题")
    owner = Column(String(64), default="", comment="交付责任人（展示快照）")
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                           nullable=True, index=True, comment="交付责任人 FK")
    owner_group = Column(String(64), default="", comment="PL组（展示快照）")
    group_id = Column(Integer, ForeignKey("resource_groups.id", ondelete="SET NULL"),
                      nullable=True, index=True, comment="PL组 FK")
    priority = Column(String(16), default="P2", comment="优先级 P0/P1/P2/P3")
    planned_version = Column(String(64), default="", comment="计划交付版本（展示快照）")
    target_version_id = Column(Integer, ForeignKey("iteration_versions.id", ondelete="SET NULL"),
                               nullable=True, index=True, comment="计划交付迭代版本 FK")

    # 6 个交付进展子项：状态枚举见 enums.PROGRESS_STATUSES（未开始/进行中/已完成/已延期/已变更/不涉及）
    progress_walkthrough = Column(String(16), default="未开始", comment="需求串讲")
    progress_reverse = Column(String(16), default="未开始", comment="反串讲")
    progress_stc = Column(String(16), default="未开始", comment="STC设计")
    progress_coding = Column(String(16), default="未开始", comment="编码")
    progress_bbit = Column(String(16), default="未开始", comment="BBIT")
    progress_clarify = Column(String(16), default="未开始", comment="转测澄清")

    # 版本质量统计 ─── 迭代质量度量用
    merge_links = Column(Text, default="", comment="合入链接（支持多个，每行一个）")
    code_volume = Column(Integer, nullable=True, comment="代码量(行)")
    self_test_case_count = Column(Integer, nullable=True, comment="自验证用例数")
    post_test_issue_count = Column(Integer, nullable=True, comment="转测后问题单数量")

    remark = Column(Text, default="", comment="备注（是否存在变更等）")

    version = Column(Integer, nullable=False, default=0, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    iteration = relationship("AnnualIteration", back_populates="requirements")


class RoadmapProject(Base):
    """首页项目里程碑：一个产品下可以挂多个项目。"""
    __tablename__ = "roadmap_projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False, comment="项目名称")
    description = Column(String(256), default="", comment="副标题/简要描述")
    year = Column(Integer, nullable=True, comment="年份（可选，仅展示）")
    granularity = Column(String(16), default="quarter", comment="精度: quarter / month")
    sort_order = Column(Integer, default=0, comment="排序")
    is_active = Column(Boolean, default=True, comment="是否在首页展示")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    phases = relationship(
        "RoadmapPhase",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="RoadmapPhase.sort_order",
    )
    milestones = relationship(
        "RoadmapMilestone",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="(RoadmapMilestone.year, RoadmapMilestone.month, RoadmapMilestone.sort_order)",
    )
    major_versions = relationship(
        "MajorVersion",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="MajorVersion.sort_order",
    )


class RoadmapPhase(Base):
    """路线图上方阶段块：含锚点、彩色标题、目标/核心产品/应用场景文本。"""
    __tablename__ = "roadmap_phases"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("roadmap_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(64), nullable=False, comment="阶段名称")
    color = Column(String(16), default="#409EFF", comment="阶段主色 #RRGGBB")
    start_year = Column(Integer, nullable=False, default=lambda: datetime.utcnow().year, comment="起始年份")
    start_month = Column(Integer, nullable=False, comment="起始月份 1-12")
    end_year = Column(Integer, nullable=False, default=lambda: datetime.utcnow().year, comment="结束年份")
    end_month = Column(Integer, nullable=False, comment="结束月份 1-12")
    goal = Column(Text, default="", comment="目标（多行）")
    core_products = Column(String(256), default="", comment="核心产品")
    scenarios = Column(Text, default="", comment="主要应用场景（多行）")
    sort_order = Column(Integer, default=0, comment="排序")
    version = Column(Integer, nullable=False, default=0, comment="乐观锁版本号")

    project = relationship("RoadmapProject", back_populates="phases")


class RoadmapMilestone(Base):
    """时间轴下方月份卡片：产品名 + 描述。"""
    __tablename__ = "roadmap_milestones"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("roadmap_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    year = Column(Integer, nullable=False, default=lambda: datetime.utcnow().year, comment="年份")
    month = Column(Integer, nullable=False, comment="月份 1-12")
    title = Column(String(128), default="", comment="产品/版本名（蓝框文字）")
    description = Column(Text, default="", comment="描述文字")
    sort_order = Column(Integer, default=0, comment="同月内排序")

    project = relationship("RoadmapProject", back_populates="milestones")


class MajorVersion(Base):
    """大版本：归属于某个里程碑项目，包含若干迭代版本。"""
    __tablename__ = "major_versions"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("roadmap_projects.id", ondelete="SET NULL"), nullable=True, index=True)
    version_no = Column(String(64), nullable=False, comment="大版本号")
    title = Column(String(256), default="", comment="标题")
    description = Column(Text, default="", comment="版本说明")
    range_start = Column(DateTime, nullable=True, comment="版本范围开始")
    range_end = Column(DateTime, nullable=True, comment="版本范围结束")
    actual_release_date = Column(DateTime, nullable=True, comment="实际发布时间")
    sort_order = Column(Integer, default=0, comment="排序")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("RoadmapProject", back_populates="major_versions")
    iteration_versions = relationship(
        "IterationVersion",
        back_populates="major_version",
        cascade="all, delete-orphan",
        order_by="IterationVersion.sort_order",
    )


class IterationVersion(Base):
    """迭代版本：隶属于大版本，预计每周一个。"""
    __tablename__ = "iteration_versions"

    id = Column(Integer, primary_key=True, index=True)
    major_version_id = Column(Integer, ForeignKey("major_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    version_no = Column(String(64), nullable=False, comment="迭代版本号")
    title = Column(String(256), default="", comment="标题")
    planned_date = Column(DateTime, nullable=True, comment="预计发布日期")
    sort_order = Column(Integer, default=0, comment="排序")
    created_at = Column(DateTime, default=datetime.utcnow)

    major_version = relationship("MajorVersion", back_populates="iteration_versions")


class StakeholderProjectContact(Base):
    """项目组沟通地图条目（两列表格）"""
    __tablename__ = "stakeholder_project_contacts"

    id = Column(Integer, primary_key=True, index=True)
    sort_order = Column(Integer, default=0, comment="排序")
    col1 = Column(String(256), default="", comment="列1（角色）")
    col2 = Column(String(256), default="", comment="列2（姓名/工号）")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class StakeholderBattlefield(Base):
    """战场沟通矩阵条目（六列表格）"""
    __tablename__ = "stakeholder_battlefields"

    id = Column(Integer, primary_key=True, index=True)
    sort_order = Column(Integer, default=0, comment="排序")
    battlefield = Column(String(128), default="", comment="战场（客户名展示快照）")
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="SET NULL"),
                         nullable=True, index=True, comment="客户主数据 FK")
    region = Column(String(128), default="", comment="地域")
    service = Column(String(256), default="", comment="服务")
    contact1 = Column(Text, default="", comment="联系方式（服务）")
    apps = Column(String(256), default="", comment="APPS")
    contact2 = Column(Text, default="", comment="联系方式（APPS）")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProjectFormationImage(Base):
    """项目阵型图：全局单张图片/SVG，存 id=1 这一行。"""
    __tablename__ = "project_formation_image"

    id = Column(Integer, primary_key=True, index=True)
    image_path = Column(String(512), default="", comment="服务器相对路径")
    image_name = Column(String(256), default="", comment="原文件名")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProjectFormationMember(Base):
    """项目阵型 人员名单：投入人员 + 挂靠情况。"""
    __tablename__ = "project_formation_members"

    id = Column(Integer, primary_key=True, index=True)
    sort_order = Column(Integer, default=0)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                     nullable=True, index=True, comment="人员主数据 FK")
    name = Column(String(64), nullable=False, comment="姓名（展示快照）")
    emp_no = Column(String(64), default="", comment="工号（展示快照）")
    pl_group = Column(String(64), default="", comment="PL组（展示快照）")
    role = Column(String(64), default="", comment="角色 / 岗位")
    special_attach = Column(String(128), default="", comment="挂靠专项 / 攻关")
    allocation = Column(String(32), default="", comment="投入比例 (如 0.5 / 30% / 全职)")
    remark = Column(Text, default="", comment="备注")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ResourceGroup(Base):
    """资源组主数据：两级结构（部门 dept → PL组 pl）。

    - code 全局唯一、作为业务主键，不允许改名（改名只改 name 即可）
    - kind="dept" 时 parent_id 必为空；kind="pl" 时 parent_id 必指向某个 dept
    - leader_id 指向 users.id；leader 离职不级联清空，靠 UI 提示
    - 业务表的 owner_group 字符串将逐步迁移成 group_id FK
    """
    __tablename__ = "resource_groups"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(64), nullable=False, unique=True, index=True, comment="内部稳定 ID，不可改")
    name = Column(String(128), nullable=False, comment="展示名（可改）")
    kind = Column(String(16), nullable=False, default="pl", comment="dept=部门 / pl=PL组")
    parent_id = Column(Integer, ForeignKey("resource_groups.id", ondelete="SET NULL"),
                       nullable=True, index=True, comment="kind=pl 时指向所属 dept")
    leader_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                       nullable=True, comment="组长 / 部门长")
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    remark = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    parent = relationship("ResourceGroup", remote_side=[id], foreign_keys=[parent_id])


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True, comment="登录名")
    full_name = Column(String(128), default="", comment="姓名")
    emp_no = Column(String(64), default="", index=True, comment="工号")
    password_hash = Column(String(256), default="", comment="密码哈希(本地账户)")
    role = Column(String(16), default="normal", comment="admin / normal")
    auth_provider = Column(String(32), default="local", comment="local / company_sso (预留)")
    is_active = Column(Boolean, default=True, comment="是否启用")
    can_login = Column(Boolean, default=True, comment="是否允许登录（false=纯人员档案）")
    group_id = Column(Integer, ForeignKey("resource_groups.id", ondelete="SET NULL"),
                      nullable=True, index=True, comment="所属 PL 组")
    job_title = Column(String(64), default="", comment="岗位 / 角色")
    created_at = Column(DateTime, default=datetime.utcnow)

    group = relationship("ResourceGroup", foreign_keys=[group_id])


class HandbookCategory(Base):
    """项目一本通：自定义分类（流程/规范/PPT模板/...）"""
    __tablename__ = "handbook_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), nullable=False, comment="分类名称")
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship(
        "HandbookItem",
        back_populates="category",
        cascade="all, delete-orphan",
        order_by="HandbookItem.sort_order",
    )


class HandbookItem(Base):
    __tablename__ = "handbook_items"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("handbook_categories.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    title = Column(String(256), nullable=False, comment="标题")
    kind = Column(String(16), default="link", comment="link / file")
    url = Column(String(1024), default="", comment="外链 URL (kind=link)")
    file_path = Column(String(512), default="", comment="服务器相对路径 (kind=file)")
    file_name = Column(String(256), default="", comment="原始文件名 (kind=file)")
    file_size = Column(Integer, default=0, comment="文件大小 字节")
    description = Column(Text, default="")
    owner = Column(String(64), default="", comment="责任人（展示快照）")
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                           nullable=True, index=True, comment="责任人 FK")
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category = relationship("HandbookCategory", back_populates="items")


class Special(Base):
    """专项 / 攻关：每条 = 一项工作（左侧二级菜单 + 一个详情页）"""
    __tablename__ = "specials"

    id = Column(Integer, primary_key=True, index=True)
    # slug 历史字段，保留兼容；新数据不再依赖。
    slug = Column(String(64), default="", index=True, comment="历史字段，不再使用")
    kind = Column(String(16), default="special", comment="special=专项 / assault=攻关")
    name = Column(String(128), nullable=False, comment="名称")
    owner = Column(String(64), default="", comment="责任人（展示快照）")
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                           nullable=True, index=True, comment="责任人 FK")
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    email_to = Column(String(512), default="", comment="周报默认主送，逗号分隔")
    email_cc = Column(String(512), default="", comment="周报默认抄送，逗号分隔")
    email_subject_tpl = Column(String(256), default="", comment="周报默认主题模板")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    content = relationship(
        "SpecialContent", uselist=False, back_populates="special",
        cascade="all, delete-orphan",
    )
    tasks = relationship(
        "SpecialTask", back_populates="special",
        cascade="all, delete-orphan", order_by="SpecialTask.sort_order",
    )
    risks = relationship(
        "SpecialRisk", back_populates="special",
        cascade="all, delete-orphan", order_by="SpecialRisk.sort_order",
    )


class SpecialContent(Base):
    """单个专项的"页面富字段"，1:1 与 specials。"""
    __tablename__ = "special_contents"

    id = Column(Integer, primary_key=True, index=True)
    special_id = Column(Integer, ForeignKey("specials.id", ondelete="CASCADE"),
                        unique=True, nullable=False, index=True)
    goal = Column(Text, default="", comment="专项目标")
    progress_summary = Column(Text, default="", comment="整体进展")
    help_request = Column(Text, default="", comment="求助")
    panorama_image_path = Column(String(512), default="", comment="专项全景图：服务器相对路径")
    panorama_image_name = Column(String(256), default="")
    # 里程碑：[{name,date,status}]
    milestones_json = Column(Text, default="[]")
    # 阵型：{"headers":[...], "rows":[[cell, cell, ...], ...]}
    formation_json = Column(Text, default='{"headers":[],"rows":[]}')
    # 附加的若干"自由表格"（已提升为独立分段）：[{title, gid, headers, rows, colTypes, colOptions}, ...]
    extra_grids_json = Column(Text, default="[]")
    # 分段显示顺序：["goal","plan",...,"grid:<gid>"]（空数组=按默认顺序）
    section_order_json = Column(Text, default="[]")
    version = Column(Integer, nullable=False, default=0, comment="乐观锁")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    special = relationship("Special", back_populates="content")


class SpecialTask(Base):
    """专项/攻关 事务表的一行。"""
    __tablename__ = "special_tasks"
    id = Column(Integer, primary_key=True, index=True)
    special_id = Column(Integer, ForeignKey("specials.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    seq = Column(Integer, default=0)
    content = Column(Text, default="", comment="事务内容")
    progress = Column(Text, default="", comment="当前进展")
    owner = Column(String(64), default="", comment="责任人（展示快照）")
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                           nullable=True, index=True, comment="责任人 FK")
    planned_close_date = Column(String(32), default="", comment="计划闭环时间")
    status = Column(String(16), default="open", comment="open / closed")
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    special = relationship("Special", back_populates="tasks")


class SpecialRisk(Base):
    """风险/问题表的一行（结构与事务同）。"""
    __tablename__ = "special_risks"
    id = Column(Integer, primary_key=True, index=True)
    special_id = Column(Integer, ForeignKey("specials.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    seq = Column(Integer, default=0)
    content = Column(Text, default="", comment="问题内容")
    progress = Column(Text, default="", comment="当前进展")
    owner = Column(String(64), default="", comment="责任人（展示快照）")
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                           nullable=True, index=True, comment="责任人 FK")
    planned_close_date = Column(String(32), default="", comment="计划闭环时间")
    status = Column(String(16), default="open", comment="open / closed")
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    special = relationship("Special", back_populates="risks")


class SpecialEditLock(Base):
    """专项详情页「编辑锁」：同一专项同一时刻只允许一个人处于编辑模式。

    - special_id 唯一 → 一项专项至多一把锁。
    - 锁靠前端心跳续期；超过 TTL 未续期视为失效，可被他人接管（服务端按时间判断，不主动清理）。
    - 管理员可强制接管。
    """
    __tablename__ = "special_edit_locks"

    special_id = Column(Integer, ForeignKey("specials.id", ondelete="CASCADE"),
                        primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    user_name = Column(String(64), default="", comment="持锁人展示名快照")
    acquired_at = Column(DateTime, default=datetime.utcnow, comment="本次取得锁的时间")
    heartbeat_at = Column(DateTime, default=datetime.utcnow, index=True, comment="最后一次心跳")


class Notification(Base):
    """站内通知。

    - recipient_id=NULL 表示广播；已读状态走 NotificationRead 表
    - recipient_id 非空表示定向：is_read 直接用本表的字段
    - kind 含义：mention / assignment / status_change / due_soon / overdue /
      version_plan / broadcast / system
    """
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    recipient_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                          nullable=True, index=True,
                          comment="收件人；NULL 表示广播")
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                      nullable=True, comment="触发者；NULL 表示系统")
    kind = Column(String(32), nullable=False, index=True, comment="见类注释")
    title = Column(String(256), nullable=False)
    body = Column(Text, default="")
    link = Column(String(512), default="", comment="前端点击跳转目标，如 /iterations/12")
    source_type = Column(String(32), default="", index=True,
                         comment="iteration_requirement / customer / special / version / ...")
    source_id = Column(Integer, default=0, index=True)
    is_read = Column(Boolean, default=False, index=True,
                     comment="仅定向通知（recipient_id 非空）用；广播通知忽略此字段")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    read_at = Column(DateTime, nullable=True)


class NotificationRead(Base):
    """广播通知的已读登记表。"""
    __tablename__ = "notification_reads"
    __table_args__ = (UniqueConstraint("notification_id", "user_id", name="uq_notif_read_user"),)

    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(Integer, ForeignKey("notifications.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    read_at = Column(DateTime, default=datetime.utcnow)


class Subscription(Base):
    """用户对某类目标的订阅。

    source_id=NULL 表示该 source_type 的全部（很少用，比如订阅"所有专项"）。
    events 为 CSV，默认 '*' 即所有事件。
    """
    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("user_id", "source_type", "source_id", name="uq_sub_user_source"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    source_type = Column(String(32), nullable=False, index=True)
    source_id = Column(Integer, nullable=True, index=True)
    events = Column(String(256), default="*", comment="CSV: status_change,comment,...")
    created_at = Column(DateTime, default=datetime.utcnow)


class OperationLog(Base):
    """登录与关键业务写操作日志，供管理员审计。"""
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    user_id = Column(Integer, nullable=True, index=True, comment="登录失败时可为空")
    username = Column(String(64), default="", index=True, comment="冗余存储,便于查询")
    action = Column(String(32), nullable=False, index=True, comment="登录/登出/登录失败/新增/修改/删除/...")
    target = Column(String(64), default="", index=True, comment="目标类型,如 用户/客户面状态/...")
    target_id = Column(String(64), default="", comment="目标主键,可为空")
    detail = Column(Text, default="", comment="补充说明 (摘要,不存敏感字段)")
    ip = Column(String(64), default="")
    user_agent = Column(String(256), default="")


class DebugVersion(Base):
    """客户面调试版本（T 版本）：发往现场调试的版本记录。

    协作编辑域——登录用户均可填，带乐观锁。新表由 create_all 自动建。
    """
    __tablename__ = "debug_versions"

    id = Column(Integer, primary_key=True, index=True)
    version_no = Column(String(128), nullable=False, comment="版本号")
    baseline_version = Column(String(128), default="", comment="基线版本")
    target_customer_id = Column(Integer, ForeignKey("customers.id", ondelete="SET NULL"),
                                nullable=True, index=True, comment="目标客户 FK（customers）")
    planned_release_date = Column(DateTime, nullable=True, comment="计划发布时间")
    release_date = Column(DateTime, nullable=True, comment="发布时间（发到现场）")
    # 合入内容三块
    merge_offline_cluster = Column(Text, default="", comment="合入内容-离线集群")
    merge_online_flow = Column(Text, default="", comment="合入内容-在线流程")
    merge_offline_analysis = Column(Text, default="", comment="合入内容-离线分析软件")
    selfcheck_archive = Column(Text, default="", comment="自验证报告归档情况")
    sort_order = Column(Integer, default=0)
    version = Column(Integer, nullable=False, default=0, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DebugDemand(Base):
    """客户面调试版本的「诉求收集」。涉及战场为客户 id 列表（JSON）。"""
    __tablename__ = "debug_demands"

    id = Column(Integer, primary_key=True, index=True)
    seq = Column(Integer, default=0, comment="序号")
    demand = Column(Text, default="", comment="诉求")
    problem_solved = Column(Text, default="", comment="解决问题")
    feature = Column(String(256), default="", comment="特性")
    battlefields_json = Column(Text, default="[]", comment="涉及战场：客户 id JSON 数组")
    expected_time = Column(String(64), default="", comment="期望时间")
    actual_version = Column(String(128), default="", comment="实际合入版本")
    sort_order = Column(Integer, default=0)
    version = Column(Integer, nullable=False, default=0, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DebugVersionRecipient(Base):
    """现场调试版本的「接受版本姓名列表」。

    发布时按调试版本的目标客户从「战场沟通矩阵」自动带出接收人，可手工增删，
    逐人勾选是否已接收。一个调试版本多行；调试版本删除则级联清理。
    """
    __tablename__ = "debug_version_recipients"

    id = Column(Integer, primary_key=True, index=True)
    debug_version_id = Column(Integer, ForeignKey("debug_versions.id", ondelete="CASCADE"),
                              nullable=False, index=True, comment="所属调试版本 FK")
    name = Column(String(128), default="", comment="接收人姓名 / 联系人")
    role = Column(String(128), default="", comment="来源 / 角色（如 服务 / APPS / 地域）")
    received = Column(Boolean, nullable=False, default=False, comment="是否已接收")
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DomainContent(Base):
    """领域管理：每个 PL 组（资源组 kind=pl）一行的手填内容。

    需求情况 / 问题单情况是从迭代需求、问题单 Excel 实时聚合的派生数据，不入库；
    这里只持久化两块需要人工维护的字段：最近主要工作（富文本）、风险与求助（结构化逐条）。
    """
    __tablename__ = "domain_contents"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("resource_groups.id", ondelete="CASCADE"),
                      unique=True, nullable=False, index=True, comment="PL 组 FK")
    recent_work = Column(Text, default="", comment="最近主要工作（富文本 HTML）")
    # 风险与求助：[{content, type: 风险|求助, status}]
    risks_json = Column(Text, default="[]", comment="风险与求助逐条 JSON")
    version = Column(Integer, nullable=False, default=0, comment="乐观锁")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DomainHidden(Base):
    """领域管理里被「移除/不管理」的 PL 组（软删除）：有行＝隐藏，删行＝恢复。

    独立成表，避免给既有 domain_contents 加列（老库 create_all 不补列）。
    """
    __tablename__ = "domain_hidden"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("resource_groups.id", ondelete="CASCADE"),
                      unique=True, nullable=False, index=True, comment="被隐藏的 PL 组 FK")
    created_at = Column(DateTime, default=datetime.utcnow)


class DomainRisk(Base):
    """领域管理 · 事务与风险跟踪。类专项的「风险和问题」，但跨领域、带责任领域列。

    协作编辑域，带乐观锁。状态 OPEN/CLOSED/挂起；新表由 create_all 自动建。
    """
    __tablename__ = "domain_risks"

    id = Column(Integer, primary_key=True, index=True)
    seq = Column(Integer, default=0, comment="序号")
    content = Column(Text, default="", comment="风险和事务")
    priority = Column(String(16), default="中", comment="优先级 高/中/低")
    progress = Column(Text, default="", comment="当前进展")
    domain_id = Column(Integer, ForeignKey("resource_groups.id", ondelete="SET NULL"),
                       nullable=True, index=True, comment="责任领域（PL 组 FK）")
    planned_close_date = Column(DateTime, nullable=True, comment="计划闭环时间")
    status = Column(String(16), default="OPEN", comment="OPEN / CLOSED / 挂起")
    sort_order = Column(Integer, default=0)
    version = Column(Integer, nullable=False, default=0, comment="乐观锁")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BusinessTrip(Base):
    """成员出差记录：谁、去哪个战场（客户主数据）、哪段时间、什么事由。

    协作编辑域——登录用户均可填，带乐观锁。状态按起止日期实时推导
    （计划中/进行中/已完成），另有 cancelled 标记。新表由 create_all 自动建。
    """
    __tablename__ = "business_trips"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                     nullable=True, index=True, comment="出差人 FK（users）")
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="SET NULL"),
                         nullable=True, index=True, comment="目的地战场 FK（customers）")
    location = Column(String(128), default="", comment="具体地点 / 非战场补充")
    purpose = Column(String(256), default="", comment="出差事由")
    start_date = Column(DateTime, nullable=True, comment="出发日期")
    end_date = Column(DateTime, nullable=True, comment="返回日期")
    cancelled = Column(Boolean, nullable=False, default=False, comment="是否取消")
    remark = Column(Text, default="", comment="备注")
    sort_order = Column(Integer, default=0)
    version = Column(Integer, nullable=False, default=0, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class IssueSnapshot(Base):
    """问题单每日快照（按项目/版本）：库里只存"数字"，明细表格落本地文件。

    每个项目每天最多一条（project+snapshot_date 唯一，重复采集覆盖）。
    - 库：total 总数 + 各维度聚合在 issue_snapshot_stats（趋势数据源，看趋势只读数字）；
    - 文件：完整明细行以 JSON 落到快照根目录（data_file 为相对路径），看某次快照才加载。
    新表由 create_all 自动建。
    """
    __tablename__ = "issue_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    project = Column(String(64), nullable=False, index=True, comment="项目/版本，如 YLS3000")
    snapshot_date = Column(String(10), nullable=False, index=True, comment="采集日 YYYY-MM-DD")
    total = Column(Integer, nullable=False, default=0, comment="问题单总数")
    data_file = Column(String(300), default="", comment="明细 JSON 相对路径（相对快照根目录）")
    source = Column(String(16), default="api", comment="来源：api（定时）/ manual（手动）")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("project", "snapshot_date", name="uq_issue_snapshot_project_date"),
    )


class IssueSnapshotStat(Base):
    """快照的维度聚合数字（趋势数据源）：dimension ∈ group / customer / severity。"""
    __tablename__ = "issue_snapshot_stats"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_id = Column(Integer, ForeignKey("issue_snapshots.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    dimension = Column(String(16), nullable=False, index=True, comment="group / customer / severity")
    dim_key = Column(String(128), nullable=False, default="", comment="维度取值，如小组名/客户面名/严重程度")
    count = Column(Integer, nullable=False, default=0)


class IssueCollectLog(Base):
    """问题单采集执行日志：每次采集（定时 / 手动）一条，成功失败都记。

    快照表只留"最后成功的结果"，失败时它什么都不写，排查无从下手。这张表专门
    记录执行过程：耗时、退出信息、失败原因，用于定位"脚本报错 / 采集超时"。
    新表由 create_all 自动建。
    """
    __tablename__ = "issue_collect_logs"

    id = Column(Integer, primary_key=True, index=True)
    project = Column(String(64), nullable=False, index=True, comment="项目/版本，如 YLS3000")
    source = Column(String(16), default="auto", comment="来源：auto（定时）/ manual（手动）")
    ok = Column(Boolean, default=False, index=True, comment="是否采集成功")
    total = Column(Integer, default=0, comment="成功时采集到的问题单条数")
    duration_ms = Column(Integer, default=0, comment="耗时（毫秒）")
    error = Column(Text, default="", comment="失败原因（含脚本 stderr 尾部）")
    started_at = Column(DateTime, default=datetime.utcnow, index=True)
    finished_at = Column(DateTime)
