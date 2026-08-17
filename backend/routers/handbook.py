"""项目一本通：分类 + 条目 + 文件上传/下载。

权限：
- GET 全部：所有登录用户
- POST/PUT/DELETE：仅 admin
"""
import os
import pathlib
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

import models
import schemas
from auth import require_admin
from database import get_db
from op_log import log_op

router = APIRouter(prefix="/api/handbook", tags=["handbook"])

UPLOAD_ROOT = pathlib.Path(__file__).resolve().parent.parent / "uploads" / "handbook"


def _ensure_dir(p: pathlib.Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _save_upload(upload: UploadFile) -> tuple[str, str, int]:
    """保存上传文件，返回 (相对路径, 原文件名, 字节数)。相对路径以 uploads/ 为根。"""
    ym = datetime.now().strftime("%Y%m")
    target_dir = UPLOAD_ROOT / ym
    _ensure_dir(target_dir)
    orig_name = upload.filename or "upload.bin"
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
    rel = f"handbook/{ym}/{stored}"
    return rel, orig_name, size


def _abs_path(rel: str) -> pathlib.Path:
    """rel 形如 'handbook/202605/xxx.pdf'，落到 backend/uploads/<rel>。"""
    base = UPLOAD_ROOT.parent
    return (base / rel).resolve()


# ─── Categories ─────────────────────────────────────────────────────

@router.get("/categories", response_model=List[schemas.HandbookCategoryOut])
def list_categories(db: Session = Depends(get_db)):
    return (
        db.query(models.HandbookCategory)
        .order_by(models.HandbookCategory.sort_order, models.HandbookCategory.id)
        .all()
    )


@router.post("/categories", response_model=schemas.HandbookCategoryOut)
def create_category(
    payload: schemas.HandbookCategoryCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    sort_order = payload.sort_order
    if sort_order is None:
        sort_order = db.query(models.HandbookCategory).count()
    item = models.HandbookCategory(name=payload.name, sort_order=sort_order)
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target="一本通分类", target_id=item.id,
           detail=f"name={item.name}", user=current_admin, request=request)
    return item


@router.put("/categories/{cid}", response_model=schemas.HandbookCategoryOut)
def update_category(
    cid: int,
    payload: schemas.HandbookCategoryUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.HandbookCategory).filter(models.HandbookCategory.id == cid).first()
    if not item:
        raise HTTPException(404, "分类不存在")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="一本通分类", target_id=item.id,
           detail=f"name={item.name}", user=current_admin, request=request)
    return item


@router.delete("/categories/{cid}")
def delete_category(
    cid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.HandbookCategory).filter(models.HandbookCategory.id == cid).first()
    if not item:
        raise HTTPException(404, "分类不存在")
    snapshot = f"name={item.name}"
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target="一本通分类", target_id=cid,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}


# ─── Items ─────────────────────────────────────────────────────────

@router.post("/items", response_model=schemas.HandbookItemOut)
def create_item(
    request: Request,
    category_id: int = Form(...),
    title: str = Form(...),
    kind: str = Form("link"),
    url: str = Form(""),
    description: str = Form(""),
    owner: str = Form(""),
    sort_order: int = Form(0),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    cat = db.query(models.HandbookCategory).filter(models.HandbookCategory.id == category_id).first()
    if not cat:
        raise HTTPException(404, "分类不存在")
    if kind not in ("link", "file"):
        raise HTTPException(400, "kind 仅支持 link / file")

    file_path = ""
    file_name = ""
    file_size = 0
    if kind == "file":
        if not file or not file.filename:
            raise HTTPException(400, "上传文件类型必须附带文件")
        file_path, file_name, file_size = _save_upload(file)
    elif kind == "link":
        if not url.strip():
            raise HTTPException(400, "外链类型必须提供 URL")

    from routers._lookups import resolve_user_id
    item = models.HandbookItem(
        category_id=category_id,
        title=title,
        kind=kind,
        url=url.strip(),
        file_path=file_path,
        file_name=file_name,
        file_size=file_size,
        description=description,
        owner=owner,
        owner_user_id=resolve_user_id(db, owner),
        sort_order=sort_order,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target="一本通条目", target_id=item.id,
           detail=f"title={item.title} kind={item.kind}",
           user=current_admin, request=request)
    return item


@router.put("/items/{iid}", response_model=schemas.HandbookItemOut)
def update_item(
    iid: int,
    request: Request,
    title: str | None = Form(None),
    category_id: int | None = Form(None),
    kind: str | None = Form(None),
    url: str | None = Form(None),
    description: str | None = Form(None),
    owner: str | None = Form(None),
    sort_order: int | None = Form(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.HandbookItem).filter(models.HandbookItem.id == iid).first()
    if not item:
        raise HTTPException(404, "条目不存在")

    if title is not None: item.title = title
    if category_id is not None: item.category_id = category_id
    if description is not None: item.description = description
    if owner is not None:
        from routers._lookups import resolve_user_id
        item.owner = owner
        item.owner_user_id = resolve_user_id(db, owner)
    if sort_order is not None: item.sort_order = sort_order

    new_kind = kind or item.kind
    if new_kind not in ("link", "file"):
        raise HTTPException(400, "kind 仅支持 link / file")
    item.kind = new_kind

    if new_kind == "link":
        if url is not None:
            item.url = url.strip()
        # 切到 link 时清掉文件信息
        if item.file_path:
            old = _abs_path(item.file_path)
            try:
                if old.exists(): old.unlink()
            except OSError:
                pass
        item.file_path = ""
        item.file_name = ""
        item.file_size = 0
    else:  # file
        if file and file.filename:
            # 替换文件：删旧
            if item.file_path:
                old = _abs_path(item.file_path)
                try:
                    if old.exists(): old.unlink()
                except OSError:
                    pass
            fp, fn, fs = _save_upload(file)
            item.file_path = fp
            item.file_name = fn
            item.file_size = fs
        if url is not None:
            item.url = url.strip()  # 允许同时记录预览链接

    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="一本通条目", target_id=item.id,
           detail=f"title={item.title}", user=current_admin, request=request)
    return item


@router.delete("/items/{iid}")
def delete_item(
    iid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.HandbookItem).filter(models.HandbookItem.id == iid).first()
    if not item:
        raise HTTPException(404, "条目不存在")
    snapshot = f"title={item.title}"
    if item.file_path:
        try:
            p = _abs_path(item.file_path)
            if p.exists(): p.unlink()
        except OSError:
            pass
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target="一本通条目", target_id=iid,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}


@router.get("/items/{iid}/download")
def download_item(iid: int, db: Session = Depends(get_db)):
    item = db.query(models.HandbookItem).filter(models.HandbookItem.id == iid).first()
    if not item or item.kind != "file" or not item.file_path:
        raise HTTPException(404, "文件不存在")
    p = _abs_path(item.file_path)
    if not p.exists():
        raise HTTPException(404, "文件已丢失")
    return FileResponse(str(p), filename=item.file_name or os.path.basename(str(p)))
