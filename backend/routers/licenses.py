"""机台授权信息、文件版本和历史下载。读需登录，所有写入仅 admin。"""
import json
import pathlib
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session, joinedload

import models
import revisions
import schemas
from auth import get_current_user, require_admin
from database import get_db
from license_options import validate_choice
from op_log import log_op

router = APIRouter(prefix="/api/licenses", tags=["licenses"])
UPLOAD_ROOT = pathlib.Path(__file__).resolve().parent.parent / "uploads" / "licenses"


def _abs_path(rel: str) -> pathlib.Path:
    path = (UPLOAD_ROOT.parent / rel).resolve()
    if not path.is_relative_to(UPLOAD_ROOT.resolve()):
        raise HTTPException(404, "文件路径无效")
    return path


def _save_upload(upload, machine_id):
    target = UPLOAD_ROOT / str(machine_id)
    target.mkdir(parents=True, exist_ok=True)
    name = (upload.filename or "license.bin").replace('\\', '/').rsplit('/', 1)[-1][:256]
    stored = uuid.uuid4().hex + pathlib.Path(name).suffix[:16]
    path = target / stored
    try:
        with path.open('wb') as stream:
            while chunk := upload.file.read(64 * 1024):
                stream.write(chunk)
        return f"licenses/{machine_id}/{stored}", name, path.stat().st_size
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _item(db, lid):
    item = db.query(models.MachineLicense).filter_by(id=lid).first()
    if not item:
        raise HTTPException(404, "License 不存在")
    return item


def _snapshot(item):
    return dict(model=item.machine_status.model or '', tool_id=item.tool_id, uuid=item.uuid,
                throughput_package=item.throughput_package, algorithm=item.algorithm,
                optional_features=json.loads(item.optional_features_json or '[]'), remark=item.remark or '')


def _out(item):
    return dict(_snapshot(item), id=item.id, machine_status_id=item.machine_status_id,
                machine_version=item.machine_status.version, version=item.version,
                file_version=item.file_version, file_name=item.file_name, file_size=item.file_size,
                uploaded_by=item.uploaded_by, uploaded_at=item.uploaded_at, created_at=item.created_at)


def _values(payload, old=None):
    values = payload.model_dump(exclude_unset=True, exclude={'version', 'machine_status_id'})
    for key, option_key in (('throughput_package', 'license_throughput_packages'), ('algorithm', 'license_algorithms')):
        if key in values:
            values[key] = validate_choice(option_key, values[key], getattr(old, key, ''))
    if 'optional_features' in values:
        previous = json.loads(old.optional_features_json or '[]') if old else []
        choices = list(dict.fromkeys(v.strip() for v in values.pop('optional_features')))
        for value in choices:
            validate_choice('license_optional_features', value, value if value in previous else '')
        values['optional_features_json'] = json.dumps([v for v in choices if v], ensure_ascii=False)
    for key in ('tool_id', 'uuid'):
        if key in values:
            values[key] = values[key].strip()
    return values


def _claim(db, item, expected):
    """条件更新先拿写锁，避免两次上传都通过内存中的 version 检查。"""
    count = db.query(models.MachineLicense).filter_by(id=item.id, version=expected).update(
        {'version': expected + 1}, synchronize_session=False)
    if not count:
        db.rollback()
        raise HTTPException(409, "数据已被他人修改，请刷新后重试")
    item.version = expected + 1


def _attach(db, item, file, user, note):
    rel, name, size = _save_upload(file, item.machine_status_id)
    try:
        item.file_name, item.file_path, item.file_size = name, rel, size
        item.uploaded_by, item.uploaded_at = user.username or '', datetime.utcnow()
        item.file_version += 1
        db.add(models.MachineLicenseFile(license_id=item.id, file_version=item.file_version,
            file_name=name, file_path=rel, file_size=size, note=note or '',
            uploaded_by=item.uploaded_by, uploaded_at=item.uploaded_at,
            snapshot_json=json.dumps(_snapshot(item), ensure_ascii=False)))
        return rel
    except Exception:
        _cleanup(rel)
        raise


def _cleanup(rel):
    if rel:
        _abs_path(rel).unlink(missing_ok=True)


@router.get('', response_model=List[schemas.MachineLicenseOut])
def list_licenses(machine_status_id: int, db: Session = Depends(get_db),
                  _: models.User = Depends(get_current_user)):
    rows = db.query(models.MachineLicense).options(joinedload(models.MachineLicense.machine_status)).filter_by(
        machine_status_id=machine_status_id).order_by(models.MachineLicense.id.desc()).all()
    return [_out(item) for item in rows]


@router.post('', response_model=schemas.MachineLicenseOut)
def create_license(request: Request, machine_status_id: int = Form(...), remark: str = Form(''),
                   metadata: str = Form('{}'), file: Optional[UploadFile] = File(None),
                   db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    machine = db.get(models.CustomerStatus, machine_status_id)
    if not machine:
        raise HTTPException(404, '机台不存在')
    try:
        payload = schemas.MachineLicenseWrite.model_validate_json(metadata)
    except ValidationError as exc:
        raise HTTPException(422, '授权信息格式无效') from exc
    values = _values(payload)
    values.setdefault('remark', remark)
    item = models.MachineLicense(machine_status=machine, file_name='', file_path='',
                                  file_size=0, file_version=0, **values)
    db.add(item)
    rel = None
    try:
        db.flush()
        if file and file.filename:
            rel = _attach(db, item, file, admin, remark)
        db.commit()
    except Exception:
        db.rollback()
        _cleanup(rel)
        raise
    db.refresh(item)
    log_op(db, action='新增', target='License', target_id=item.id,
           detail=f'machine={machine.machine_id}', user=admin, request=request)
    return _out(item)


@router.put('/{lid}', response_model=schemas.MachineLicenseOut)
def update_license(lid: int, payload: schemas.MachineLicenseUpdate, request: Request,
                   db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    item = _item(db, lid)
    values = _values(payload, item)
    before = revisions.snapshot(item)
    _claim(db, item, payload.version)
    for key, value in values.items():
        setattr(item, key, value)
    revisions.record(db, item, before, user=admin)
    db.commit()
    db.refresh(item)
    log_op(db, action='修改', target='License', target_id=lid,
           detail='fields=' + ','.join(values), user=admin, request=request)
    return _out(item)


@router.post('/{lid}/files', response_model=schemas.MachineLicenseOut)
def upload_version(lid: int, request: Request, version: int = Form(...), note: str = Form(''),
                   file: UploadFile = File(...), db: Session = Depends(get_db),
                   admin: models.User = Depends(require_admin)):
    item = _item(db, lid)
    if not file.filename:
        raise HTTPException(400, '必须上传文件')
    before = revisions.snapshot(item)
    _claim(db, item, version)
    rel = None
    try:
        rel = _attach(db, item, file, admin, note)
        revisions.record(db, item, before, user=admin)
        db.commit()
    except Exception:
        db.rollback()
        _cleanup(rel)
        raise
    db.refresh(item)
    log_op(db, action='上传', target='License', target_id=lid,
           detail=f'file_version={item.file_version}', user=admin, request=request)
    return _out(item)


@router.get('/{lid}/files', response_model=List[schemas.MachineLicenseFileOut])
def list_files(lid: int, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    item = _item(db, lid)
    return [dict(id=f.id, file_version=f.file_version, file_name=f.file_name, file_size=f.file_size,
                 uploaded_by=f.uploaded_by or '', uploaded_at=f.uploaded_at, note=f.note or '',
                 snapshot=json.loads(f.snapshot_json)) for f in item.files]


def _download(path, name):
    full = _abs_path(path)
    if not path or not full.is_file():
        raise HTTPException(404, '文件不存在或已丢失')
    return FileResponse(full, filename=name)


@router.get('/{lid}/files/{fid}/download')
def download_history(lid: int, fid: int, db: Session = Depends(get_db),
                     _: models.User = Depends(get_current_user)):
    row = db.query(models.MachineLicenseFile).filter_by(id=fid, license_id=lid).first()
    if not row:
        raise HTTPException(404, '历史文件不存在')
    return _download(row.file_path, row.file_name)


@router.get('/{lid}/download')
def download_license(lid: int, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    item = _item(db, lid)
    return _download(item.file_path, item.file_name)


@router.delete('/{lid}')
def delete_license(lid: int, request: Request, db: Session = Depends(get_db),
                   admin: models.User = Depends(require_admin)):
    item = _item(db, lid)
    paths = {f.file_path for f in item.files} | {item.file_path}
    revisions.record_delete(db, item, user=admin)
    db.delete(item)
    db.commit()
    for path in paths:
        try:
            _cleanup(path)
        except OSError:
            pass
    log_op(db, action='删除', target='License', target_id=lid,
           detail='删除授权及其文件版本', user=admin, request=request)
    return {'ok': True}
