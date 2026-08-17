"""机台自定义信息块（如 MPH状态）：
- 块定义（CustomerExtraField）：全局共享一份，admin 在 客户管理 里维护
- 每台机台一份值（CustomerExtraValue）：文本 + 单个附件/图片

权限：
- 块定义读：所有登录用户；写：仅 admin
- 机台值读：所有登录用户；写（文本/附件）：仅 admin（与 SOW / License 一致）
"""
import os
import pathlib
import uuid
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

import models
import schemas
from auth import get_current_user, require_admin
from database import get_db
from op_log import log_op

router = APIRouter(prefix="/api/customer-extra", tags=["customer-extra"])

UPLOAD_ROOT = pathlib.Path(__file__).resolve().parent.parent / "uploads" / "customer_extra"


def _ensure_dir(p: pathlib.Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _abs_path(rel: str) -> pathlib.Path:
    return (UPLOAD_ROOT.parent / rel).resolve()


def _serialize_value(v: models.CustomerExtraValue) -> dict:
    return {
        "id": v.id,
        "machine_status_id": v.machine_status_id,
        "field_id": v.field_id,
        "text": v.text or "",
        "file_name": v.file_name or "",
        "file_size": v.file_size or 0,
        "has_file": bool(v.file_path),
        "version": v.version or 0,
    }


# ─── 块定义 ──────────────────────────────────────────────────────────
@router.get("/fields", response_model=List[schemas.CustomerExtraFieldOut])
def list_fields(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    q = db.query(models.CustomerExtraField)
    if not include_inactive:
        q = q.filter(models.CustomerExtraField.is_active.is_(True))
    return q.order_by(models.CustomerExtraField.sort_order, models.CustomerExtraField.id).all()


@router.post("/fields", response_model=schemas.CustomerExtraFieldOut)
def create_field(
    payload: schemas.CustomerExtraFieldCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    key = (payload.key or "").strip()
    label = (payload.label or "").strip()
    if not key or not label:
        raise HTTPException(400, "key 和 label 不能为空")
    if db.query(models.CustomerExtraField).filter(models.CustomerExtraField.key == key).first():
        raise HTTPException(400, f"key「{key}」已存在")
    item = models.CustomerExtraField(
        key=key, label=label,
        sort_order=payload.sort_order or 0,
        is_active=payload.is_active if payload.is_active is not None else True,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target="自定义信息块", target_id=item.id,
           detail=f"key={item.key} label={item.label}",
           user=current_admin, request=request)
    return item


@router.put("/fields/{fid}", response_model=schemas.CustomerExtraFieldOut)
def update_field(
    fid: int,
    payload: schemas.CustomerExtraFieldUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.CustomerExtraField).filter(models.CustomerExtraField.id == fid).first()
    if not item:
        raise HTTPException(404, "Not found")
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="自定义信息块", target_id=item.id,
           detail=f"key={item.key} fields={','.join(changes.keys()) or '无'}",
           user=current_admin, request=request)
    return item


@router.delete("/fields/{fid}")
def delete_field(
    fid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.CustomerExtraField).filter(models.CustomerExtraField.id == fid).first()
    if not item:
        raise HTTPException(404, "Not found")
    # 连带删除所有机台下该块的值及其附件文件
    values = db.query(models.CustomerExtraValue).filter(
        models.CustomerExtraValue.field_id == fid
    ).all()
    for v in values:
        if v.file_path:
            try:
                p = _abs_path(v.file_path)
                if p.exists():
                    p.unlink()
            except OSError:
                pass
        db.delete(v)
    snapshot = f"key={item.key} label={item.label} values={len(values)}"
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target="自定义信息块", target_id=fid,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}


# ─── 机台值 ──────────────────────────────────────────────────────────
def _get_or_create_value(db: Session, machine_status_id: int, field_id: int) -> models.CustomerExtraValue:
    v = (
        db.query(models.CustomerExtraValue)
        .filter(
            models.CustomerExtraValue.machine_status_id == machine_status_id,
            models.CustomerExtraValue.field_id == field_id,
        )
        .first()
    )
    if v:
        return v
    v = models.CustomerExtraValue(machine_status_id=machine_status_id, field_id=field_id)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


@router.get("/values")
def list_values(
    machine_status_id: int = Query(...),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    rows = (
        db.query(models.CustomerExtraValue)
        .filter(models.CustomerExtraValue.machine_status_id == machine_status_id)
        .all()
    )
    return [_serialize_value(v) for v in rows]


@router.put("/values")
def upsert_value_text(
    request: Request,
    machine_status_id: int = Body(...),
    field_id: int = Body(...),
    text: str = Body(""),
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    """保存某机台某信息块的文本（不存在则创建）。低并发，末写者生效。"""
    if not db.query(models.CustomerStatus).filter(models.CustomerStatus.id == machine_status_id).first():
        raise HTTPException(404, "机台不存在")
    if not db.query(models.CustomerExtraField).filter(models.CustomerExtraField.id == field_id).first():
        raise HTTPException(404, "信息块不存在")
    v = _get_or_create_value(db, machine_status_id, field_id)
    v.text = text or ""
    v.version = (v.version or 0) + 1
    db.commit()
    db.refresh(v)
    log_op(db, action="修改", target="自定义信息块值", target_id=v.id,
           detail=f"machine={machine_status_id} field={field_id}",
           user=current_admin, request=request)
    return _serialize_value(v)


@router.post("/values/attachment")
def upload_attachment(
    request: Request,
    machine_status_id: int = Form(...),
    field_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    """上传/替换某机台某信息块的附件（单个）。"""
    if not db.query(models.CustomerStatus).filter(models.CustomerStatus.id == machine_status_id).first():
        raise HTTPException(404, "机台不存在")
    if not db.query(models.CustomerExtraField).filter(models.CustomerExtraField.id == field_id).first():
        raise HTTPException(404, "信息块不存在")
    if not file or not file.filename:
        raise HTTPException(400, "必须上传文件")

    v = _get_or_create_value(db, machine_status_id, field_id)

    # 写入新文件
    target_dir = UPLOAD_ROOT / str(machine_status_id)
    _ensure_dir(target_dir)
    orig_name = file.filename or "attachment.bin"
    safe_ext = pathlib.Path(orig_name).suffix[:16]
    stored = f"{uuid.uuid4().hex}{safe_ext}"
    full = target_dir / stored
    size = 0
    with open(full, "wb") as f:
        while True:
            chunk = file.file.read(64 * 1024)
            if not chunk:
                break
            f.write(chunk)
            size += len(chunk)

    # 删旧
    if v.file_path:
        try:
            old = _abs_path(v.file_path)
            if old.exists() and old != full.resolve():
                old.unlink()
        except OSError:
            pass

    v.file_path = f"customer_extra/{machine_status_id}/{stored}"
    v.file_name = orig_name
    v.file_size = size
    v.version = (v.version or 0) + 1
    db.commit()
    db.refresh(v)
    log_op(db, action="上传附件", target="自定义信息块值", target_id=v.id,
           detail=f"machine={machine_status_id} field={field_id} file={orig_name}",
           user=current_admin, request=request)
    return _serialize_value(v)


@router.get("/values/{value_id}/attachment")
def download_attachment(
    value_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    v = db.query(models.CustomerExtraValue).filter(models.CustomerExtraValue.id == value_id).first()
    if not v or not v.file_path:
        raise HTTPException(404, "附件不存在")
    p = _abs_path(v.file_path)
    if not p.exists():
        raise HTTPException(404, "文件已丢失")
    return FileResponse(str(p), filename=v.file_name or os.path.basename(str(p)))


@router.delete("/values/{value_id}/attachment")
def delete_attachment(
    value_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    v = db.query(models.CustomerExtraValue).filter(models.CustomerExtraValue.id == value_id).first()
    if not v:
        raise HTTPException(404, "Not found")
    if v.file_path:
        try:
            p = _abs_path(v.file_path)
            if p.exists():
                p.unlink()
        except OSError:
            pass
    v.file_path = ""
    v.file_name = ""
    v.file_size = 0
    v.version = (v.version or 0) + 1
    db.commit()
    db.refresh(v)
    log_op(db, action="删除附件", target="自定义信息块值", target_id=v.id,
           detail=f"value_id={value_id}", user=current_admin, request=request)
    return _serialize_value(v)
