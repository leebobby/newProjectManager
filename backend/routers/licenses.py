"""机台 License 管理：每台机台可以挂多个 license 文件。

权限：
- GET 列表 / GET 下载：所有登录用户
- POST 上传 / PUT 备注 / DELETE 删除：仅 admin
"""
import os
import pathlib
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

import models
import schemas
from auth import get_current_user, require_admin
from database import get_db
from op_log import log_op

router = APIRouter(prefix="/api/licenses", tags=["licenses"])

UPLOAD_ROOT = pathlib.Path(__file__).resolve().parent.parent / "uploads" / "licenses"


def _ensure_dir(p: pathlib.Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _save_upload(upload: UploadFile, machine_status_id: int) -> tuple[str, str, int]:
    """保存上传文件，返回 (相对路径, 原文件名, 字节数)。相对路径以 uploads/ 为根。"""
    target_dir = UPLOAD_ROOT / str(machine_status_id)
    _ensure_dir(target_dir)
    orig_name = upload.filename or "license.bin"
    safe_ext = pathlib.Path(orig_name).suffix[:16]
    stored = f"{uuid.uuid4().hex}{safe_ext}"
    full = target_dir / stored
    size = 0
    with open(full, "wb") as f:
        while True:
            chunk = upload.file.read(64 * 1024)
            if not chunk:
                break
            f.write(chunk)
            size += len(chunk)
    rel = f"licenses/{machine_status_id}/{stored}"
    return rel, orig_name, size


def _abs_path(rel: str) -> pathlib.Path:
    base = UPLOAD_ROOT.parent
    return (base / rel).resolve()


@router.get("", response_model=List[schemas.MachineLicenseOut])
def list_licenses(
    machine_status_id: int,
    db: Session = Depends(get_db),
):
    return (
        db.query(models.MachineLicense)
        .filter(models.MachineLicense.machine_status_id == machine_status_id)
        .order_by(models.MachineLicense.id.desc())
        .all()
    )


@router.post("", response_model=schemas.MachineLicenseOut)
def upload_license(
    request: Request,
    machine_status_id: int = Form(...),
    remark: str = Form(""),
    file: UploadFile = File(...),
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
    if not file or not file.filename:
        raise HTTPException(400, "必须上传文件")
    rel, orig_name, size = _save_upload(file, machine_status_id)
    item = models.MachineLicense(
        machine_status_id=machine_status_id,
        file_name=orig_name,
        file_path=rel,
        file_size=size,
        remark=remark or "",
        uploaded_by=current_admin.username or "",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target="License", target_id=item.id,
           detail=f"machine={ms.machine_id} file={orig_name}",
           user=current_admin, request=request)
    return item


@router.put("/{lid}", response_model=schemas.MachineLicenseOut)
def update_license(
    lid: int,
    request: Request,
    remark: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.MachineLicense).filter(models.MachineLicense.id == lid).first()
    if not item:
        raise HTTPException(404, "License 不存在")
    if remark is not None:
        item.remark = remark
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="License", target_id=item.id,
           detail=f"license_id={item.id}", user=current_admin, request=request)
    return item


@router.delete("/{lid}")
def delete_license(
    lid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.MachineLicense).filter(models.MachineLicense.id == lid).first()
    if not item:
        raise HTTPException(404, "License 不存在")
    snapshot = f"file={item.file_name}"
    if item.file_path:
        try:
            p = _abs_path(item.file_path)
            if p.exists():
                p.unlink()
        except OSError:
            pass
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target="License", target_id=lid,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}


@router.get("/{lid}/download")
def download_license(
    lid: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    item = db.query(models.MachineLicense).filter(models.MachineLicense.id == lid).first()
    if not item or not item.file_path:
        raise HTTPException(404, "文件不存在")
    p = _abs_path(item.file_path)
    if not p.exists():
        raise HTTPException(404, "文件已丢失")
    return FileResponse(str(p), filename=item.file_name or os.path.basename(str(p)))
