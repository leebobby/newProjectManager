"""关键特性目录（全局）+ 机台多对多引用。

一张全局特性目录：交付状态六档＝点灯、需求度量（总SR/已验收/已转测）、责任人
（FO/特性SE）、简介、附件/链接、关联问题单特性。机台通过 machine_key_features
勾选引用；客户面状态总览据此点灯。协作编辑域；删除限 admin。附件文件落
backend/uploads/key_features/<id>/，走鉴权 blob 端点，不走静态目录。
"""
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

import models
import schemas
from auth import get_current_user, require_admin
from database import get_db
from op_log import log_op

router = APIRouter(prefix="/api/key-features", tags=["key-features"])

_UPLOAD_ROOT = Path(__file__).resolve().parent.parent / "uploads" / "key_features"
_STORED_RE = re.compile(r"^[0-9a-f]{32}(\.[A-Za-z0-9]{1,10})?$")   # uuid hex + 可选后缀


def _parse_attachments(raw: Optional[str]) -> List[Dict[str, Any]]:
    try:
        data = json.loads(raw or "[]")
        return data if isinstance(data, list) else []
    except (ValueError, TypeError):
        return []


def _serialize(row: models.KeyFeature, machine_ids: List[int] = None) -> Dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name or "",
        "status": row.status or "",
        "total_sr": row.total_sr or 0,
        "accepted_sr": row.accepted_sr or 0,
        "to_test_sr": row.to_test_sr or 0,
        "fo": row.fo or "",
        "se": row.se or "",
        "intro": row.intro or "",
        "issue_feature": row.issue_feature or "",
        "attachments": _parse_attachments(row.attachments_json),
        "sort_order": row.sort_order or 0,
        "version": row.version,
        "updated_at": row.updated_at,
        "machine_ids": machine_ids or [],
    }


def _machine_ids_map(db: Session, feature_ids: List[int]) -> Dict[int, List[int]]:
    """批量取每个特性被哪些机台引用。"""
    if not feature_ids:
        return {}
    rows = (
        db.query(models.MachineKeyFeature)
        .filter(models.MachineKeyFeature.feature_id.in_(feature_ids))
        .all()
    )
    out: Dict[int, List[int]] = {}
    for r in rows:
        out.setdefault(r.feature_id, []).append(r.machine_status_id)
    return out


def _get_feature(db: Session, fid: int) -> models.KeyFeature:
    row = db.query(models.KeyFeature).filter(models.KeyFeature.id == fid).first()
    if not row:
        raise HTTPException(status_code=404, detail="特性不存在")
    return row


@router.get("", response_model=List[schemas.KeyFeatureOut])
def list_items(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    rows = (
        db.query(models.KeyFeature)
        .order_by(models.KeyFeature.sort_order, models.KeyFeature.id)
        .all()
    )
    mmap = _machine_ids_map(db, [r.id for r in rows])
    return [_serialize(r, mmap.get(r.id, [])) for r in rows]


@router.get("/by-machine")
def by_machine(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    """{machine_status_id(str): [关键特性...]}，供客户面总览点灯。"""
    links = db.query(models.MachineKeyFeature).all()
    if not links:
        return {}
    feats = {
        f.id: f for f in db.query(models.KeyFeature)
        .filter(models.KeyFeature.id.in_({l.feature_id for l in links})).all()
    }
    out: Dict[str, List[Dict[str, Any]]] = {}
    for l in links:
        f = feats.get(l.feature_id)
        if f is None:
            continue
        out.setdefault(str(l.machine_status_id), []).append({
            "id": f.id, "name": f.name or "", "status": f.status or "",
        })
    for lst in out.values():
        lst.sort(key=lambda d: d["name"])
    return out


@router.post("", response_model=schemas.KeyFeatureOut)
def create_item(
    payload: schemas.KeyFeatureCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    data = payload.model_dump()
    if data.get("sort_order") in (None, 0):
        last = db.query(models.KeyFeature).order_by(models.KeyFeature.sort_order.desc()).first()
        data["sort_order"] = ((last.sort_order or 0) + 1) if last else 1
    item = models.KeyFeature(**data)
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target="关键特性", target_id=item.id,
           detail=f"name={(item.name or '')[:40]} status={item.status}",
           user=current_user, request=request)
    return _serialize(item)


@router.put("/{item_id}", response_model=schemas.KeyFeatureOut)
def update_item(
    item_id: int,
    payload: schemas.KeyFeatureUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = _get_feature(db, item_id)
    if item.version != payload.version:
        raise HTTPException(status_code=409, detail="数据已被他人修改，请刷新后重试")
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("version", None)
    for k, v in changes.items():
        setattr(item, k, v)
    item.version += 1
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="关键特性", target_id=item.id,
           detail=f"fields={','.join(changes.keys()) or '无'}",
           user=current_user, request=request)
    mmap = _machine_ids_map(db, [item.id])
    return _serialize(item, mmap.get(item.id, []))


@router.delete("/{item_id}")
def delete_item(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = _get_feature(db, item_id)
    snapshot = f"name={(item.name or '')[:40]}"
    # 删掉磁盘附件
    d = _UPLOAD_ROOT / str(item_id)
    if d.exists():
        for f in d.glob("*"):
            try:
                f.unlink()
            except OSError:
                pass
    db.delete(item)   # 关联行 CASCADE
    db.commit()
    log_op(db, action="删除", target="关键特性", target_id=item_id,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}


# ── 机台关联（多对多）─────────────────────────────────
@router.put("/machine/{machine_status_id}")
def set_machine_features(
    machine_status_id: int,
    payload: schemas.MachineFeatureSet,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """整体替换某机台勾选的关键特性集合。"""
    machine = (
        db.query(models.CustomerStatus)
        .filter(models.CustomerStatus.id == machine_status_id)
        .first()
    )
    if not machine:
        raise HTTPException(status_code=404, detail="机台不存在")
    want = set(payload.feature_ids or [])
    # 校验特性存在
    if want:
        valid = {f.id for f in db.query(models.KeyFeature.id).filter(models.KeyFeature.id.in_(want)).all()}
        want = {fid for fid in want if fid in valid}
    have = {
        l.feature_id: l for l in db.query(models.MachineKeyFeature)
        .filter(models.MachineKeyFeature.machine_status_id == machine_status_id).all()
    }
    for fid in want - set(have):
        db.add(models.MachineKeyFeature(machine_status_id=machine_status_id, feature_id=fid))
    for fid in set(have) - want:
        db.delete(have[fid])
    db.commit()
    log_op(db, action="修改", target="机台关键特性", target_id=machine_status_id,
           detail=f"machine={machine.machine_id} features={sorted(want)}",
           user=current_user, request=request)
    return {"machine_status_id": machine_status_id, "feature_ids": sorted(want)}


# ── 附件 / 链接 ───────────────────────────────────────
def _save_attachments(db: Session, item: models.KeyFeature, atts: List[Dict[str, Any]]) -> None:
    item.attachments_json = json.dumps(atts, ensure_ascii=False)
    db.commit()


@router.post("/{item_id}/attachments")
async def upload_attachment(
    item_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = _get_feature(db, item_id)
    ext = Path(file.filename or "").suffix.lower()[:10]
    stored = uuid.uuid4().hex + ext
    d = _UPLOAD_ROOT / str(item_id)
    d.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    (d / stored).write_bytes(content)
    atts = _parse_attachments(item.attachments_json)
    entry = {"id": uuid.uuid4().hex, "kind": "file", "name": file.filename or stored,
             "stored": stored, "size": len(content)}
    atts.append(entry)
    _save_attachments(db, item, atts)
    log_op(db, action="上传附件", target="关键特性", target_id=item_id,
           detail=f"file={file.filename}", user=current_user, request=request)
    return {"attachments": atts}


@router.post("/{item_id}/links")
def add_link(
    item_id: int,
    request: Request,
    name: str = Form(""),
    url: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = _get_feature(db, item_id)
    if not url.strip():
        raise HTTPException(status_code=400, detail="链接不能为空")
    atts = _parse_attachments(item.attachments_json)
    atts.append({"id": uuid.uuid4().hex, "kind": "link",
                 "name": (name.strip() or url.strip()), "url": url.strip()})
    _save_attachments(db, item, atts)
    return {"attachments": atts}


@router.get("/{item_id}/attachments/{stored}")
def download_attachment(
    item_id: int, stored: str,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    if not _STORED_RE.match(stored):
        raise HTTPException(status_code=400, detail="非法文件名")
    fp = _UPLOAD_ROOT / str(item_id) / stored
    if not fp.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    item = _get_feature(db, item_id)
    name = next((a.get("name") for a in _parse_attachments(item.attachments_json)
                 if a.get("stored") == stored), stored)
    return FileResponse(str(fp), filename=name)


@router.delete("/{item_id}/attachments/{att_id}")
def delete_attachment(
    item_id: int, att_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = _get_feature(db, item_id)
    atts = _parse_attachments(item.attachments_json)
    target = next((a for a in atts if a.get("id") == att_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="附件不存在")
    if target.get("kind") == "file" and target.get("stored"):
        fp = _UPLOAD_ROOT / str(item_id) / target["stored"]
        try:
            fp.unlink()
        except OSError:
            pass
    atts = [a for a in atts if a.get("id") != att_id]
    _save_attachments(db, item, atts)
    return {"attachments": atts}
