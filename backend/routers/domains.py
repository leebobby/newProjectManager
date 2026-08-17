"""领域管理：按 PL 资源组聚合的总览。

每个启用的 PL 组（resource_groups.kind == "pl"）一行，关联：
- 需求情况   —— 从迭代需求（iteration_requirements）按 group_id 聚合，口径＝当前进行中迭代
- 问题单情况 —— 从问题单 Excel「原始数据」按「责任人所属小组」聚合（实时读取，不入库）
- 最近主要工作 —— 富文本，人工维护（domain_contents.recent_work）
- 风险与求助 —— 结构化逐条，人工维护（domain_contents.risks_json）

权限：协作编辑域（见 CLAUDE.md「Write-permission principle」）——读对所有登录用户开放，
最近主要工作 / 风险求助 登录用户均可写。
"""
import json
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
import schemas
from auth import get_current_user
from database import get_db
from op_log import log_op
from routers.config import _load as _load_config

router = APIRouter(prefix="/api/domains", tags=["domains"])

_PROG_FIELDS = [
    "progress_walkthrough", "progress_reverse", "progress_stc",
    "progress_coding", "progress_bbit", "progress_clarify",
]
_SEVERITIES = ["严重", "一般", "提示"]
_RISK_TYPES = {"风险", "求助"}
# 问题单加权分值：致命10 严重3 一般1 提示0.1（未列出的级别记 0 分，仍计入数量）
_SEVERITY_WEIGHTS = {"致命": 10.0, "严重": 3.0, "一般": 1.0, "提示": 0.1}


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
def _req_summary(db: Session, group_id: int, iteration_ids: List[int]) -> schemas.DomainReqSummary:
    s = schemas.DomainReqSummary(by_priority={})
    if not iteration_ids:
        return s
    rows = (
        db.query(models.IterationRequirement)
        .filter(
            models.IterationRequirement.group_id == group_id,
            models.IterationRequirement.iteration_id.in_(iteration_ids),
        )
        .all()
    )
    for r in rows:
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


# ─── helpers：问题单聚合（从 Excel 实时读取）─────────────────────────────────────
def _load_issue_raw() -> Tuple[Optional[List[dict]], Optional[str], Optional[str]]:
    """读取最新问题单 Excel 的原始行。

    返回 (raw_rows, file_mtime, note)；不可用时 raw_rows 为 None、note 给出原因。
    """
    cfg = _load_config()
    path_str = (cfg.get("issue_report_path") or "").strip()
    if not path_str:
        return None, None, "未配置问题单报表路径"
    try:
        from routers.issues import _parse_excel_cached, _resolve_for_date

        target = _resolve_for_date(path_str)
        # 复用问题单模块的 mtime 缓存解析：文件没变时不重读 Excel（领域总览每次打开都会调这里）
        parsed = _parse_excel_cached(str(target))
        raw = parsed.get("raw") or []
        return raw, parsed.get("file_mtime"), None
    except HTTPException as exc:
        return None, None, str(exc.detail)
    except Exception as exc:
        return None, None, f"读取问题单失败：{exc}"


def _issue_rows_for_group(raw: List[dict], g: models.ResourceGroup) -> List[dict]:
    keys = {k for k in (g.name, g.code) if k}
    return [r for r in raw if (r.get("group") or "").strip() in keys]


def _issue_summary_from_rows(rows: List[dict], mtime: Optional[str]) -> schemas.DomainIssueSummary:
    by_sev = {}
    score = 0.0
    for r in rows:
        sev = (r.get("severity") or "").strip()
        if sev:
            by_sev[sev] = by_sev.get(sev, 0) + 1
            score += _SEVERITY_WEIGHTS.get(sev, 0.0)
    return schemas.DomainIssueSummary(
        available=True, total=len(rows), score=round(score, 1),
        by_severity=by_sev, file_mtime=mtime,
    )


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
    include_hidden: bool = Query(False, description="是否一并返回已隐藏（不管理）的领域"),
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
    its = _scope_iterations(db, year, month)
    iteration_ids = [it.id for it in its]
    raw, mtime, note = _load_issue_raw()

    rows: List[schemas.DomainRowOut] = []
    for g in groups:
        content = _get_content(db, g.id)
        if raw is None:
            issue_summary = schemas.DomainIssueSummary(available=False, note=note)
        else:
            issue_summary = _issue_summary_from_rows(_issue_rows_for_group(raw, g), mtime)
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
            req_summary=_req_summary(db, g.id, iteration_ids),
            issue_summary=issue_summary,
            recent_work=(content.recent_work if content else "") or "",
            risks=_parse_risks(content.risks_json if content else "[]"),
            version=content.version if content else 0,
            hidden=(g.id in hidden_ids),
        ))
    return schemas.DomainListOut(
        iteration_label=_iteration_label(its),
        selected_year=year, selected_month=month,
        iterations=_available_iterations(db),
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
    db: Session = Depends(get_db),
):
    """下钻：该领域在选定月份（或进行中迭代）下的需求明细。"""
    _require_pl_group(db, group_id)
    iteration_ids = [it.id for it in _scope_iterations(db, year, month)]
    if not iteration_ids:
        return []
    return (
        db.query(models.IterationRequirement)
        .filter(
            models.IterationRequirement.group_id == group_id,
            models.IterationRequirement.iteration_id.in_(iteration_ids),
        )
        .order_by(models.IterationRequirement.iteration_id.desc(),
                  models.IterationRequirement.seq.asc())
        .all()
    )


@router.get("/{group_id}/issues")
def list_group_issues(group_id: int, db: Session = Depends(get_db)):
    """下钻：该领域名下的问题单原始行。"""
    g = _require_pl_group(db, group_id)
    raw, mtime, note = _load_issue_raw()
    if raw is None:
        return {"available": False, "note": note, "rows": []}
    return {"available": True, "file_mtime": mtime, "rows": _issue_rows_for_group(raw, g)}


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
    db.commit()
    db.refresh(content)
    log_op(db, action="修改", target="领域内容", target_id=group_id,
           detail=f"group={g.name} fields={','.join(changed) or '无'}",
           user=current_user, request=request)

    # 复用列表口径回包一行，前端可直接替换
    its = _in_progress_iterations(db)
    iteration_ids = [it.id for it in its]
    raw, mtime, note = _load_issue_raw()
    if raw is None:
        issue_summary = schemas.DomainIssueSummary(available=False, note=note)
    else:
        issue_summary = _issue_summary_from_rows(_issue_rows_for_group(raw, g), mtime)
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


def _task_out(obj: models.DomainRisk, name_map: dict) -> schemas.DomainTaskOut:
    out = schemas.DomainTaskOut.model_validate(obj)
    out.domain_name = name_map.get(obj.domain_id)
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
    name_map = _domain_name_map(db)
    return [_task_out(r, name_map) for r in rows]


@router.post("/risks", response_model=schemas.DomainTaskOut)
def create_domain_risk(
    payload: schemas.DomainTaskCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    data = payload.model_dump()
    if not data.get("seq"):
        data["seq"] = (db.query(func.coalesce(func.max(models.DomainRisk.seq), 0)).scalar() or 0) + 1
    obj = models.DomainRisk(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    log_op(db, action="新增", target="领域事务/风险", target_id=obj.id,
           detail=(obj.content or "")[:40], user=current_user, request=request)
    return _task_out(obj, _domain_name_map(db))


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
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("version", None)
    for k, v in changes.items():
        setattr(obj, k, v)
    obj.version += 1
    db.commit()
    db.refresh(obj)
    log_op(db, action="修改", target="领域事务/风险", target_id=obj.id,
           detail=(obj.content or "")[:40], user=current_user, request=request)
    return _task_out(obj, _domain_name_map(db))


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
    db.delete(obj)
    db.commit()
    log_op(db, action="删除", target="领域事务/风险", target_id=rid,
           detail="", user=current_user, request=request)
    return {"ok": True}
