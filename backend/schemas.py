from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, field_validator

import enums


# Pydantic v2 把 model_ 视为受保护命名空间，CustomerStatus 里有个 `model` 列，
# 这里全局放开，避免警告/冲突。
_BASE_CONFIG = ConfigDict(from_attributes=True, protected_namespaces=())


# ===== Customer (主数据) =====
class CustomerAliasOut(BaseModel):
    id: int
    alias: str

    model_config = ConfigDict(from_attributes=True)


class CustomerBase(BaseModel):
    code: str
    display_name: Optional[str] = ""
    region: Optional[str] = ""
    industry: Optional[str] = ""
    intro: Optional[str] = ""
    key_focus: Optional[str] = ""
    remark: Optional[str] = ""
    is_active: Optional[bool] = True
    sort_order: Optional[int] = 0


class CustomerCreate(CustomerBase):
    aliases: List[str] = []


class CustomerUpdate(BaseModel):
    """单字段或多字段更新；提供 aliases 则做全量替换，未提供则别名不变。"""
    version: int
    code: Optional[str] = None
    display_name: Optional[str] = None
    region: Optional[str] = None
    industry: Optional[str] = None
    intro: Optional[str] = None
    key_focus: Optional[str] = None
    remark: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    aliases: Optional[List[str]] = None


class CustomerOut(CustomerBase):
    id: int
    version: int
    aliases: List[CustomerAliasOut] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ===== CustomerStatus =====
class CustomerStatusBase(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    machine_id: str
    battlefield: str
    model: Optional[str] = ""
    current_stage: str
    field_version: Optional[str] = ""
    attention_level: Optional[int] = 0
    customer_status: str
    recent_focus: Optional[str] = ""
    key_issues: Optional[str] = ""
    issue_url: Optional[str] = ""
    milestones_json: Optional[str] = ""


class CustomerStatusCreate(CustomerStatusBase):
    pass


class CustomerStatusUpdate(BaseModel):
    """编辑允许的字段；机台编号/客户/型号 创建后锁定，由后端忽略。
    管理员字段：current_stage / field_version / attention_level / issue_url
    所有用户：customer_status / recent_focus / key_issues
    路由层按角色再做校验。
    """
    model_config = ConfigDict(protected_namespaces=())

    version: int
    current_stage: Optional[str] = None
    field_version: Optional[str] = None
    attention_level: Optional[int] = None
    issue_url: Optional[str] = None
    customer_status: Optional[str] = None
    recent_focus: Optional[str] = None
    key_issues: Optional[str] = None
    milestones_json: Optional[str] = None


class CustomerStatusOut(CustomerStatusBase):
    id: int
    customer_id: Optional[int] = None
    version: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


# ===== CustomerIssue（软件类问题 / 现场关键事务）=====
class CustomerIssueBase(BaseModel):
    """注意：不在 Base 上挂 norm_* 校验器。

    Base 被 Out 继承，而 Out 走 from_attributes 读库；老库里若有历史脏值，
    读取时就会 422。校验只放在 Create/Update（写入口）上。
    """
    kind: Optional[str] = "issue"
    description: Optional[str] = ""
    issue_ref: Optional[str] = ""
    urgency: Optional[str] = "一般"
    owner_user_id: Optional[int] = None
    owner_name: Optional[str] = ""
    group_id: Optional[int] = None
    owner_group: Optional[str] = ""
    progress_note: Optional[str] = ""
    category: Optional[str] = ""
    raised_at: Optional[str] = ""
    due_date: Optional[str] = ""
    closed_at: Optional[str] = ""
    status: Optional[str] = "OPEN"
    sort_order: Optional[int] = 0


class CustomerIssueCreate(CustomerIssueBase):
    machine_status_id: int

    @field_validator("kind")
    @classmethod
    def _v_kind(cls, v):
        return enums.norm_issue_kind(v)

    @field_validator("status")
    @classmethod
    def _v_status(cls, v):
        return enums.norm_issue_status(v)

    @field_validator("urgency")
    @classmethod
    def _v_urgency(cls, v):
        return enums.norm_issue_urgency(v)


class CustomerIssueUpdate(BaseModel):
    version: int
    description: Optional[str] = None
    issue_ref: Optional[str] = None
    urgency: Optional[str] = None
    owner_user_id: Optional[int] = None
    owner_name: Optional[str] = None
    group_id: Optional[int] = None
    owner_group: Optional[str] = None
    progress_note: Optional[str] = None
    category: Optional[str] = None
    raised_at: Optional[str] = None
    due_date: Optional[str] = None
    closed_at: Optional[str] = None
    status: Optional[str] = None
    sort_order: Optional[int] = None

    @field_validator("status")
    @classmethod
    def _v_status(cls, v):
        return enums.norm_issue_status(v, partial=True)

    @field_validator("urgency")
    @classmethod
    def _v_urgency(cls, v):
        return enums.norm_issue_urgency(v, partial=True)


class CustomerIssueOut(CustomerIssueBase):
    id: int
    machine_status_id: int
    customer_id: Optional[int] = None
    version: int
    updated_at: Optional[datetime] = None
    # 汇总页展示用的冗余字段，由路由层填充（非 ORM 列）
    machine_id: Optional[str] = ""
    battlefield: Optional[str] = ""
    owner_display: Optional[str] = ""
    group_name: Optional[str] = ""
    overdue: Optional[bool] = False

    model_config = _BASE_CONFIG


# ===== 硬件问题清零 =====
class HardwareIssueBase(BaseModel):
    source: Optional[str] = ""
    issue_ref: Optional[str] = ""
    summary: Optional[str] = ""
    replaced_part: Optional[str] = ""
    issue_source: Optional[str] = ""
    group_id: Optional[int] = None
    owner_group: Optional[str] = ""
    owner_user_id: Optional[int] = None
    owner_name: Optional[str] = ""
    ccb_conclusion: Optional[str] = ""
    ship_clear_from: Optional[str] = ""
    clear_progress: Optional[str] = ""
    sop_status: Optional[str] = ""
    sort_order: Optional[int] = 0
    # {machine_status_id(str): 清零状态}；后端与 machine_cells_json 互转
    machine_cells: Dict[str, str] = {}
    # 自定义列取值 {列key: 值}；列定义在 config.hw_extra_columns
    extra_fields: Dict[str, str] = {}


class HardwareIssueCreate(HardwareIssueBase):
    pass


class HardwareIssueUpdate(BaseModel):
    version: int
    source: Optional[str] = None
    issue_ref: Optional[str] = None
    summary: Optional[str] = None
    replaced_part: Optional[str] = None
    issue_source: Optional[str] = None
    group_id: Optional[int] = None
    owner_group: Optional[str] = None
    owner_user_id: Optional[int] = None
    owner_name: Optional[str] = None
    ccb_conclusion: Optional[str] = None
    ship_clear_from: Optional[str] = None
    clear_progress: Optional[str] = None
    sop_status: Optional[str] = None
    sort_order: Optional[int] = None
    machine_cells: Optional[Dict[str, str]] = None
    extra_fields: Optional[Dict[str, str]] = None


class HardwareIssueOut(HardwareIssueBase):
    id: int
    version: int
    updated_at: Optional[datetime] = None
    owner_display: Optional[str] = ""
    group_name: Optional[str] = ""

    model_config = _BASE_CONFIG


# ===== 关键特性目录（交付状态点灯 + 需求度量 + 责任人 + 附件）=====
class KeyFeatureBase(BaseModel):
    name: Optional[str] = ""
    status: Optional[str] = "分析"
    total_sr: Optional[int] = 0
    accepted_sr: Optional[int] = 0
    to_test_sr: Optional[int] = 0
    fo: Optional[str] = ""
    se: Optional[str] = ""
    intro: Optional[str] = ""
    issue_feature: Optional[str] = ""
    sort_order: Optional[int] = 0


class KeyFeatureCreate(KeyFeatureBase):
    @field_validator("status")
    @classmethod
    def _v_status(cls, v):
        return enums.norm_key_feature_status(v)


class KeyFeatureUpdate(BaseModel):
    version: int
    name: Optional[str] = None
    status: Optional[str] = None
    total_sr: Optional[int] = None
    accepted_sr: Optional[int] = None
    to_test_sr: Optional[int] = None
    fo: Optional[str] = None
    se: Optional[str] = None
    intro: Optional[str] = None
    issue_feature: Optional[str] = None
    sort_order: Optional[int] = None

    @field_validator("status")
    @classmethod
    def _v_status(cls, v):
        return enums.norm_key_feature_status(v, partial=True)


class KeyFeatureOut(KeyFeatureBase):
    id: int
    version: int
    updated_at: Optional[datetime] = None
    attachments: List[dict] = []          # 由路由解析 attachments_json
    machine_ids: List[int] = []           # 引用该特性的机台（路由批量填充）

    model_config = _BASE_CONFIG


class MachineFeatureSet(BaseModel):
    feature_ids: List[int] = []


# ===== 客户详情：机台 + SOW + License =====
class CustomerMachineOut(BaseModel):
    """客户详情页机台 tab 用：从 customer_status 派生，含编辑当前进展所需字段。"""
    id: int
    machine_id: str
    model: Optional[str] = ""
    current_stage: Optional[str] = ""
    customer_status: Optional[str] = ""
    field_version: Optional[str] = ""
    attention_level: Optional[int] = 0
    milestones_json: Optional[str] = ""
    version: int

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class SowFieldDefBase(BaseModel):
    key: str
    label: str
    field_type: str = "text"  # text / date / select
    options: Optional[List[str]] = []
    required: Optional[bool] = False
    sort_order: Optional[int] = 0
    is_active: Optional[bool] = True


class SowFieldDefCreate(SowFieldDefBase):
    pass


class SowFieldDefUpdate(BaseModel):
    label: Optional[str] = None
    field_type: Optional[str] = None
    options: Optional[List[str]] = None
    required: Optional[bool] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class SowFieldDefOut(SowFieldDefBase):
    """options 是 JSON Text 列；返回前由 router 显式解码成 list。"""
    id: int


class SowRowBase(BaseModel):
    data: dict = {}
    sort_order: Optional[int] = 0


class SowRowCreate(SowRowBase):
    pass


class SowRowUpdate(BaseModel):
    version: int
    data: Optional[dict] = None
    sort_order: Optional[int] = None


class SowRowOut(SowRowBase):
    """data 是 JSON Text 列；返回前由 router 显式解码成 dict。"""
    id: int
    machine_status_id: int
    version: int
    created_at: datetime
    updated_at: datetime


class MachineLicenseOut(BaseModel):
    id: int
    machine_status_id: int
    file_name: str
    file_size: int = 0
    remark: Optional[str] = ""
    uploaded_by: Optional[str] = ""
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ===== 客户自定义信息块（如 MPH状态）=====
class CustomerExtraFieldBase(BaseModel):
    key: str
    label: str
    sort_order: Optional[int] = 0
    is_active: Optional[bool] = True


class CustomerExtraFieldCreate(CustomerExtraFieldBase):
    pass


class CustomerExtraFieldUpdate(BaseModel):
    label: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class CustomerExtraFieldOut(CustomerExtraFieldBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class CustomerExtraValueOut(BaseModel):
    id: int
    machine_status_id: int
    field_id: int
    text: Optional[str] = ""
    file_name: Optional[str] = ""
    file_size: int = 0
    has_file: bool = False
    version: int

    model_config = ConfigDict(from_attributes=True)


class CustomerExtraValueUpdate(BaseModel):
    version: int
    text: Optional[str] = None


# ===== 客户定制化需求 =====
class CustomerCustomReqBase(BaseModel):
    seq: Optional[int] = 0
    description: Optional[str] = ""
    customer_value: Optional[str] = ""
    domain: Optional[str] = ""
    designer: Optional[str] = ""
    involves_other: Optional[str] = ""
    planned_version: Optional[str] = ""
    remark: Optional[str] = ""


class CustomerCustomReqCreate(CustomerCustomReqBase):
    customer_id: int


class CustomerCustomReqUpdate(BaseModel):
    version: int
    seq: Optional[int] = None
    description: Optional[str] = None
    customer_value: Optional[str] = None
    domain: Optional[str] = None
    designer: Optional[str] = None
    involves_other: Optional[str] = None
    planned_version: Optional[str] = None
    remark: Optional[str] = None


class CustomerCustomReqOut(CustomerCustomReqBase):
    id: int
    customer_id: int
    version: int

    model_config = ConfigDict(from_attributes=True)


# ===== Version =====
class VersionBase(BaseModel):
    version_no: str
    title: str
    description: Optional[str] = ""
    release_url: Optional[str] = ""
    released_at: Optional[datetime] = None


class VersionCreate(VersionBase):
    pass


class VersionUpdate(VersionBase):
    pass


class VersionOut(VersionBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


# ===== Iteration (legacy) =====
class IterationBase(BaseModel):
    name: str
    goal: Optional[str] = ""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[str] = "planning"
    owner: Optional[str] = ""


class IterationCreate(IterationBase):
    pass


class IterationUpdate(IterationBase):
    pass


class IterationOut(IterationBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


# ===== AnnualIteration =====
class AnnualIterationBase(BaseModel):
    year: int
    month: int
    name: Optional[str] = ""
    owner: Optional[str] = ""
    status: Optional[str] = "planning"
    goal: Optional[str] = ""


class AnnualIterationCreate(AnnualIterationBase):
    pass


class AnnualIterationUpdate(BaseModel):
    name: Optional[str] = None
    owner: Optional[str] = None
    status: Optional[str] = None
    goal: Optional[str] = None


class AnnualIterationOut(AnnualIterationBase):
    id: int
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ===== IterationRequirement =====
class IterationRequirementBase(BaseModel):
    seq: Optional[int] = 0
    req_no: Optional[str] = ""
    req_url: Optional[str] = ""
    title: Optional[str] = ""
    owner: Optional[str] = ""
    owner_user_id: Optional[int] = None
    owner_group: Optional[str] = ""
    group_id: Optional[int] = None
    priority: Optional[str] = "P2"
    planned_version: Optional[str] = ""
    target_version_id: Optional[int] = None
    progress_walkthrough: Optional[str] = "未开始"
    progress_reverse: Optional[str] = "未开始"
    progress_stc: Optional[str] = "未开始"
    progress_coding: Optional[str] = "未开始"
    progress_bbit: Optional[str] = "未开始"
    progress_clarify: Optional[str] = "未开始"
    merge_links: Optional[str] = ""
    code_volume: Optional[int] = None
    self_test_case_count: Optional[int] = None
    post_test_issue_count: Optional[int] = None
    remark: Optional[str] = ""


_IR_PROGRESS = ("progress_walkthrough", "progress_reverse", "progress_stc",
                "progress_coding", "progress_bbit", "progress_clarify")


class IterationRequirementCreate(IterationRequirementBase):
    iteration_id: int

    @field_validator("priority")
    @classmethod
    def _v_priority(cls, v):
        return enums.norm_priority(v, partial=False)

    @field_validator(*_IR_PROGRESS)
    @classmethod
    def _v_progress(cls, v):
        return enums.norm_progress(v, partial=False)


class IterationRequirementUpdate(BaseModel):
    version: int
    seq: Optional[int] = None
    req_no: Optional[str] = None
    req_url: Optional[str] = None
    title: Optional[str] = None
    owner: Optional[str] = None
    owner_user_id: Optional[int] = None
    owner_group: Optional[str] = None
    group_id: Optional[int] = None
    priority: Optional[str] = None
    planned_version: Optional[str] = None
    target_version_id: Optional[int] = None
    progress_walkthrough: Optional[str] = None
    progress_reverse: Optional[str] = None
    progress_stc: Optional[str] = None
    progress_coding: Optional[str] = None
    progress_bbit: Optional[str] = None
    progress_clarify: Optional[str] = None
    merge_links: Optional[str] = None
    code_volume: Optional[int] = None
    self_test_case_count: Optional[int] = None
    post_test_issue_count: Optional[int] = None
    remark: Optional[str] = None

    @field_validator("priority")
    @classmethod
    def _v_priority(cls, v):
        return enums.norm_priority(v, partial=True)

    @field_validator(*_IR_PROGRESS)
    @classmethod
    def _v_progress(cls, v):
        return enums.norm_progress(v, partial=True)


class IterationRequirementOut(IterationRequirementBase):
    id: int
    iteration_id: int
    version: int

    model_config = ConfigDict(from_attributes=True)


# ===== IterationProductRequirement =====
class IterationProductRequirementBase(BaseModel):
    seq: Optional[int] = 0
    req_no: Optional[str] = ""
    req_url: Optional[str] = ""
    title: Optional[str] = ""
    planned_version: Optional[str] = ""
    target_version_id: Optional[int] = None
    priority: Optional[str] = "P2"
    feature: Optional[str] = ""
    feature_fo: Optional[str] = ""
    feature_fo_user_id: Optional[int] = None
    feature_se: Optional[str] = ""
    feature_se_user_id: Optional[int] = None
    feature_tfo: Optional[str] = ""
    feature_tfo_user_id: Optional[int] = None
    code_areas: Optional[str] = ""
    progress_walkthrough: Optional[str] = "未开始"
    progress_reverse: Optional[str] = "未开始"
    progress_domain: Optional[str] = "未开始"
    progress_coding: Optional[str] = "未开始"
    progress_joint_debug: Optional[str] = "未开始"
    progress_clarify: Optional[str] = "未开始"
    progress_test_result: Optional[str] = "未开始"
    estimated_loc: Optional[str] = ""
    actual_loc: Optional[str] = ""
    actual_effort: Optional[str] = ""
    key_risks: Optional[str] = ""


_IPR_PROGRESS = ("progress_walkthrough", "progress_reverse", "progress_domain",
                 "progress_coding", "progress_joint_debug", "progress_clarify",
                 "progress_test_result")


class IterationProductRequirementCreate(IterationProductRequirementBase):
    iteration_id: int

    @field_validator("priority")
    @classmethod
    def _v_priority(cls, v):
        return enums.norm_priority(v, partial=False)

    @field_validator(*_IPR_PROGRESS)
    @classmethod
    def _v_progress(cls, v):
        return enums.norm_progress(v, partial=False)


class IterationProductRequirementUpdate(BaseModel):
    version: int
    seq: Optional[int] = None
    req_no: Optional[str] = None
    req_url: Optional[str] = None
    title: Optional[str] = None
    planned_version: Optional[str] = None
    target_version_id: Optional[int] = None
    priority: Optional[str] = None
    feature: Optional[str] = None
    feature_fo: Optional[str] = None
    feature_fo_user_id: Optional[int] = None
    feature_se: Optional[str] = None
    feature_se_user_id: Optional[int] = None
    feature_tfo: Optional[str] = None
    feature_tfo_user_id: Optional[int] = None
    code_areas: Optional[str] = None
    progress_walkthrough: Optional[str] = None
    progress_reverse: Optional[str] = None
    progress_domain: Optional[str] = None
    progress_coding: Optional[str] = None
    progress_joint_debug: Optional[str] = None
    progress_clarify: Optional[str] = None
    progress_test_result: Optional[str] = None
    estimated_loc: Optional[str] = None
    actual_loc: Optional[str] = None
    actual_effort: Optional[str] = None
    key_risks: Optional[str] = None

    @field_validator("priority")
    @classmethod
    def _v_priority(cls, v):
        return enums.norm_priority(v, partial=True)

    @field_validator(*_IPR_PROGRESS)
    @classmethod
    def _v_progress(cls, v):
        return enums.norm_progress(v, partial=True)


class IterationProductRequirementOut(IterationProductRequirementBase):
    id: int
    iteration_id: int
    version: int

    model_config = ConfigDict(from_attributes=True)


# ===== Roadmap =====
class RoadmapPhaseBase(BaseModel):
    name: str
    color: Optional[str] = "#409EFF"
    start_year: int
    start_month: int
    end_year: int
    end_month: int
    goal: Optional[str] = ""
    core_products: Optional[str] = ""
    scenarios: Optional[str] = ""
    sort_order: Optional[int] = 0


class RoadmapPhaseCreate(RoadmapPhaseBase):
    project_id: int


class RoadmapPhaseUpdate(BaseModel):
    version: int
    name: Optional[str] = None
    color: Optional[str] = None
    start_year: Optional[int] = None
    start_month: Optional[int] = None
    end_year: Optional[int] = None
    end_month: Optional[int] = None
    goal: Optional[str] = None
    core_products: Optional[str] = None
    scenarios: Optional[str] = None
    sort_order: Optional[int] = None


class RoadmapPhaseOut(RoadmapPhaseBase):
    id: int
    project_id: int
    version: int

    model_config = ConfigDict(from_attributes=True)


class RoadmapMilestoneBase(BaseModel):
    year: int
    month: int
    title: Optional[str] = ""
    description: Optional[str] = ""
    sort_order: Optional[int] = 0


class RoadmapMilestoneCreate(RoadmapMilestoneBase):
    project_id: int


class RoadmapMilestoneUpdate(BaseModel):
    year: Optional[int] = None
    month: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None


class RoadmapMilestoneOut(RoadmapMilestoneBase):
    id: int
    project_id: int

    model_config = ConfigDict(from_attributes=True)


class RoadmapProjectBase(BaseModel):
    name: str
    description: Optional[str] = ""
    year: Optional[int] = None
    granularity: Optional[str] = "quarter"
    sort_order: Optional[int] = 0
    is_active: Optional[bool] = True


class RoadmapProjectCreate(RoadmapProjectBase):
    pass


class RoadmapProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    year: Optional[int] = None
    granularity: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class RoadmapProjectOut(RoadmapProjectBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class RoadmapProjectDetailOut(RoadmapProjectOut):
    phases: List[RoadmapPhaseOut] = []
    milestones: List[RoadmapMilestoneOut] = []


# ===== MajorVersion / IterationVersion =====
class IterationVersionBase(BaseModel):
    version_no: str
    title: Optional[str] = ""
    planned_date: Optional[datetime] = None
    sort_order: Optional[int] = 0


class IterationVersionCreate(IterationVersionBase):
    major_version_id: int


class IterationVersionUpdate(BaseModel):
    version_no: Optional[str] = None
    title: Optional[str] = None
    planned_date: Optional[datetime] = None
    sort_order: Optional[int] = None


class IterationVersionOut(IterationVersionBase):
    id: int
    major_version_id: int

    model_config = ConfigDict(from_attributes=True)


class MajorVersionBase(BaseModel):
    version_no: str
    title: Optional[str] = ""
    description: Optional[str] = ""
    range_start: Optional[datetime] = None
    range_end: Optional[datetime] = None
    actual_release_date: Optional[datetime] = None
    sort_order: Optional[int] = 0


class MajorVersionCreate(MajorVersionBase):
    project_id: Optional[int] = None


class MajorVersionUpdate(BaseModel):
    version_no: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    range_start: Optional[datetime] = None
    range_end: Optional[datetime] = None
    actual_release_date: Optional[datetime] = None
    sort_order: Optional[int] = None


class MajorVersionOut(MajorVersionBase):
    id: int
    project_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class MajorVersionDetailOut(MajorVersionOut):
    iteration_versions: List[IterationVersionOut] = []


# ===== Stakeholder =====
class ProjectContactBase(BaseModel):
    col1: Optional[str] = ""
    col2: Optional[str] = ""


class ProjectContactCreate(ProjectContactBase):
    pass


class ProjectContactUpdate(ProjectContactBase):
    pass


class ProjectContactOut(ProjectContactBase):
    id: int
    sort_order: int = 0

    model_config = ConfigDict(from_attributes=True)


class BattlefieldBase(BaseModel):
    battlefield: Optional[str] = ""
    region: Optional[str] = ""
    service: Optional[str] = ""
    contact1: Optional[str] = ""
    apps: Optional[str] = ""
    contact2: Optional[str] = ""


class BattlefieldCreate(BattlefieldBase):
    pass


class BattlefieldUpdate(BattlefieldBase):
    pass


class BattlefieldOut(BattlefieldBase):
    id: int
    sort_order: int = 0

    model_config = ConfigDict(from_attributes=True)


# ===== Auth / User =====
class UserBase(BaseModel):
    username: str
    full_name: Optional[str] = ""
    emp_no: Optional[str] = ""
    job_title: Optional[str] = ""
    group_id: Optional[int] = None


class UserCreate(UserBase):
    password: Optional[str] = None  # 纯档案（can_login=false）可不填
    role: Optional[str] = "normal"
    can_login: Optional[bool] = True


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    emp_no: Optional[str] = None
    job_title: Optional[str] = None
    group_id: Optional[int] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    can_login: Optional[bool] = None
    password: Optional[str] = None


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    emp_no: str = ""
    job_title: str = ""
    group_id: Optional[int] = None
    group_name: Optional[str] = None       # 由 router 显式填充
    dept_id: Optional[int] = None          # 由 router 显式填充
    dept_name: Optional[str] = None        # 由 router 显式填充
    role: str
    is_active: bool
    can_login: bool = True
    auth_provider: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ===== Notification / Subscription =====
class NotificationOut(BaseModel):
    id: int
    kind: str
    title: str
    body: str = ""
    link: str = ""
    source_type: str = ""
    source_id: int = 0
    is_read: bool = False
    is_broadcast: bool = False
    actor_id: Optional[int] = None
    actor_name: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationListResponse(BaseModel):
    items: List[NotificationOut]
    unread_count: int
    total: int


class BroadcastPayload(BaseModel):
    title: str
    body: Optional[str] = ""
    link: Optional[str] = ""
    kind: Optional[str] = "broadcast"


class SubscriptionOut(BaseModel):
    id: int
    source_type: str
    source_id: Optional[int]
    events: str = "*"
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubscriptionPayload(BaseModel):
    source_type: str
    source_id: Optional[int] = None
    events: Optional[str] = "*"


# ===== ResourceGroup（部门 / PL 组）=====
class ResourceGroupBase(BaseModel):
    code: str
    name: str
    kind: str = "pl"              # "dept" / "pl"
    parent_id: Optional[int] = None
    leader_id: Optional[int] = None
    sort_order: Optional[int] = 0
    is_active: Optional[bool] = True
    remark: Optional[str] = ""


class ResourceGroupCreate(ResourceGroupBase):
    pass


class ResourceGroupUpdate(BaseModel):
    # code 不可改；name/parent/leader 等可改
    name: Optional[str] = None
    parent_id: Optional[int] = None
    leader_id: Optional[int] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    remark: Optional[str] = None


class ResourceGroupOut(ResourceGroupBase):
    id: int
    parent_name: Optional[str] = None
    leader_name: Optional[str] = None
    member_count: Optional[int] = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = ""


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ===== OperationLog =====
class OperationLogOut(BaseModel):
    id: int
    created_at: datetime
    user_id: Optional[int] = None
    username: str
    action: str
    target: str
    target_id: str
    detail: str
    ip: str
    user_agent: str

    model_config = ConfigDict(from_attributes=True)


class OperationLogPage(BaseModel):
    total: int
    items: List[OperationLogOut]


# ===== Handbook =====
class HandbookCategoryBase(BaseModel):
    name: str
    sort_order: Optional[int] = 0


class HandbookCategoryCreate(HandbookCategoryBase):
    pass


class HandbookCategoryUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None


class HandbookItemBase(BaseModel):
    title: str
    kind: str = "link"   # "link" or "file"
    url: Optional[str] = ""
    description: Optional[str] = ""
    owner: Optional[str] = ""
    sort_order: Optional[int] = 0


class HandbookItemCreate(HandbookItemBase):
    category_id: int


class HandbookItemUpdate(BaseModel):
    category_id: Optional[int] = None
    title: Optional[str] = None
    kind: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    owner: Optional[str] = None
    sort_order: Optional[int] = None


class HandbookItemOut(HandbookItemBase):
    id: int
    category_id: int
    file_path: str = ""
    file_name: str = ""
    file_size: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HandbookCategoryOut(HandbookCategoryBase):
    id: int
    items: List[HandbookItemOut] = []

    model_config = ConfigDict(from_attributes=True)


# ===== Special =====
class SpecialBase(BaseModel):
    name: str
    kind: Optional[str] = "special"  # special / assault
    owner: Optional[str] = ""
    sort_order: Optional[int] = 0
    is_active: Optional[bool] = True
    email_to: Optional[str] = ""
    email_cc: Optional[str] = ""
    email_subject_tpl: Optional[str] = ""


class SpecialCreate(SpecialBase):
    pass


class SpecialUpdate(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    owner: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    email_to: Optional[str] = None
    email_cc: Optional[str] = None
    email_subject_tpl: Optional[str] = None


class SpecialOut(SpecialBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class SpecialContentUpdate(BaseModel):
    version: int
    goal: Optional[str] = None
    progress_summary: Optional[str] = None
    help_request: Optional[str] = None
    milestones_json: Optional[str] = None
    formation_json: Optional[str] = None
    extra_grids_json: Optional[str] = None
    section_order_json: Optional[str] = None


class SpecialContentOut(BaseModel):
    id: int
    special_id: int
    goal: str = ""
    progress_summary: str = ""
    help_request: str = ""
    panorama_image_path: str = ""
    panorama_image_name: str = ""
    milestones_json: str = "[]"
    formation_json: str = '{"headers":[],"rows":[]}'
    extra_grids_json: str = "[]"
    section_order_json: str = "[]"
    version: int = 0
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SpecialItemBase(BaseModel):
    seq: Optional[int] = 0
    content: Optional[str] = ""
    progress: Optional[str] = ""
    owner: Optional[str] = ""
    planned_close_date: Optional[str] = ""
    status: Optional[str] = "open"
    sort_order: Optional[int] = 0


class SpecialItemCreate(SpecialItemBase):
    special_id: int


class SpecialItemUpdate(SpecialItemBase):
    pass


class SpecialItemOut(SpecialItemBase):
    id: int
    special_id: int

    model_config = ConfigDict(from_attributes=True)


class SpecialDetailOut(SpecialOut):
    content: Optional[SpecialContentOut] = None
    tasks: List[SpecialItemOut] = []
    risks: List[SpecialItemOut] = []


class SpecialLockOut(BaseModel):
    """编辑锁状态。

    - locked: 当前是否有人正持有（未过期）的锁
    - mine: 该锁是否归当前请求用户
    - by / by_user_id / since: 持锁人信息
    - ttl: 锁的存活秒数（前端据此安排心跳与过期判断）
    """
    locked: bool = False
    mine: bool = False
    by: Optional[str] = None
    by_user_id: Optional[int] = None
    since: Optional[datetime] = None
    ttl: int = 180


class FormationMemberBase(BaseModel):
    name: str
    emp_no: Optional[str] = ""
    pl_group: Optional[str] = ""
    role: Optional[str] = ""
    special_attach: Optional[str] = ""
    allocation: Optional[str] = ""
    remark: Optional[str] = ""
    sort_order: Optional[int] = 0


class FormationMemberCreate(FormationMemberBase):
    pass


class FormationMemberUpdate(BaseModel):
    name: Optional[str] = None
    emp_no: Optional[str] = None
    pl_group: Optional[str] = None
    role: Optional[str] = None
    special_attach: Optional[str] = None
    allocation: Optional[str] = None
    remark: Optional[str] = None
    sort_order: Optional[int] = None


class FormationMemberOut(FormationMemberBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class FormationImageOut(BaseModel):
    image_path: str = ""
    image_name: str = ""
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SpecialReportDraft(BaseModel):
    """周报草稿：纯文本，前端可编辑后复制/导出 mailto。"""
    subject: str
    to: str
    cc: str
    body: str


# ===== Domain（领域管理：按 PL 组聚合）=====
class DomainRiskItem(BaseModel):
    content: str = ""
    type: str = "风险"            # 风险 / 求助
    status: str = ""


class DomainReqSummary(BaseModel):
    total: int = 0
    done: int = 0
    in_progress: int = 0
    not_started: int = 0
    delayed: int = 0
    by_priority: dict = {}        # {"P0": n, "P1": n, ...}


class DomainIssueSummary(BaseModel):
    available: bool = True        # 问题单 Excel 不可读时为 False
    total: int = 0
    score: float = 0.0            # 加权总分：致命10 严重3 一般1 提示0.1
    by_severity: dict = {}        # {"致命": n, "严重": n, "一般": n, "提示": n}
    file_mtime: Optional[str] = None
    note: Optional[str] = None     # available=False 时的原因


class DomainIterationOpt(BaseModel):
    """领域管理顶部「月份选择器」的一个可选项（= 一个年度迭代）。"""
    year: int
    month: int
    status: str = ""               # planning / in_progress / done
    label: str = ""                # "2026年6月"
    in_progress: bool = False


class DomainContentUpdate(BaseModel):
    recent_work: Optional[str] = None
    risks: Optional[List[DomainRiskItem]] = None
    version: int


class DomainRowOut(BaseModel):
    group_id: int
    code: str
    name: str
    dept_name: Optional[str] = None
    leader_name: Optional[str] = None
    member_count: int = 0
    req_summary: DomainReqSummary
    issue_summary: DomainIssueSummary
    recent_work: str = ""
    risks: List[DomainRiskItem] = []
    version: int = 0
    hidden: bool = False           # 在领域管理中被移除/不管理


class DomainListOut(BaseModel):
    iteration_label: str = ""      # 当前生效口径标签，如 "2026年6月"
    selected_year: Optional[int] = None     # 选中的月份（未选时为空＝进行中口径）
    selected_month: Optional[int] = None
    iterations: List[DomainIterationOpt] = []   # 可选月份列表（年度迭代）
    rows: List[DomainRowOut] = []


class DomainVisibilityUpdate(BaseModel):
    hidden: bool                   # True=从领域管理移除（隐藏），False=恢复


# ===== 领域 · 事务与风险跟踪 =====
class DomainTaskBase(BaseModel):
    seq: Optional[int] = 0
    content: Optional[str] = ""
    priority: Optional[str] = "中"          # 高 / 中 / 低
    progress: Optional[str] = ""
    domain_id: Optional[int] = None         # 责任领域（PL 组）
    planned_close_date: Optional[datetime] = None
    status: Optional[str] = "OPEN"          # OPEN / CLOSED / 挂起
    sort_order: Optional[int] = 0


class DomainTaskCreate(DomainTaskBase):
    pass


class DomainTaskUpdate(BaseModel):
    version: int
    seq: Optional[int] = None
    content: Optional[str] = None
    priority: Optional[str] = None
    progress: Optional[str] = None
    domain_id: Optional[int] = None
    planned_close_date: Optional[datetime] = None
    status: Optional[str] = None
    sort_order: Optional[int] = None


class DomainTaskOut(DomainTaskBase):
    id: int
    domain_name: Optional[str] = None       # 由后端解析回填
    version: int

    model_config = ConfigDict(from_attributes=True)


# ===== 客户面调试版本（T 版本）+ 诉求收集 =====
class DebugVersionBase(BaseModel):
    version_no: str
    baseline_version: Optional[str] = ""
    target_customer_id: Optional[int] = None
    planned_release_date: Optional[datetime] = None
    release_date: Optional[datetime] = None
    merge_offline_cluster: Optional[str] = ""
    merge_online_flow: Optional[str] = ""
    merge_offline_analysis: Optional[str] = ""
    selfcheck_archive: Optional[str] = ""
    sort_order: Optional[int] = 0


class DebugVersionCreate(DebugVersionBase):
    pass


class DebugVersionUpdate(BaseModel):
    version: int
    version_no: Optional[str] = None
    baseline_version: Optional[str] = None
    target_customer_id: Optional[int] = None
    planned_release_date: Optional[datetime] = None
    release_date: Optional[datetime] = None
    merge_offline_cluster: Optional[str] = None
    merge_online_flow: Optional[str] = None
    merge_offline_analysis: Optional[str] = None
    selfcheck_archive: Optional[str] = None
    sort_order: Optional[int] = None


class DebugVersionOut(DebugVersionBase):
    id: int
    target_customer_name: Optional[str] = None   # 由后端解析回填
    version: int

    model_config = ConfigDict(from_attributes=True)


class DebugDemandBase(BaseModel):
    seq: Optional[int] = 0
    demand: Optional[str] = ""
    problem_solved: Optional[str] = ""
    feature: Optional[str] = ""
    battlefields: Optional[List[int]] = []       # 客户 id 列表（涉及战场）
    expected_time: Optional[str] = ""
    actual_version: Optional[str] = ""
    sort_order: Optional[int] = 0


class DebugDemandCreate(DebugDemandBase):
    pass


class DebugDemandUpdate(BaseModel):
    version: int
    seq: Optional[int] = None
    demand: Optional[str] = None
    problem_solved: Optional[str] = None
    feature: Optional[str] = None
    battlefields: Optional[List[int]] = None
    expected_time: Optional[str] = None
    actual_version: Optional[str] = None
    sort_order: Optional[int] = None


class DebugDemandOut(DebugDemandBase):
    id: int
    battlefield_names: List[str] = []            # 由后端解析回填
    version: int


class DebugDashboardMonth(BaseModel):
    month: str                  # "2026-06" 或 "未排期"
    total: int = 0
    by_customer: dict = {}      # {客户名: 数量}


class DebugDashboardOut(BaseModel):
    customers: List[str] = []   # 列顺序：出现过的目标客户名
    months: List[DebugDashboardMonth] = []


# ===== 现场调试版本 · 接受版本姓名列表 =====
class DebugRecipientBase(BaseModel):
    name: Optional[str] = ""
    role: Optional[str] = ""
    received: Optional[bool] = False
    sort_order: Optional[int] = 0


class DebugRecipientCreate(DebugRecipientBase):
    pass


class DebugRecipientUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    received: Optional[bool] = None
    sort_order: Optional[int] = None


class DebugRecipientOut(DebugRecipientBase):
    id: int
    debug_version_id: int

    model_config = ConfigDict(from_attributes=True)


# ===== Business trip（成员出差管理） =====
class BusinessTripBase(BaseModel):
    user_id: Optional[int] = None
    customer_id: Optional[int] = None
    location: Optional[str] = ""
    purpose: Optional[str] = ""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    cancelled: Optional[bool] = False
    remark: Optional[str] = ""
    sort_order: Optional[int] = 0


class BusinessTripCreate(BusinessTripBase):
    pass


class BusinessTripUpdate(BaseModel):
    version: int
    user_id: Optional[int] = None
    customer_id: Optional[int] = None
    location: Optional[str] = None
    purpose: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    cancelled: Optional[bool] = None
    remark: Optional[str] = None
    sort_order: Optional[int] = None


class BusinessTripOut(BusinessTripBase):
    id: int
    user_name: Optional[str] = None       # 由后端解析回填
    user_group: Optional[str] = None      # 出差人所属 PL 组（展示用）
    customer_name: Optional[str] = None   # 由后端解析回填
    status: str = ""                      # 计划中/进行中/已完成/已取消（按日期推导）
    version: int

    model_config = ConfigDict(from_attributes=True)


class TripDimStat(BaseModel):
    """看板某一维度（战场/人/领域）的区间统计项。"""
    name: str
    count: int = 0       # 区间内支撑人次


class BusinessTripDashboardOut(BaseModel):
    on_trip_now: int = 0     # 当前支撑中人次（now 快照）
    planned: int = 0         # 计划中人次（now 快照）
    range_label: str = ""    # 区间口径标签，如 "2026-06-01 ~ 2026-06-30"
    range_total: int = 0     # 区间内支撑人次合计
    by_customer: List[TripDimStat] = []   # 区间内按战场
    by_person: List[TripDimStat] = []     # 区间内按支撑人
    by_domain: List[TripDimStat] = []     # 区间内按领域（支撑人所属 PL 组）
