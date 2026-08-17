"""项目里程碑（首页路线图）相关接口。

- GET 接口：任意登录用户可访问。
- POST/PUT/DELETE：需要管理员权限。
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

import models
import schemas
from auth import get_current_user, require_admin
from database import get_db
from op_log import log_op

router = APIRouter(prefix="/api/roadmap", tags=["roadmap"])


# ===== 项目 =====
@router.get("/projects", response_model=List[schemas.RoadmapProjectDetailOut])
def list_projects(db: Session = Depends(get_db), include_inactive: bool = False):
    q = db.query(models.RoadmapProject)
    if not include_inactive:
        q = q.filter(models.RoadmapProject.is_active.is_(True))
    q = q.order_by(models.RoadmapProject.sort_order.asc(), models.RoadmapProject.id.asc())
    return q.all()


@router.get("/projects/{project_id}", response_model=schemas.RoadmapProjectDetailOut)
def get_project(project_id: int, db: Session = Depends(get_db)):
    item = db.query(models.RoadmapProject).filter(models.RoadmapProject.id == project_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="项目不存在")
    return item


@router.post(
    "/projects",
    response_model=schemas.RoadmapProjectDetailOut,
)
def create_project(
    payload: schemas.RoadmapProjectCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = models.RoadmapProject(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target="路线图项目", target_id=item.id,
           detail=f"name={item.name}", user=current_admin, request=request)
    return item


@router.put(
    "/projects/{project_id}",
    response_model=schemas.RoadmapProjectDetailOut,
)
def update_project(
    project_id: int,
    payload: schemas.RoadmapProjectUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.RoadmapProject).filter(models.RoadmapProject.id == project_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="项目不存在")
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="路线图项目", target_id=item.id,
           detail=f"name={item.name} fields={','.join(changes.keys()) or '无'}",
           user=current_admin, request=request)
    return item


@router.delete("/projects/{project_id}")
def delete_project(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.RoadmapProject).filter(models.RoadmapProject.id == project_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="项目不存在")
    snapshot = f"name={item.name}"
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target="路线图项目", target_id=project_id,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}


# ===== 阶段 =====
def _validate_phase_range(start_year: int, start_month: int, end_year: int, end_month: int):
    if not (1 <= start_month <= 12 and 1 <= end_month <= 12):
        raise HTTPException(status_code=400, detail="月份需在 1-12 之间")
    if not (1900 <= start_year <= 2200 and 1900 <= end_year <= 2200):
        raise HTTPException(status_code=400, detail="年份需在 1900-2200 之间")
    start_abs = start_year * 12 + (start_month - 1)
    end_abs = end_year * 12 + (end_month - 1)
    if end_abs < start_abs:
        raise HTTPException(status_code=400, detail="结束时间不能早于起始时间")


@router.post(
    "/phases",
    response_model=schemas.RoadmapPhaseOut,
)
def create_phase(
    payload: schemas.RoadmapPhaseCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    project = db.query(models.RoadmapProject).filter(models.RoadmapProject.id == payload.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    _validate_phase_range(payload.start_year, payload.start_month, payload.end_year, payload.end_month)
    item = models.RoadmapPhase(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target="路线图阶段", target_id=item.id,
           detail=f"project_id={item.project_id} name={item.name}",
           user=current_admin, request=request)
    return item


@router.put(
    "/phases/{phase_id}",
    response_model=schemas.RoadmapPhaseOut,
)
def update_phase(
    phase_id: int,
    payload: schemas.RoadmapPhaseUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.RoadmapPhase).filter(models.RoadmapPhase.id == phase_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="阶段不存在")
    if item.version != payload.version:
        raise HTTPException(status_code=409, detail="数据已被他人修改，请刷新后重试")
    data = payload.model_dump(exclude_unset=True)
    data.pop("version", None)
    sy = data.get("start_year", item.start_year)
    sm = data.get("start_month", item.start_month)
    ey = data.get("end_year", item.end_year)
    em = data.get("end_month", item.end_month)
    _validate_phase_range(sy, sm, ey, em)
    for k, v in data.items():
        setattr(item, k, v)
    item.version += 1
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="路线图阶段", target_id=item.id,
           detail=f"name={item.name} fields={','.join(data.keys()) or '无'}",
           user=current_admin, request=request)
    return item


@router.delete("/phases/{phase_id}")
def delete_phase(
    phase_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.RoadmapPhase).filter(models.RoadmapPhase.id == phase_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="阶段不存在")
    snapshot = f"name={item.name}"
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target="路线图阶段", target_id=phase_id,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}


# ===== 里程碑 =====
def _validate_milestone(year: int, month: int):
    if not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail="月份需在 1-12 之间")
    if not (1900 <= year <= 2200):
        raise HTTPException(status_code=400, detail="年份需在 1900-2200 之间")


@router.post(
    "/milestones",
    response_model=schemas.RoadmapMilestoneOut,
)
def create_milestone(
    payload: schemas.RoadmapMilestoneCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    project = db.query(models.RoadmapProject).filter(models.RoadmapProject.id == payload.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    _validate_milestone(payload.year, payload.month)
    item = models.RoadmapMilestone(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target="路线图里程碑", target_id=item.id,
           detail=f"project_id={item.project_id} {item.year}-{item.month:02d} title={item.title}",
           user=current_admin, request=request)
    return item


@router.put(
    "/milestones/{milestone_id}",
    response_model=schemas.RoadmapMilestoneOut,
)
def update_milestone(
    milestone_id: int,
    payload: schemas.RoadmapMilestoneUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.RoadmapMilestone).filter(models.RoadmapMilestone.id == milestone_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="里程碑不存在")
    data = payload.model_dump(exclude_unset=True)
    y = data.get("year", item.year)
    m = data.get("month", item.month)
    _validate_milestone(y, m)
    for k, v in data.items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="路线图里程碑", target_id=item.id,
           detail=f"{item.year}-{item.month:02d} fields={','.join(data.keys()) or '无'}",
           user=current_admin, request=request)
    return item


@router.delete("/milestones/{milestone_id}")
def delete_milestone(
    milestone_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.RoadmapMilestone).filter(models.RoadmapMilestone.id == milestone_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="里程碑不存在")
    snapshot = f"{item.year}-{item.month:02d} title={item.title}"
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target="路线图里程碑", target_id=milestone_id,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}
