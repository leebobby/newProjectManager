from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, joinedload

import models
import schemas
from auth import require_admin
from database import get_db
from op_log import log_op
from notify import broadcast

router = APIRouter(prefix="/api", tags=["versions"])

# 触发"版本计划变更"广播的字段（计划相关；纯文字描述/排序不广播）
_PLAN_FIELDS = {"version_no", "title", "range_start", "range_end", "actual_release_date"}


@router.get("/major-versions", response_model=List[schemas.MajorVersionDetailOut])
def list_major_versions(project_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(models.MajorVersion).options(joinedload(models.MajorVersion.iteration_versions))
    if project_id is not None:
        q = q.filter(models.MajorVersion.project_id == project_id)
    else:
        q = q.filter(models.MajorVersion.project_id.is_(None))
    return q.order_by(models.MajorVersion.sort_order).all()


@router.post("/major-versions", response_model=schemas.MajorVersionDetailOut)
def create_major_version(
    payload: schemas.MajorVersionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = models.MajorVersion(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target="大版本", target_id=item.id,
           detail=f"version_no={item.version_no}",
           user=current_admin, request=request)
    broadcast(
        db, kind="version_plan",
        title=f"新增版本计划：{item.version_no}{(' ' + item.title) if item.title else ''}",
        body="", link="/roadmaps", actor=current_admin,
    )
    return item


@router.put("/major-versions/{item_id}", response_model=schemas.MajorVersionDetailOut)
def update_major_version(
    item_id: int,
    payload: schemas.MajorVersionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.MajorVersion).filter(models.MajorVersion.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="大版本", target_id=item.id,
           detail=f"version_no={item.version_no} fields={','.join(changes.keys()) or '无'}",
           user=current_admin, request=request)
    plan_changed = sorted(set(changes.keys()) & _PLAN_FIELDS)
    if plan_changed:
        broadcast(
            db, kind="version_plan",
            title=f"版本计划变更：{item.version_no}{(' ' + item.title) if item.title else ''}",
            body=f"变更字段：{'、'.join(plan_changed)}",
            link="/roadmaps", actor=current_admin,
        )
    return item


@router.delete("/major-versions/{item_id}")
def delete_major_version(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.MajorVersion).filter(models.MajorVersion.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    snapshot = f"version_no={item.version_no}"
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target="大版本", target_id=item_id,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}


@router.post("/iteration-versions", response_model=schemas.IterationVersionOut)
def create_iteration_version(
    payload: schemas.IterationVersionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = models.IterationVersion(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target="迭代版本", target_id=item.id,
           detail=f"version_no={item.version_no} major_id={item.major_version_id}",
           user=current_admin, request=request)
    return item


@router.put("/iteration-versions/{item_id}", response_model=schemas.IterationVersionOut)
def update_iteration_version(
    item_id: int,
    payload: schemas.IterationVersionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.IterationVersion).filter(models.IterationVersion.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="迭代版本", target_id=item.id,
           detail=f"version_no={item.version_no} fields={','.join(changes.keys()) or '无'}",
           user=current_admin, request=request)
    return item


@router.delete("/iteration-versions/{item_id}")
def delete_iteration_version(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.IterationVersion).filter(models.IterationVersion.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    snapshot = f"version_no={item.version_no}"
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target="迭代版本", target_id=item_id,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}


@router.get("/iteration-versions/all")
def list_all_iteration_versions(db: Session = Depends(get_db)):
    """Flat list of all iteration versions with parent info — used for planned_version dropdown."""
    items = (
        db.query(models.IterationVersion)
        .options(
            joinedload(models.IterationVersion.major_version).joinedload(models.MajorVersion.project)
        )
        .order_by(models.IterationVersion.major_version_id, models.IterationVersion.sort_order)
        .all()
    )
    result = []
    for it in items:
        mv = it.major_version
        result.append({
            "id": it.id,
            "major_version_id": it.major_version_id,
            "major_version_no": mv.version_no,
            "major_version_title": mv.title,
            "project_id": mv.project_id,
            "project_name": mv.project.name if mv.project else "",
            "version_no": it.version_no,
            "title": it.title,
            "planned_date": it.planned_date,
        })
    return result
