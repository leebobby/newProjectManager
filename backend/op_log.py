"""操作日志工具：在路由里显式调用 log_op 记录登录与关键写操作。

设计要点：
- 由路由显式调用而非全局中间件，避免对 GET / 健康检查等无意义记录。
- 失败也不应阻塞主业务；写入异常吞掉并打 print，可在日志中排查。
- detail 仅保留语义摘要（如 "version_no=v1.0.0"），不写密码等敏感内容。
"""
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

import models


def _client_ip(request: Optional[Request]) -> str:
    if request is None:
        return ""
    fwd = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


def _ua(request: Optional[Request]) -> str:
    if request is None:
        return ""
    return (request.headers.get("user-agent") or "")[:256]


def log_op(
    db: Session,
    *,
    action: str,
    target: str = "",
    target_id: Optional[object] = None,
    detail: str = "",
    user: Optional[models.User] = None,
    username: Optional[str] = None,
    request: Optional[Request] = None,
) -> None:
    """写一条操作日志。任何异常都会被吞掉，绝不影响主流程。"""
    try:
        rec = models.OperationLog(
            user_id=user.id if user else None,
            username=(user.username if user else (username or "")) or "",
            action=action,
            target=target or "",
            target_id="" if target_id is None else str(target_id),
            detail=(detail or "")[:2000],
            ip=_client_ip(request),
            user_agent=_ua(request),
        )
        db.add(rec)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        print(f"[op_log] failed: {exc}")
        try:
            db.rollback()
        except Exception:
            pass
