"""客户定制化需求（客户级）：客户详情页"问题单情况"上方的表格。

权限：读对所有登录用户开放；增删改仅 admin（与客户主数据 / SOW 一致）。
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

import models
import schemas
from auth import get_current_user, require_admin
from database import get_db
from op_log import log_op

router = APIRouter(prefix="/api/customer-custom-reqs", tags=["customer-custom-reqs"])


@router.get("", response_model=List[schemas.CustomerCustomReqOut])
def list_reqs(
    customer_id: int = Query(...),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    return (
        db.query(models.CustomerCustomReq)
        .filter(models.CustomerCustomReq.customer_id == customer_id)
        .order_by(models.CustomerCustomReq.seq.asc(), models.CustomerCustomReq.id.asc())
        .all()
    )


@router.post("", response_model=schemas.CustomerCustomReqOut)
def create_req(
    payload: schemas.CustomerCustomReqCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    if not db.query(models.Customer).filter(models.Customer.id == payload.customer_id).first():
        raise HTTPException(404, "客户不存在")
    data = payload.model_dump()
    if not data.get("seq"):
        cnt = (
            db.query(models.CustomerCustomReq)
            .filter(models.CustomerCustomReq.customer_id == payload.customer_id)
            .count()
        )
        data["seq"] = cnt + 1
    item = models.CustomerCustomReq(**data)
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target="客户定制化需求", target_id=item.id,
           detail=f"customer_id={item.customer_id} desc={(item.description or '')[:40]}",
           user=current_admin, request=request)
    return item


@router.put("/{item_id}", response_model=schemas.CustomerCustomReqOut)
def update_req(
    item_id: int,
    payload: schemas.CustomerCustomReqUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.CustomerCustomReq).filter(models.CustomerCustomReq.id == item_id).first()
    if not item:
        raise HTTPException(404, "Not found")
    if item.version != payload.version:
        raise HTTPException(409, "数据已被他人修改，请刷新后重试")
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("version", None)
    for k, v in changes.items():
        setattr(item, k, v)
    item.version += 1
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="客户定制化需求", target_id=item.id,
           detail=f"customer_id={item.customer_id} fields={','.join(changes.keys()) or '无'}",
           user=current_admin, request=request)
    return item


@router.delete("/{item_id}")
def delete_req(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.CustomerCustomReq).filter(models.CustomerCustomReq.id == item_id).first()
    if not item:
        raise HTTPException(404, "Not found")
    snapshot = f"customer_id={item.customer_id} desc={(item.description or '')[:40]}"
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target="客户定制化需求", target_id=item_id,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}
