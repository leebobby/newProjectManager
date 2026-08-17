from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

import models
import schemas
from auth import get_current_user, hash_password, require_admin
from database import get_db
from op_log import log_op

router = APIRouter(prefix="/api/users", tags=["users"])


# ─── helpers ────────────────────────────────────────────────────────────────
def _serialize_user(db: Session, u: models.User, groups: dict = None, depts: dict = None) -> dict:
    """把 User 实例转成包含组/部门派生字段的 dict，供 UserOut 直接消费。

    传入预取的 groups/depts 映射时走批量路径（不再逐用户查库）；不传则按单用户惰性查。
    """
    if groups is None:
        group = u.group  # relationship 惰性加载；可能为 None
        dept = db.query(models.ResourceGroup).get(group.parent_id) if (group and group.parent_id) else None
    else:
        group = groups.get(u.group_id)
        dept = depts.get(group.parent_id) if (group and group.parent_id) else None
    return {
        "id": u.id,
        "username": u.username,
        "full_name": u.full_name or "",
        "emp_no": u.emp_no or "",
        "job_title": u.job_title or "",
        "group_id": u.group_id,
        "group_name": group.name if group else None,
        "dept_id": dept.id if dept else None,
        "dept_name": dept.name if dept else None,
        "role": u.role,
        "is_active": u.is_active,
        "can_login": bool(u.can_login) if u.can_login is not None else True,
        "auth_provider": u.auth_provider or "local",
        "created_at": u.created_at,
    }


def _serialize_users(db: Session, users: List[models.User]) -> List[dict]:
    """批量序列化：组、部门各一次性取出，避免逐用户 N+1 查询（用户多时是卡顿来源）。"""
    group_ids = {u.group_id for u in users if u.group_id}
    groups = (
        {g.id: g for g in db.query(models.ResourceGroup).filter(models.ResourceGroup.id.in_(group_ids)).all()}
        if group_ids else {}
    )
    dept_ids = {g.parent_id for g in groups.values() if g.parent_id}
    depts = (
        {d.id: d for d in db.query(models.ResourceGroup).filter(models.ResourceGroup.id.in_(dept_ids)).all()}
        if dept_ids else {}
    )
    return [_serialize_user(db, u, groups, depts) for u in users]


def _validate_group_id(db: Session, group_id: Optional[int]) -> None:
    if group_id is None:
        return
    g = db.query(models.ResourceGroup).filter(models.ResourceGroup.id == group_id).first()
    if not g:
        raise HTTPException(400, f"组 id={group_id} 不存在")
    if g.kind != "pl":
        # 允许暂时挂到 dept 也行，但通常是 pl 级；这里给个明确提示
        raise HTTPException(400, f"应选择 PL 组而不是部门（当前选中的是 {g.kind}）")


# ─── routes ─────────────────────────────────────────────────────────────────
@router.get("", response_model=List[schemas.UserOut], dependencies=[Depends(require_admin)])
def list_users(db: Session = Depends(get_db)):
    rows = db.query(models.User).order_by(models.User.id.asc()).all()
    return _serialize_users(db, rows)


@router.get("/options", response_model=List[schemas.UserOut])
def list_user_options(
    include_inactive: bool = Query(False),
    only_can_login: bool = Query(False, description="只列允许登录的（建议给 owner 选择器用）"),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    """供 owner / leader 等下拉选择器使用。普通用户也可读，但只返回基础字段。"""
    q = db.query(models.User)
    if not include_inactive:
        q = q.filter(models.User.is_active.is_(True))
    if only_can_login:
        q = q.filter(models.User.can_login.is_(True))
    rows = q.order_by(models.User.full_name, models.User.id).all()
    return _serialize_users(db, rows)


@router.post("", response_model=schemas.UserOut, dependencies=[Depends(require_admin)])
def create_user(
    payload: schemas.UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    if db.query(models.User).filter(models.User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    role = payload.role or "normal"
    if role not in ("admin", "normal"):
        raise HTTPException(status_code=400, detail="role 只能是 admin 或 normal")
    can_login = True if payload.can_login is None else bool(payload.can_login)
    if can_login and not (payload.password or "").strip():
        raise HTTPException(status_code=400, detail="允许登录的账号必须设置密码")
    _validate_group_id(db, payload.group_id)

    user = models.User(
        username=payload.username,
        full_name=payload.full_name or "",
        emp_no=payload.emp_no or "",
        job_title=payload.job_title or "",
        group_id=payload.group_id,
        password_hash=hash_password(payload.password) if can_login and payload.password else "",
        role=role,
        auth_provider="local",
        is_active=True,
        can_login=can_login,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_op(db, action="新增", target="用户", target_id=user.id,
           detail=f"username={user.username} role={user.role} can_login={can_login}",
           user=current_admin, request=request)
    return _serialize_user(db, user)


@router.put("/{user_id}", response_model=schemas.UserOut, dependencies=[Depends(require_admin)])
def update_user(
    user_id: int,
    payload: schemas.UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    changed = []
    if payload.full_name is not None and payload.full_name != user.full_name:
        user.full_name = payload.full_name
        changed.append("full_name")
    if payload.emp_no is not None and payload.emp_no != user.emp_no:
        user.emp_no = payload.emp_no
        changed.append("emp_no")
    if payload.job_title is not None and payload.job_title != user.job_title:
        user.job_title = payload.job_title
        changed.append("job_title")
    if payload.group_id is not None and payload.group_id != user.group_id:
        # 允许传 0 / 显式 null 来清空（FastAPI 不会把缺省字段传进来）
        if payload.group_id == 0:
            user.group_id = None
        else:
            _validate_group_id(db, payload.group_id)
            user.group_id = payload.group_id
        changed.append(f"group_id->{user.group_id}")
    if payload.role is not None:
        if payload.role not in ("admin", "normal"):
            raise HTTPException(status_code=400, detail="role 只能是 admin 或 normal")
        if user.id == current_admin.id and payload.role != "admin":
            raise HTTPException(status_code=400, detail="不能修改自己的管理员角色")
        if user.role != payload.role:
            user.role = payload.role
            changed.append(f"role->{payload.role}")
    if payload.is_active is not None:
        if user.id == current_admin.id and not payload.is_active:
            raise HTTPException(status_code=400, detail="不能禁用自己")
        if user.is_active != payload.is_active:
            user.is_active = payload.is_active
            changed.append(f"is_active->{payload.is_active}")
    if payload.can_login is not None and bool(payload.can_login) != bool(user.can_login):
        if user.id == current_admin.id and not payload.can_login:
            raise HTTPException(status_code=400, detail="不能关闭自己的登录权限")
        user.can_login = bool(payload.can_login)
        changed.append(f"can_login->{user.can_login}")
    if payload.password:
        user.password_hash = hash_password(payload.password)
        changed.append("password")

    db.commit()
    db.refresh(user)
    log_op(db, action="修改", target="用户", target_id=user.id,
           detail=f"username={user.username} fields={','.join(changed) or '无变化'}",
           user=current_admin, request=request)
    return _serialize_user(db, user)


@router.delete("/{user_id}", dependencies=[Depends(require_admin)])
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == current_admin.id:
        raise HTTPException(status_code=400, detail="不能删除自己")
    snapshot = f"username={user.username}"
    db.delete(user)
    db.commit()
    log_op(db, action="删除", target="用户", target_id=user_id,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}
