"""站内通知接口：列表 / 标已读 / 订阅管理 / 广播。

广播通知的特殊处理：
- 用户查列表时，定向通知按 recipient_id 过滤；广播通知 LEFT JOIN notification_reads
- 标记已读时，定向→更新 is_read；广播→插入 notification_reads
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import Session

import models
import schemas
from auth import get_current_user, require_admin
from database import get_db
from notify import broadcast as do_broadcast
from op_log import log_op

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _to_out(db: Session, n: models.Notification, current_user_id: int) -> dict:
    is_broadcast = n.recipient_id is None
    # broadcast 的已读看 NotificationRead
    is_read = bool(n.is_read)
    if is_broadcast:
        is_read = db.query(models.NotificationRead).filter(
            models.NotificationRead.notification_id == n.id,
            models.NotificationRead.user_id == current_user_id,
        ).first() is not None
    actor_name = None
    if n.actor_id:
        a = db.query(models.User).get(n.actor_id)
        if a:
            actor_name = a.full_name or a.username
    return {
        "id": n.id,
        "kind": n.kind,
        "title": n.title or "",
        "body": n.body or "",
        "link": n.link or "",
        "source_type": n.source_type or "",
        "source_id": n.source_id or 0,
        "is_read": is_read,
        "is_broadcast": is_broadcast,
        "actor_id": n.actor_id,
        "actor_name": actor_name,
        "created_at": n.created_at,
    }


# ─── 列表 / 未读数 ──────────────────────────────────────────────────────────
@router.get("", response_model=schemas.NotificationListResponse)
def list_notifications(
    only_unread: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    uid = current_user.id

    # 取定向 + 广播
    targeted_q = db.query(models.Notification).filter(models.Notification.recipient_id == uid)
    broadcast_q = db.query(models.Notification).filter(models.Notification.recipient_id.is_(None))

    if only_unread:
        targeted_q = targeted_q.filter(models.Notification.is_read.is_(False))
        # broadcast：排除已在 notification_reads 里的
        read_subq = db.query(models.NotificationRead.notification_id).filter(
            models.NotificationRead.user_id == uid
        ).subquery()
        broadcast_q = broadcast_q.filter(~models.Notification.id.in_(read_subq))

    rows = (targeted_q.union(broadcast_q)
            .order_by(models.Notification.created_at.desc())
            .limit(limit).all())

    # 算未读总数（与 only_unread 无关）
    unread_targeted = db.query(models.Notification).filter(
        models.Notification.recipient_id == uid,
        models.Notification.is_read.is_(False),
    ).count()
    read_bc_ids_subq = db.query(models.NotificationRead.notification_id).filter(
        models.NotificationRead.user_id == uid
    ).subquery()
    unread_bc = db.query(models.Notification).filter(
        models.Notification.recipient_id.is_(None),
        ~models.Notification.id.in_(read_bc_ids_subq),
    ).count()

    items = [_to_out(db, n, uid) for n in rows]
    return {
        "items": items,
        "unread_count": unread_targeted + unread_bc,
        "total": len(items),
    }


@router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    uid = current_user.id
    n1 = db.query(models.Notification).filter(
        models.Notification.recipient_id == uid,
        models.Notification.is_read.is_(False),
    ).count()
    read_bc_ids_subq = db.query(models.NotificationRead.notification_id).filter(
        models.NotificationRead.user_id == uid
    ).subquery()
    n2 = db.query(models.Notification).filter(
        models.Notification.recipient_id.is_(None),
        ~models.Notification.id.in_(read_bc_ids_subq),
    ).count()
    return {"unread": n1 + n2}


# ─── 标记已读 ──────────────────────────────────────────────────────────────
@router.post("/{nid}/read")
def mark_read(
    nid: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    n = db.query(models.Notification).filter(models.Notification.id == nid).first()
    if not n:
        raise HTTPException(404, "Not found")
    if n.recipient_id is None:
        # 广播：插入 read 记录
        already = db.query(models.NotificationRead).filter(
            models.NotificationRead.notification_id == nid,
            models.NotificationRead.user_id == current_user.id,
        ).first()
        if not already:
            db.add(models.NotificationRead(
                notification_id=nid, user_id=current_user.id, read_at=datetime.utcnow(),
            ))
            db.commit()
    else:
        if n.recipient_id != current_user.id:
            raise HTTPException(403, "无权操作他人通知")
        if not n.is_read:
            n.is_read = True
            n.read_at = datetime.utcnow()
            db.commit()
    return {"ok": True}


@router.post("/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    uid = current_user.id
    # 定向：批量更新
    db.query(models.Notification).filter(
        models.Notification.recipient_id == uid,
        models.Notification.is_read.is_(False),
    ).update({models.Notification.is_read: True, models.Notification.read_at: datetime.utcnow()},
             synchronize_session=False)
    # 广播：插入缺失的 read 记录
    bc_ids = [n.id for n in db.query(models.Notification).filter(
        models.Notification.recipient_id.is_(None)
    ).all()]
    if bc_ids:
        existing = {
            r.notification_id for r in db.query(models.NotificationRead).filter(
                models.NotificationRead.user_id == uid,
                models.NotificationRead.notification_id.in_(bc_ids),
            ).all()
        }
        for nid in bc_ids:
            if nid not in existing:
                db.add(models.NotificationRead(
                    notification_id=nid, user_id=uid, read_at=datetime.utcnow(),
                ))
    db.commit()
    return {"ok": True}


# ─── 订阅管理 ──────────────────────────────────────────────────────────────
@router.get("/subscriptions", response_model=List[schemas.SubscriptionOut])
def list_subscriptions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Subscription)
        .filter(models.Subscription.user_id == current_user.id)
        .order_by(models.Subscription.source_type, models.Subscription.id)
        .all()
    )


@router.post("/subscriptions", response_model=schemas.SubscriptionOut)
def add_subscription(
    payload: schemas.SubscriptionPayload,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not payload.source_type:
        raise HTTPException(400, "source_type 必填")
    sid = payload.source_id
    existing = db.query(models.Subscription).filter(
        models.Subscription.user_id == current_user.id,
        models.Subscription.source_type == payload.source_type,
        models.Subscription.source_id == sid,
    ).first()
    if existing:
        return existing
    sub = models.Subscription(
        user_id=current_user.id,
        source_type=payload.source_type,
        source_id=sid,
        events=payload.events or "*",
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


@router.delete("/subscriptions")
def remove_subscription(
    source_type: str = Query(...),
    source_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    q = db.query(models.Subscription).filter(
        models.Subscription.user_id == current_user.id,
        models.Subscription.source_type == source_type,
    )
    if source_id is None:
        q = q.filter(models.Subscription.source_id.is_(None))
    else:
        q = q.filter(models.Subscription.source_id == source_id)
    n = q.delete(synchronize_session=False)
    db.commit()
    return {"removed": n}


# ─── 广播：admin ───────────────────────────────────────────────────────────
@router.post("/broadcast", dependencies=[Depends(require_admin)])
def post_broadcast(
    payload: schemas.BroadcastPayload,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    if not (payload.title or "").strip():
        raise HTTPException(400, "标题必填")
    n = do_broadcast(
        db, kind=payload.kind or "broadcast",
        title=payload.title.strip(),
        body=payload.body or "",
        link=payload.link or "",
        actor=current_admin,
    )
    log_op(db, action="广播", target="通知",
           detail=f"title={payload.title} kind={payload.kind}",
           user=current_admin, request=request)
    return {"ok": True, "count": n}
