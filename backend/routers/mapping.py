"""数据对账：把历史字符串字段批量绑定到主数据。

两条主线：
1. 客户对账：customer_status.battlefield / stakeholder_battlefields.battlefield
   按 ∈ {customer.code, ...aliases} 自动回填 customer_id；剩下的 admin 手动指。
2. 人员对账：project_formation_members.name + emp_no
   按 emp_no → full_name 顺序自动匹配 User；剩下的 admin 手动指或一键建档。
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from auth import require_admin
from database import get_db
from op_log import log_op

router = APIRouter(prefix="/api/mapping", tags=["mapping"])


# ─── 客户对账 ───────────────────────────────────────────────────────────────
def _build_name_index(db: Session) -> dict[str, int]:
    """返回 {字符串 -> customer_id} 索引；code 和 alias 都放进来。"""
    idx: dict[str, int] = {}
    for cu in db.query(models.Customer).all():
        if cu.code:
            idx[cu.code.strip()] = cu.id
    for al in db.query(models.CustomerAlias).all():
        if al.alias:
            idx[al.alias.strip()] = al.customer_id
    return idx


class CustomerUnmappedRow(BaseModel):
    source: str       # "customer_status" / "stakeholder_battlefield"
    id: int
    battlefield: str
    extra: str = ""   # 机台号 / 战场说明等辅助信息


@router.get("/customers/unmapped", response_model=List[CustomerUnmappedRow],
            dependencies=[Depends(require_admin)])
def list_customer_unmapped(db: Session = Depends(get_db)):
    out: list[CustomerUnmappedRow] = []
    for r in db.query(models.CustomerStatus).filter(
        models.CustomerStatus.customer_id.is_(None)
    ).order_by(models.CustomerStatus.id).all():
        out.append(CustomerUnmappedRow(
            source="customer_status",
            id=r.id,
            battlefield=r.battlefield or "",
            extra=f"机台 {r.machine_id}",
        ))
    for r in db.query(models.StakeholderBattlefield).filter(
        models.StakeholderBattlefield.customer_id.is_(None)
    ).order_by(models.StakeholderBattlefield.id).all():
        out.append(CustomerUnmappedRow(
            source="stakeholder_battlefield",
            id=r.id,
            battlefield=r.battlefield or "",
            extra=r.region or "",
        ))
    return out


class CustomerAutoFillResult(BaseModel):
    matched: int
    unmatched: int
    details: List[CustomerUnmappedRow]   # 剩下匹配不上的


@router.post("/customers/auto-fill", response_model=CustomerAutoFillResult,
             dependencies=[Depends(require_admin)])
def auto_fill_customers(
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    idx = _build_name_index(db)
    matched = 0
    leftover: list[CustomerUnmappedRow] = []

    for r in db.query(models.CustomerStatus).filter(
        models.CustomerStatus.customer_id.is_(None)
    ).all():
        cid = idx.get((r.battlefield or "").strip())
        if cid:
            r.customer_id = cid
            matched += 1
        else:
            leftover.append(CustomerUnmappedRow(
                source="customer_status", id=r.id,
                battlefield=r.battlefield or "", extra=f"机台 {r.machine_id}",
            ))
    for r in db.query(models.StakeholderBattlefield).filter(
        models.StakeholderBattlefield.customer_id.is_(None)
    ).all():
        cid = idx.get((r.battlefield or "").strip())
        if cid:
            r.customer_id = cid
            matched += 1
        else:
            leftover.append(CustomerUnmappedRow(
                source="stakeholder_battlefield", id=r.id,
                battlefield=r.battlefield or "", extra=r.region or "",
            ))
    db.commit()
    log_op(db, action="对账", target="客户主数据",
           detail=f"auto-fill matched={matched} leftover={len(leftover)}",
           user=current_admin, request=request)
    return CustomerAutoFillResult(matched=matched, unmatched=len(leftover), details=leftover)


class CustomerAssignPayload(BaseModel):
    source: str
    id: int
    customer_id: Optional[int]   # 传 None 表示清空


@router.put("/customers/assign", dependencies=[Depends(require_admin)])
def assign_customer(
    payload: CustomerAssignPayload,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    if payload.customer_id is not None:
        cu = db.query(models.Customer).filter(models.Customer.id == payload.customer_id).first()
        if not cu:
            raise HTTPException(400, f"客户 id={payload.customer_id} 不存在")

    if payload.source == "customer_status":
        row = db.query(models.CustomerStatus).filter(models.CustomerStatus.id == payload.id).first()
    elif payload.source == "stakeholder_battlefield":
        row = db.query(models.StakeholderBattlefield).filter(
            models.StakeholderBattlefield.id == payload.id
        ).first()
    else:
        raise HTTPException(400, f"未知 source: {payload.source}")
    if not row:
        raise HTTPException(404, "记录不存在")

    row.customer_id = payload.customer_id
    db.commit()
    log_op(db, action="对账", target="客户主数据", target_id=row.id,
           detail=f"source={payload.source} → customer_id={payload.customer_id}",
           user=current_admin, request=request)
    return {"ok": True}


# ─── 人员对账 ───────────────────────────────────────────────────────────────
def _build_user_indices(db: Session) -> tuple[dict[str, int], dict[str, int]]:
    """返回 (emp_no_idx, name_idx)。name_idx 的 value 是首个匹配；重名时不可靠。"""
    emp_idx: dict[str, int] = {}
    name_idx: dict[str, int] = {}
    for u in db.query(models.User).all():
        if u.emp_no and u.emp_no.strip():
            emp_idx[u.emp_no.strip()] = u.id
        if u.full_name and u.full_name.strip() and u.full_name not in name_idx:
            name_idx[u.full_name.strip()] = u.id
    return emp_idx, name_idx


class FormationUnmappedRow(BaseModel):
    id: int
    name: str
    emp_no: str
    pl_group: str
    role: str
    suggest_user_id: Optional[int] = None
    suggest_user_name: Optional[str] = None
    suggest_reason: Optional[str] = None   # "emp_no" / "name" / None


@router.get("/persons/formation-unmapped", response_model=List[FormationUnmappedRow],
            dependencies=[Depends(require_admin)])
def list_formation_unmapped(db: Session = Depends(get_db)):
    emp_idx, name_idx = _build_user_indices(db)
    out: list[FormationUnmappedRow] = []
    for m in db.query(models.ProjectFormationMember).filter(
        models.ProjectFormationMember.user_id.is_(None)
    ).order_by(models.ProjectFormationMember.id).all():
        suggest_id = None
        reason = None
        if m.emp_no and m.emp_no.strip() in emp_idx:
            suggest_id = emp_idx[m.emp_no.strip()]
            reason = "emp_no"
        elif m.name and m.name.strip() in name_idx:
            suggest_id = name_idx[m.name.strip()]
            reason = "name"
        suggest_name = None
        if suggest_id is not None:
            u = db.query(models.User).get(suggest_id)
            if u:
                suggest_name = u.full_name or u.username
        out.append(FormationUnmappedRow(
            id=m.id, name=m.name or "", emp_no=m.emp_no or "",
            pl_group=m.pl_group or "", role=m.role or "",
            suggest_user_id=suggest_id, suggest_user_name=suggest_name,
            suggest_reason=reason,
        ))
    return out


class PersonAutoFillResult(BaseModel):
    matched_by_emp_no: int
    matched_by_name: int
    unmatched: int


@router.post("/persons/auto-fill", response_model=PersonAutoFillResult,
             dependencies=[Depends(require_admin)])
def auto_fill_persons(
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    emp_idx, name_idx = _build_user_indices(db)
    cnt_emp = cnt_name = cnt_none = 0
    for m in db.query(models.ProjectFormationMember).filter(
        models.ProjectFormationMember.user_id.is_(None)
    ).all():
        if m.emp_no and m.emp_no.strip() in emp_idx:
            m.user_id = emp_idx[m.emp_no.strip()]
            cnt_emp += 1
        elif m.name and m.name.strip() in name_idx:
            m.user_id = name_idx[m.name.strip()]
            cnt_name += 1
        else:
            cnt_none += 1
    db.commit()
    log_op(db, action="对账", target="人员主数据",
           detail=f"emp_no={cnt_emp} name={cnt_name} leftover={cnt_none}",
           user=current_admin, request=request)
    return PersonAutoFillResult(
        matched_by_emp_no=cnt_emp, matched_by_name=cnt_name, unmatched=cnt_none,
    )


class PersonAssignPayload(BaseModel):
    member_id: int
    user_id: Optional[int]   # None = 清空


@router.put("/persons/assign", dependencies=[Depends(require_admin)])
def assign_person(
    payload: PersonAssignPayload,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    m = db.query(models.ProjectFormationMember).filter(
        models.ProjectFormationMember.id == payload.member_id
    ).first()
    if not m:
        raise HTTPException(404, "成员记录不存在")
    if payload.user_id is not None:
        if not db.query(models.User).filter(models.User.id == payload.user_id).first():
            raise HTTPException(400, f"用户 id={payload.user_id} 不存在")
    m.user_id = payload.user_id
    db.commit()
    log_op(db, action="对账", target="人员主数据", target_id=m.id,
           detail=f"member={m.name} → user_id={payload.user_id}",
           user=current_admin, request=request)
    return {"ok": True}


class CreateUserFromMemberPayload(BaseModel):
    member_id: int
    username: str           # 显式让 admin 决定登录名，默认建议用 emp_no


@router.post("/persons/create-from-member", dependencies=[Depends(require_admin)])
def create_user_from_member(
    payload: CreateUserFromMemberPayload,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    """把某阵型成员一键建档：创建一个 can_login=false 的 User，并把 member.user_id 指过去。"""
    m = db.query(models.ProjectFormationMember).filter(
        models.ProjectFormationMember.id == payload.member_id
    ).first()
    if not m:
        raise HTTPException(404, "成员记录不存在")
    if m.user_id:
        raise HTTPException(400, "该成员已绑定到 User，无需重复创建")
    username = (payload.username or "").strip()
    if not username:
        raise HTTPException(400, "请指定登录名")
    if db.query(models.User).filter(models.User.username == username).first():
        raise HTTPException(400, f"用户名「{username}」已存在")

    u = models.User(
        username=username,
        full_name=m.name or username,
        emp_no=m.emp_no or "",
        role="normal",
        auth_provider="local",
        is_active=True,
        can_login=False,
        password_hash="",
    )
    db.add(u)
    db.flush()
    m.user_id = u.id
    db.commit()
    log_op(db, action="新增", target="用户", target_id=u.id,
           detail=f"from-member username={u.username} member_id={m.id}",
           user=current_admin, request=request)
    return {"ok": True, "user_id": u.id}
