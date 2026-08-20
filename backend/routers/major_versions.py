"""版本管理：大版本 → 版本 → 迭代版本 三层。

  major_versions      大版本    C10SPC100        号段，不发布，只有规划区间与主干/分支状态
    └ release_versions  版本    C10SPC101/102    真正对外发布的一级
        └ iteration_versions 迭代版本 C10SPC101B001  构建，DTS 问题单的「版本信息」落在这层

哪一层给谁用（改口径前先看这张表，改错了各页面对不上）：
- 客户面（现场版本、定制化需求的预计合入版本）→ **版本**
- 迭代管理（领域/产品需求的计划交付版本）、问题单 → **迭代版本**
- 版本达成率（metrics）→ **版本**

写权限：三层都是主数据/配置类，一律 admin（见 CLAUDE.md「Write-permission principle」）。
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, joinedload

import models
import schemas
from auth import require_admin
from database import get_db
from op_log import log_op
from notify import broadcast

router = APIRouter(prefix="/api", tags=["versions"])

# 触发「版本计划变更」广播的字段（计划相关；纯文字描述/排序不广播）
_PLAN_FIELDS = {"version_no", "title", "range_start", "range_end", "actual_release_date",
                "planned_date"}


def _get_release(db: Session, rv_id: int) -> models.ReleaseVersion:
    rv = db.query(models.ReleaseVersion).filter(models.ReleaseVersion.id == rv_id).first()
    if not rv:
        raise HTTPException(status_code=404, detail="版本不存在")
    return rv


def _sync_major_id(db: Session, iv: models.IterationVersion) -> None:
    """迭代版本的 major_version_id 是冗余列，永远从父版本推导，不收客户端的值。"""
    rv = _get_release(db, iv.release_version_id)
    iv.major_version_id = rv.major_version_id


# ─── 大版本 ──────────────────────────────────────────────────────────────────
@router.get("/major-versions", response_model=List[schemas.MajorVersionDetailOut])
def list_major_versions(project_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(models.MajorVersion).options(
        joinedload(models.MajorVersion.release_versions)
        .joinedload(models.ReleaseVersion.iteration_versions)
    )
    if project_id is not None:
        q = q.filter(models.MajorVersion.project_id == project_id)
    else:
        q = q.filter(models.MajorVersion.project_id.is_(None))
    return q.order_by(models.MajorVersion.sort_order).all()


@router.post("/major-versions", response_model=schemas.MajorVersionDetailOut)
def create_major_version(
    payload: schemas.MajorVersionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    data = payload.model_dump()
    # 新建的大版本默认是分支：主干只能显式切换，否则一建就冒出第二个主干
    item = models.MajorVersion(**data, line="branch")
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target="大版本", target_id=item.id,
           detail=f"version_no={item.version_no}",
           user=current_admin, request=request)
    broadcast(
        db, kind="version_plan",
        title=f"新增版本计划：{item.version_no}{(' ' + item.title) if item.title else ''}",
        body="", link="/roadmaps", actor=current_admin,
    )
    return item


@router.put("/major-versions/{item_id}", response_model=schemas.MajorVersionDetailOut)
def update_major_version(
    item_id: int,
    payload: schemas.MajorVersionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.MajorVersion).filter(models.MajorVersion.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="大版本", target_id=item.id,
           detail=f"version_no={item.version_no} fields={','.join(changes.keys()) or '无'}",
           user=current_admin, request=request)
    plan_changed = sorted(set(changes.keys()) & _PLAN_FIELDS)
    if plan_changed:
        broadcast(
            db, kind="version_plan",
            title=f"版本计划变更：{item.version_no}{(' ' + item.title) if item.title else ''}",
            body=f"变更字段：{'、'.join(plan_changed)}",
            link="/roadmaps", actor=current_admin,
        )
    return item


@router.post("/major-versions/{item_id}/set-master", response_model=schemas.MajorVersionDetailOut)
def set_master(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    """把某个大版本设为主干，同项目内原来的主干自动降为分支并盖上 branched_at。

    降级与升级必须在同一个事务里做完——拆成两个开关让人手点，迟早出现两个主干
    或零个主干，而且页面上看着都正常，没人会当 bug 报。
    """
    from datetime import datetime as _dt

    item = db.query(models.MajorVersion).filter(models.MajorVersion.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    if item.line == "master":
        return item

    demoted = []
    q = db.query(models.MajorVersion).filter(
        models.MajorVersion.line == "master", models.MajorVersion.id != item.id)
    # project_id 可能为 None（未挂项目的大版本自成一档），is_() 与 == 不能混用
    q = q.filter(models.MajorVersion.project_id.is_(None) if item.project_id is None
                 else models.MajorVersion.project_id == item.project_id)
    for old in q.all():
        old.line = "branch"
        old.branched_at = _dt.utcnow()
        if not (old.branch_name or "").strip():
            old.branch_name = f"release/{old.version_no}"
        demoted.append(old.version_no)

    item.line = "master"
    item.branch_name = ""
    item.branched_at = None
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="大版本", target_id=item.id,
           detail=f"set_master version_no={item.version_no} demoted={','.join(demoted) or '无'}",
           user=current_admin, request=request)
    if demoted:
        broadcast(
            db, kind="version_plan",
            title=f"主干切换：{item.version_no} 接管主干",
            body=f"{'、'.join(demoted)} 已拉为分支",
            link="/versions", actor=current_admin,
        )
    return item


@router.delete("/major-versions/{item_id}")
def delete_major_version(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.MajorVersion).filter(models.MajorVersion.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    snapshot = f"version_no={item.version_no}"
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target="大版本", target_id=item_id,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}


# ─── 版本 ────────────────────────────────────────────────────────────────────
@router.post("/release-versions", response_model=schemas.ReleaseVersionDetailOut)
def create_release_version(
    payload: schemas.ReleaseVersionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    mv = db.query(models.MajorVersion).filter(
        models.MajorVersion.id == payload.major_version_id).first()
    if not mv:
        raise HTTPException(status_code=404, detail="大版本不存在")
    item = models.ReleaseVersion(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target="版本", target_id=item.id,
           detail=f"version_no={item.version_no} major_id={item.major_version_id}",
           user=current_admin, request=request)
    broadcast(
        db, kind="version_plan",
        title=f"新增版本：{item.version_no}{(' ' + item.title) if item.title else ''}",
        body=f"所属大版本 {mv.version_no}", link="/versions", actor=current_admin,
    )
    return item


@router.put("/release-versions/{item_id}", response_model=schemas.ReleaseVersionDetailOut)
def update_release_version(
    item_id: int,
    payload: schemas.ReleaseVersionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = _get_release(db, item_id)
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(item, k, v)
    db.flush()
    if "major_version_id" in changes:
        # 改挂父级时把下面所有构建的冗余列一起搬走，否则指标会按旧大版本聚合
        for iv in item.iteration_versions:
            iv.major_version_id = item.major_version_id
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="版本", target_id=item.id,
           detail=f"version_no={item.version_no} fields={','.join(changes.keys()) or '无'}",
           user=current_admin, request=request)
    plan_changed = sorted(set(changes.keys()) & _PLAN_FIELDS)
    if plan_changed:
        broadcast(
            db, kind="version_plan",
            title=f"版本计划变更：{item.version_no}{(' ' + item.title) if item.title else ''}",
            body=f"变更字段：{'、'.join(plan_changed)}",
            link="/versions", actor=current_admin,
        )
    return item


@router.delete("/release-versions/{item_id}")
def delete_release_version(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = _get_release(db, item_id)
    snapshot = f"version_no={item.version_no} iterations={len(item.iteration_versions)}"
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target="版本", target_id=item_id,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}


@router.get("/release-versions/all")
def list_all_release_versions(db: Session = Depends(get_db)):
    """所有版本的扁平列表 —— 客户面（现场版本 / 预计合入版本）的下拉数据源。"""
    items = (
        db.query(models.ReleaseVersion)
        .options(joinedload(models.ReleaseVersion.major_version)
                 .joinedload(models.MajorVersion.project))
        .order_by(models.ReleaseVersion.major_version_id, models.ReleaseVersion.sort_order)
        .all()
    )
    out = []
    for rv in items:
        mv = rv.major_version
        out.append({
            "id": rv.id,
            "version_no": rv.version_no,
            "title": rv.title,
            "planned_date": rv.planned_date,
            "actual_release_date": rv.actual_release_date,
            "major_version_id": rv.major_version_id,
            "major_version_no": mv.version_no if mv else "",
            "major_line": mv.line if mv else "",
            "project_id": mv.project_id if mv else None,
            "project_name": mv.project.name if mv and mv.project else "",
        })
    return out


# ─── 迭代版本 ────────────────────────────────────────────────────────────────
@router.post("/iteration-versions", response_model=schemas.IterationVersionOut)
def create_iteration_version(
    payload: schemas.IterationVersionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = models.IterationVersion(**payload.model_dump())
    _sync_major_id(db, item)
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target="迭代版本", target_id=item.id,
           detail=f"version_no={item.version_no} release_id={item.release_version_id}",
           user=current_admin, request=request)
    return item


@router.put("/iteration-versions/{item_id}", response_model=schemas.IterationVersionOut)
def update_iteration_version(
    item_id: int,
    payload: schemas.IterationVersionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.IterationVersion).filter(models.IterationVersion.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(item, k, v)
    if "release_version_id" in changes:
        _sync_major_id(db, item)
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="迭代版本", target_id=item.id,
           detail=f"version_no={item.version_no} fields={','.join(changes.keys()) or '无'}",
           user=current_admin, request=request)
    return item


@router.delete("/iteration-versions/{item_id}")
def delete_iteration_version(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.IterationVersion).filter(models.IterationVersion.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    snapshot = f"version_no={item.version_no}"
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target="迭代版本", target_id=item_id,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}


@router.get("/iteration-versions/all")
def list_all_iteration_versions(db: Session = Depends(get_db)):
    """所有迭代版本的扁平列表 —— 迭代管理「计划交付版本」下拉的数据源。"""
    items = (
        db.query(models.IterationVersion)
        .options(
            joinedload(models.IterationVersion.release_version)
            .joinedload(models.ReleaseVersion.major_version)
            .joinedload(models.MajorVersion.project)
        )
        .order_by(models.IterationVersion.major_version_id, models.IterationVersion.sort_order)
        .all()
    )
    result = []
    for it in items:
        rv = it.release_version
        mv = rv.major_version if rv else None
        result.append({
            "id": it.id,
            "release_version_id": it.release_version_id,
            "release_version_no": rv.version_no if rv else "",
            "release_version_title": rv.title if rv else "",
            "major_version_id": it.major_version_id,
            "major_version_no": mv.version_no if mv else "",
            "major_version_title": mv.title if mv else "",
            "project_id": mv.project_id if mv else None,
            "project_name": mv.project.name if mv and mv.project else "",
            "version_no": it.version_no,
            "title": it.title,
            "planned_date": it.planned_date,
        })
    return result
