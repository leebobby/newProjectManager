"""现场调试版本（T 版本）+ 诉求收集 + 接受版本姓名列表 + 现场使用看板。

权限：协作编辑域（见 CLAUDE.md「Write-permission principle」）——日常记录，
登录用户均可读写，带乐观锁。新表由 create_all 自动建。
"""
import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
import schemas
from auth import get_current_user
from database import get_db
from op_log import log_op

router = APIRouter(prefix="/api", tags=["debug-versions"])


# ─── helpers ─────────────────────────────────────────────────────────────────
def _cust_name_map(db: Session) -> dict:
    rows = db.query(models.Customer.id, models.Customer.code, models.Customer.display_name).all()
    return {r.id: (r.display_name or r.code) for r in rows}


def _version_out(obj: models.DebugVersion, name_map: dict) -> schemas.DebugVersionOut:
    out = schemas.DebugVersionOut.model_validate(obj)
    out.target_customer_name = name_map.get(obj.target_customer_id)
    return out


def _parse_bf(raw: str) -> List[int]:
    try:
        data = json.loads(raw or "[]")
    except (ValueError, TypeError):
        return []
    out = []
    for x in data if isinstance(data, list) else []:
        try:
            out.append(int(x))
        except (ValueError, TypeError):
            continue
    return out


def _demand_out(obj: models.DebugDemand, name_map: dict) -> schemas.DebugDemandOut:
    ids = _parse_bf(obj.battlefields_json)
    return schemas.DebugDemandOut(
        id=obj.id, seq=obj.seq or 0, demand=obj.demand or "",
        problem_solved=obj.problem_solved or "", feature=obj.feature or "",
        battlefields=ids, battlefield_names=[name_map[i] for i in ids if i in name_map],
        expected_time=obj.expected_time or "", actual_version=obj.actual_version or "",
        sort_order=obj.sort_order or 0, version=obj.version,
    )


def _next_sort(db: Session, column) -> int:
    mx = db.query(func.coalesce(func.max(column), 0)).scalar() or 0
    return mx + 1


# ─── 调试版本 CRUD ────────────────────────────────────────────────────────────
@router.get("/debug-versions", response_model=List[schemas.DebugVersionOut])
def list_versions(db: Session = Depends(get_db)):
    name_map = _cust_name_map(db)
    rows = (
        db.query(models.DebugVersion)
        .order_by(models.DebugVersion.sort_order.asc(), models.DebugVersion.id.asc())
        .all()
    )
    return [_version_out(r, name_map) for r in rows]


@router.get("/debug-versions/dashboard", response_model=schemas.DebugDashboardOut)
def dashboard(db: Session = Depends(get_db)):
    """现场使用看板：按月统计调试版本数量，并按目标客户分布。

    月份口径＝发布时间，缺失则用计划发布时间；两者都无归入「未排期」。
    """
    name_map = _cust_name_map(db)
    rows = db.query(models.DebugVersion).all()
    buckets: dict = {}
    cust_set = set()
    for r in rows:
        d = r.release_date or r.planned_release_date
        month = f"{d.year}-{d.month:02d}" if d else "未排期"
        cname = name_map.get(r.target_customer_id) or "未指定"
        cust_set.add(cname)
        buckets.setdefault(month, {})
        buckets[month][cname] = buckets[month].get(cname, 0) + 1

    def mkey(m):
        return (1, "") if m == "未排期" else (0, m)

    months = [
        schemas.DebugDashboardMonth(month=m, total=sum(buckets[m].values()), by_customer=buckets[m])
        for m in sorted(buckets.keys(), key=mkey)
    ]
    return schemas.DebugDashboardOut(customers=sorted(cust_set), months=months)


@router.post("/debug-versions", response_model=schemas.DebugVersionOut)
def create_version(
    payload: schemas.DebugVersionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    data = payload.model_dump()
    if not data.get("sort_order"):
        data["sort_order"] = _next_sort(db, models.DebugVersion.sort_order)
    obj = models.DebugVersion(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    log_op(db, action="新增", target="现场调试版本", target_id=obj.id,
           detail=f"version_no={obj.version_no}", user=current_user, request=request)
    return _version_out(obj, _cust_name_map(db))


@router.put("/debug-versions/{vid}", response_model=schemas.DebugVersionOut)
def update_version(
    vid: int,
    payload: schemas.DebugVersionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    obj = db.query(models.DebugVersion).filter(models.DebugVersion.id == vid).first()
    if not obj:
        raise HTTPException(404, "Not found")
    if obj.version != payload.version:
        raise HTTPException(409, "数据已被他人修改，请刷新后重试")
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("version", None)
    for k, v in changes.items():
        setattr(obj, k, v)
    obj.version += 1
    db.commit()
    db.refresh(obj)
    log_op(db, action="修改", target="现场调试版本", target_id=obj.id,
           detail=f"version_no={obj.version_no}", user=current_user, request=request)
    return _version_out(obj, _cust_name_map(db))


@router.delete("/debug-versions/{vid}")
def delete_version(
    vid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    obj = db.query(models.DebugVersion).filter(models.DebugVersion.id == vid).first()
    if not obj:
        raise HTTPException(404, "Not found")
    vn = obj.version_no
    db.delete(obj)
    db.commit()
    log_op(db, action="删除", target="现场调试版本", target_id=vid,
           detail=f"version_no={vn}", user=current_user, request=request)
    return {"ok": True}


# ─── 诉求收集 CRUD ────────────────────────────────────────────────────────────
@router.get("/debug-demands", response_model=List[schemas.DebugDemandOut])
def list_demands(db: Session = Depends(get_db)):
    name_map = _cust_name_map(db)
    rows = (
        db.query(models.DebugDemand)
        .order_by(models.DebugDemand.seq.asc(), models.DebugDemand.id.asc())
        .all()
    )
    return [_demand_out(r, name_map) for r in rows]


@router.post("/debug-demands", response_model=schemas.DebugDemandOut)
def create_demand(
    payload: schemas.DebugDemandCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    data = payload.model_dump()
    bf = data.pop("battlefields", None) or []
    if not data.get("seq"):
        data["seq"] = _next_sort(db, models.DebugDemand.seq)
    obj = models.DebugDemand(**data, battlefields_json=json.dumps([int(x) for x in bf]))
    db.add(obj)
    db.commit()
    db.refresh(obj)
    log_op(db, action="新增", target="调试版本诉求", target_id=obj.id,
           detail=(obj.demand or "")[:40], user=current_user, request=request)
    return _demand_out(obj, _cust_name_map(db))


@router.put("/debug-demands/{did}", response_model=schemas.DebugDemandOut)
def update_demand(
    did: int,
    payload: schemas.DebugDemandUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    obj = db.query(models.DebugDemand).filter(models.DebugDemand.id == did).first()
    if not obj:
        raise HTTPException(404, "Not found")
    if obj.version != payload.version:
        raise HTTPException(409, "数据已被他人修改，请刷新后重试")
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("version", None)
    if "battlefields" in changes:
        bf = changes.pop("battlefields") or []
        obj.battlefields_json = json.dumps([int(x) for x in bf])
    for k, v in changes.items():
        setattr(obj, k, v)
    obj.version += 1
    db.commit()
    db.refresh(obj)
    log_op(db, action="修改", target="调试版本诉求", target_id=obj.id,
           detail=(obj.demand or "")[:40], user=current_user, request=request)
    return _demand_out(obj, _cust_name_map(db))


@router.delete("/debug-demands/{did}")
def delete_demand(
    did: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    obj = db.query(models.DebugDemand).filter(models.DebugDemand.id == did).first()
    if not obj:
        raise HTTPException(404, "Not found")
    db.delete(obj)
    db.commit()
    log_op(db, action="删除", target="调试版本诉求", target_id=did,
           detail="", user=current_user, request=request)
    return {"ok": True}


# ─── 接受版本姓名列表 ─────────────────────────────────────────────────────────
def _recipients_of(db: Session, vid: int):
    return (
        db.query(models.DebugVersionRecipient)
        .filter(models.DebugVersionRecipient.debug_version_id == vid)
        .order_by(models.DebugVersionRecipient.sort_order.asc(),
                  models.DebugVersionRecipient.id.asc())
        .all()
    )


@router.get("/debug-versions/{vid}/recipients", response_model=List[schemas.DebugRecipientOut])
def list_recipients(vid: int, db: Session = Depends(get_db)):
    return _recipients_of(db, vid)


@router.post("/debug-versions/{vid}/recipients/auto-match",
             response_model=List[schemas.DebugRecipientOut])
def auto_match_recipients(
    vid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """按调试版本的目标客户，从「战场沟通矩阵」自动带出接收人（补充式，不覆盖已有）。"""
    ver = db.query(models.DebugVersion).filter(models.DebugVersion.id == vid).first()
    if not ver:
        raise HTTPException(404, "调试版本不存在")
    if not ver.target_customer_id:
        raise HTTPException(400, "该调试版本未指定目标客户，无法匹配战场干系人")

    existing = {(r.name or "").strip() for r in _recipients_of(db, vid) if (r.name or "").strip()}
    base_sort = max([r.sort_order or 0 for r in _recipients_of(db, vid)] or [0])

    rows = (
        db.query(models.StakeholderBattlefield)
        .filter(models.StakeholderBattlefield.customer_id == ver.target_customer_id)
        .all()
    )
    added = 0
    for bf in rows:
        pairs = [
            (bf.contact1, "服务" + (f"/{bf.service}" if bf.service else "")),
            (bf.contact2, "APPS" + (f"/{bf.apps}" if bf.apps else "")),
        ]
        for raw, role in pairs:
            for line in str(raw or "").splitlines():
                name = line.strip()
                if not name or name in existing:
                    continue
                existing.add(name)
                base_sort += 1
                db.add(models.DebugVersionRecipient(
                    debug_version_id=vid, name=name, role=role,
                    received=False, sort_order=base_sort,
                ))
                added += 1
    db.commit()
    log_op(db, action="自动匹配", target="版本接收人", target_id=vid,
           detail=f"customer_id={ver.target_customer_id} added={added}",
           user=current_user, request=request)
    return _recipients_of(db, vid)


@router.post("/debug-versions/{vid}/recipients", response_model=schemas.DebugRecipientOut)
def add_recipient(
    vid: int,
    payload: schemas.DebugRecipientCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ver = db.query(models.DebugVersion).filter(models.DebugVersion.id == vid).first()
    if not ver:
        raise HTTPException(404, "调试版本不存在")
    data = payload.model_dump()
    if not data.get("sort_order"):
        data["sort_order"] = max([r.sort_order or 0 for r in _recipients_of(db, vid)] or [0]) + 1
    obj = models.DebugVersionRecipient(debug_version_id=vid, **data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    log_op(db, action="新增", target="版本接收人", target_id=obj.id,
           detail=f"version={vid} name={obj.name}", user=current_user, request=request)
    return obj


@router.put("/debug-versions/recipients/{rid}", response_model=schemas.DebugRecipientOut)
def update_recipient(
    rid: int,
    payload: schemas.DebugRecipientUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    obj = db.query(models.DebugVersionRecipient).filter(models.DebugVersionRecipient.id == rid).first()
    if not obj:
        raise HTTPException(404, "Not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/debug-versions/recipients/{rid}")
def delete_recipient(
    rid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    obj = db.query(models.DebugVersionRecipient).filter(models.DebugVersionRecipient.id == rid).first()
    if not obj:
        raise HTTPException(404, "Not found")
    db.delete(obj)
    db.commit()
    log_op(db, action="删除", target="版本接收人", target_id=rid,
           detail="", user=current_user, request=request)
    return {"ok": True}
