"""SOW 管理：全局字段定义 + 每机台 SOW 行数据。

权限：
- GET（字段定义 / 行）：所有登录用户
- POST/PUT/DELETE：仅 admin
"""
import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

import models
import schemas
from auth import require_admin
from database import get_db
from op_log import log_op

router = APIRouter(prefix="/api/sow", tags=["sow"])

_ALLOWED_TYPES = {"text", "date", "select"}


def _options_to_list(raw: str) -> List[str]:
    if not raw:
        return []
    try:
        v = json.loads(raw)
        if isinstance(v, list):
            return [str(x) for x in v]
    except (ValueError, TypeError):
        pass
    return []


def _serialize_field(f: models.SowFieldDef) -> dict:
    return {
        "id": f.id,
        "key": f.key,
        "label": f.label,
        "field_type": f.field_type,
        "options": _options_to_list(f.options or ""),
        "required": bool(f.required),
        "sort_order": f.sort_order or 0,
        "is_active": bool(f.is_active),
    }


def _serialize_row(r: models.SowRow) -> dict:
    try:
        data = json.loads(r.data or "{}")
        if not isinstance(data, dict):
            data = {}
    except (ValueError, TypeError):
        data = {}
    return {
        "id": r.id,
        "machine_status_id": r.machine_status_id,
        "data": data,
        "sort_order": r.sort_order or 0,
        "version": r.version,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }


# ─── 字段定义 ─────────────────────────────────────────────────────

@router.get("/fields", response_model=List[schemas.SowFieldDefOut])
def list_fields(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    q = db.query(models.SowFieldDef)
    if not include_inactive:
        q = q.filter(models.SowFieldDef.is_active.is_(True))
    rows = q.order_by(models.SowFieldDef.sort_order, models.SowFieldDef.id).all()
    return [_serialize_field(f) for f in rows]


@router.post("/fields", response_model=schemas.SowFieldDefOut)
def create_field(
    payload: schemas.SowFieldDefCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    key = payload.key.strip()
    if not key:
        raise HTTPException(400, "key 不能为空")
    if payload.field_type not in _ALLOWED_TYPES:
        raise HTTPException(400, f"field_type 仅支持 {sorted(_ALLOWED_TYPES)}")
    exists = db.query(models.SowFieldDef).filter(models.SowFieldDef.key == key).first()
    if exists:
        raise HTTPException(400, f"字段 key「{key}」已存在")

    item = models.SowFieldDef(
        key=key,
        label=payload.label.strip() or key,
        field_type=payload.field_type,
        options=json.dumps(payload.options or [], ensure_ascii=False),
        required=bool(payload.required),
        sort_order=payload.sort_order or 0,
        is_active=payload.is_active if payload.is_active is not None else True,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target="SOW字段", target_id=item.id,
           detail=f"key={item.key} type={item.field_type}",
           user=current_admin, request=request)
    return _serialize_field(item)


@router.put("/fields/{fid}", response_model=schemas.SowFieldDefOut)
def update_field(
    fid: int,
    payload: schemas.SowFieldDefUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.SowFieldDef).filter(models.SowFieldDef.id == fid).first()
    if not item:
        raise HTTPException(404, "字段不存在")
    data = payload.model_dump(exclude_unset=True)

    if "field_type" in data and data["field_type"] not in _ALLOWED_TYPES:
        raise HTTPException(400, f"field_type 仅支持 {sorted(_ALLOWED_TYPES)}")

    if "options" in data:
        item.options = json.dumps(data.pop("options") or [], ensure_ascii=False)

    for k, v in data.items():
        setattr(item, k, v)

    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="SOW字段", target_id=item.id,
           detail=f"key={item.key} fields={','.join(data.keys()) or '无'}",
           user=current_admin, request=request)
    return _serialize_field(item)


@router.delete("/fields/{fid}")
def delete_field(
    fid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    """硬删除字段。注意：已有 SowRow 中该 key 的值会变成"游离数据"，但不会引发报错。
    建议优先用"停用"（is_active=False）来隐藏列。
    """
    item = db.query(models.SowFieldDef).filter(models.SowFieldDef.id == fid).first()
    if not item:
        raise HTTPException(404, "字段不存在")
    snapshot = f"key={item.key}"
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target="SOW字段", target_id=fid,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}


# ─── SOW 行（按机台）─────────────────────────────────────────────

@router.get("/rows", response_model=List[schemas.SowRowOut])
def list_rows(
    machine_status_id: int,
    db: Session = Depends(get_db),
):
    rows = (
        db.query(models.SowRow)
        .filter(models.SowRow.machine_status_id == machine_status_id)
        .order_by(models.SowRow.sort_order, models.SowRow.id)
        .all()
    )
    return [_serialize_row(r) for r in rows]


@router.post("/rows", response_model=schemas.SowRowOut)
def create_row(
    machine_status_id: int,
    payload: schemas.SowRowCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    ms = (
        db.query(models.CustomerStatus)
        .filter(models.CustomerStatus.id == machine_status_id)
        .first()
    )
    if not ms:
        raise HTTPException(404, "机台不存在")
    sort_order = payload.sort_order
    if sort_order is None or sort_order == 0:
        sort_order = (
            db.query(models.SowRow)
            .filter(models.SowRow.machine_status_id == machine_status_id)
            .count()
        )
    item = models.SowRow(
        machine_status_id=machine_status_id,
        data=json.dumps(payload.data or {}, ensure_ascii=False),
        sort_order=sort_order,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target="SOW行", target_id=item.id,
           detail=f"machine={ms.machine_id}",
           user=current_admin, request=request)
    return _serialize_row(item)


@router.put("/rows/{rid}", response_model=schemas.SowRowOut)
def update_row(
    rid: int,
    payload: schemas.SowRowUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.SowRow).filter(models.SowRow.id == rid).first()
    if not item:
        raise HTTPException(404, "SOW 行不存在")
    if item.version != payload.version:
        raise HTTPException(409, "数据已被他人修改，请刷新后重试")
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("version", None)
    if "data" in changes:
        item.data = json.dumps(changes.pop("data") or {}, ensure_ascii=False)
    for k, v in changes.items():
        setattr(item, k, v)
    item.version += 1
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="SOW行", target_id=item.id,
           detail=f"row_id={item.id}",
           user=current_admin, request=request)
    return _serialize_row(item)


@router.delete("/rows/{rid}")
def delete_row(
    rid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.SowRow).filter(models.SowRow.id == rid).first()
    if not item:
        raise HTTPException(404, "SOW 行不存在")
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target="SOW行", target_id=rid,
           detail=f"row_id={rid}", user=current_admin, request=request)
    return {"ok": True}
