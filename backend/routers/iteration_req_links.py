"""产品需求 ↔ 领域需求的**拆解关系**。

一行关联＝「这条产品需求由这条领域需求承接」。为什么是独立的一张关联表而不是
在领域需求上加一个父外键，见 `models.IterationRequirementLink` 的说明
（一条领域需求可以承接多条产品需求；挂接不该去 PUT 别人正在编辑的需求行）。

口径上有三条硬规则，改之前先读：

- **关联本身不承载进展**。「这条产品需求拆下去做到哪儿了」由领域需求行现算
  （`_req_progress`，与度量看板同一份），关联表里不存任何汇总数字。存一份的话，
  领域需求那边一改，产品需求页上的数字就停在上一次挂接的时刻，而两边看着都对。
- **产品需求自己那 7 个进展子项不被拆解汇总覆盖，也不该被覆盖**。它答的是
  「这条产品需求的串讲/澄清/测试结论走到哪一步」，拆解汇总答的是「底下几条领域
  需求做完没有」——两个问题。所以页面上是并排两列，不是一列。
- **跨迭代关联允许，但要标出来**（`cross_iteration`）。同一条需求本轮没做完、
  下个月接着排是正常的（同 `_req_dedup` 的跨迭代口径）；限定同迭代会让产品需求
  在下个月凭空变成"未拆解"。

权限：读＝登录用户；增 / 改 / 删＝**登录用户**。按「删掉的是什么」定档
（见 CLAUDE.md「Write-permission principle」）：解挂丢掉的是一条挂接关系，
两条需求本身一行不动，重新挂上就是再点一次——与"别人跟了几周的进展"不是一回事。
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

import models
import schemas
from auth import get_current_user
from database import get_db
from op_log import log_op
from routers._lookups import project_name_map, resolve_release_version_id
from routers._req_progress import (
    DOMAIN_PROGRESS_FIELDS, PRODUCT_PROGRESS_FIELDS, is_done, row_completion,
)

import enums

router = APIRouter(prefix="/api/iteration-req-links", tags=["iteration-req-links"])

_PRODUCT = models.IterationProductRequirement
_DOMAIN = models.IterationRequirement

#: 候选检索一次最多返回多少条。搜索框是用来"找到那一条"的，不是用来翻全表的
_CANDIDATE_LIMIT = 100


class _Ctx:
    """一次请求内的反查缓存：迭代名、项目名、版本→版本(release)。

    列表接口一次要摊开几十条关联、每条两侧，逐行去查就是 N+1；这些映射一次性
    取全，之后全在内存里。
    """

    def __init__(self, db: Session):
        self.db = db
        self.iterations = {i.id: f"{i.year}-{i.month:02d}"
                           for i in db.query(models.AnnualIteration).all()}
        self.projects = project_name_map(db)
        self.iv_release = {iv.id: iv.release_version_id
                           for iv in db.query(models.IterationVersion).all()}
        self._by_text: dict = {}

    def release_id_of(self, row) -> Optional[int]:
        """这条需求的计划交付**版本**（release 层）id；推不出来返回 None。

        FK 优先；FK 为空才看字符串快照（老需求里不少直接把版本号写进了
        planned_version，FK 还没反查上）——同 `_req_scope.version_clause()`。
        """
        if row.target_version_id:
            return self.iv_release.get(row.target_version_id)
        text = (row.planned_version or "").strip()
        if not text:
            return None
        if text not in self._by_text:
            self._by_text[text] = resolve_release_version_id(self.db, text)
        return self._by_text[text]


def _side(row, fields: List[str], ctx: _Ctx) -> schemas.ReqLinkSide:
    return schemas.ReqLinkSide(
        id=row.id,
        seq=row.seq,
        req_no=(row.req_no or "").strip(),
        req_url=(row.req_url or "").strip(),
        title=(row.title or "").strip(),
        iteration_id=row.iteration_id,
        iteration_label=ctx.iterations.get(row.iteration_id, str(row.iteration_id)),
        project_id=row.project_id,
        project_name=ctx.projects.get(row.project_id),
        planned_version=(row.planned_version or "").strip(),
        owner=(getattr(row, "owner", "") or "").strip(),
        owner_group=(getattr(row, "owner_group", "") or "").strip(),
        done=is_done(row, fields),
        changed=enums.is_changed_row(row, fields),
        completion=round(row_completion(row, fields), 4),
    )


def _out(link, product, domain, ctx: _Ctx) -> schemas.ReqLinkOut:
    prid = ctx.release_id_of(product)
    drid = ctx.release_id_of(domain)
    return schemas.ReqLinkOut(
        id=link.id,
        product_req_id=link.product_req_id,
        domain_req_id=link.domain_req_id,
        remark=(link.remark or "").strip(),
        cross_iteration=product.iteration_id != domain.iteration_id,
        # 两边都推得出版本、且不是同一个才算"不一致"。推不出来的一律不标——
        # 只断言"不一致"，从不断言"一致"（同 overdue_unknown：算不出来就别说）
        version_mismatch=bool(prid and drid and prid != drid),
        product=_side(product, PRODUCT_PROGRESS_FIELDS, ctx),
        domain=_side(domain, DOMAIN_PROGRESS_FIELDS, ctx),
    )


def _load_pair(db: Session, product_req_id: int, domain_req_id: int):
    product = db.query(_PRODUCT).filter(_PRODUCT.id == product_req_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品需求不存在")
    domain = db.query(_DOMAIN).filter(_DOMAIN.id == domain_req_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="领域需求不存在")
    return product, domain


@router.get("", response_model=List[schemas.ReqLinkOut])
def list_links(
    iteration_id: int = Query(..., description="迭代 ID"),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    """这个迭代**两侧任一侧**涉及到的全部关联。

    产品需求 Tab 与领域需求 Tab 吃的是同一份返回，各自按 product_req_id /
    domain_req_id 切片。两个 Tab 各拉一遍各自方向的话，同一条跨迭代关联会在
    一个 Tab 里看得见、另一个 Tab 里看不见，而两边看着都对。
    """
    prod_ids = [r[0] for r in db.query(_PRODUCT.id)
                .filter(_PRODUCT.iteration_id == iteration_id).all()]
    dom_ids = [r[0] for r in db.query(_DOMAIN.id)
               .filter(_DOMAIN.iteration_id == iteration_id).all()]
    if not prod_ids and not dom_ids:
        return []
    from sqlalchemy import or_
    links = (
        db.query(models.IterationRequirementLink)
        .filter(or_(models.IterationRequirementLink.product_req_id.in_(prod_ids or [0]),
                    models.IterationRequirementLink.domain_req_id.in_(dom_ids or [0])))
        .order_by(models.IterationRequirementLink.id.asc())
        .all()
    )
    if not links:
        return []
    products = {p.id: p for p in db.query(_PRODUCT)
                .filter(_PRODUCT.id.in_({x.product_req_id for x in links})).all()}
    domains = {d.id: d for d in db.query(_DOMAIN)
               .filter(_DOMAIN.id.in_({x.domain_req_id for x in links})).all()}
    ctx = _Ctx(db)
    out = []
    for link in links:
        p, d = products.get(link.product_req_id), domains.get(link.domain_req_id)
        if p is None or d is None:      # 理论上被 CASCADE 清掉了，防御一下
            continue
        out.append(_out(link, p, d, ctx))
    return out


@router.get("/candidates", response_model=List[schemas.ReqLinkSide])
def list_candidates(
    side: str = Query(..., description="要找哪一侧：domain＝领域需求，product＝产品需求"),
    iteration_id: int = Query(..., description="当前迭代 ID"),
    q: Optional[str] = Query(None, description="按需求编号 / 标题模糊找"),
    all_iterations: bool = Query(False, description="是否连别的迭代一起找"),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    """挂接时的候选清单。

    **默认只在当前迭代里找**：绝大多数拆解就发生在本月，一上来铺全表会把要找的
    那一条埋掉。要挂上个月那条没做完的，勾「含其它迭代」——允许但要显式，
    免得手一滑挂到一条同名的老需求上。
    """
    if side == "domain":
        model, fields = _DOMAIN, DOMAIN_PROGRESS_FIELDS
    elif side == "product":
        model, fields = _PRODUCT, PRODUCT_PROGRESS_FIELDS
    else:
        raise HTTPException(status_code=400, detail="side 应为 domain 或 product")
    query = db.query(model)
    if not all_iterations:
        query = query.filter(model.iteration_id == iteration_id)
    text = (q or "").strip()
    if text:
        like = f"%{text}%"
        from sqlalchemy import or_
        query = query.filter(or_(model.req_no.ilike(like), model.title.ilike(like)))
    rows = (query.order_by(model.iteration_id.desc(), model.seq.asc(), model.id.asc())
            .limit(_CANDIDATE_LIMIT).all())
    ctx = _Ctx(db)
    return [_side(r, fields, ctx) for r in rows]


@router.post("", response_model=schemas.ReqLinkOut)
def create_link(
    payload: schemas.ReqLinkCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    product, domain = _load_pair(db, payload.product_req_id, payload.domain_req_id)
    dup = (
        db.query(models.IterationRequirementLink)
        .filter(models.IterationRequirementLink.product_req_id == payload.product_req_id,
                models.IterationRequirementLink.domain_req_id == payload.domain_req_id)
        .first()
    )
    if dup is not None:
        # 判重在路由里做而不是只靠唯一约束：撞上约束是一条 500 + IntegrityError，
        # 页面上表现成"保存失败"，看不出是已经挂过了
        raise HTTPException(status_code=400, detail="这两条需求已经关联过了")
    link = models.IterationRequirementLink(
        product_req_id=payload.product_req_id,
        domain_req_id=payload.domain_req_id,
        remark=(payload.remark or "").strip(),
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    log_op(db, action="新增", target="需求拆解关联", target_id=link.id,
           detail=f"product_req_id={link.product_req_id} domain_req_id={link.domain_req_id}",
           user=current_user, request=request)
    return _out(link, product, domain, _Ctx(db))


@router.put("/{link_id}", response_model=schemas.ReqLinkOut)
def update_link(
    link_id: int,
    payload: schemas.ReqLinkUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    link = (db.query(models.IterationRequirementLink)
            .filter(models.IterationRequirementLink.id == link_id).first())
    if not link:
        raise HTTPException(status_code=404, detail="Not found")
    changes = payload.model_dump(exclude_unset=True)
    if "remark" in changes:
        link.remark = (changes["remark"] or "").strip()
    db.commit()
    db.refresh(link)
    product, domain = _load_pair(db, link.product_req_id, link.domain_req_id)
    log_op(db, action="修改", target="需求拆解关联", target_id=link.id,
           detail="fields=remark", user=current_user, request=request)
    return _out(link, product, domain, _Ctx(db))


@router.delete("/{link_id}")
def delete_link(
    link_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    link = (db.query(models.IterationRequirementLink)
            .filter(models.IterationRequirementLink.id == link_id).first())
    if not link:
        raise HTTPException(status_code=404, detail="Not found")
    detail = f"product_req_id={link.product_req_id} domain_req_id={link.domain_req_id}"
    db.delete(link)
    db.commit()
    log_op(db, action="删除", target="需求拆解关联", target_id=link_id,
           detail=detail, user=current_user, request=request)
    return {"ok": True}
