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
from datetime import date
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


def _is_released(actual_release_date) -> bool:
    """「已发布」＝填了实际发布日期**并且那天已经过了**。

    判定放服务端而不是各页面自己比日期：`actual_release_date` 是用户填的本地日期
    （不做时区转换，见 CLAUDE.md「时间」），前端各写一遍 `new Date()` 比较，
    跨时区或跨零点时两个页面会给出不同答案，而两边看着都对。

    取「日子过了」而不是「填了就算」：发版计划确定后就会先把日期填上，
    那之前这个版本还在收需求，不该从「计划交付版本」下拉里消失。
    """
    if not actual_release_date:
        return False
    d = actual_release_date
    return (d.date() if hasattr(d, "date") else d) <= date.today()


def _get_release(db: Session, rv_id: int) -> models.ReleaseVersion:
    rv = db.query(models.ReleaseVersion).filter(models.ReleaseVersion.id == rv_id).first()
    if not rv:
        raise HTTPException(status_code=404, detail="版本不存在")
    return rv


def _reorder(db: Session, model, parent_col, parent_id: Optional[int],
             ids: List[int]) -> int:
    """按 ids 的先后重写同一父级下的 sort_order。

    整体重排而不是逐个 PUT：后者在中途被打断就留下「排到一半」的顺序，而顺序错了
    没有任何报错，只是看着不对。ids 里混进别的父级的行直接 400——那多半是前端把
    两个分组的列表拼错了，静默忽略只会让人以为排序功能时灵时不灵。
    列表里没提到的兄弟节点排在后面，这样别人刚新增的行不会因为你的列表是旧的而被挤乱。
    """
    q = db.query(model).filter(parent_col.is_(None) if parent_id is None
                               else parent_col == parent_id)
    rows = {r.id: r for r in q.all()}
    unknown = [i for i in ids if i not in rows]
    if unknown:
        raise HTTPException(status_code=400, detail=f"这些 id 不属于该父级：{unknown}")
    order = list(dict.fromkeys(ids))                       # 去重，保留首次出现的位置
    order += [i for i in sorted(rows, key=lambda k: (rows[k].sort_order or 0, k))
              if i not in set(order)]
    for idx, rid in enumerate(order):
        rows[rid].sort_order = idx
    db.commit()
    return len(order)


def _tail_sort_order(db: Session, model, parent_col, parent_id: Optional[int]) -> int:
    """新父级下的末位序号。改挂父级时用它，否则那一行会带着旧序号插进中间。"""
    q = db.query(model).filter(parent_col.is_(None) if parent_id is None
                               else parent_col == parent_id)
    return max([r.sort_order or 0 for r in q.all()] or [-1]) + 1


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


@router.post("/major-versions/reorder")
def reorder_major_versions(
    payload: schemas.VersionReorderIn,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    """重排某个里程碑项目下的大版本。parent_id＝project_id（空＝未挂项目的那批）。"""
    n = _reorder(db, models.MajorVersion, models.MajorVersion.project_id,
                 payload.parent_id, payload.ids)
    log_op(db, action="修改", target="大版本", target_id=payload.parent_id or 0,
           detail=f"reorder project_id={payload.parent_id} count={n}",
           user=current_admin, request=request)
    return {"ok": True, "count": n}


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


@router.post("/release-versions/reorder")
def reorder_release_versions(
    payload: schemas.VersionReorderIn,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    """重排某个大版本下的版本。parent_id＝major_version_id。"""
    n = _reorder(db, models.ReleaseVersion, models.ReleaseVersion.major_version_id,
                 payload.parent_id, payload.ids)
    log_op(db, action="修改", target="版本", target_id=payload.parent_id or 0,
           detail=f"reorder major_id={payload.parent_id} count={n}",
           user=current_admin, request=request)
    return {"ok": True, "count": n}


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
    moved = ("major_version_id" in changes
             and changes["major_version_id"] != item.major_version_id)
    if moved and not db.query(models.MajorVersion).filter(
            models.MajorVersion.id == changes["major_version_id"]).first():
        raise HTTPException(status_code=404, detail="目标大版本不存在")
    for k, v in changes.items():
        setattr(item, k, v)
    if moved and "sort_order" not in changes:
        # 搬到新父级下就排到末尾：留着旧序号会插进中间某个位置，看着像随机落点
        item.sort_order = _tail_sort_order(db, models.ReleaseVersion,
                                           models.ReleaseVersion.major_version_id,
                                           item.major_version_id)
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
    """所有版本的扁平列表 —— 客户面（现场版本 / 预计合入版本）的下拉数据源。

    **不在服务端过滤已发布的版本**：客户面的「现场版本」多数就是已发布的那些，
    度量看板要的更是发布完的版本。谁该藏由调用页决定，这里只如实标一个 `released`。
    """
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
            "released": _is_released(rv.actual_release_date),
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


@router.post("/iteration-versions/reorder")
def reorder_iteration_versions(
    payload: schemas.VersionReorderIn,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    """重排某个版本下的迭代版本。parent_id＝release_version_id。"""
    n = _reorder(db, models.IterationVersion, models.IterationVersion.release_version_id,
                 payload.parent_id, payload.ids)
    log_op(db, action="修改", target="迭代版本", target_id=payload.parent_id or 0,
           detail=f"reorder release_id={payload.parent_id} count={n}",
           user=current_admin, request=request)
    return {"ok": True, "count": n}


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
    moved = ("release_version_id" in changes
             and changes["release_version_id"] != item.release_version_id)
    for k, v in changes.items():
        setattr(item, k, v)
    if "release_version_id" in changes:
        _sync_major_id(db, item)      # 顺带校验目标版本存在，不存在会 404
    if moved and "sort_order" not in changes:
        item.sort_order = _tail_sort_order(db, models.IterationVersion,
                                           models.IterationVersion.release_version_id,
                                           item.release_version_id)
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
    """所有迭代版本的扁平列表 —— 迭代管理「计划交付版本」下拉的数据源。

    每行带一个 `released`：构建自己发布了、**或者它挂的那个版本已经发布**，都算已发布
    （版本一发，名下的构建就都是历史了，不可能再往里合需求）。
    与 `/release-versions/all` 一样只标不滤——问题单管理那边要按构建号查历史数据。
    """
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
            "actual_release_date": it.actual_release_date,
            "released": (_is_released(it.actual_release_date)
                         or (rv is not None and _is_released(rv.actual_release_date))),
        })
    return result
