"""问题单跟踪：进展说明 + 合入计划。

**为什么不挂在快照上**：问题单每天采集一次，明细落文件、只有维度数字入库，
快照本身是"当天还开着的单"的一份存档。跟踪记录要是跟着某一天的快照走，
第二天重新采集就等于全丢了——页面上只表现成"昨天填的怎么没了"，看着像丢数据。
所以这张表按「采集项目 + 缺陷编号」独立存，与快照解耦：只要这单还在 DTS 里开着
（没被关闭/撤销、没从快照里消失），今天填的进展与合入计划每天都看得到。

权限：协作编辑域（见 CLAUDE.md「Write-permission principle」）——日常填报，
登录用户均可写。**没有删除接口**：这条记录清空就等于没填，用不着删；
而误删的是别人跟了几周的进展。
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

import models
import schemas
from auth import get_current_user
from database import get_db
from op_log import log_op
from routers._lookups import fill_release_version_fk, fill_version_fk

router = APIRouter(prefix="/api/issue-tracks", tags=["issue-tracks"])


@router.get("", response_model=List[schemas.IssueTrackOut])
def list_tracks(
    project: str = Query(..., description="采集项目"),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    """某项目下所有已填过的跟踪记录。

    一次全给：一份快照几百上千条单，页面拿它按缺陷编号并到明细行上，
    逐条查等于几百个请求。已填过的通常只是其中一小部分，量不大。
    """
    return (
        db.query(models.IssueTrack)
        .filter(models.IssueTrack.project == project)
        .order_by(models.IssueTrack.issue_id)
        .all()
    )


@router.put("", response_model=schemas.IssueTrackOut)
def upsert_track(
    payload: schemas.IssueTrackUpsert,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """新建或更新一条跟踪记录（按 项目 + 缺陷编号 认领）。

    做成 upsert 而不是 POST + PUT：问题单不是我们建的，第一次给某个单填进展时
    「这条记录存不存在」是实现细节，不该让页面先查一次再决定调哪个接口。
    """
    project = (payload.project or "").strip()
    issue_id = (payload.issue_id or "").strip()
    if not project or not issue_id:
        raise HTTPException(status_code=400, detail="缺少项目或缺陷编号")

    item = (
        db.query(models.IssueTrack)
        .filter(models.IssueTrack.project == project,
                models.IssueTrack.issue_id == issue_id)
        .first()
    )
    changes = payload.model_dump(exclude_unset=True)
    for k in ("project", "issue_id", "version"):
        changes.pop(k, None)

    # 字符串 → FK：计划落**版本**层、实际落**迭代版本（构建）**层，两层不能填反
    fill_release_version_fk(db, changes, "plan_version", "plan_version_id")
    fill_version_fk(db, changes, "merged_build", "merged_build_id")

    created = item is None
    if created:
        item = models.IssueTrack(project=project, issue_id=issue_id)
        db.add(item)
    elif payload.version is not None and item.version != payload.version:
        raise HTTPException(status_code=409, detail="这条跟踪已被他人修改，请刷新后重试")

    for k, v in changes.items():
        setattr(item, k, v)
    item.updated_by = current_user.full_name or current_user.username
    item.version = (item.version or 0) + 1
    db.commit()
    db.refresh(item)

    log_op(db, action="新增" if created else "修改", target="问题单跟踪", target_id=item.id,
           detail=f"project={project} issue_id={issue_id} "
                  f"fields={','.join(changes.keys()) or '无'}",
           user=current_user, request=request)
    return item
