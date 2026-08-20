"""客户面支撑管理（协作编辑域）。

谁、支撑哪个战场（客户主数据）与哪个项目（roadmap_projects）、现场还是线上、
哪段时间、什么事由。状态按起止日期实时推导（计划中/进行中/已完成/已取消），不入库。
登录用户均可读写，带乐观锁。

**工作量（人天）口径**收口在本文件的 `_calc_man_days()` / `_man_days_in()`，改之前先读
它们：记录填了 man_days 就以 man_days 为准，没填才按日历天数推。区间统计按重叠天数
**按比例分摊**——一条跨月的支撑不该整段算进任一个月，否则两个月的看板加起来比全年还多。
"""
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

import enums
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


def _proj_map(db: Session) -> dict:
    rows = db.query(models.RoadmapProject.id, models.RoadmapProject.name).all()
    return {r.id: (r.name or "") for r in rows}


def _span(obj: models.BusinessTrip):
    """→ (起, 止) 两个 date。只填了一头时按当天算，两头都空返回 (None, None)。"""
    s = obj.start_date.date() if obj.start_date else None
    e = obj.end_date.date() if obj.end_date else None
    lo = s or e
    hi = e or s
    if lo is None:
        return None, None
    return (lo, hi) if lo <= hi else (hi, lo)


def _cal_days(lo: date, hi: date) -> int:
    """含头含尾的日历天数。"""
    return (hi - lo).days + 1


def _calc_man_days(obj: models.BusinessTrip) -> float:
    """整段工作量：填了 man_days 用它，否则按日历天数。"""
    if obj.man_days is not None:
        return round(float(obj.man_days), 2)
    lo, hi = _span(obj)
    return float(_cal_days(lo, hi)) if lo else 0.0


def _man_days_in(obj: models.BusinessTrip, rs: date, re_: date) -> float:
    """落在 [rs, re_] 区间里的工作量。

    手填的 man_days 不知道具体分布在哪几天，只能**按重叠天数占整段的比例分摊**。
    别改成「有重叠就整段计入」——跨月的支撑会在每个月各算一遍，各月看着都对，
    加起来却比全年总量还大，而这种错没人会去核。
    """
    lo, hi = _span(obj)
    if lo is None:
        return 0.0
    a, b = max(lo, rs), min(hi, re_)
    if a > b:
        return 0.0
    total = _cal_days(lo, hi)
    overlap = _cal_days(a, b)
    if obj.man_days is None:
        return float(overlap)
    return round(float(obj.man_days) * overlap / total, 2)


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


def _trip_out(obj: models.BusinessTrip, umap: dict, cmap: dict,
              pmap: dict) -> schemas.BusinessTripOut:
    out = schemas.BusinessTripOut.model_validate(obj)
    name, group = umap.get(obj.user_id, (None, None))
    out.user_name = name
    out.user_group = group
    out.customer_name = cmap.get(obj.customer_id)
    out.project_name = pmap.get(obj.project_id)
    out.status = _status(obj)
    out.calc_man_days = _calc_man_days(obj)
    return out


def _maps(db: Session):
    return _user_map(db), _cust_map(db), _proj_map(db)


# ─── CRUD ────────────────────────────────────────────────────────────────────
@router.get("", response_model=List[schemas.BusinessTripOut])
def list_trips(
    user_id: Optional[int] = Query(None),
    customer_id: Optional[int] = Query(None),
    project_id: Optional[int] = Query(None),
    support_mode: Optional[str] = Query(None, description="现场支撑 / 线上支撑"),
    db: Session = Depends(get_db),
):
    q = db.query(models.BusinessTrip)
    if user_id is not None:
        q = q.filter(models.BusinessTrip.user_id == user_id)
    if customer_id is not None:
        q = q.filter(models.BusinessTrip.customer_id == customer_id)
    if project_id is not None:
        q = q.filter(models.BusinessTrip.project_id == project_id)
    if support_mode:
        q = q.filter(models.BusinessTrip.support_mode == support_mode)
    # 起止日期靠后的排前面（SQLite 下 DESC 时 NULL 自然殿后），再按 id
    rows = q.order_by(models.BusinessTrip.start_date.desc(),
                      models.BusinessTrip.id.desc()).all()
    umap, cmap, pmap = _maps(db)
    return [_trip_out(r, umap, cmap, pmap) for r in rows]


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
    project_id: Optional[int] = Query(None, description="只看某个支撑项目"),
    support_mode: Optional[str] = Query(None, description="只看 现场支撑 / 线上支撑"),
    db: Session = Depends(get_db),
):
    """客户面支撑看板：当前支撑中/计划中（now 快照）+ 区间内按 战场/人/领域/项目/方式
    统计人次与**工作量（人天）**。

    领域口径＝支撑人所属 PL 组。区间默认＝当月。人天口径见 `_man_days_in()`：
    跨区间的记录按重叠天数比例分摊，不整段计入。

    project_id / support_mode 这两个筛选**同时作用于 now 快照与区间统计**——
    否则上面的「当前支撑中」和下面的分项对不上，页面看着像统计错了。
    """
    today = date.today()
    rs = _parse_day(start) or date(today.year, today.month, 1)
    re_ = _parse_day(end) or today
    if re_ < rs:
        rs, re_ = re_, rs

    q = db.query(models.BusinessTrip)
    if project_id is not None:
        q = q.filter(models.BusinessTrip.project_id == project_id)
    if support_mode:
        q = q.filter(models.BusinessTrip.support_mode == support_mode)
    rows = q.all()
    umap, cmap, pmap = _maps(db)

    on_now = planned = range_total = 0
    onsite_md = online_md = 0.0
    by_cust: dict = {}
    by_person: dict = {}
    by_domain: dict = {}
    by_project: dict = {}
    by_mode: dict = {}

    def _acc(d: dict, key: str, md: float) -> None:
        cnt, tot = d.get(key, (0, 0.0))
        d[key] = (cnt + 1, tot + md)

    for r in rows:
        if r.cancelled:
            continue
        st = _status(r)
        if st == "进行中":
            on_now += 1
        elif st == "计划中":
            planned += 1
        # 区间统计：与 [rs, re_] 有交集
        md = _man_days_in(r, rs, re_)
        lo, hi = _span(r)
        if lo is None or not (lo <= re_ and hi >= rs):
            continue
        range_total += 1
        cname = cmap.get(r.customer_id) or "未指定"
        pname, gname = umap.get(r.user_id, ("未指定", ""))
        pname = pname or "未指定"
        gname = gname or "未指定领域"
        prj = pmap.get(r.project_id) or "未指定项目"
        mode = r.support_mode or enums.SUPPORT_MODE_DEFAULT
        _acc(by_cust, cname, md)
        _acc(by_person, pname, md)
        _acc(by_domain, gname, md)
        _acc(by_project, prj, md)
        _acc(by_mode, mode, md)
        if mode == "线上支撑":
            online_md += md
        else:
            onsite_md += md

    def _mk(d: dict) -> List[schemas.TripDimStat]:
        # 排序主键是人天而不是人次：看板问的是工作量投在哪儿，一个人去 30 天
        # 排在三个人各去一天后面就没意义了
        return [
            schemas.TripDimStat(name=k, count=v[0], man_days=round(v[1], 2))
            for k, v in sorted(d.items(), key=lambda kv: (-kv[1][1], -kv[1][0], kv[0]))
        ]

    return schemas.BusinessTripDashboardOut(
        on_trip_now=on_now, planned=planned,
        range_label=f"{rs.isoformat()} ~ {re_.isoformat()}",
        range_total=range_total,
        range_man_days=round(onsite_md + online_md, 2),
        onsite_man_days=round(onsite_md, 2),
        online_man_days=round(online_md, 2),
        by_customer=_mk(by_cust), by_person=_mk(by_person), by_domain=_mk(by_domain),
        by_project=_mk(by_project), by_mode=_mk(by_mode),
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
           detail=f"user_id={obj.user_id} customer_id={obj.customer_id} project_id={obj.project_id} mode={obj.support_mode}",
           user=current_user, request=request)
    return _trip_out(obj, *_maps(db))


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
    # support_mode 清空＝保持原值：这一列不可为空，前端误传空串不该把它写成 NULL
    if changes.get("support_mode") is None:
        changes.pop("support_mode", None)
    for k, v in changes.items():
        setattr(obj, k, v)
    obj.version += 1
    db.commit()
    db.refresh(obj)
    log_op(db, action="修改", target="成员出差", target_id=obj.id,
           detail=f"fields={','.join(changes.keys()) or '无'}",
           user=current_user, request=request)
    return _trip_out(obj, *_maps(db))


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
