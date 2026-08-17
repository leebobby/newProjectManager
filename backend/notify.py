"""通知分发器：业务层产生事件 → 这里决定通知谁。

调用方式（在 router 内）：
    from notify import dispatch
    dispatch(db, kind="status_change", title=..., body=..., link=...,
             source_type="iteration_requirement", source_id=42,
             actor=current_user, recipient_ids=[owner_user_id], extra_subs=True)

设计：
- recipient_ids 显式指定 → 给这些人各发一条
- extra_subs=True → 同时按 Subscription 表查订阅了 (source_type, source_id) 的用户，去重后追加
- 任何异常都吞掉；通知不能阻塞主业务

注意：日志记录在 op_log 里，通知是独立路径。两者目的不同，不要混。
"""
from typing import Iterable, Optional

from sqlalchemy.orm import Session

import models


def _collect_subscribers(db: Session, source_type: str, source_id: Optional[int]) -> set[int]:
    if not source_type:
        return set()
    q = db.query(models.Subscription).filter(models.Subscription.source_type == source_type)
    if source_id is not None:
        # 命中具体 id 的订阅；以及 source_id IS NULL 的"全订阅"
        q = q.filter(
            (models.Subscription.source_id == source_id) |
            (models.Subscription.source_id.is_(None))
        )
    rows = q.all()
    return {s.user_id for s in rows}


def dispatch(
    db: Session,
    *,
    kind: str,
    title: str,
    body: str = "",
    link: str = "",
    source_type: str = "",
    source_id: int = 0,
    actor: Optional[models.User] = None,
    recipient_ids: Optional[Iterable[int]] = None,
    extra_subs: bool = True,
    exclude_actor: bool = True,
) -> int:
    """生成并入库通知。返回实际入库的条数（去重后）。"""
    try:
        ids: set[int] = set(recipient_ids or [])
        if extra_subs:
            ids |= _collect_subscribers(db, source_type, source_id or None)
        if exclude_actor and actor is not None:
            ids.discard(actor.id)
        if not ids:
            return 0

        actor_id = actor.id if actor is not None else None
        for uid in ids:
            db.add(models.Notification(
                recipient_id=uid,
                actor_id=actor_id,
                kind=kind,
                title=title or "",
                body=body or "",
                link=link or "",
                source_type=source_type or "",
                source_id=source_id or 0,
                is_read=False,
            ))
        db.commit()
        return len(ids)
    except Exception:
        # 静默：通知失败不能影响业务请求
        try:
            db.rollback()
        except Exception:
            pass
        return 0


def broadcast(
    db: Session,
    *,
    kind: str,
    title: str,
    body: str = "",
    link: str = "",
    actor: Optional[models.User] = None,
) -> int:
    """广播：写一条 recipient_id=NULL 的 Notification；阅读状态走 NotificationRead。"""
    try:
        n = models.Notification(
            recipient_id=None,
            actor_id=actor.id if actor else None,
            kind=kind,
            title=title or "",
            body=body or "",
            link=link or "",
            source_type="broadcast",
            source_id=0,
            is_read=False,
        )
        db.add(n)
        db.commit()
        return 1
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return 0


def notify_owner_change(
    db: Session,
    *,
    source_type: str,
    source_id: int,
    title: str,
    body: str = "",
    link: str = "",
    actor: Optional[models.User] = None,
    owner_user_id: Optional[int],
):
    """通用：业务表 owner 字段变更时调用，会把 owner 和订阅者都通知到。"""
    recip = [owner_user_id] if owner_user_id else []
    dispatch(
        db, kind="assignment",
        title=title, body=body, link=link,
        source_type=source_type, source_id=source_id,
        actor=actor, recipient_ids=recip, extra_subs=True,
    )
