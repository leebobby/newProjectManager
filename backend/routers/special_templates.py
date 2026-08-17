"""专项模板（版式预设）：主数据，admin 增删改，所有登录用户可读。

读权限开放给所有登录用户：建专项虽然只有 admin 能做，但详情页要显示
「当前版式来自哪个模板」，而且模板清单本身不含业务数据。
写权限按 CLAUDE.md 的 Write-permission principle 落「仅 admin」档——
模板是配置类主数据，误改会影响此后所有新建专项。
"""
import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

import models
import schemas
import special_layout
from auth import get_current_user, require_admin
from database import get_db
from enums import GRID_COL_TYPES, SPECIAL_BLOCK_KINDS, SPECIAL_SECTION_KEYS
from op_log import log_op

router = APIRouter(prefix="/api/special-templates", tags=["special-templates"])


def _get_or_404(db: Session, tid: int) -> models.SpecialTemplate:
    item = db.query(models.SpecialTemplate).filter(
        models.SpecialTemplate.id == tid).first()
    if not item:
        raise HTTPException(404, "模板不存在")
    return item


def _validate_layout(raw: str) -> str:
    """校验并规范化 layout_json，非法结构一律 400。

    模板会被套到任意专项上，脏结构在这里放过去就会变成详情页/导出的运行期异常，
    所以入口处按内置分段白名单逐 key 校验，落库前统一序列化一遍。
    """
    try:
        layout = json.loads(raw or "{}")
    except (ValueError, TypeError):
        raise HTTPException(400, "layout_json 不是合法 JSON")
    if not isinstance(layout, dict):
        raise HTTPException(400, "layout_json 应为对象")

    blocks_in = layout.get("blocks") or []
    if not isinstance(blocks_in, list):
        raise HTTPException(400, "layout.blocks 应为数组")
    blocks = []
    seen_tkey = set()
    for b in blocks_in:
        if not isinstance(b, dict):
            raise HTTPException(400, "layout.blocks 的元素应为对象")
        tkey = str(b.get("tkey") or "").strip()
        if not tkey:
            raise HTTPException(400, "自定义分段缺少 tkey")
        if tkey in seen_tkey:
            raise HTTPException(400, f"自定义分段 tkey 重复：{tkey}")
        seen_tkey.add(tkey)
        kind = b.get("kind") or "grid"
        if kind not in SPECIAL_BLOCK_KINDS:
            raise HTTPException(400, f"分段类型「{kind}」非法，应为 {'/'.join(SPECIAL_BLOCK_KINDS)}")
        types = b.get("colTypes") or []
        if not isinstance(types, list):
            raise HTTPException(400, "colTypes 应为数组")
        for t in types:
            if t not in GRID_COL_TYPES:
                raise HTTPException(400, f"列格式「{t}」非法，应为 {'/'.join(GRID_COL_TYPES)}")
        blocks.append(b)

    cfg_in = layout.get("config") or {}
    if not isinstance(cfg_in, dict):
        raise HTTPException(400, "layout.config 应为对象")
    config = {}
    for key, entry in cfg_in.items():
        if key not in SPECIAL_SECTION_KEYS:
            raise HTTPException(400, f"未知内置分段：{key}")
        if not isinstance(entry, dict):
            raise HTTPException(400, f"分段 {key} 的配置应为对象")
        config[key] = {"title": str(entry.get("title") or "").strip(),
                       "enabled": entry.get("enabled") is not False}

    order_in = layout.get("order") or []
    if not isinstance(order_in, list):
        raise HTTPException(400, "layout.order 应为数组")
    valid = set(SPECIAL_SECTION_KEYS) | {f"tpl:{t}" for t in seen_tkey}
    order = []
    for key in order_in:
        if not isinstance(key, str) or key not in valid:
            raise HTTPException(400, f"order 里的「{key}」既不是内置分段也不对应任何自定义分段")
        order.append(key)

    return json.dumps({"order": special_layout.dedupe(order),
                       "config": config, "blocks": blocks}, ensure_ascii=False)


@router.get("/sections")
def list_builtin_sections(_: models.User = Depends(get_current_user)):
    """内置分段清单，给模板编辑页列可选项（默认标题按「专项」口径给）。"""
    return {"sections": special_layout.builtin_registry(),
            "block_kinds": list(SPECIAL_BLOCK_KINDS),
            "col_types": list(GRID_COL_TYPES)}


@router.get("", response_model=List[schemas.SpecialTemplateOut])
def list_templates(
    include_inactive: bool = False,
    kind: str = "",
    _: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(models.SpecialTemplate)
    if not include_inactive:
        q = q.filter(models.SpecialTemplate.is_active.is_(True))
    if kind in ("special", "assault"):
        # kind 为空的模板是通用模板，两种类型都能选
        q = q.filter(models.SpecialTemplate.kind.in_([kind, ""]))
    return q.order_by(models.SpecialTemplate.sort_order,
                      models.SpecialTemplate.id).all()


@router.get("/{tid}", response_model=schemas.SpecialTemplateOut)
def get_template(tid: int, _: models.User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    return _get_or_404(db, tid)


@router.post("", response_model=schemas.SpecialTemplateOut)
def create_template(
    payload: schemas.SpecialTemplateCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    data = payload.model_dump()
    if not str(data.get("name") or "").strip():
        raise HTTPException(400, "模板名不能为空")
    if data.get("kind") not in ("special", "assault", "", None):
        raise HTTPException(400, "kind 仅支持 special / assault / 空")
    data["kind"] = data.get("kind") or ""
    data["layout_json"] = _validate_layout(data.get("layout_json"))
    item = models.SpecialTemplate(**data)
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target="专项模板", target_id=item.id,
           detail=f"name={item.name}", user=current_admin, request=request)
    return item


@router.put("/{tid}", response_model=schemas.SpecialTemplateOut)
def update_template(
    tid: int,
    payload: schemas.SpecialTemplateUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = _get_or_404(db, tid)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and not str(data["name"] or "").strip():
        raise HTTPException(400, "模板名不能为空")
    if "kind" in data:
        if data["kind"] not in ("special", "assault", "", None):
            raise HTTPException(400, "kind 仅支持 special / assault / 空")
        data["kind"] = data["kind"] or ""
    if "layout_json" in data:
        data["layout_json"] = _validate_layout(data["layout_json"])
    for k, v in data.items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target="专项模板", target_id=item.id,
           detail=f"name={item.name} fields={','.join(data.keys()) or '无'}",
           user=current_admin, request=request)
    return item


@router.delete("/{tid}")
def delete_template(
    tid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    """删除模板。已套用该模板的专项不受影响——版式在套用时已落到各专项自己的行上。"""
    item = _get_or_404(db, tid)
    name = item.name
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target="专项模板", target_id=tid,
           detail=f"name={name}", user=current_admin, request=request)
    return {"ok": True}
