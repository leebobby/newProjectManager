"""成员出差管理（协作编辑域）。

谁、去哪个战场（关联客户主数据）、哪段时间、什么事由。状态按起止日期实时
推导（计划中/进行中/已完成/已取消），不入库。登录用户均可读写，带乐观锁。
新表由 create_all 自动建。
"""
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

import models
import schemas
from auth import get_current_user
from database import get_db
from op_log import log_op

router = APIRouter(prefix="/api/business-trips", tags=["business-trips"])


# ─── helpers ─────────────────────────────────────────────────────────────────
def _user_map(db: Session) -> dict:
    """{user_id: (展示名, 所属 PL 组名)}。"""
    rows = (
        db.query(models.User.id, models.User.full_name, models.User.username,
                 models.ResourceGroup.name.label("group_name"))
        .outerjoin(models.ResourceGroup, models.User.group_id == models.ResourceGroup.id)
        .all()
    )
    return {r.id: ((r.full_name or r.username or ""), (r.group_name or "")) for r in rows}


def _cust_map(db: Session) -> dict:
    rows = db.query(models.Customer.id, models.Customer.code, models.Customer.display_name).all()
    return {r.id: (r.display_name or r.code) for r in rows}


def _status(obj: models.BusinessTrip) -> str:
    if obj.cancelled:
        return "已取消"
    today = date.today()
    s = obj.start_date.date() if obj.start_date else None
    e = obj.end_date.date() if obj.end_date else None
    if s and e:
        if today < s:
            return "计划中"
        if today > e:
            return "已完成"
        return "进行中"
    if s and not e:
        return "进行中" if today >= s else "计划中"
    if e and not s:
        return "已完成" if today > e else "进行中"
    return "计划中"


def _trip_out(obj: models.BusinessTrip, umap: dict, cmap: dict) -> schemas.BusinessTripOut:
    out = schemas.BusinessTripOut.model_validate(obj)
    name, group = umap.get(obj.user_id, (None, None))
    out.user_name = name
    out.user_group = group
    out.customer_name = cmap.get(obj.customer_id)
    out.status = _status(obj)
    return out


# ─── CRUD ────────────────────────────────────────────────────────────────────
@router.get("", response_model=List[schemas.BusinessTripOut])
def list_trips(
    user_id: Optional[int] = Query(None),
    customer_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(models.BusinessTrip)
    if user_id is not None:
        q = q.filter(models.BusinessTrip.user_id == user_id)
    if customer_id is not None:
        q = q.filter(models.BusinessTrip.customer_id == customer_id)
    # 起止日期靠后的排前面（SQLite 下 DESC 时 NULL 自然殿后），再按 id
    rows = q.order_by(models.BusinessTrip.start_date.desc(),
                      models.BusinessTrip.id.desc()).all()
    umap, cmap = _user_map(db), _cust_map(db)
    return [_trip_out(r, umap, cmap) for r in rows]


def _parse_day(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


@router.get("/dashboard", response_model=schemas.BusinessTripDashboardOut)
def dashboard(
    start: Optional[str] = Query(None, description="区间开始 YYYY-MM-DD，默认当月 1 号"),
    end: Optional[str] = Query(None, description="区间结束 YYYY-MM-DD，默认今天"),
    db: Session = Depends(get_db),
):
    """客户面支撑看板：当前支撑中/计划中（now 快照）+ 区间内按 战场/人/领域 统计人次。

    领域口径＝支撑人所属 PL 组。区间默认＝当月。
    """
    today = date.today()
    rs = _parse_day(start) or date(today.year, today.month, 1)
    re_ = _parse_day(end) or today
    if re_ < rs:
        rs, re_ = re_, rs

    rows = db.query(models.BusinessTrip).all()
    umap, cmap = _user_map(db), _cust_map(db)

    on_now = planned = range_total = 0
    by_cust: dict = {}
    by_person: dict = {}
    by_domain: dict = {}

    for r in rows:
        if r.cancelled:
            continue
        st = _status(r)
        if st == "进行中":
            on_now += 1
        elif st == "计划中":
            planned += 1
        # 区间统计：与 [rs, re_] 有交集
        s = r.start_date.date() if r.start_date else None
        e = r.end_date.date() if r.end_date else None
        lo = s or e
        hi = e or s
        if lo is None or not (lo <= re_ and hi >= rs):
            continue
        range_total += 1
        cname = cmap.get(r.customer_id) or "未指定"
        pname, gname = umap.get(r.user_id, ("未指定", ""))
        pname = pname or "未指定"
        gname = gname or "未指定领域"
        by_cust[cname] = by_cust.get(cname, 0) + 1
        by_person[pname] = by_person.get(pname, 0) + 1
        by_domain[gname] = by_domain.get(gname, 0) + 1

    def _mk(d: dict) -> List[schemas.TripDimStat]:
        return [
            schemas.TripDimStat(name=k, count=v)
            for k, v in sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))
        ]

    return schemas.BusinessTripDashboardOut(
        on_trip_now=on_now, planned=planned,
        range_label=f"{rs.isoformat()} ~ {re_.isoformat()}",
        range_total=range_total,
        by_customer=_mk(by_cust), by_person=_mk(by_person), by_domain=_mk(by_domain),
    )


@router.post("", response_model=schemas.BusinessTripOut)
def create_trip(
    payload: schemas.BusinessTripCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    obj = models.BusinessTrip(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    log_op(db, action="新增", target="成员出差", target_id=obj.id,
           detail=f"user_id={obj.user_id} customer_id={obj.customer_id}",
           user=current_user, request=request)
    return _trip_out(obj, _user_map(db), _cust_map(db))


@router.put("/{trip_id}", response_model=schemas.BusinessTripOut)
def update_trip(
    trip_id: int,
    payload: schemas.BusinessTripUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    obj = db.query(models.BusinessTrip).filter(models.BusinessTrip.id == trip_id).first()
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
    log_op(db, action="修改", target="成员出差", target_id=obj.id,
           detail=f"fields={','.join(changes.keys()) or '无'}",
           user=current_user, request=request)
    return _trip_out(obj, _user_map(db), _cust_map(db))


@router.delete("/{trip_id}")
def delete_trip(
    trip_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    obj = db.query(models.BusinessTrip).filter(models.BusinessTrip.id == trip_id).first()
    if not obj:
        raise HTTPException(404, "Not found")
    db.delete(obj)
    db.commit()
    log_op(db, action="删除", target="成员出差", target_id=trip_id,
           detail="", user=current_user, request=request)
    return {"ok": True}
