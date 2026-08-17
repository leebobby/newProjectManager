"""客户面状态 CRUD + PPT 导出。

权限矩阵：
- 列表 GET：所有登录用户
- 新增 POST / 删除 DELETE：仅 admin
- 编辑 PUT：
    机台编号 / 客户(battlefield) / 型号(model) —— 创建后锁定，路由层拒绝任何修改
    current_stage / field_version / attention_level —— 仅 admin 可改
    customer_status / milestones_json             —— 所有登录用户均可改
- 导出 PPT：仅 admin

注：recent_focus / key_issues 两列已被 customer_issues 表取代（见 routers/customer_issues.py），
仅为回滚保险保留在模型与白名单里，现有前端不再写入它们。
"""
import io
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import models
import schemas
from auth import get_current_user, require_admin
from database import get_db
from op_log import log_op
from notify import dispatch

router = APIRouter(prefix="/api/customer-status", tags=["customer-status"])

_ADMIN_ONLY_FIELDS = {"current_stage", "field_version", "attention_level", "issue_url"}
_USER_FIELDS = {"customer_status", "recent_focus", "key_issues", "milestones_json"}


def _resolve_customer_id_by_name(db: Session, name: str):
    """按 battlefield 字符串反查 customer_id；找不到返回 None。"""
    s = (name or "").strip()
    if not s:
        return None
    cu = db.query(models.Customer).filter(models.Customer.code == s).first()
    if cu:
        return cu.id
    al = db.query(models.CustomerAlias).filter(models.CustomerAlias.alias == s).first()
    if al:
        return al.customer_id
    return None


@router.get("", response_model=List[schemas.CustomerStatusOut])
def list_items(db: Session = Depends(get_db)):
    return db.query(models.CustomerStatus).order_by(models.CustomerStatus.id.desc()).all()


@router.post("", response_model=schemas.CustomerStatusOut)
def create_item(
    payload: schemas.CustomerStatusCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    exists = (
        db.query(models.CustomerStatus)
        .filter(models.CustomerStatus.machine_id == payload.machine_id)
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="机台编号已存在")
    data = payload.model_dump()
    data["customer_id"] = _resolve_customer_id_by_name(db, data.get("battlefield", ""))
    item = models.CustomerStatus(**data)
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target="客户面状态", target_id=item.id,
           detail=f"machine_id={item.machine_id} battlefield={item.battlefield}",
           user=current_admin, request=request)
    return item


@router.put("/{item_id}", response_model=schemas.CustomerStatusOut)
def update_item(
    item_id: int,
    payload: schemas.CustomerStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = db.query(models.CustomerStatus).filter(models.CustomerStatus.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    if item.version != payload.version:
        raise HTTPException(status_code=409, detail="数据已被他人修改，请刷新后重试")
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("version", None)
    is_admin = current_user.role == "admin"
    for k, v in changes.items():
        if k in _ADMIN_ONLY_FIELDS and not is_admin:
            raise HTTPException(status_code=403, detail=f"字段「{k}」仅管理员可修改")
        if k not in _ADMIN_ONLY_FIELDS and k not in _USER_FIELDS:
            raise HTTPException(status_code=400, detail=f"字段「{k}」不允许修改")
        setattr(item, k, v)
    item.version += 1
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="客户面状态", target_id=item.id,
           detail=f"machine_id={item.machine_id} fields={','.join(changes.keys()) or '无'}",
           user=current_user, request=request)

    # 通知：订阅了该客户的人
    if changes and item.customer_id:
        dispatch(
            db, kind="status_change",
            title=f"客户面状态更新：{item.battlefield or ''} {item.machine_id or ''}".strip(),
            body=f"变更字段：{'、'.join(changes.keys())}",
            link=f"/customers/{item.customer_id}",
            source_type="customer", source_id=item.customer_id,
            actor=current_user, recipient_ids=[], extra_subs=True,
        )
    return item


@router.delete("/{item_id}")
def delete_item(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.CustomerStatus).filter(models.CustomerStatus.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    snapshot = f"machine_id={item.machine_id} battlefield={item.battlefield}"
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target="客户面状态", target_id=item_id,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}


@router.get("/export.pptx")
def export_pptx(
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    """导出当前所有客户面状态为 PPT（单页表格）。"""
    from pptx_utils import build_customer_status_pptx

    rows = db.query(models.CustomerStatus).order_by(models.CustomerStatus.id.asc()).all()
    stream = build_customer_status_pptx(rows)
    filename = f"customer-status-{datetime.now().strftime('%Y%m%d-%H%M%S')}.pptx"
    log_op(db, action="导出PPT", target="客户面状态",
           detail=f"rows={len(rows)}", user=current_admin, request=request)
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
