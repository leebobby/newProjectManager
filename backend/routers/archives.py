"""整页存档：每周自动存一份，也可手工存；按对象/日期翻回去看。

构造与渲染收口在 [archives.py](../archives.py)，这里只管接口与权限。

权限分档（见 CLAUDE.md「Write-permission principle」）：
- **读**＝所有登录用户；
- **手工存一份**＝登录用户。存档是"填报动作"的一部分——大改之前先存一档的正是
  动手的那个人，要 admin 代存的话就没人会去存了；同一对象同一天覆盖，堆不出一摞；
- **删存档**＝仅 admin。删除权限按「删掉的是什么」定：这是别人回溯要用的历史，
  和客户面记录同一档，误删了补不回来。
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

import archives
import models
import schemas
from auth import get_current_user, require_admin
from database import get_db
from op_log import log_op

router = APIRouter(prefix="/api/archives", tags=["archives"])


def _label(kind: str) -> str:
    spec = archives.BUILDERS.get(kind)
    return spec[0] if spec else kind


def _out(s: models.PageSnapshot) -> schemas.PageSnapshotOut:
    return schemas.PageSnapshotOut(
        id=s.id, kind=s.kind, kind_label=_label(s.kind), ref_id=s.ref_id,
        label=s.label, title=s.title or "", reason=s.reason or "weekly",
        created_by=s.created_by or "", created_at=s.created_at,
    )


@router.get("/kinds")
def list_kinds():
    """可存档的页面类型。前端不要再写一份 kind→中文 的对照。"""
    return [{"kind": k, "label": v[0]} for k, v in archives.BUILDERS.items()]


@router.get("/targets", response_model=List[schemas.PageSnapshotTarget])
def list_targets(kind: str = Query("", description="留空＝全部类型"),
                 db: Session = Depends(get_db)):
    """有档的对象各一行（从存档表自己聚合，不去挨个表查在不在）。

    对象被删掉之后它的存档还在——这正是要能翻的情况，所以清单只认存档表。
    """
    q = (db.query(models.PageSnapshot.kind, models.PageSnapshot.ref_id,
                  func.count(models.PageSnapshot.id).label("n"),
                  func.max(models.PageSnapshot.label).label("latest"))
         .group_by(models.PageSnapshot.kind, models.PageSnapshot.ref_id))
    if kind:
        q = q.filter(models.PageSnapshot.kind == kind)
    out = []
    for k, ref, n, latest in q.all():
        # 标题取最近那一份档的：对象改过名的话，显示的是最新的叫法
        newest = (db.query(models.PageSnapshot)
                  .filter(models.PageSnapshot.kind == k, models.PageSnapshot.ref_id == ref)
                  .order_by(models.PageSnapshot.label.desc()).first())
        out.append(schemas.PageSnapshotTarget(
            kind=k, ref_id=ref, title=(newest.title if newest else "") or "",
            count=n, latest=latest or ""))
    out.sort(key=lambda t: (t.kind, t.title))
    return out


@router.get("", response_model=List[schemas.PageSnapshotOut])
def list_snapshots(
    kind: str = Query(""),
    ref_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(models.PageSnapshot)
    if kind:
        q = q.filter(models.PageSnapshot.kind == kind)
    if ref_id is not None:
        q = q.filter(models.PageSnapshot.ref_id == ref_id)
    rows = (q.order_by(models.PageSnapshot.label.desc(), models.PageSnapshot.id.desc())
            .limit(limit).all())
    return [_out(r) for r in rows]


@router.post("", response_model=schemas.PageSnapshotOut)
def create_snapshot(
    payload: schemas.PageSnapshotCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """手工存一份。同一对象同一天覆盖，不会越存越多。"""
    try:
        snap = archives.create_snapshot(
            db, payload.kind, payload.ref_id, reason="manual",
            created_by=(current_user.username or ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    if snap is None:
        raise HTTPException(404, "要存档的对象不存在")
    db.commit()
    db.refresh(snap)
    log_op(db, action="存档", target=f"{_label(payload.kind)}整页", target_id=payload.ref_id,
           detail=f"label={snap.label} title={snap.title}",
           user=current_user, request=request)
    return _out(snap)


def _get_or_404(db: Session, snap_id: int) -> models.PageSnapshot:
    snap = db.query(models.PageSnapshot).filter(models.PageSnapshot.id == snap_id).first()
    if snap is None:
        raise HTTPException(404, "存档不存在")
    return snap


# 注意：/kinds、/targets 必须注册在 /{snap_id} 之前，否则会被当成 id 解析成 422
# （同 specials 的 /overview、iteration_requirements 的 /duplicates）
@router.get("/{snap_id}/view", response_class=HTMLResponse)
def view_snapshot(snap_id: int, db: Session = Depends(get_db)):
    """一份存档渲染成 HTML。专项走的是周报那一份渲染，见 archives.py 开头。"""
    return HTMLResponse(archives.render_html(_get_or_404(db, snap_id)))


@router.get("/{snap_id}", response_model=schemas.PageSnapshotDetail)
def get_snapshot(snap_id: int, db: Session = Depends(get_db)):
    import json
    snap = _get_or_404(db, snap_id)
    try:
        payload = json.loads(snap.payload_json or "{}")
    except (TypeError, ValueError):
        payload = {}
    base = _out(snap)
    return schemas.PageSnapshotDetail(**base.model_dump(), payload=payload)


@router.delete("/{snap_id}")
def delete_snapshot(
    snap_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    snap = _get_or_404(db, snap_id)
    detail = f"kind={snap.kind} ref_id={snap.ref_id} label={snap.label} title={snap.title}"
    db.delete(snap)
    db.commit()
    log_op(db, action="删除", target="整页存档", target_id=snap_id,
           detail=detail, user=current_admin, request=request)
    return {"ok": True}
