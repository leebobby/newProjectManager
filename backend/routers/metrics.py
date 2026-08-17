"""度量接口：版本完成率 / 迭代质量 / 组级负载。

设计要点：
- 完成率算法：把 6/7 个进展子项按"已完成 = 1.0、进行中 = 0.5、未开始/已延期 = 0、不涉及 = 不计入"加权
- 优先用 owner_user_id / group_id / target_version_id FK；FK 为空时回退到字符串
- 所有接口对登录用户可读（PM 周报场景）
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
from database import get_db

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


# ─── helpers ────────────────────────────────────────────────────────────────
_DOMAIN_PROGRESS_FIELDS = [
    "progress_walkthrough", "progress_reverse", "progress_stc",
    "progress_coding", "progress_bbit", "progress_clarify",
]
_PRODUCT_PROGRESS_FIELDS = [
    "progress_walkthrough", "progress_reverse", "progress_domain",
    "progress_coding", "progress_joint_debug", "progress_clarify",
    "progress_test_result",
]

_WEIGHT = {
    "已完成": 1.0,
    "进行中": 0.5,
    "已延期": 0.0,
    "已变更": 0.5,    # 变更后仍在做，按一半算
    "未开始": 0.0,
    # "不涉及" 不计入分母
}


def _completion_score(values: list[str]) -> tuple[float, int]:
    """返回 (得分, 计入分母的项数)。"""
    score = 0.0
    cnt = 0
    for v in values:
        if not v or v == "不涉及":
            continue
        cnt += 1
        score += _WEIGHT.get(v, 0.0)
    return score, cnt


def _row_completion(row, progress_fields: list[str]) -> float:
    vals = [getattr(row, f, None) for f in progress_fields]
    score, cnt = _completion_score(vals)
    return (score / cnt) if cnt else 0.0


def _is_done(row, progress_fields: list[str]) -> bool:
    """全部进展项 ∈ {已完成, 不涉及}。"""
    for f in progress_fields:
        v = getattr(row, f, None)
        if v == "不涉及" or v is None or v == "":
            continue
        if v != "已完成":
            return False
    return True


def _is_delayed(row, progress_fields: list[str]) -> bool:
    return any(getattr(row, f, None) == "已延期" for f in progress_fields)


# ─── 版本完成率 ─────────────────────────────────────────────────────────────
class VersionItem(BaseModel):
    id: int
    kind: str        # "domain" / "product"
    title: str
    completion: float
    is_done: bool


class VersionMetric(BaseModel):
    major_version_id: int
    version_no: str
    total: int
    done: int
    avg_completion: float    # 0-1
    # 版本质量统计（仅领域需求填报，汇总求和）
    total_code_volume: int
    total_self_test_cases: int
    total_post_test_issues: int
    items: List[VersionItem]


@router.get("/version/{major_version_id}", response_model=VersionMetric)
def version_metric(
    major_version_id: int,
    db: Session = Depends(get_db),
):
    mv = db.query(models.MajorVersion).filter(models.MajorVersion.id == major_version_id).first()
    if not mv:
        raise HTTPException(404, "Not found")

    # 该大版本下所有迭代版本 id
    iv_ids = [iv.id for iv in mv.iteration_versions]
    iv_no_set = {iv.version_no for iv in mv.iteration_versions if iv.version_no}
    iv_no_set.add(mv.version_no)

    # 取领域 / 产品需求，FK 命中 或 字符串命中
    domain_q = db.query(models.IterationRequirement).filter(or_(
        models.IterationRequirement.target_version_id.in_(iv_ids) if iv_ids else False,
        (models.IterationRequirement.target_version_id.is_(None)) &
        (models.IterationRequirement.planned_version.in_(iv_no_set) if iv_no_set else False),
    ))
    product_q = db.query(models.IterationProductRequirement).filter(or_(
        models.IterationProductRequirement.target_version_id.in_(iv_ids) if iv_ids else False,
        (models.IterationProductRequirement.target_version_id.is_(None)) &
        (models.IterationProductRequirement.planned_version.in_(iv_no_set) if iv_no_set else False),
    ))

    items: list[VersionItem] = []
    completions: list[float] = []
    done_cnt = 0
    code_volume = 0
    self_test_cases = 0
    post_test_issues = 0

    for r in domain_q.all():
        c = _row_completion(r, _DOMAIN_PROGRESS_FIELDS)
        done = _is_done(r, _DOMAIN_PROGRESS_FIELDS)
        items.append(VersionItem(
            id=r.id, kind="domain", title=r.title or "",
            completion=c, is_done=done,
        ))
        completions.append(c)
        if done:
            done_cnt += 1
        code_volume += r.code_volume or 0
        self_test_cases += r.self_test_case_count or 0
        post_test_issues += r.post_test_issue_count or 0
    for r in product_q.all():
        c = _row_completion(r, _PRODUCT_PROGRESS_FIELDS)
        done = _is_done(r, _PRODUCT_PROGRESS_FIELDS)
        items.append(VersionItem(
            id=r.id, kind="product", title=r.title or "",
            completion=c, is_done=done,
        ))
        completions.append(c)
        if done:
            done_cnt += 1

    avg = sum(completions) / len(completions) if completions else 0.0
    return VersionMetric(
        major_version_id=mv.id,
        version_no=mv.version_no or "",
        total=len(items),
        done=done_cnt,
        avg_completion=round(avg, 3),
        total_code_volume=code_volume,
        total_self_test_cases=self_test_cases,
        total_post_test_issues=post_test_issues,
        items=items,
    )


# ─── 迭代质量 ─────────────────────────────────────────────────────────────
class IterationMetric(BaseModel):
    iteration_id: int
    year: int
    month: int
    name: str
    total_domain: int
    total_product: int
    done_count: int
    delayed_count: int
    avg_completion: float
    by_priority: dict[str, int]   # {"P0": 3, "P1": 5, ...}


@router.get("/iteration/{iteration_id}", response_model=IterationMetric)
def iteration_metric(
    iteration_id: int,
    db: Session = Depends(get_db),
):
    it = db.query(models.AnnualIteration).filter(models.AnnualIteration.id == iteration_id).first()
    if not it:
        raise HTTPException(404, "Not found")

    domain_rows = (
        db.query(models.IterationRequirement)
        .filter(models.IterationRequirement.iteration_id == iteration_id).all()
    )
    product_rows = (
        db.query(models.IterationProductRequirement)
        .filter(models.IterationProductRequirement.iteration_id == iteration_id).all()
    )

    completions: list[float] = []
    done = 0
    delayed = 0
    by_priority: dict[str, int] = {}
    for r in domain_rows:
        c = _row_completion(r, _DOMAIN_PROGRESS_FIELDS)
        completions.append(c)
        if _is_done(r, _DOMAIN_PROGRESS_FIELDS):
            done += 1
        if _is_delayed(r, _DOMAIN_PROGRESS_FIELDS):
            delayed += 1
        p = (r.priority or "").strip() or "未设置"
        by_priority[p] = by_priority.get(p, 0) + 1
    for r in product_rows:
        c = _row_completion(r, _PRODUCT_PROGRESS_FIELDS)
        completions.append(c)
        if _is_done(r, _PRODUCT_PROGRESS_FIELDS):
            done += 1
        if _is_delayed(r, _PRODUCT_PROGRESS_FIELDS):
            delayed += 1
        p = (r.priority or "").strip() or "未设置"
        by_priority[p] = by_priority.get(p, 0) + 1

    avg = sum(completions) / len(completions) if completions else 0.0
    return IterationMetric(
        iteration_id=it.id,
        year=it.year, month=it.month, name=it.name or "",
        total_domain=len(domain_rows),
        total_product=len(product_rows),
        done_count=done,
        delayed_count=delayed,
        avg_completion=round(avg, 3),
        by_priority=by_priority,
    )


# ─── 迭代质量（按年度逐迭代的代码量/用例/密度）─────────────────────────────
class IterationQualityRow(BaseModel):
    iteration_id: int
    year: int
    month: int
    name: str
    code_volume: int                 # 代码量（行）
    self_test_cases: int             # 自验证用例数
    post_test_issues: int            # 转测后问题单数
    self_test_case_density: float    # 自验证用例密度（个/kloc）
    post_test_issue_density: float   # 转测后问题单密度（个/kloc）


def _per_kloc(count: int, code_volume: int) -> float:
    """每千行代码的数量；代码量为 0 时返回 0。"""
    if not code_volume:
        return 0.0
    return round(count / (code_volume / 1000.0), 2)


@router.get("/iteration-quality/{year}", response_model=List[IterationQualityRow])
def iteration_quality_by_year(year: int, db: Session = Depends(get_db)):
    """返回某年度每个迭代（月）的质量统计，质量数据来自领域需求填报的汇总。"""
    iters = (
        db.query(models.AnnualIteration)
        .filter(models.AnnualIteration.year == year)
        .order_by(models.AnnualIteration.month.asc())
        .all()
    )
    rows: list[IterationQualityRow] = []
    for it in iters:
        domain_rows = (
            db.query(models.IterationRequirement)
            .filter(models.IterationRequirement.iteration_id == it.id)
            .all()
        )
        cv = sum(r.code_volume or 0 for r in domain_rows)
        cases = sum(r.self_test_case_count or 0 for r in domain_rows)
        issues = sum(r.post_test_issue_count or 0 for r in domain_rows)
        rows.append(IterationQualityRow(
            iteration_id=it.id, year=it.year, month=it.month, name=it.name or "",
            code_volume=cv, self_test_cases=cases, post_test_issues=issues,
            self_test_case_density=_per_kloc(cases, cv),
            post_test_issue_density=_per_kloc(issues, cv),
        ))
    return rows


# ─── 组级负载 ─────────────────────────────────────────────────────────────
class GroupMemberLoad(BaseModel):
    user_id: int
    full_name: str
    open_count: int
    delayed_count: int
    avg_completion: float


class GroupLoad(BaseModel):
    group_id: int
    group_name: str
    total_open: int
    delayed: int
    avg_completion: float
    by_member: List[GroupMemberLoad]


@router.get("/group/{group_id}", response_model=GroupLoad)
def group_load(
    group_id: int,
    year: Optional[int] = Query(None, description="按年度过滤；不传则全量"),
    db: Session = Depends(get_db),
):
    g = db.query(models.ResourceGroup).filter(models.ResourceGroup.id == group_id).first()
    if not g:
        raise HTTPException(404, "Not found")

    members = db.query(models.User).filter(models.User.group_id == group_id).all()
    member_ids = [u.id for u in members]
    if not member_ids:
        return GroupLoad(group_id=g.id, group_name=g.name, total_open=0, delayed=0,
                         avg_completion=0.0, by_member=[])

    q = db.query(models.IterationRequirement).filter(
        models.IterationRequirement.owner_user_id.in_(member_ids)
    )
    if year is not None:
        # 通过 iteration join 过滤年份
        ann_ids = [i.id for i in db.query(models.AnnualIteration).filter(
            models.AnnualIteration.year == year
        ).all()]
        q = q.filter(models.IterationRequirement.iteration_id.in_(ann_ids or [0]))
    rows = q.all()

    by_user: dict[int, list] = {}
    for r in rows:
        by_user.setdefault(r.owner_user_id, []).append(r)

    out_members: list[GroupMemberLoad] = []
    total_open = 0
    total_delayed = 0
    total_completion: list[float] = []
    for u in members:
        rs = by_user.get(u.id, [])
        open_cnt = 0
        delayed_cnt = 0
        cs = []
        for r in rs:
            done = _is_done(r, _DOMAIN_PROGRESS_FIELDS)
            if not done:
                open_cnt += 1
            if _is_delayed(r, _DOMAIN_PROGRESS_FIELDS):
                delayed_cnt += 1
            cs.append(_row_completion(r, _DOMAIN_PROGRESS_FIELDS))
        avg = sum(cs) / len(cs) if cs else 0.0
        total_open += open_cnt
        total_delayed += delayed_cnt
        total_completion.extend(cs)
        out_members.append(GroupMemberLoad(
            user_id=u.id, full_name=u.full_name or u.username,
            open_count=open_cnt, delayed_count=delayed_cnt,
            avg_completion=round(avg, 3),
        ))

    return GroupLoad(
        group_id=g.id, group_name=g.name,
        total_open=total_open, delayed=total_delayed,
        avg_completion=round(sum(total_completion) / len(total_completion), 3)
        if total_completion else 0.0,
        by_member=out_members,
    )
