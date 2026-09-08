"""干系人管理：项目组沟通地图 + 战场沟通矩阵 + 关键特性责任人（FO/SE/TFO）CRUD。

权限：读取 — 所有登录用户；写入 — 仅 admin。
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

import models
import schemas
from auth import require_admin
from database import get_db
from op_log import log_op
from routers._lookups import project_name_map

router = APIRouter(prefix="/api/stakeholders", tags=["stakeholders"])


def _resolve_customer_id_by_name(db: Session, name: str):
    s = (name or "").strip()
    if not s:
        return None
    cu = db.query(models.Customer).filter(models.Customer.code == s).first()
    if cu:
        return cu.id
    al = db.query(models.CustomerAlias).filter(models.CustomerAlias.alias == s).first()
    return al.customer_id if al else None


# ── 项目组沟通地图 ──────────────────────────────────────────

@router.get("/project-contacts", response_model=List[schemas.ProjectContactOut])
def list_project_contacts(db: Session = Depends(get_db)):
    return (
        db.query(models.StakeholderProjectContact)
        .order_by(models.StakeholderProjectContact.sort_order,
                  models.StakeholderProjectContact.id)
        .all()
    )


@router.post("/project-contacts", response_model=schemas.ProjectContactOut)
def create_project_contact(
    payload: schemas.ProjectContactCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    max_order = db.query(models.StakeholderProjectContact).count()
    item = models.StakeholderProjectContact(**payload.model_dump(), sort_order=max_order)
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target="项目组联系人", target_id=item.id,
           detail=f"col1={item.col1} col2={item.col2}",
           user=current_admin, request=request)
    return item


@router.put("/project-contacts/{item_id}", response_model=schemas.ProjectContactOut)
def update_project_contact(
    item_id: int,
    payload: schemas.ProjectContactUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.StakeholderProjectContact).filter(
        models.StakeholderProjectContact.id == item_id
    ).first()
    if not item:
        raise HTTPException(404, "Not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="项目组联系人", target_id=item.id,
           detail=f"col1={item.col1} col2={item.col2}",
           user=current_admin, request=request)
    return item


@router.delete("/project-contacts/{item_id}")
def delete_project_contact(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.StakeholderProjectContact).filter(
        models.StakeholderProjectContact.id == item_id
    ).first()
    if not item:
        raise HTTPException(404, "Not found")
    snapshot = f"col1={item.col1} col2={item.col2}"
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target="项目组联系人", target_id=item_id,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}


# ── 战场沟通矩阵 ──────────────────────────────────────────

@router.get("/battlefields", response_model=List[schemas.BattlefieldOut])
def list_battlefields(db: Session = Depends(get_db)):
    return (
        db.query(models.StakeholderBattlefield)
        .order_by(models.StakeholderBattlefield.sort_order,
                  models.StakeholderBattlefield.id)
        .all()
    )


@router.post("/battlefields", response_model=schemas.BattlefieldOut)
def create_battlefield(
    payload: schemas.BattlefieldCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    max_order = db.query(models.StakeholderBattlefield).count()
    data = payload.model_dump()
    item = models.StakeholderBattlefield(
        **data, sort_order=max_order,
        customer_id=_resolve_customer_id_by_name(db, data.get("battlefield", "")),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target="战场矩阵", target_id=item.id,
           detail=f"battlefield={item.battlefield}",
           user=current_admin, request=request)
    return item


@router.put("/battlefields/{item_id}", response_model=schemas.BattlefieldOut)
def update_battlefield(
    item_id: int,
    payload: schemas.BattlefieldUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.StakeholderBattlefield).filter(
        models.StakeholderBattlefield.id == item_id
    ).first()
    if not item:
        raise HTTPException(404, "Not found")
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(item, k, v)
    # battlefield 字段被改写时，刷新 customer_id 绑定
    if "battlefield" in changes:
        item.customer_id = _resolve_customer_id_by_name(db, item.battlefield or "")
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="战场矩阵", target_id=item.id,
           detail=f"battlefield={item.battlefield}",
           user=current_admin, request=request)
    return item


@router.delete("/battlefields/{item_id}")
def delete_battlefield(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.StakeholderBattlefield).filter(
        models.StakeholderBattlefield.id == item_id
    ).first()
    if not item:
        raise HTTPException(404, "Not found")
    snapshot = f"battlefield={item.battlefield}"
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target="战场矩阵", target_id=item_id,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}


# ── 关键特性 × 项目 的 FO / SE / TFO ────────────────────────────────────────
# 「这个特性在这个项目上找谁」。同一个特性在不同项目上责任人常常不是同一批人，
# 所以项目是行上的一个维度。**FO / SE 留空＝继承 key_features 上那个特性级的责任人**，
# 并在出接口时标出来是继承的（同 domain_issue_targets：继承来的值要在界面上标出来，
# 否则改的人会以为自己在改本项目的值）。TFO 在特性表里没有对应列，空就是空。

def _feature_owner_out(
    item: models.StakeholderFeatureOwner,
    features: dict,
    projects: dict,
) -> schemas.FeatureOwnerOut:
    kf = features.get(item.key_feature_id)
    fo_own = (item.fo or "").strip()
    se_own = (item.se or "").strip()
    fo_feat = ((kf.fo if kf else "") or "").strip()
    se_feat = ((kf.se if kf else "") or "").strip()
    return schemas.FeatureOwnerOut(
        id=item.id,
        key_feature_id=item.key_feature_id,
        project_id=item.project_id,
        fo=item.fo or "", se=item.se or "", tfo=item.tfo or "",
        remark=item.remark or "", sort_order=item.sort_order or 0,
        feature_name=(kf.name if kf else ""),
        feature_status=(kf.status if kf else ""),
        project_name=projects.get(item.project_id, ""),
        fo_effective=fo_own or fo_feat,
        se_effective=se_own or se_feat,
        fo_inherited=(not fo_own) and bool(fo_feat),
        se_inherited=(not se_own) and bool(se_feat),
    )


def _feature_map(db: Session) -> dict:
    """{key_features.id: 行}。特性表只有几十行，一次取全比逐行 join 便宜（同 project_name_map）。"""
    return {f.id: f for f in db.query(models.KeyFeature).all()}


def _assert_no_dup(db: Session, key_feature_id: int, project_id, exclude_id=None):
    """同一个 (特性, 项目) 只允许一行。

    这道判重放在路由而不是数据库唯一约束上：SQLite 里 NULL 互不相等，
    带 project_id 为空的行照样能建出好几条来，约束只挡住一半，
    表现是"有时候拦得住有时候拦不住"。
    """
    q = db.query(models.StakeholderFeatureOwner).filter(
        models.StakeholderFeatureOwner.key_feature_id == key_feature_id,
        models.StakeholderFeatureOwner.project_id.is_(None)
        if project_id is None
        else models.StakeholderFeatureOwner.project_id == project_id,
    )
    if exclude_id is not None:
        q = q.filter(models.StakeholderFeatureOwner.id != exclude_id)
    if q.first():
        raise HTTPException(400, "这个关键特性在该项目下已经有一行了，直接改那一行")


@router.get("/feature-owners", response_model=List[schemas.FeatureOwnerOut])
def list_feature_owners(db: Session = Depends(get_db)):
    items = (
        db.query(models.StakeholderFeatureOwner)
        .order_by(models.StakeholderFeatureOwner.sort_order,
                  models.StakeholderFeatureOwner.id)
        .all()
    )
    features = _feature_map(db)
    projects = project_name_map(db)
    return [_feature_owner_out(i, features, projects) for i in items]


@router.post("/feature-owners", response_model=schemas.FeatureOwnerOut)
def create_feature_owner(
    payload: schemas.FeatureOwnerCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    data = payload.model_dump()
    kf = db.query(models.KeyFeature).filter(
        models.KeyFeature.id == data["key_feature_id"]
    ).first()
    if not kf:
        raise HTTPException(400, "关键特性不存在")
    _assert_no_dup(db, data["key_feature_id"], data.get("project_id"))
    max_order = db.query(models.StakeholderFeatureOwner).count()
    item = models.StakeholderFeatureOwner(**data, sort_order=max_order)
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target="关键特性责任人", target_id=item.id,
           detail=f"feature={kf.name} project_id={item.project_id}",
           user=current_admin, request=request)
    return _feature_owner_out(item, _feature_map(db), project_name_map(db))


@router.put("/feature-owners/{item_id}", response_model=schemas.FeatureOwnerOut)
def update_feature_owner(
    item_id: int,
    payload: schemas.FeatureOwnerUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.StakeholderFeatureOwner).filter(
        models.StakeholderFeatureOwner.id == item_id
    ).first()
    if not item:
        raise HTTPException(404, "Not found")
    changes = payload.model_dump(exclude_unset=True)
    if "key_feature_id" in changes and not db.query(models.KeyFeature).filter(
        models.KeyFeature.id == changes["key_feature_id"]
    ).first():
        raise HTTPException(400, "关键特性不存在")
    if "key_feature_id" in changes or "project_id" in changes:
        _assert_no_dup(
            db,
            changes.get("key_feature_id", item.key_feature_id),
            changes.get("project_id", item.project_id),
            exclude_id=item.id,
        )
    for k, v in changes.items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="关键特性责任人", target_id=item.id,
           detail=f"fields={','.join(changes.keys()) or '无'}",
           user=current_admin, request=request)
    return _feature_owner_out(item, _feature_map(db), project_name_map(db))


@router.delete("/feature-owners/{item_id}")
def delete_feature_owner(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = db.query(models.StakeholderFeatureOwner).filter(
        models.StakeholderFeatureOwner.id == item_id
    ).first()
    if not item:
        raise HTTPException(404, "Not found")
    snapshot = f"key_feature_id={item.key_feature_id} project_id={item.project_id}"
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target="关键特性责任人", target_id=item_id,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}
