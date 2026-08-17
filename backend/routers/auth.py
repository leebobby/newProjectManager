from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

import models
import schemas
from auth import create_access_token, get_current_user, hash_password, require_admin, verify_password
from database import get_db
from op_log import log_op
from routers.users import _serialize_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == payload.username).first()
    if not user or not user.is_active:
        log_op(db, action="登录失败", target="账号", username=payload.username,
               detail="用户不存在或已禁用", request=request)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if user.auth_provider != "local":
        log_op(db, action="登录失败", target="账号", user=user,
               detail="非本地账户", request=request)
        raise HTTPException(status_code=400, detail="该账号需通过企业 SSO 登录")
    if user.can_login is False:
        log_op(db, action="登录失败", target="账号", user=user,
               detail="纯人员档案，不允许登录", request=request)
        raise HTTPException(status_code=401, detail="该账号为人员档案，不允许登录")
    if not verify_password(payload.password, user.password_hash):
        log_op(db, action="登录失败", target="账号", user=user,
               detail="密码错误", request=request)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token({"sub": user.username, "role": user.role})
    log_op(db, action="登录", target="账号", user=user, request=request)
    return schemas.TokenResponse(access_token=token, user=_serialize_user(db, user))


@router.post("/logout")
def logout(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """前端调用以记录登出；JWT 本身无服务端会话，仅做日志。"""
    log_op(db, action="登出", target="账号", user=current_user, request=request)
    return {"ok": True}


@router.post("/register", response_model=schemas.UserOut)
def register(
    payload: schemas.RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    """由管理员代为开户：固定 normal 角色，账户默认启用。

    历史上这里是公开的自助注册入口，任何能访问接口的人都能建号——属于安全洞。
    现已收紧为仅管理员可调用；日常建号建议直接走「用户管理」（/api/users）。
    """
    if db.query(models.User).filter(models.User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = models.User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name or "",
        role="normal",
        auth_provider="local",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_op(db, action="注册", target="账号", user=user,
           detail=f"username={user.username}", request=request)
    return user


@router.get("/me", response_model=schemas.UserOut)
def me(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _serialize_user(db, current_user)


@router.post("/change-password")
def change_password(
    payload: schemas.PasswordChangeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """当前登录用户修改自己的密码。"""
    if current_user.auth_provider != "local":
        raise HTTPException(status_code=400, detail="非本地账号无法在此修改密码")
    if not verify_password(payload.old_password, current_user.password_hash):
        log_op(db, action="修改密码失败", target="账号", user=current_user,
               detail="原密码不正确", request=request)
        raise HTTPException(status_code=400, detail="原密码不正确")
    if not payload.new_password or len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码至少 6 位")
    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    log_op(db, action="修改密码", target="账号", user=current_user, request=request)
    return {"ok": True}
