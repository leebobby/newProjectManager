"""修订历史：翻某个对象 / 某一行 / 某一列被改过什么，以及"某个时刻是什么值"。

读权限＝**所有登录用户**（见 CLAUDE.md「Write-permission principle」：读默认开放）。
这里**只有读**——历史没有写接口，也不该有：能改的历史就不是历史了。
留痕本身收口在 [revisions.py](../revisions.py)，各写路径调 `record()` 落库。
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import models
import revisions
import schemas
from database import get_db
from timeutil import local_to_utc

router = APIRouter(prefix="/api/history", tags=["history"])

_MAX_LIMIT = 200


def _out(r: models.FieldRevision) -> schemas.FieldRevisionOut:
    from routers.specials import _rich_to_html  # 延迟导入，避免 router 之间互相拉起

    spec = revisions.TRACKED.get(r.entity) or {}
    return schemas.FieldRevisionOut(
        id=r.id, entity=r.entity, entity_label=spec.get("label", r.entity),
        entity_id=r.entity_id, entity_title=r.entity_title or "",
        scope_key=r.scope_key or "", field=r.field or "",
        field_label=(revisions.field_label(r.entity, r.field) if r.field else "整条记录"),
        old_value=r.old_value or "", new_value=r.new_value or "",
        old_html=_rich_to_html(r.old_value or ""), new_html=_rich_to_html(r.new_value or ""),
        action=r.action or "update", username=r.username or "",
        created_at=r.created_at,
    )


@router.get("/entities")
def list_entities():
    """留痕登记表：前端据此渲染筛选项，不要在前端再写一份实体/列名对照。"""
    return {
        "scopes": revisions.SCOPE_LABELS,
        "entities": [
            {
                "entity": name,
                "label": spec["label"],
                "fields": [{"field": f, "label": revisions.field_label(name, f)}
                           for f in spec["fields"]],
            }
            for name, spec in revisions.TRACKED.items()
        ],
    }


@router.get("/at", response_model=schemas.RowAtOut)
def row_at(
    entity: str = Query(..., description="实体类型，取值见 /entities"),
    entity_id: int = Query(...),
    at: datetime = Query(..., description="时刻（本地时间）"),
    db: Session = Depends(get_db),
):
    """这一行在 `at` 那一刻的样子。

    查询条件用 `local_to_utc()`：前端传的是本地时间，而 created_at 存的是朴素 UTC
    （见 CLAUDE.md「时间」）。不转的话查出来的是 8 小时前那一版，而值看着都挺像的。
    """
    spec = revisions.TRACKED.get(entity)
    if not spec:
        raise HTTPException(400, f"未知的实体类型：{entity}")
    when = local_to_utc(at) or at
    obj = db.query(spec["model"]).filter(spec["model"].id == entity_id).first()
    if obj is None:
        # 行已经被删了：当时的值要去删除记录里看，这里如实说"现在没有这一行"
        return schemas.RowAtOut(entity=entity, entity_id=entity_id,
                                at=at.isoformat(), exists=False, fields=[])
    values = revisions.row_at(db, obj, when)
    return schemas.RowAtOut(
        entity=entity, entity_id=entity_id, at=at.isoformat(), exists=True,
        fields=[{"field": f, "label": revisions.field_label(entity, f),
                 "value": values.get(f, "")} for f in spec["fields"]],
    )


@router.get("", response_model=schemas.FieldRevisionPage)
def list_revisions(
    scope: str = Query("", description="归属对象，如 special:12"),
    entity: str = Query(""),
    entity_id: Optional[int] = Query(None),
    field: List[str] = Query(default=[]),
    limit: int = Query(50, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """倒序翻历史。至少给一个 scope 或 entity——不给就是全库拉，没有使用场景。"""
    if not scope and not entity:
        raise HTTPException(400, "请指定 scope 或 entity")
    # 按行号翻历史要以「这一行什么时候建的」为下界：SQLite 会复用已删行的 id，
    # 不设下界的话新行会把同号旧行的历史整段认领过来（见 revisions.born_at）
    since = None
    spec = revisions.TRACKED.get(entity) if entity else None
    if spec and entity_id is not None:
        obj = db.query(spec["model"]).filter(spec["model"].id == entity_id).first()
        if obj is not None:
            since = revisions.born_at(obj)
    q = revisions.query(db, scope_key=scope, entity=entity,
                        entity_id=entity_id, fields=field, since=since)
    total = q.order_by(None).count()
    rows = q.offset(offset).limit(limit).all()
    return schemas.FieldRevisionPage(total=total, items=[_out(r) for r in rows])
