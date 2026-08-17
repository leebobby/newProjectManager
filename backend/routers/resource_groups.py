"""资源组（部门 / PL 组）主数据 CRUD。

设计要点：
- 两级结构：kind="dept"（部门，parent_id 必空）/ kind="pl"（PL 组，parent_id 必为某 dept）
- code 全局唯一，业务表统一引用 group_id，看到的展示名走 join
- 读对所有登录用户开放（owner / group 选择器要用），写仅 admin
- 删除前若有成员或子组挂着，要拦截并提示
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

import models
import schemas
from auth import require_admin
from database import get_db
from op_log import log_op

router = APIRouter(prefix="/api/resource-groups", tags=["resource-groups"])

_ALLOWED_KINDS = ("dept", "pl")


# ─── helpers ────────────────────────────────────────────────────────────────
def _serialize(db: Session, g: models.ResourceGroup) -> dict:
    parent_name = None
    if g.parent_id and g.parent:
        parent_name = g.parent.name
    leader_name = None
    if g.leader_id:
        leader = db.query(models.User).get(g.leader_id)
        leader_name = leader.full_name or leader.username if leader else None
    member_count = (
        db.query(models.User).filter(models.User.group_id == g.id).count()
        if g.kind == "pl" else 0
    )
    return {
        "id": g.id,
        "code": g.code,
        "name": g.name,
        "kind": g.kind,
        "parent_id": g.parent_id,
        "parent_name": parent_name,
        "leader_id": g.leader_id,
        "leader_name": leader_name,
        "sort_order": g.sort_order or 0,
        "is_active": g.is_active if g.is_active is not None else True,
        "remark": g.remark or "",
        "member_count": member_count,
        "created_at": g.created_at,
        "updated_at": g.updated_at,
    }


def _validate_kind_and_parent(db: Session, kind: str, parent_id: Optional[int],
                              self_id: Optional[int] = None) -> None:
    if kind not in _ALLOWED_KINDS:
        raise HTTPException(400, f"kind 仅支持 {_ALLOWED_KINDS}")
    if kind == "dept":
        if parent_id is not None:
            raise HTTPException(400, "部门不能有上级")
        return
    # kind == "pl"
    if parent_id is None:
        raise HTTPException(400, "PL 组必须指定所属部门")
    if self_id is not None and parent_id == self_id:
        raise HTTPException(400, "不能将自己设为上级")
    parent = db.query(models.ResourceGroup).filter(
        models.ResourceGroup.id == parent_id
    ).first()
    if not parent:
        raise HTTPException(400, f"上级部门 id={parent_id} 不存在")
    if parent.kind != "dept":
        raise HTTPException(400, "PL 组的上级必须是部门（kind=dept）")


# ─── routes ─────────────────────────────────────────────────────────────────
@router.get("", response_model=List[schemas.ResourceGroupOut])
def list_groups(
    kind: Optional[str] = Query(None, description="dept / pl，留空返回全部"),
    parent_id: Optional[int] = Query(None, description="按所属部门过滤"),
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
):
    q = db.query(models.ResourceGroup)
    if kind:
        if kind not in _ALLOWED_KINDS:
            raise HTTPException(400, f"kind 仅支持 {_ALLOWED_KINDS}")
        q = q.filter(models.ResourceGroup.kind == kind)
    if parent_id is not None:
        q = q.filter(models.ResourceGroup.parent_id == parent_id)
    if not include_inactive:
        q = q.filter(models.ResourceGroup.is_active.is_(True))
    rows = q.order_by(
        models.ResourceGroup.kind.desc(),  # dept 在前
        models.ResourceGroup.sort_order,
        models.ResourceGroup.id,
    ).all()
    return [_serialize(db, g) for g in rows]


@router.get("/{group_id}", response_model=schemas.ResourceGroupOut)
def get_group(group_id: int, db: Session = Depends(get_db)):
    g = db.query(models.ResourceGroup).filter(models.ResourceGroup.id == group_id).first()
    if not g:
        raise HTTPException(404, "Not found")
    return _serialize(db, g)


@router.post("", response_model=schemas.ResourceGroupOut)
def create_group(
    payload: schemas.ResourceGroupCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    code = (payload.code or "").strip()
    name = (payload.name or "").strip()
    if not code or not name:
        raise HTTPException(400, "code 和 name 不能为空")
    if db.query(models.ResourceGroup).filter(models.ResourceGroup.code == code).first():
        raise HTTPException(400, f"code「{code}」已存在")
    _validate_kind_and_parent(db, payload.kind, payload.parent_id)

    g = models.ResourceGroup(
        code=code,
        name=name,
        kind=payload.kind,
        parent_id=payload.parent_id,
        leader_id=payload.leader_id,
        sort_order=payload.sort_order or 0,
        is_active=payload.is_active if payload.is_active is not None else True,
        remark=payload.remark or "",
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    log_op(db, action="新增", target="资源组", target_id=g.id,
           detail=f"code={g.code} kind={g.kind} name={g.name}",
           user=current_admin, request=request)
    return _serialize(db, g)


@router.put("/{group_id}", response_model=schemas.ResourceGroupOut)
def update_group(
    group_id: int,
    payload: schemas.ResourceGroupUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    g = db.query(models.ResourceGroup).filter(models.ResourceGroup.id == group_id).first()
    if not g:
        raise HTTPException(404, "Not found")

    changes = payload.model_dump(exclude_unset=True)
    changed = []

    # parent_id 变更需要重新校验
    if "parent_id" in changes:
        new_parent_id = changes["parent_id"]
        # 部门不允许设父；PL 组允许换父
        _validate_kind_and_parent(db, g.kind, new_parent_id, self_id=g.id)
        if g.parent_id != new_parent_id:
            g.parent_id = new_parent_id
            changed.append(f"parent_id->{new_parent_id}")

    for field in ("name", "leader_id", "sort_order", "is_active", "remark"):
        if field in changes and getattr(g, field) != changes[field]:
            setattr(g, field, changes[field])
            changed.append(field)

    db.commit()
    db.refresh(g)
    log_op(db, action="修改", target="资源组", target_id=g.id,
           detail=f"code={g.code} fields={','.join(changed) or '无变化'}",
           user=current_admin, request=request)
    return _serialize(db, g)


@router.delete("/{group_id}")
def delete_group(
    group_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    g = db.query(models.ResourceGroup).filter(models.ResourceGroup.id == group_id).first()
    if not g:
        raise HTTPException(404, "Not found")

    # 拦截：仍有挂靠的成员或子组
    member_cnt = db.query(models.User).filter(models.User.group_id == g.id).count()
    if member_cnt:
        raise HTTPException(400, f"该组下仍有 {member_cnt} 名成员，请先调整后再删除")
    child_cnt = db.query(models.ResourceGroup).filter(models.ResourceGroup.parent_id == g.id).count()
    if child_cnt:
        raise HTTPException(400, f"该部门下仍有 {child_cnt} 个 PL 组，请先调整后再删除")

    snapshot = f"code={g.code} kind={g.kind} name={g.name}"
    db.delete(g)
    db.commit()
    log_op(db, action="删除", target="资源组", target_id=group_id,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}
