"""领域管理：按 PL 资源组聚合的总览。

每个启用的 PL 组（resource_groups.kind == "pl"）一行，关联：
- 需求情况   —— 从迭代需求（iteration_requirements）按 group_id 聚合，口径＝当前进行中迭代
- 问题单情况 —— 优先取**问题单管理的最新快照**（issue_snapshots，按项目分），
                按「责任人所属小组」聚合；没有任何快照时回退到旧的问题单 Excel
- 最近主要工作 —— 富文本，人工维护（domain_contents.recent_work）
- 风险与求助 —— 结构化逐条，人工维护（domain_contents.risks_json）

问题单口径只看**最新一份快照**（历史趋势在问题单管理里看，这里不重复造第二套趋势）；
目标值（domain_issue_targets）是管理口径不是采集事实，仅 admin 可写。

权限：协作编辑域（见 CLAUDE.md「Write-permission principle」）——读对所有登录用户开放，
最近主要工作 / 风险求助 / 事务风险 / 遗留问题 登录用户均可写；问题单目标仅 admin。
"""
import json
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import false as sa_false, func
from sqlalchemy.orm import Session

import enums
import models
import schemas
from auth import get_current_user, require_admin
from database import get_db
from op_log import log_op
import revisions
from routers import _issue_source, _req_scope
from routers._lookups import project_name_map
from routers.config import _load as _load_config

router = APIRouter(prefix="/api/domains", tags=["domains"])

_PROG_FIELDS = [
    "progress_walkthrough", "progress_reverse", "progress_stc",
    "progress_coding", "progress_bbit", "progress_clarify",
]
_SEVERITIES = ["严重", "一般", "提示"]
_RISK_TYPES = {"风险", "求助"}
# 问题单加权分值：致命10 严重3 一般1 提示0.1（实现在 _issue_source，度量看板共用）
_SEVERITY_WEIGHTS = _issue_source.SEVERITY_WEIGHTS


# ─── helpers：迭代口径 ─────────────────────────────────────────────────────────
def _in_progress_iterations(db: Session) -> List[models.AnnualIteration]:
    return (
        db.query(models.AnnualIteration)
        .filter(models.AnnualIteration.status == "in_progress")
        .order_by(models.AnnualIteration.year.desc(), models.AnnualIteration.month.desc())
        .all()
    )


def _iteration_label(its: List[models.AnnualIteration]) -> str:
    if not its:
        return "无进行中迭代"
    return "、".join(f"{it.year}年{it.month}月" for it in its)


def _scope_iterations(db: Session, year: Optional[int], month: Optional[int]) -> List[models.AnnualIteration]:
    """选中具体月份时只看该年度迭代；否则回退到「进行中」口径。"""
    if year and month:
        it = (
            db.query(models.AnnualIteration)
            .filter(models.AnnualIteration.year == year, models.AnnualIteration.month == month)
            .first()
        )
        return [it] if it else []
    return _in_progress_iterations(db)


class _ReqScope:
    """需求口径：**要么按迭代、要么按版本，二选一**。

    两者不叠加是有意的：版本是跨迭代的（C10SPC101 上的需求分散在好几个月里），
    叠上「当前迭代」会得到一个既不是这个版本、也不是这个迭代的数，
    页面上看着像"这个版本怎么只有 3 条"，而没人会想到是被月份截了一刀。
    生效的是哪一档由 `label` 明写在页头，别让人猜。
    """

    def __init__(self, iteration_ids: Optional[List[int]] = None,
                 release_version: Optional[models.ReleaseVersion] = None,
                 label: str = ""):
        self.iteration_ids = iteration_ids or []
        self.release_version = release_version
        self.label = label

    @property
    def by_version(self) -> bool:
        return self.release_version is not None


def _resolve_req_scope(db: Session, year: Optional[int], month: Optional[int],
                       release_version_id: Optional[int]) -> _ReqScope:
    if release_version_id:
        rv = (
            db.query(models.ReleaseVersion)
            .filter(models.ReleaseVersion.id == release_version_id)
            .first()
        )
        if not rv:
            raise HTTPException(404, "版本不存在")
        mv = rv.major_version
        head = f"{mv.version_no} · " if mv and mv.version_no else ""
        return _ReqScope(release_version=rv, label=f"版本 {head}{rv.version_no or ''}")
    its = _scope_iterations(db, year, month)
    return _ReqScope(iteration_ids=[it.id for it in its], label=_iteration_label(its))


def _req_query(db: Session, scope: _ReqScope):
    """按当前口径筛出领域需求。口径落空时返回一个必然为空的查询，而不是 None——
    调用方少一次判空，也不会出现"忘了判空就把全表算进去"。"""
    q = db.query(models.IterationRequirement)
    if scope.by_version:
        return q.filter(_req_scope.version_clause(models.IterationRequirement,
                                                  scope.release_version))
    if not scope.iteration_ids:
        return q.filter(sa_false())
    return q.filter(models.IterationRequirement.iteration_id.in_(scope.iteration_ids))


def _version_options(db: Session) -> List[schemas.DomainVersionOpt]:
    """可选版本＝**当前确实挂着领域需求**的那些版本，带上条数。

    不把版本表整个列出来：三层版本里光构建就上百个，铺成一排标签没法看，
    而且点进去大半是空的。条数在这里一次算完（一趟扫描），
    不要改成每个版本各查一次——版本一多就是几十条 SQL。
    """
    rvs = (
        db.query(models.ReleaseVersion)
        .join(models.MajorVersion, models.ReleaseVersion.major_version_id == models.MajorVersion.id)
        .order_by(models.MajorVersion.sort_order, models.MajorVersion.id,
                  models.ReleaseVersion.sort_order, models.ReleaseVersion.id)
        .all()
    )
    if not rvs:
        return []
    by_iv: Dict[int, int] = {}      # 构建 id → 版本 id
    by_no: Dict[str, int] = {}      # 版本号 / 构建号 → 版本 id
    for rv in rvs:
        if rv.version_no:
            by_no.setdefault(rv.version_no, rv.id)
        for iv in rv.iteration_versions:
            by_iv[iv.id] = rv.id
            if iv.version_no:
                by_no.setdefault(iv.version_no, rv.id)

    counts: Dict[int, int] = {}
    rows = db.query(models.IterationRequirement.target_version_id,
                    models.IterationRequirement.planned_version).all()
    for target_id, planned in rows:
        # 与 _req_scope.version_clause 同款：FK 优先，FK 为空才看字符串
        rid = by_iv.get(target_id) if target_id else by_no.get((planned or "").strip())
        if rid:
            counts[rid] = counts.get(rid, 0) + 1

    out: List[schemas.DomainVersionOpt] = []
    for rv in rvs:
        n = counts.get(rv.id, 0)
        if not n:
            continue
        mv = rv.major_version
        out.append(schemas.DomainVersionOpt(
            id=rv.id,
            version_no=rv.version_no or "",
            major_version_no=(mv.version_no if mv else "") or "",
            req_count=n,
        ))
    return out


def _available_iterations(db: Session) -> List[schemas.DomainIterationOpt]:
    its = (
        db.query(models.AnnualIteration)
        .order_by(models.AnnualIteration.year.desc(), models.AnnualIteration.month.desc())
        .all()
    )
    return [
        schemas.DomainIterationOpt(
            year=it.year, month=it.month, status=it.status or "",
            label=f"{it.year}年{it.month}月",
            in_progress=(it.status == "in_progress"),
        )
        for it in its
    ]


# ─── helpers：需求聚合 ─────────────────────────────────────────────────────────
def _req_summary(db: Session, group_id: int, scope: "_ReqScope") -> schemas.DomainReqSummary:
    s = schemas.DomainReqSummary(by_priority={})
    rows = (
        _req_query(db, scope)
        .filter(models.IterationRequirement.group_id == group_id)
        .all()
    )
    for r in rows:
        # 「已变更」＝本轮不做了，整行不进统计，与度量看板同口径
        # （判定收口在 enums.is_changed_row；两处各写一份迟早分叉）。
        if enums.is_changed_row(r, _PROG_FIELDS):
            s.changed += 1
            continue
        s.total += 1
        vals = [getattr(r, f) or "未开始" for f in _PROG_FIELDS]
        delayed = any(v == "已延期" for v in vals)
        done = all(v in ("已完成", "不涉及") for v in vals)
        started = any(v not in ("未开始", "不涉及") for v in vals)
        if delayed:
            s.delayed += 1
        if done:
            s.done += 1
        elif not started:
            s.not_started += 1
        else:
            s.in_progress += 1
        pr = (r.priority or "未分级").strip() or "未分级"
        s.by_priority[pr] = s.by_priority.get(pr, 0) + 1
    return s


# ─── helpers：问题单数据源 ────────────────────────────────────────────────────
# 实现搬到 routers/_issue_source.py：度量看板的版本质量也要按领域切问题单，
# 两处各写一份的表现是同一个领域在两个页面上问题单数不一样，而两边看着都像对的。
_IssueSource = _issue_source.IssueSource
_load_issue_raw = _issue_source.load_issue_raw
_issue_rows_for_group = _issue_source.issue_rows_for_group
_latest_snapshot = _issue_source.latest_snapshot
_snapshot_rows = _issue_source.snapshot_rows
_issue_projects = _issue_source.issue_projects
_resolve_issue_source = _issue_source.resolve_issue_source


# ─── helpers：问题单目标（仅 admin 维护）──────────────────────────────────────
def _targets_map(db: Session, project: Optional[str]) -> Dict[int, models.DomainIssueTarget]:
    """{group_id: 目标}。优先取该项目的目标行，缺失时回退到 project="" 的通用目标。"""
    rows = (
        db.query(models.DomainIssueTarget)
        .filter(models.DomainIssueTarget.project.in_([project or "", ""]))
        .all()
    )
    # 项目专属覆盖通用：先铺通用，再用专属盖上去
    specific = {r.group_id: r for r in rows if r.project == (project or "")}
    generic = {r.group_id: r for r in rows if r.project == ""}
    return {**generic, **specific}


def _issue_summary_from_rows(rows: List[dict], src: "_IssueSource",
                             target: Optional[models.DomainIssueTarget] = None
                             ) -> schemas.DomainIssueSummary:
    by_sev = {}
    score = 0.0
    for r in rows:
        sev = (r.get("severity") or "").strip()
        if sev:
            by_sev[sev] = by_sev.get(sev, 0) + 1
            score += _SEVERITY_WEIGHTS.get(sev, 0.0)
    score = round(score, 1)
    total = len(rows)
    overdue, overdue_unknown = _issue_source.overdue_stats(rows)
    t_total = target.target_total if target else None
    t_score = target.target_score if target else None
    return schemas.DomainIssueSummary(
        available=True, total=total, score=score,
        by_severity=by_sev, file_mtime=src.stamp,
        source=src.source, project=src.project,
        target_total=t_total, target_score=t_score,
        over_total=bool(t_total is not None and total > t_total),
        over_score=bool(t_score is not None and score > t_score),
        overdue=overdue, overdue_unknown=overdue_unknown,
    )


def _issue_summary_for_group(g: models.ResourceGroup, src: "_IssueSource",
                             targets: Dict[int, models.DomainIssueTarget]
                             ) -> schemas.DomainIssueSummary:
    if src.rows is None:
        return schemas.DomainIssueSummary(available=False, note=src.note,
                                          source=src.source, project=src.project)
    return _issue_summary_from_rows(_issue_rows_for_group(src.rows, g), src,
                                    targets.get(g.id))


# ─── helpers：手填内容 ─────────────────────────────────────────────────────────
def _get_content(db: Session, group_id: int) -> Optional[models.DomainContent]:
    return (
        db.query(models.DomainContent)
        .filter(models.DomainContent.group_id == group_id)
        .first()
    )


def _parse_risks(raw_json: Optional[str]) -> List[schemas.DomainRiskItem]:
    try:
        data = json.loads(raw_json or "[]")
    except (ValueError, TypeError):
        return []
    out = []
    if isinstance(data, list):
        for it in data:
            if not isinstance(it, dict):
                continue
            out.append(schemas.DomainRiskItem(
                content=str(it.get("content", "") or ""),
                type=it.get("type") if it.get("type") in _RISK_TYPES else "风险",
                status=str(it.get("status", "") or ""),
            ))
    return out


def _dept_name(db: Session, g: models.ResourceGroup) -> Optional[str]:
    if g.parent_id:
        parent = db.query(models.ResourceGroup).get(g.parent_id)
        return parent.name if parent else None
    return None


def _leader_name(db: Session, g: models.ResourceGroup) -> Optional[str]:
    if g.leader_id:
        u = db.query(models.User).get(g.leader_id)
        if u:
            return u.full_name or u.username
    return None


# ─── routes ─────────────────────────────────────────────────────────────────
@router.get("", response_model=schemas.DomainListOut)
def list_domains(
    year: Optional[int] = Query(None, description="按年度迭代月份取需求口径；与 month 同时给"),
    month: Optional[int] = Query(None, ge=1, le=12),
    release_version_id: Optional[int] = Query(
        None, description="按版本取需求口径（跨迭代）；给了它就**忽略 year/month**"),
    include_hidden: bool = Query(False, description="是否一并返回已隐藏（不管理）的领域"),
    project: Optional[str] = Query(None, description="问题单项目/版本；省略取第一个有快照的项目"),
    db: Session = Depends(get_db),
):
    groups = (
        db.query(models.ResourceGroup)
        .filter(models.ResourceGroup.kind == "pl", models.ResourceGroup.is_active.is_(True))
        .order_by(models.ResourceGroup.sort_order, models.ResourceGroup.id)
        .all()
    )
    hidden_ids = {h.group_id for h in db.query(models.DomainHidden).all()}
    if not include_hidden:
        groups = [g for g in groups if g.id not in hidden_ids]
    scope = _resolve_req_scope(db, year, month, release_version_id)
    src = _resolve_issue_source(db, project)
    targets = _targets_map(db, src.project)

    rows: List[schemas.DomainRowOut] = []
    for g in groups:
        content = _get_content(db, g.id)
        issue_summary = _issue_summary_for_group(g, src, targets)
        member_count = (
            db.query(models.User).filter(models.User.group_id == g.id).count()
        )
        rows.append(schemas.DomainRowOut(
            group_id=g.id,
            code=g.code,
            name=g.name,
            dept_name=_dept_name(db, g),
            leader_name=_leader_name(db, g),
            member_count=member_count,
            req_summary=_req_summary(db, g.id, scope),
            issue_summary=issue_summary,
            recent_work=(content.recent_work if content else "") or "",
            risks=_parse_risks(content.risks_json if content else "[]"),
            version=content.version if content else 0,
            hidden=(g.id in hidden_ids),
        ))
    return schemas.DomainListOut(
        iteration_label=scope.label,
        selected_year=None if scope.by_version else year,
        selected_month=None if scope.by_version else month,
        iterations=_available_iterations(db),
        versions=_version_options(db),
        selected_release_version_id=(scope.release_version.id if scope.by_version else None),
        projects=_issue_projects(db),
        selected_project=src.project,
        rows=rows,
    )


def _require_pl_group(db: Session, group_id: int) -> models.ResourceGroup:
    g = db.query(models.ResourceGroup).filter(models.ResourceGroup.id == group_id).first()
    if not g:
        raise HTTPException(404, "资源组不存在")
    if g.kind != "pl":
        raise HTTPException(400, "领域只能挂在 PL 组上")
    return g


@router.get("/{group_id}/requirements", response_model=List[schemas.IterationRequirementOut])
def list_group_requirements(
    group_id: int,
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None, ge=1, le=12),
    release_version_id: Optional[int] = Query(None, description="与总览同款：给了它就按版本、忽略 year/month"),
    db: Session = Depends(get_db),
):
    """下钻：该领域在当前口径（选定月份 / 进行中迭代 / 选定版本）下的需求明细。

    口径必须与总览用同一个 `_resolve_req_scope`——两边各筛一次的表现是
    「格子里写 8 条、点进去 5 条」，看着像丢数据。
    """
    _require_pl_group(db, group_id)
    scope = _resolve_req_scope(db, year, month, release_version_id)
    pmap = project_name_map(db)
    items = (
        _req_query(db, scope)
        .filter(models.IterationRequirement.group_id == group_id)
        .order_by(models.IterationRequirement.iteration_id.desc(),
                  models.IterationRequirement.seq.asc())
        .all()
    )
    out = []
    for it in items:
        o = schemas.IterationRequirementOut.model_validate(it)
        o.project_name = pmap.get(it.project_id)
        out.append(o)
    return out


@router.get("/{group_id}/issues")
def list_group_issues(
    group_id: int,
    project: Optional[str] = Query(None, description="问题单项目/版本，与总览口径一致"),
    overdue: bool = Query(False, description="只看超过预计闭环时间还没处理的"),
    db: Session = Depends(get_db),
):
    """下钻：该领域名下的问题单原始行（口径与总览同一个数据源）。

    `overdue=true` 时只留超期未处理的那些——总览里那个数字点得进来，
    否则「超期 8 条」只是个数字，没人说得清是哪 8 条。
    """
    g = _require_pl_group(db, group_id)
    src = _resolve_issue_source(db, project)
    if src.rows is None:
        return {"available": False, "note": src.note, "rows": []}
    rows = _issue_rows_for_group(src.rows, g)
    if overdue:
        rows = [r for r in rows if _issue_source.is_overdue(r)]
    return {"available": True, "file_mtime": src.stamp, "source": src.source,
            "project": src.project, "rows": rows}


@router.put("/{group_id}/content", response_model=schemas.DomainRowOut)
def update_domain_content(
    group_id: int,
    payload: schemas.DomainContentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """更新「最近主要工作 / 风险与求助」。协作编辑域：登录用户均可写，带乐观锁。"""
    from routers.specials import _sanitize_rich

    g = _require_pl_group(db, group_id)
    content = _get_content(db, group_id)
    if content is None:
        if payload.version not in (0, None):
            raise HTTPException(409, "数据已被他人修改，请刷新后重试")
        content = models.DomainContent(group_id=group_id, recent_work="", risks_json="[]", version=0)
        db.add(content)
        db.flush()
    elif content.version != payload.version:
        raise HTTPException(409, "数据已被他人修改，请刷新后重试")

    before = revisions.snapshot(content)
    changed = []
    if payload.recent_work is not None:
        content.recent_work = _sanitize_rich(payload.recent_work)
        changed.append("recent_work")
    if payload.risks is not None:
        clean = []
        for it in payload.risks:
            content_txt = (it.content or "").strip()
            status_txt = (it.status or "").strip()
            if not content_txt and not status_txt:
                continue
            clean.append({
                "content": content_txt,
                "type": it.type if it.type in _RISK_TYPES else "风险",
                "status": status_txt,
            })
        content.risks_json = json.dumps(clean, ensure_ascii=False)
        changed.append("risks")

    content.version += 1
    revisions.record(db, content, before, user=current_user)
    db.commit()
    db.refresh(content)
    log_op(db, action="修改", target="领域内容", target_id=group_id,
           detail=f"group={g.name} fields={','.join(changed) or '无'}",
           user=current_user, request=request)

    # 复用列表口径回包一行，前端可直接替换
    its = _in_progress_iterations(db)
    iteration_ids = [it.id for it in its]
    src = _resolve_issue_source(db, None)
    issue_summary = _issue_summary_for_group(g, src, _targets_map(db, src.project))
    member_count = db.query(models.User).filter(models.User.group_id == g.id).count()
    return schemas.DomainRowOut(
        group_id=g.id, code=g.code, name=g.name,
        dept_name=_dept_name(db, g), leader_name=_leader_name(db, g),
        member_count=member_count,
        req_summary=_req_summary(db, g.id, iteration_ids),
        issue_summary=issue_summary,
        recent_work=content.recent_work or "",
        risks=_parse_risks(content.risks_json),
        version=content.version,
    )


# ─── 领域显隐（软删除 / 恢复）─────────────────────────────────────────────────
@router.put("/{group_id}/visibility")
def set_domain_visibility(
    group_id: int,
    payload: schemas.DomainVisibilityUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """从领域管理移除（隐藏）或恢复某个领域；不影响组织架构里的 PL 组主数据。"""
    g = _require_pl_group(db, group_id)
    existing = db.query(models.DomainHidden).filter(models.DomainHidden.group_id == group_id).first()
    if payload.hidden and not existing:
        db.add(models.DomainHidden(group_id=group_id))
    elif not payload.hidden and existing:
        db.delete(existing)
    db.commit()
    log_op(db, action="隐藏" if payload.hidden else "恢复", target="领域", target_id=group_id,
           detail=f"group={g.name}", user=current_user, request=request)
    return {"ok": True, "hidden": payload.hidden}


# ─── 事务与风险跟踪 ───────────────────────────────────────────────────────────
_DOMAIN_RISK_STATUSES = {"OPEN", "CLOSED", "挂起"}


def _domain_name_map(db: Session) -> dict:
    rows = db.query(models.ResourceGroup.id, models.ResourceGroup.name).all()
    return {r.id: r.name for r in rows}


def _task_out(obj: models.DomainRisk, name_map: dict,
              users: Optional[Dict[int, str]] = None) -> schemas.DomainTaskOut:
    from routers.specials import _rich_to_html

    out = schemas.DomainTaskOut.model_validate(obj)
    out.domain_name = name_map.get(obj.domain_id)
    out.owner_name = (users or {}).get(obj.owner_id)
    # 「当前进展」改成富文本前，这一列存了多年的纯文本。改用 v-html 渲染之后，
    # 那些老值里的 < 会被浏览器当标签吃掉、换行会被压平——所以出口过一道
    # _rich_to_html()：看着像 HTML 的清洗，纯文本的转义并把 \n 换成 <br>，
    # 老行显示成什么样和改造前一模一样。顺带也挡住老数据里可能存着的标记
    # （入口清洗是这次才加的，之前存进来的没洗过）。
    out.progress = _rich_to_html(obj.progress or "")
    return out


@router.get("/risks", response_model=List[schemas.DomainTaskOut])
def list_domain_risks(
    include_done: bool = Query(True, description="是否包含 CLOSED / 挂起"),
    db: Session = Depends(get_db),
):
    q = db.query(models.DomainRisk)
    if not include_done:
        q = q.filter(models.DomainRisk.status == "OPEN")
    rows = q.order_by(
        models.DomainRisk.sort_order.asc(),
        models.DomainRisk.seq.asc(),
        models.DomainRisk.id.asc(),
    ).all()
    name_map, users = _domain_name_map(db), _user_name_map(db)
    return [_task_out(r, name_map, users) for r in rows]


@router.post("/risks", response_model=schemas.DomainTaskOut)
def create_domain_risk(
    payload: schemas.DomainTaskCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from routers.specials import _sanitize_rich

    data = payload.model_dump()
    # 进展在表格里用 v-html 渲染：入口不清洗＝任何登录用户都能往别人的条目里存脚本
    data["progress"] = _sanitize_rich(data.get("progress") or "")
    if not data.get("seq"):
        data["seq"] = (db.query(func.coalesce(func.max(models.DomainRisk.seq), 0)).scalar() or 0) + 1
    obj = models.DomainRisk(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    log_op(db, action="新增", target="领域事务/风险", target_id=obj.id,
           detail=(obj.content or "")[:40], user=current_user, request=request)
    return _task_out(obj, _domain_name_map(db), _user_name_map(db))


@router.put("/risks/{rid}", response_model=schemas.DomainTaskOut)
def update_domain_risk(
    rid: int,
    payload: schemas.DomainTaskUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    obj = db.query(models.DomainRisk).filter(models.DomainRisk.id == rid).first()
    if not obj:
        raise HTTPException(404, "Not found")
    if obj.version != payload.version:
        raise HTTPException(409, "数据已被他人修改，请刷新后重试")
    from routers.specials import _sanitize_rich

    changes = payload.model_dump(exclude_unset=True)
    changes.pop("version", None)
    if changes.get("progress") is not None:
        changes["progress"] = _sanitize_rich(changes["progress"])
    before = revisions.snapshot(obj)
    for k, v in changes.items():
        setattr(obj, k, v)
    obj.version += 1
    revisions.record(db, obj, before, user=current_user)
    db.commit()
    db.refresh(obj)
    log_op(db, action="修改", target="领域事务/风险", target_id=obj.id,
           detail=(obj.content or "")[:40], user=current_user, request=request)
    return _task_out(obj, _domain_name_map(db), _user_name_map(db))


@router.delete("/risks/{rid}")
def delete_domain_risk(
    rid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    obj = db.query(models.DomainRisk).filter(models.DomainRisk.id == rid).first()
    if not obj:
        raise HTTPException(404, "Not found")
    revisions.record_delete(db, obj, user=current_user)
    db.delete(obj)
    db.commit()
    log_op(db, action="删除", target="领域事务/风险", target_id=rid,
           detail="", user=current_user, request=request)
    return {"ok": True}


# ─── 问题单目标（仅 admin 可写，见 CLAUDE.md「Write-permission principle」）────
@router.get("/issue-targets")
def list_issue_targets(
    project: Optional[str] = Query(None, description="项目/版本；省略＝通用目标"),
    db: Session = Depends(get_db),
):
    """某项目下各领域的问题单目标。读对所有登录用户开放（页面要显示达成情况）。"""
    proj = project or ""
    groups = (
        db.query(models.ResourceGroup)
        .filter(models.ResourceGroup.kind == "pl", models.ResourceGroup.is_active.is_(True))
        .order_by(models.ResourceGroup.sort_order, models.ResourceGroup.id)
        .all()
    )
    hidden_ids = {h.group_id for h in db.query(models.DomainHidden).all()}
    targets = _targets_map(db, proj)
    return {
        "project": proj,
        "items": [
            {
                "group_id": g.id,
                "group_name": g.name,
                "target_total": targets[g.id].target_total if g.id in targets else None,
                "target_score": targets[g.id].target_score if g.id in targets else None,
                "remark": (targets[g.id].remark or "") if g.id in targets else "",
                # 通用目标（project=""）被继承时标出来，免得管理员以为改的是本项目的值
                "inherited": bool(g.id in targets and targets[g.id].project != proj),
            }
            for g in groups if g.id not in hidden_ids
        ],
    }


@router.put("/issue-targets")
def update_issue_targets(
    payload: schemas.DomainIssueTargetsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """批量设定/清除问题单目标。两个目标都留空＝删除该行（回到"未设目标"）。"""
    proj = (payload.project or "").strip()
    touched = 0
    for item in payload.items:
        g = db.query(models.ResourceGroup).filter(models.ResourceGroup.id == item.group_id).first()
        if not g or g.kind != "pl":
            continue
        row = (
            db.query(models.DomainIssueTarget)
            .filter(models.DomainIssueTarget.group_id == item.group_id,
                    models.DomainIssueTarget.project == proj)
            .first()
        )
        empty = item.target_total is None and item.target_score is None
        if empty:
            if row:
                db.delete(row)
                touched += 1
            continue
        if row is None:
            row = models.DomainIssueTarget(group_id=item.group_id, project=proj)
            db.add(row)
        row.target_total = item.target_total
        row.target_score = item.target_score
        row.remark = (item.remark or "")[:256]
        touched += 1
    db.commit()
    log_op(db, action="修改", target="领域问题单目标", target_id=None,
           detail=f"project={proj or '通用'} rows={touched}",
           user=current_user, request=request)
    return {"ok": True, "project": proj, "updated": touched}


# ─── 遗留问题 ────────────────────────────────────────────────────────────────
def _parse_participants(raw_json: Optional[str]) -> List[int]:
    try:
        data = json.loads(raw_json or "[]")
    except (ValueError, TypeError):
        return []
    out = []
    for v in (data if isinstance(data, list) else []):
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            continue
    return out


def _user_name_map(db: Session) -> Dict[int, str]:
    rows = db.query(models.User.id, models.User.full_name, models.User.username).all()
    return {r.id: (r.full_name or r.username) for r in rows}


def _legacy_out(obj: models.DomainLegacyIssue, names: Dict[int, str],
                domains: Dict[int, str]) -> schemas.DomainLegacyIssueOut:
    pids = _parse_participants(obj.participants_json)
    out = schemas.DomainLegacyIssueOut.model_validate(obj)
    out.participants = pids
    out.participant_names = [names[i] for i in pids if i in names]
    out.owner_name = names.get(obj.owner_id)
    out.reporter_name = names.get(obj.reporter_id)
    out.confirmer_name = names.get(obj.confirmer_id)
    out.domain_name = domains.get(obj.domain_id)
    return out


@router.get("/legacy-issues", response_model=List[schemas.DomainLegacyIssueOut])
def list_legacy_issues(
    include_done: bool = Query(True, description="是否包含 CLOSED"),
    domain_id: Optional[int] = Query(None, description="只看某个领域"),
    db: Session = Depends(get_db),
):
    q = db.query(models.DomainLegacyIssue)
    if not include_done:
        q = q.filter(models.DomainLegacyIssue.status != "CLOSED")
    if domain_id:
        q = q.filter(models.DomainLegacyIssue.domain_id == domain_id)
    rows = q.order_by(
        models.DomainLegacyIssue.sort_order.asc(),
        models.DomainLegacyIssue.seq.asc(),
        models.DomainLegacyIssue.id.asc(),
    ).all()
    names, domains = _user_name_map(db), _domain_name_map(db)
    return [_legacy_out(r, names, domains) for r in rows]


@router.post("/legacy-issues", response_model=schemas.DomainLegacyIssueOut)
def create_legacy_issue(
    payload: schemas.DomainLegacyIssueCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from routers.specials import _sanitize_rich

    data = payload.model_dump()
    participants = data.pop("participants", None) or []
    # 当前进展是富文本且详情表里用 v-html 渲染：入口不清洗＝任何登录用户都能往
    # 别人的遗留问题里存一段脚本（见 CLAUDE.md「富文本：入口清洗，出口也清洗」）
    data["progress"] = _sanitize_rich(data.get("progress") or "")
    if not data.get("seq"):
        data["seq"] = (db.query(func.coalesce(func.max(models.DomainLegacyIssue.seq), 0))
                       .scalar() or 0) + 1
    obj = models.DomainLegacyIssue(
        **data, participants_json=json.dumps([int(x) for x in participants]),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    log_op(db, action="新增", target="领域遗留问题", target_id=obj.id,
           detail=(obj.title or "")[:40], user=current_user, request=request)
    return _legacy_out(obj, _user_name_map(db), _domain_name_map(db))


@router.put("/legacy-issues/{lid}", response_model=schemas.DomainLegacyIssueOut)
def update_legacy_issue(
    lid: int,
    payload: schemas.DomainLegacyIssueUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    obj = db.query(models.DomainLegacyIssue).filter(models.DomainLegacyIssue.id == lid).first()
    if not obj:
        raise HTTPException(404, "Not found")
    if obj.version != payload.version:
        raise HTTPException(409, "数据已被他人修改，请刷新后重试")
    from routers.specials import _sanitize_rich

    changes = payload.model_dump(exclude_unset=True)
    changes.pop("version", None)
    if changes.get("progress") is not None:
        changes["progress"] = _sanitize_rich(changes["progress"])
    if "participants" in changes:
        ids = changes.pop("participants") or []
        obj.participants_json = json.dumps([int(x) for x in ids])
    before = revisions.snapshot(obj)
    for k, v in changes.items():
        setattr(obj, k, v)
    obj.version += 1
    revisions.record(db, obj, before, user=current_user)
    db.commit()
    db.refresh(obj)
    log_op(db, action="修改", target="领域遗留问题", target_id=obj.id,
           detail=(obj.title or "")[:40], user=current_user, request=request)
    return _legacy_out(obj, _user_name_map(db), _domain_name_map(db))


@router.delete("/legacy-issues/{lid}")
def delete_legacy_issue(
    lid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """删除权限＝登录用户：与同页的事务/风险同档（自己录的日常条目，见 CLAUDE.md）。"""
    obj = db.query(models.DomainLegacyIssue).filter(models.DomainLegacyIssue.id == lid).first()
    if not obj:
        raise HTTPException(404, "Not found")
    revisions.record_delete(db, obj, user=current_user)
    db.delete(obj)
    db.commit()
    log_op(db, action="删除", target="领域遗留问题", target_id=lid,
           detail="", user=current_user, request=request)
    return {"ok": True}
