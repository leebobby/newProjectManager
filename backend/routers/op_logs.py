"""管理员审计日志：分页 + 过滤查询。"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
import schemas
from auth import require_admin
from database import get_db

router = APIRouter(
    prefix="/api/op-logs",
    tags=["op-logs"],
    dependencies=[Depends(require_admin)],
)


@router.get("", response_model=schemas.OperationLogPage)
def list_logs(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    username: Optional[str] = None,
    action: Optional[str] = None,
    target: Optional[str] = None,
    keyword: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
):
    q = db.query(models.OperationLog)
    if username:
        q = q.filter(models.OperationLog.username == username)
    if action:
        q = q.filter(models.OperationLog.action == action)
    if target:
        q = q.filter(models.OperationLog.target == target)
    if date_from:
        q = q.filter(models.OperationLog.created_at >= date_from)
    if date_to:
        q = q.filter(models.OperationLog.created_at <= date_to)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(or_(
            models.OperationLog.detail.like(like),
            models.OperationLog.target_id.like(like),
            models.OperationLog.username.like(like),
        ))
    total = q.count()
    items = (
        q.order_by(models.OperationLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"total": total, "items": items}


@router.get("/options")
def list_options(db: Session = Depends(get_db)):
    """返回去重后的 action / target / username 列表，便于前端做下拉过滤。"""
    actions = [r[0] for r in db.query(models.OperationLog.action).distinct().all() if r[0]]
    targets = [r[0] for r in db.query(models.OperationLog.target).distinct().all() if r[0]]
    usernames = [r[0] for r in db.query(models.OperationLog.username).distinct().all() if r[0]]
    return {
        "actions": sorted(actions),
        "targets": sorted(targets),
        "usernames": sorted(usernames),
    }
