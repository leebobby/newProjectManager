"""干系人管理：项目组沟通地图 + 战场沟通矩阵 CRUD。

权限：读取 — 所有登录用户；写入 — 仅 admin。
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

import models
import schemas
from auth import require_admin
from database import get_db
from op_log import log_op

router = APIRouter(prefix="/api/stakeholders", tags=["stakeholders"])


def _resolve_customer_id_by_name(db: Session, name: str):
    s = (name or "").strip()
    if not s:
        return None
    cu = db.query(models.Customer).filter(models.Customer.code == s).first()
    if cu:
        return cu.id
    al = db.query(models.CustomerAlias).filter(models.CustomerAlias.alias == s).first()
    return al.customer_id if al else None


# ── 项目组沟通地图 ──────────────────────────────────────────

@router.get("/project-contacts", response_model=List[schemas.ProjectContactOut])
def list_project_contacts(db: Session = Depends(get_db)):
    return (
        db.query(models.StakeholderProjectContact)
        .order_by(models.StakeholderProjectContact.sort_order,
                  models.StakeholderProjectContact.id)
        .all()
    )


@router.post("/project-contacts", response_model=schemas.ProjectContactOut)
def create_project_contact(
    payload: schemas.ProjectContactCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    max_order = db.query(models.StakeholderProjectContact).count()
    item = models.StakeholderProjectContact(**payload.model_dump(), sort_order=max_order)
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target="项目组联系人", target_id=item.id,
           detail=f"col1={item.col1} col2={item.col2}",
           user=current_admin, request=request)
    return item


@router.put("/project-contacts/{item_id}", response_model=schemas.ProjectContactOut)
def update_project_contact(
    item_id: int,
    payload: schemas.ProjectContactUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.StakeholderProjectContact).filter(
        models.StakeholderProjectContact.id == item_id
    ).first()
    if not item:
        raise HTTPException(404, "Not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="项目组联系人", target_id=item.id,
           detail=f"col1={item.col1} col2={item.col2}",
           user=current_admin, request=request)
    return item


@router.delete("/project-contacts/{item_id}")
def delete_project_contact(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.StakeholderProjectContact).filter(
        models.StakeholderProjectContact.id == item_id
    ).first()
    if not item:
        raise HTTPException(404, "Not found")
    snapshot = f"col1={item.col1} col2={item.col2}"
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target="项目组联系人", target_id=item_id,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}


# ── 战场沟通矩阵 ──────────────────────────────────────────

@router.get("/battlefields", response_model=List[schemas.BattlefieldOut])
def list_battlefields(db: Session = Depends(get_db)):
    return (
        db.query(models.StakeholderBattlefield)
        .order_by(models.StakeholderBattlefield.sort_order,
                  models.StakeholderBattlefield.id)
        .all()
    )


@router.post("/battlefields", response_model=schemas.BattlefieldOut)
def create_battlefield(
    payload: schemas.BattlefieldCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    max_order = db.query(models.StakeholderBattlefield).count()
    data = payload.model_dump()
    item = models.StakeholderBattlefield(
        **data, sort_order=max_order,
        customer_id=_resolve_customer_id_by_name(db, data.get("battlefield", "")),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target="战场矩阵", target_id=item.id,
           detail=f"battlefield={item.battlefield}",
           user=current_admin, request=request)
    return item


@router.put("/battlefields/{item_id}", response_model=schemas.BattlefieldOut)
def update_battlefield(
    item_id: int,
    payload: schemas.BattlefieldUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.StakeholderBattlefield).filter(
        models.StakeholderBattlefield.id == item_id
    ).first()
    if not item:
        raise HTTPException(404, "Not found")
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(item, k, v)
    # battlefield 字段被改写时，刷新 customer_id 绑定
    if "battlefield" in changes:
        item.customer_id = _resolve_customer_id_by_name(db, item.battlefield or "")
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="战场矩阵", target_id=item.id,
           detail=f"battlefield={item.battlefield}",
           user=current_admin, request=request)
    return item


@router.delete("/battlefields/{item_id}")
def delete_battlefield(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.StakeholderBattlefield).filter(
        models.StakeholderBattlefield.id == item_id
    ).first()
    if not item:
        raise HTTPException(404, "Not found")
    snapshot = f"battlefield={item.battlefield}"
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target="战场矩阵", target_id=item_id,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}
