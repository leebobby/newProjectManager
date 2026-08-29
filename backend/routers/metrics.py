"""度量接口：版本质量 / 领域质量 / 迭代质量 / 组级负载。

**质量看两个维度，各有各的口径，别互换**：

| 维度 | 口径 | 接口 |
| --- | --- | --- |
| 版本质量 | **整个版本**（C10SPC101 这一层，跨迭代） | `GET /version/{release_version_id}` |
| 领域质量 | **一个迭代**（按月排活） | `GET /domain-quality/{iteration_id}` |

领域是按月排活的，问「这个月各领域干得怎么样」才有意义；版本是跨月的，
按月截一刀会得到一个既不是这个版本、也不是这个月的数（同 domains._ReqScope 的取舍）。
两个接口的行形状共用 `DomainQualityRow`——各定义一份的话，同一批字段会长出两套列名。

**质量字段（代码量 / 自验证用例 / 转测后问题单）只有领域需求有**：
版本口径的 total 把产品需求也算进来（进度要看全），但 by_domain 各行只数领域需求，
两个数对不上是正常的，表头要写明白。

设计要点：
- 完成率算法：把 6/7 个进展子项按"已完成 = 1.0、进行中 = 0.5、未开始/已延期 = 0、不涉及 = 不计入"加权
- 优先用 owner_user_id / group_id / target_version_id FK；FK 为空时回退到字符串
- 所有接口对登录用户可读（PM 周报场景）

**「已变更」整行排除**：任一进展子项标了「已变更」＝这条需求本轮不做了，
四个接口一律**不统计它**（判定见 `enums.is_changed_row`）。和 `unassigned` 一样，
响应里带一个 `changed` 报出被排除的条数，否则「数字怎么少了一截」没人说得清。

**按项目度量**：四个接口都接受可选的 `project_id`。项目挂在需求行上
（迭代本身跨项目，见 models.AnnualIteration），传了就**只统计该项目的行**，
不把 project_id 为空的老数据算进任何一个项目——数字看着都合理，混进去了没人看得出来。
作为补偿，响应里带一个 `unassigned`：同口径下还没填项目、因而没被计入的条数，
前端据此提示去补，而不是让人对着一个偏小的数字纳闷。
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

import enums
import models
import schemas
from database import get_db
from routers import _issue_source, _req_scope

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
    "未开始": 0.0,
    # "不涉及" 不计入分母
    # "已变更" 不在表里是有意的：带它的行在 _split_changed() 就整行被剔掉了，
    # 到不了这里。别再给它加权重——那等于把一条已经不做的需求重新算进平均完成度。
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


def _split_changed(rows: list, progress_fields: list[str]) -> tuple[list, int]:
    """剔掉「已变更」的行，返回 (计入统计的行, 被剔掉的条数)。

    先剔已变更、再按项目切（见各接口）：反过来的话 `unassigned` 里会混进
    本来就不该统计的已变更行，页面提示「有 N 条没填项目」，去补了却发现数字纹丝不动。
    """
    kept = [r for r in rows if not enums.is_changed_row(r, progress_fields)]
    return kept, len(rows) - len(kept)


def _split_by_project(rows: list, project_id: Optional[int]) -> tuple[list, int]:
    """按项目切一刀，返回 (计入统计的行, 未指定项目而被排除的条数)。

    project_id 为 None 时不筛，`unassigned` 也归零——全量口径下没有"被排除"这回事。
    """
    if project_id is None:
        return rows, 0
    kept = [r for r in rows if r.project_id == project_id]
    blank = sum(1 for r in rows if r.project_id is None)
    return kept, blank


def _per_kloc(count: int, code_volume: int) -> float:
    """每千行代码的数量；代码量为 0 时返回 0。"""
    if not code_volume:
        return 0.0
    return round(count / (code_volume / 1000.0), 2)


# ─── 按领域（PL 组）分行的质量聚合 ─────────────────────────────────────────
class DomainQualityRow(BaseModel):
    """一个领域在某个口径下的质量数字。

    版本口径与迭代口径共用这一个形状：两边各定义一份的话，同一批字段会长出
    两套列名，前端也得写两份表格。快照问题单两列只有版本口径填得出来
    （快照没有迭代维度，见 domain_quality 的说明），迭代口径下留空。
    """
    group_id: Optional[int]          # None ＝ 未指定领域
    group_name: str
    total: int                       # 领域需求条数（已剔除「已变更」）
    done: int
    avg_completion: float
    code_volume: int
    self_test_cases: int
    self_test_case_density: float
    post_test_issues: int            # 需求行上人填的「转测后问题单数」
    post_test_issue_density: float
    snapshot_issues: Optional[int] = None   # 采集快照里命中该版本 + 该领域的条数
    snapshot_score: Optional[float] = None  # 同上的加权分（致命10/严重3/一般1/提示0.1）


def _group_name_map(db: Session) -> dict[int, str]:
    return {g.id: g.name for g in db.query(models.ResourceGroup).all()}


def _by_domain_rows(db: Session, rows: list) -> List[DomainQualityRow]:
    """把领域需求按 group_id 分组算质量。

    **只列当前口径下确实挂着需求的领域**：把所有 PL 组都铺出来，一屏全是 0，
    真正在干活的那几行反而找不到。没填 PL 组的行归到「未指定领域」一行——
    和「未指定项目」同理，那正是最该被捞出来补录的那批，藏起来就永远没人去补。
    """
    names = _group_name_map(db)
    buckets: dict[Optional[int], list] = {}
    for r in rows:
        buckets.setdefault(r.group_id, []).append(r)

    out: List[DomainQualityRow] = []
    for gid, rs in buckets.items():
        cv = sum(r.code_volume or 0 for r in rs)
        cases = sum(r.self_test_case_count or 0 for r in rs)
        issues = sum(r.post_test_issue_count or 0 for r in rs)
        cs = [_row_completion(r, _DOMAIN_PROGRESS_FIELDS) for r in rs]
        out.append(DomainQualityRow(
            group_id=gid,
            group_name=names.get(gid) or ("未指定领域" if gid is None else f"#{gid}"),
            total=len(rs),
            done=sum(1 for r in rs if _is_done(r, _DOMAIN_PROGRESS_FIELDS)),
            avg_completion=round(sum(cs) / len(cs), 3) if cs else 0.0,
            code_volume=cv,
            self_test_cases=cases,
            self_test_case_density=_per_kloc(cases, cv),
            post_test_issues=issues,
            post_test_issue_density=_per_kloc(issues, cv),
        ))
    # 未指定领域固定排最后，其余按需求条数倒序：一屏之内先看到干得最多的那几个领域
    out.sort(key=lambda r: (r.group_id is None, -r.total, r.group_name))
    return out


# ─── 版本 × 问题单：把采集来的单按「版本信息」挂到版本上 ────────────────────
class VersionIssueStat(BaseModel):
    """采集快照里命中该版本的问题单情况，**带匹配率**。

    快照行的「版本信息」是 DTS 那边的自由串（多数是 pbiName），和三层版本号
    不保证对得上。所以这里既不硬猜也不静默丢：只做**精确匹配**
    （版本号本身 + 名下所有构建号，与 _req_scope.version_clause 同一份口径），
    命中多少如实报，没命中的取值也报出来——匹配率低时一眼能看出是命名没对上，
    而不是"这个版本怎么一个问题单都没有"。模糊匹配是明确不做的：
    C10SPC101 很容易被认到 C10SPC1011 上，错挂的单在质量表里只是数字偏一点。
    """
    available: bool = False
    note: Optional[str] = None
    source: str = ""                  # snapshot / excel
    project: Optional[str] = None
    stamp: Optional[str] = None       # 快照日 / Excel 文件时间
    total: int = 0                    # 数据源里的总条数
    matched: int = 0                  # 「版本信息」命中该版本的条数
    match_rate: float = 0.0
    unmatched_top: List[str] = []     # 没命中的「版本信息」取值 Top 8（形如 "YLS3000×132"）


def _version_issue_rows(src: "_issue_source.IssueSource", rv: models.ReleaseVersion
                        ) -> tuple[List[dict], VersionIssueStat]:
    if src.rows is None:
        return [], VersionIssueStat(available=False, note=src.note,
                                    source=src.source, project=src.project)
    nos = {n.strip() for n in _req_scope.build_no_set(rv) if n and n.strip()}
    matched: List[dict] = []
    misses: dict[str, int] = {}
    for r in src.rows:
        v = (r.get("version") or "").strip()
        if v and v in nos:
            matched.append(r)
        else:
            k = v or "（版本信息为空）"
            misses[k] = misses.get(k, 0) + 1
    total = len(src.rows)
    top = [f"{k}×{n}" for k, n in sorted(misses.items(), key=lambda kv: -kv[1])[:8]]
    return matched, VersionIssueStat(
        available=True, source=src.source, project=src.project, stamp=src.stamp,
        total=total, matched=len(matched),
        match_rate=round(len(matched) / total, 3) if total else 0.0,
        unmatched_top=top,
    )


def _fill_snapshot_columns(db: Session, rows: List[DomainQualityRow],
                           issue_rows: List[dict]) -> None:
    """给按领域分行的表补上快照问题单两列（就地改）。"""
    groups = {g.id: g for g in db.query(models.ResourceGroup).all()}
    for row in rows:
        g = groups.get(row.group_id) if row.group_id else None
        if g is None:
            # 未指定领域这一行没法按组切问题单，留空而不是记 0——
            # 0 会被读成"这个领域没问题单"，留空才是"这一格算不出来"
            continue
        rs = _issue_source.issue_rows_for_group(issue_rows, g)
        row.snapshot_issues = len(rs)
        row.snapshot_score = _issue_source.weighted_score(rs)



# ─── 版本完成率 ─────────────────────────────────────────────────────────────
class VersionItem(BaseModel):
    id: int
    kind: str        # "domain" / "product"
    title: str
    completion: float
    is_done: bool


class VersionMetric(BaseModel):
    release_version_id: int
    major_version_id: int
    version_no: str
    major_version_no: str
    total: int
    done: int
    avg_completion: float    # 0-1
    # 版本质量统计（仅领域需求填报，汇总求和）
    total_code_volume: int
    total_self_test_cases: int
    total_post_test_issues: int
    unassigned: int          # 命中该版本但没填项目、因而没被计入的条数（未按项目筛时恒为 0）
    changed: int             # 因标了「已变更」而整行排除的条数
    items: List[VersionItem]
    # 按领域拆开的质量：**质量字段只有领域需求有**，所以这几行的 total 是领域需求条数，
    # 与上面把产品需求也算进来的 total 对不上——这不是 bug，表头要写明白。
    by_domain: List[DomainQualityRow] = []
    total_self_test_case_density: float = 0.0
    total_post_test_issue_density: float = 0.0
    issues: VersionIssueStat = VersionIssueStat()
    issue_projects: List[schemas.DomainProjectOpt] = []


@router.get("/version/{release_version_id}", response_model=VersionMetric)
def version_metric(
    release_version_id: int,
    project_id: Optional[int] = Query(None, description="只统计该项目的需求；不传＝全部"),
    issue_project: Optional[str] = Query(None, description="问题单快照取哪个项目；不传＝第一个有快照的"),
    db: Session = Depends(get_db),
):
    """版本达成率 —— 看的是「版本」这一层（C10SPC101），不是大版本。

    需求填的是迭代版本（C10SPC101B001），所以这里把该版本下所有构建的 id 收齐再聚合；
    字符串回退时把版本号本身也算进来，因为不少需求就直接写了 C10SPC101。
    """
    rv = db.query(models.ReleaseVersion).filter(
        models.ReleaseVersion.id == release_version_id).first()
    if not rv:
        raise HTTPException(404, "Not found")
    mv = rv.major_version

    # 取领域 / 产品需求：FK 命中 或 字符串命中。匹配规则收口在 _req_scope，
    # 领域总览的「按版本」口径走的是同一份，否则同一个版本两个页面给出不同条数。
    domain_q = db.query(models.IterationRequirement).filter(
        _req_scope.version_clause(models.IterationRequirement, rv))
    product_q = db.query(models.IterationProductRequirement).filter(
        _req_scope.version_clause(models.IterationProductRequirement, rv))

    items: list[VersionItem] = []
    completions: list[float] = []
    done_cnt = 0
    code_volume = 0
    self_test_cases = 0
    post_test_issues = 0

    domain_rows, chg_d = _split_changed(domain_q.all(), _DOMAIN_PROGRESS_FIELDS)
    product_rows, chg_p = _split_changed(product_q.all(), _PRODUCT_PROGRESS_FIELDS)
    domain_rows, blank_d = _split_by_project(domain_rows, project_id)
    product_rows, blank_p = _split_by_project(product_rows, project_id)

    for r in domain_rows:
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
    for r in product_rows:
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

    # 按领域拆行：只用领域需求（产品需求没有 PL 组归属，也没有质量字段）
    by_domain = _by_domain_rows(db, domain_rows)
    src = _issue_source.resolve_issue_source(db, issue_project)
    issue_rows, issue_stat = _version_issue_rows(src, rv)
    _fill_snapshot_columns(db, by_domain, issue_rows)

    return VersionMetric(
        release_version_id=rv.id,
        major_version_id=rv.major_version_id,
        version_no=rv.version_no or "",
        major_version_no=(mv.version_no if mv else "") or "",
        total=len(items),
        done=done_cnt,
        avg_completion=round(avg, 3),
        total_code_volume=code_volume,
        total_self_test_cases=self_test_cases,
        total_post_test_issues=post_test_issues,
        unassigned=blank_d + blank_p,
        changed=chg_d + chg_p,
        items=items,
        by_domain=by_domain,
        # 密度的分子分母来自同一批领域需求行——只筛分子会得到一个分母含别的口径的密度，
        # 量纲对、数值错（见 CLAUDE.md「密度类指标要分子分母一起筛」）
        total_self_test_case_density=_per_kloc(self_test_cases, code_volume),
        total_post_test_issue_density=_per_kloc(post_test_issues, code_volume),
        issues=issue_stat,
        issue_projects=_issue_source.issue_projects(db),
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
    unassigned: int               # 该迭代里没填项目、因而没被计入的条数（未按项目筛时恒为 0）
    changed: int                  # 因标了「已变更」而整行排除的条数


@router.get("/iteration/{iteration_id}", response_model=IterationMetric)
def iteration_metric(
    iteration_id: int,
    project_id: Optional[int] = Query(None, description="只统计该项目的需求；不传＝全部"),
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
    domain_rows, chg_d = _split_changed(domain_rows, _DOMAIN_PROGRESS_FIELDS)
    product_rows, chg_p = _split_changed(product_rows, _PRODUCT_PROGRESS_FIELDS)
    domain_rows, blank_d = _split_by_project(domain_rows, project_id)
    product_rows, blank_p = _split_by_project(product_rows, project_id)

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
        unassigned=blank_d + blank_p,
        changed=chg_d + chg_p,
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
    changed: int = 0                 # 因标了「已变更」而整行排除的条数


@router.get("/iteration-quality/{year}", response_model=List[IterationQualityRow])
def iteration_quality_by_year(
    year: int,
    project_id: Optional[int] = Query(None, description="只统计该项目的需求；不传＝全部"),
    db: Session = Depends(get_db),
):
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
        domain_rows, chg = _split_changed(domain_rows, _DOMAIN_PROGRESS_FIELDS)
        domain_rows, _ = _split_by_project(domain_rows, project_id)
        cv = sum(r.code_volume or 0 for r in domain_rows)
        cases = sum(r.self_test_case_count or 0 for r in domain_rows)
        issues = sum(r.post_test_issue_count or 0 for r in domain_rows)
        rows.append(IterationQualityRow(
            iteration_id=it.id, year=it.year, month=it.month, name=it.name or "",
            code_volume=cv, self_test_cases=cases, post_test_issues=issues,
            self_test_case_density=_per_kloc(cases, cv),
            post_test_issue_density=_per_kloc(issues, cv),
            changed=chg,
        ))
    return rows


# ─── 领域质量（按迭代）────────────────────────────────────────────────────
class DomainQualityOut(BaseModel):
    iteration_id: int
    year: int
    month: int
    name: str
    rows: List[DomainQualityRow]
    # 合计＝各行相加，前端不用自己加一遍（加法散在两端迟早对不上）
    total: int
    done: int
    avg_completion: float
    code_volume: int
    self_test_cases: int
    self_test_case_density: float
    post_test_issues: int
    post_test_issue_density: float
    unassigned: int
    changed: int


@router.get("/domain-quality/{iteration_id}", response_model=DomainQualityOut)
def domain_quality(
    iteration_id: int,
    project_id: Optional[int] = Query(None, description="只统计该项目的需求；不传＝全部"),
    db: Session = Depends(get_db),
):
    """某个迭代里各领域的质量数字。

    **领域看迭代、版本看整个版本**，是两个口径各自的自然粒度：领域是按月排活的，
    问「这个月各领域干得怎么样」才有意义；版本是跨月的，按月截一刀会得到一个
    既不是这个版本、也不是这个月的数（同 domains._ReqScope 的取舍）。

    **这里没有采集问题单那两列**：快照是"当天还开着的单"，没有迭代维度，
    按月摊给某个迭代是编的。这里的「转测后问题单」是需求行上人填的那一列。
    版本口径下才有快照问题单（能按「版本信息」精确匹配），见 VersionIssueStat。
    """
    it = db.query(models.AnnualIteration).filter(
        models.AnnualIteration.id == iteration_id).first()
    if not it:
        raise HTTPException(404, "Not found")

    rows = (
        db.query(models.IterationRequirement)
        .filter(models.IterationRequirement.iteration_id == iteration_id).all()
    )
    rows, chg = _split_changed(rows, _DOMAIN_PROGRESS_FIELDS)
    rows, blank = _split_by_project(rows, project_id)

    by_domain = _by_domain_rows(db, rows)
    cv = sum(r.code_volume or 0 for r in rows)
    cases = sum(r.self_test_case_count or 0 for r in rows)
    issues = sum(r.post_test_issue_count or 0 for r in rows)
    cs = [_row_completion(r, _DOMAIN_PROGRESS_FIELDS) for r in rows]
    return DomainQualityOut(
        iteration_id=it.id, year=it.year, month=it.month, name=it.name or "",
        rows=by_domain,
        total=len(rows),
        done=sum(1 for r in rows if _is_done(r, _DOMAIN_PROGRESS_FIELDS)),
        avg_completion=round(sum(cs) / len(cs), 3) if cs else 0.0,
        code_volume=cv,
        self_test_cases=cases,
        self_test_case_density=_per_kloc(cases, cv),
        post_test_issues=issues,
        post_test_issue_density=_per_kloc(issues, cv),
        unassigned=blank,
        changed=chg,
    )


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
    unassigned: int          # 该组名下没填项目、因而没被计入的条数（未按项目筛时恒为 0）
    changed: int             # 因标了「已变更」而整行排除的条数
    by_member: List[GroupMemberLoad]


@router.get("/group/{group_id}", response_model=GroupLoad)
def group_load(
    group_id: int,
    year: Optional[int] = Query(None, description="按年度过滤；不传则全量"),
    project_id: Optional[int] = Query(None, description="只统计该项目的需求；不传＝全部"),
    db: Session = Depends(get_db),
):
    g = db.query(models.ResourceGroup).filter(models.ResourceGroup.id == group_id).first()
    if not g:
        raise HTTPException(404, "Not found")

    members = db.query(models.User).filter(models.User.group_id == group_id).all()
    member_ids = [u.id for u in members]
    if not member_ids:
        return GroupLoad(group_id=g.id, group_name=g.name, total_open=0, delayed=0,
                         avg_completion=0.0, unassigned=0, changed=0, by_member=[])

    q = db.query(models.IterationRequirement).filter(
        models.IterationRequirement.owner_user_id.in_(member_ids)
    )
    if year is not None:
        # 通过 iteration join 过滤年份
        ann_ids = [i.id for i in db.query(models.AnnualIteration).filter(
            models.AnnualIteration.year == year
        ).all()]
        q = q.filter(models.IterationRequirement.iteration_id.in_(ann_ids or [0]))
    rows, chg = _split_changed(q.all(), _DOMAIN_PROGRESS_FIELDS)
    rows, blank = _split_by_project(rows, project_id)

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
        unassigned=blank,
        changed=chg,
        by_member=out_members,
    )
