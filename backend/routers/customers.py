"""客户主数据 CRUD。

设计要点：
- code 全局唯一，作为业务主键 / 默认展示名（缩写英文）
- 别名(alias)全局唯一，方便按字符串反查归并到客户
- 详情/列表对所有登录用户开放；写操作仅管理员
- 更新走乐观锁（version）；aliases 字段如果提供则全量替换
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

import models
import schemas
from auth import require_admin
from database import get_db
from op_log import log_op

router = APIRouter(prefix="/api/customers", tags=["customers"])


def _clean_aliases(values: List[str]) -> List[str]:
    """去重 + 去空白；保持首次出现顺序。"""
    seen, out = set(), []
    for v in values or []:
        s = (v or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _check_alias_conflicts(db: Session, aliases: List[str], owner_id: Optional[int]) -> None:
    """确认这些 alias 当前没有被其它客户占用；owner_id 为当前客户，自身已有的允许保留。"""
    if not aliases:
        return
    q = db.query(models.CustomerAlias).filter(models.CustomerAlias.alias.in_(aliases))
    if owner_id is not None:
        q = q.filter(models.CustomerAlias.customer_id != owner_id)
    hit = q.first()
    if hit:
        raise HTTPException(status_code=400, detail=f"别名「{hit.alias}」已被其它客户占用")


def _replace_aliases(db: Session, customer: models.Customer, aliases: List[str]) -> None:
    aliases = _clean_aliases(aliases)
    _check_alias_conflicts(db, aliases, customer.id)
    # 简单粗暴：先删后插。客户别名量级很小，不必做最小化 diff。
    db.query(models.CustomerAlias).filter(
        models.CustomerAlias.customer_id == customer.id
    ).delete(synchronize_session=False)
    db.flush()
    for a in aliases:
        db.add(models.CustomerAlias(customer_id=customer.id, alias=a))


@router.get("", response_model=List[schemas.CustomerOut])
def list_customers(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
):
    q = db.query(models.Customer)
    if not include_inactive:
        q = q.filter(models.Customer.is_active.is_(True))
    return q.order_by(models.Customer.sort_order, models.Customer.id).all()


@router.get("/resolve", response_model=Optional[schemas.CustomerOut])
def resolve_customer(
    name: str = Query(..., description="客户的 code 或任意别名"),
    db: Session = Depends(get_db),
):
    """通过 code 或别名查找客户；找不到返回 null。供其它模块按字符串匹配老数据用。"""
    s = (name or "").strip()
    if not s:
        return None
    cu = db.query(models.Customer).filter(models.Customer.code == s).first()
    if cu:
        return cu
    al = db.query(models.CustomerAlias).filter(models.CustomerAlias.alias == s).first()
    if al:
        return al.customer
    return None


@router.get("/{customer_id}", response_model=schemas.CustomerOut)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    cu = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if not cu:
        raise HTTPException(404, "Not found")
    return cu


def _customer_name_set(cu: models.Customer) -> list[str]:
    """该客户在业务表里可能出现的所有字符串：code + 所有 alias。"""
    names = [cu.code]
    names.extend(a.alias for a in (cu.aliases or []))
    return names


@router.get("/{customer_id}/machines", response_model=List[schemas.CustomerMachineOut])
def list_customer_machines(customer_id: int, db: Session = Depends(get_db)):
    """客户详情页：取出该客户名下的所有机台（来自 customer_status）。

    优先走 customer_status.customer_id FK；
    向后兼容：未对账的旧行按 battlefield ∈ {code, ...aliases} 字符串匹配兜底。
    """
    cu = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if not cu:
        raise HTTPException(404, "Not found")
    names = _customer_name_set(cu)
    # FK 命中的（权威）+ FK 为空但名字命中的（向后兼容）
    from sqlalchemy import or_
    rows = (
        db.query(models.CustomerStatus)
        .filter(or_(
            models.CustomerStatus.customer_id == cu.id,
            (models.CustomerStatus.customer_id.is_(None)) & (models.CustomerStatus.battlefield.in_(names)),
        ))
        .order_by(models.CustomerStatus.machine_id)
        .all()
    )
    return rows


@router.post("", response_model=schemas.CustomerOut)
def create_customer(
    payload: schemas.CustomerCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    code = payload.code.strip()
    if not code:
        raise HTTPException(400, "code 不能为空")
    exists = db.query(models.Customer).filter(models.Customer.code == code).first()
    if exists:
        raise HTTPException(400, f"客户编码「{code}」已存在")

    data = payload.model_dump(exclude={"aliases"})
    data["code"] = code
    cu = models.Customer(**data)
    db.add(cu)
    db.flush()  # 拿到 cu.id
    _replace_aliases(db, cu, payload.aliases)
    db.commit()
    db.refresh(cu)
    log_op(db, action="新增", target="客户", target_id=cu.id,
           detail=f"code={cu.code} aliases={len(cu.aliases)}",
           user=current_admin, request=request)
    return cu


@router.put("/{customer_id}", response_model=schemas.CustomerOut)
def update_customer(
    customer_id: int,
    payload: schemas.CustomerUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    cu = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if not cu:
        raise HTTPException(404, "Not found")
    if cu.version != payload.version:
        raise HTTPException(409, "数据已被他人修改，请刷新后重试")

    changes = payload.model_dump(exclude_unset=True)
    changes.pop("version", None)
    aliases = changes.pop("aliases", None)

    # code 唯一性
    new_code = changes.get("code")
    if new_code is not None:
        new_code = new_code.strip()
        if not new_code:
            raise HTTPException(400, "code 不能为空")
        clash = (
            db.query(models.Customer)
            .filter(models.Customer.code == new_code, models.Customer.id != cu.id)
            .first()
        )
        if clash:
            raise HTTPException(400, f"客户编码「{new_code}」已存在")
        changes["code"] = new_code

    for k, v in changes.items():
        setattr(cu, k, v)

    if aliases is not None:
        _replace_aliases(db, cu, aliases)

    cu.version += 1
    db.commit()
    db.refresh(cu)
    log_op(db, action="修改", target="客户", target_id=cu.id,
           detail=f"code={cu.code} fields={','.join(changes.keys()) or '无'}"
                  + (f" aliases={len(cu.aliases)}" if aliases is not None else ""),
           user=current_admin, request=request)
    return cu


@router.delete("/{customer_id}")
def delete_customer(
    customer_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    cu = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if not cu:
        raise HTTPException(404, "Not found")
    snapshot = f"code={cu.code}"
    db.delete(cu)  # cascade 会自动删 aliases
    db.commit()
    log_op(db, action="删除", target="客户", target_id=customer_id,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}
