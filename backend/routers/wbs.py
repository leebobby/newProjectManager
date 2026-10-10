"""WBS：把一件事拆到能派活的粒度。

一份 WBS（`wbs_plans`）挂在**一个专项**或**一台机台的调试**上，不挂版本——
一个版本里同时跑着好几件事，挂版本就得把它们混在一棵树里。

树（`wbs_items`）**层数不限**，靠 parent_id 分层。三条口径全部收口在本文件，
改之前先读懂，页面、导出、汇总都吃这一份：

1. **能不能填，看它有没有子行，不看它在第几层。** 叶子行填人天 / 完成度 / 状态 /
   计划起止；只要挂了子行，这几项一律由 `_rollup()` 从叶子汇总，服务端算、不入库，
   写入也会被忽略。父行能单独填的话，把 `2.1` 拆开之后父子两个数就对不上了，
   而两边看着都对。
2. **完成度按人天加权**，分子分母都只数叶子：`Σ(人天×完成度) ÷ Σ人天`。
   按条数算的话，一个 20 人天的包和一个 1 人天的包各算一条。
3. **「已变更 / 不涉及」整行不进统计，但排除了多少条要如实报出来**
   （`excluded` / `excluded_days`）。只筛不报的表现是「数字怎么小了一截」，
   而没人说得清少的是哪些（同 unassigned / overdue_unknown / match_rate）。

编号（`code`，1.2.3）**不入库**，出接口时按 parent_id + sort_order 现算：
存下来的话，上移一行、加一个子项之后编号就和位置对不上了，而每一行单独看都合法。

导出有两个出口，**版面只有一份**（[wbs_diagram.py](../wbs_diagram.py)，它只算不画）：
`GET /plans/{id}/export.xlsx`（第 1 页平表 + 第 2 页调试框图 PNG）与
`GET /plans/{id}/diagram`（只回版面，页面拿它画 SVG）。前端自己再排一次的话，
同一份 WBS 在页面上是 4 列、在导出的图里是 5 列，而两边单独看都正常。
各级任务的字号阶梯在 `enums.wbs_level_font()`，页面表格 / Excel 表格 / 框图共用一份。

权限（见 CLAUDE.md「Write-permission principle」）：
- 建 / 改 WBS、以及树里的所有增删改 ＝ **登录用户**（协作编辑域的日常填报）。
  要 admin 代建的话，现场调试那边就没人建了。
- **删整份 WBS ＝ 仅 admin**，按「删掉的是什么」定档：那是别人跟了几个月的计划。
"""
from datetime import date, datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import brand
import enums
import models
import schemas
import wbs_diagram
import wbs_timeline
from auth import get_current_user, require_admin
from database import get_db
from op_log import log_op
from xlsx_io import beautify, style_header

router = APIRouter(prefix="/api/wbs", tags=["WBS"])

_UNCOUNTED = set(enums.WBS_UNCOUNTED_STATUSES)


# ─── 树的构建与汇总 ────────────────────────────────────────────────────────
def _children_map(items: List[models.WbsItem]) -> Dict[Optional[int], List[models.WbsItem]]:
    kids: Dict[Optional[int], List[models.WbsItem]] = {}
    for it in items:
        kids.setdefault(it.parent_id, []).append(it)
    for lst in kids.values():
        lst.sort(key=lambda x: (x.sort_order or 0, x.id))
    return kids


def _rollup(node: models.WbsItem, kids: Dict, out: Dict[int, dict]) -> dict:
    """后序遍历：先算子树，再把叶子的数汇总上来。返回本行的汇总字典。

    汇总只数**叶子**——中间层不重复计入，所以「2」的数字和
    「2.1.1 + 2.1.2 + 2.2 + …」永远对得上。
    """
    children = kids.get(node.id, [])
    if not children:
        counted = (node.status or "") not in _UNCOUNTED
        days = float(node.man_days or 0) if counted else 0.0
        rec = {
            "is_leaf": True, "child_count": 0,
            "roll_days": days,
            "roll_pct": int(node.progress_pct or 0) if counted else 0,
            "roll_start": node.planned_start if counted else None,
            "roll_end": node.planned_end if counted else None,
            "leaf_count": 1 if counted else 0,
            "excluded": 0 if counted else 1,
            "excluded_days": 0.0 if counted else float(node.man_days or 0),
            "_weighted": days * int(node.progress_pct or 0),
        }
        out[node.id] = rec
        return rec

    days = weighted = excl_days = 0.0
    leaf_count = excluded = 0
    starts: List[datetime] = []
    ends: List[datetime] = []
    for ch in children:
        r = _rollup(ch, kids, out)
        days += r["roll_days"]
        weighted += r["_weighted"]
        leaf_count += r["leaf_count"]
        excluded += r["excluded"]
        excl_days += r["excluded_days"]
        if r["roll_start"]:
            starts.append(r["roll_start"])
        if r["roll_end"]:
            ends.append(r["roll_end"])
    rec = {
        "is_leaf": False, "child_count": len(children),
        "roll_days": round(days, 2),
        # 人天全是 0 时完成度只能是 0——按条数退化成"平均完成度"会得到一个
        # 权重全乱的数，而它看着挺合理
        "roll_pct": int(round(weighted / days)) if days else 0,
        "roll_start": min(starts) if starts else None,
        "roll_end": max(ends) if ends else None,
        "leaf_count": leaf_count, "excluded": excluded,
        "excluded_days": round(excl_days, 2),
        "_weighted": weighted,
    }
    out[node.id] = rec
    return rec


def _is_overdue(item: models.WbsItem, is_leaf: bool, today: Optional[date] = None) -> int:
    """这一行延期了多少天。没延期（或判不了）返回 0。

    **判定只有这一份实现**：页面上那条「待补录」提示（`_issues`）与框图上的红框
    都走它。两处各写一份的表现是**表格里写着延期、图上不红**，而两边单独看都对。

    - **只判叶子**：父行的计划起止本来就是汇总来的，判它等于骂错人
      （父行红不红由它底下有没有红的叶子决定，见 `_diagram_rows`）。
    - **「已变更 / 不涉及」不算延期**：那条本轮就不做了，算进去会让「延期 N 行」
      里混着一批根本没人要做的活。
    - **「超过」才算，当天到期不算**——记成延期会让人白紧张一天（同领域管理的超期口径）。
    - 没填计划完成日的**不算延期**，但要单独报（框图的 `undated`）：
      记成"没延期"等于把一批说不出交期的行悄悄记成达标。
    """
    if not is_leaf or (item.status or "") in _UNCOUNTED:
        return 0
    if not item.planned_end or item.status == "已完成":
        return 0
    today = today or date.today()
    gap = (today - item.planned_end.date()).days
    return gap if gap > 0 else 0


def _issues(item: models.WbsItem, is_leaf: bool, today: Optional[date] = None) -> List[str]:
    """待补录提示。**只判叶子**：父行的这几项本来就是汇总来的，判它等于骂错人。

    「已过计划完成日」只提示、不自动改状态：延期是人来认的，系统替他认了的话，
    页面上写着「已延期」而当事人根本不知道是谁标的。
    """
    if not is_leaf or (item.status or "") in _UNCOUNTED:
        return []
    today = today or date.today()
    out: List[str] = []
    if not (item.owner_user_id or (item.owner or "").strip()):
        out.append("没填负责人")
    if not (item.man_days and item.man_days > 0):
        out.append("没填工期")
    if item.status == "已完成" and int(item.progress_pct or 0) < 100:
        out.append("状态是已完成，完成度却不到 100%")
    if item.planned_start and item.planned_end and item.planned_end < item.planned_start:
        out.append("计划完成早于计划开始")
    # 「超过」才算，当天到期不算——判定收口在 _is_overdue()，框图的红框走的是同一个
    if _is_overdue(item, is_leaf, today):
        out.append(f"已过计划完成日（{item.planned_end.date()}），状态还不是已完成")
    return out


def _walk(kids: Dict, parent: Optional[int], depth: int, prefix: str,
          rolls: Dict[int, dict], acc: List[dict]) -> None:
    for i, node in enumerate(kids.get(parent, []), start=1):
        code = f"{prefix}{i}" if not prefix else f"{prefix}.{i}"
        r = rolls[node.id]
        acc.append({"item": node, "code": code, "depth": depth, **r})
        _walk(kids, node.id, depth + 1, code, rolls, acc)


def _flatten(items: List[models.WbsItem]) -> List[dict]:
    """整棵树拍平成「按页面顺序」的一串，每行带 code / depth / 汇总。"""
    kids = _children_map(items)
    rolls: Dict[int, dict] = {}
    for root in kids.get(None, []):
        _rollup(root, kids, rolls)
    acc: List[dict] = []
    _walk(kids, None, 1, "", rolls, acc)
    return acc


def _ref_map(rows: List[dict]) -> Dict[int, dict]:
    """id → 这一行现在的编号与名字。编号不入库，所以前置关联的显示名只能现算。"""
    return {r["item"].id: {"code": r["code"], "name": r["item"].name or ""} for r in rows}


def _predecessors(item: models.WbsItem, refs: Dict[int, dict]) -> List[schemas.WbsItemRef]:
    """存着的 id 串 → 页面要画的那几条超链接。

    **指向的行已经被删掉时照样返回一条**（`missing=True`）：悄悄滤掉的话，
    页面上那条前置凭空消失，填的人以为自己没填过，也就永远不会去修。
    """
    out: List[schemas.WbsItemRef] = []
    for tok in str(item.predecessor_ids or "").split(","):
        tok = tok.strip()
        if not tok.isdigit():
            continue
        pid = int(tok)
        got = refs.get(pid)
        out.append(schemas.WbsItemRef(id=pid, code=(got or {}).get("code", ""),
                                      name=(got or {}).get("name", ""), missing=got is None))
    return out


def _norm_predecessors(db: Session, item: models.WbsItem, ids) -> str:
    """前置关联入库前的归一：去重、保序、限同一份 WBS、不许自引用或成环。

    **只认同一份 WBS 里的行**：前置表达的是同一件事内部的先后，跨 WBS 的先后
    是两份计划之间的事，得由别的东西表达（那条超链接也就不是"切到这棵树里的
    另一行"了）。指向自己返回 400——存进去之后那条链接点了原地不动，看着像坏了。
    """
    out: List[str] = []
    seen = set()
    for raw in (ids or []):
        try:
            pid = int(raw)
        except (TypeError, ValueError):
            raise HTTPException(400, "前置工作包 id 不合法")
        if pid == item.id:
            raise HTTPException(400, "前置工作包不能是它自己")
        if pid in seen:
            continue
        other = db.get(models.WbsItem, pid)
        if other is None or other.plan_id != item.plan_id:
            raise HTTPException(400, "前置工作包不在这份 WBS 里")
        seen.add(pid)
        out.append(str(pid))

    # 边的方向是「工作包 -> 它的前置工作包」。先用库里的整份计划建图，再用本次
    # 待保存的值替换当前节点；否则更新依赖时会拿旧边判断，既可能漏报也可能误报。
    # 历史数据允许保留已删除的前置 id（详情页仍显示 missing=True），但不存在的节点
    # 不可能再通向任何节点，环检测时应忽略。新请求写入缺失 id 已在上面的校验中拒绝。
    items = db.query(models.WbsItem).filter(models.WbsItem.plan_id == item.plan_id).all()
    node_ids = {row.id for row in items}
    graph: Dict[int, List[int]] = {}
    for row in items:
        predecessors: List[int] = []
        for token in str(row.predecessor_ids or "").split(","):
            token = token.strip()
            if token.isdigit() and int(token) in node_ids:
                predecessors.append(int(token))
        graph[row.id] = predecessors
    graph[item.id] = [int(pid) for pid in out]

    for predecessor_id in graph[item.id]:
        pending = [predecessor_id]
        visited = set()
        while pending:
            current = pending.pop()
            if current == item.id:
                raise HTTPException(400, "前置关系会形成循环")
            if current in visited:
                continue
            visited.add(current)
            pending.extend(graph.get(current, []))
    return ",".join(out)


def _item_out(rec: dict, refs: Optional[Dict[int, dict]] = None) -> schemas.WbsItemOut:
    it = rec["item"]
    o = schemas.WbsItemOut.model_validate(it)
    o.code, o.depth = rec["code"], rec["depth"]
    o.is_leaf, o.child_count = rec["is_leaf"], rec["child_count"]
    o.roll_days, o.roll_pct = rec["roll_days"], rec["roll_pct"]
    o.roll_start, o.roll_end = rec["roll_start"], rec["roll_end"]
    o.leaf_count, o.excluded = rec["leaf_count"], rec["excluded"]
    o.issues = _issues(it, rec["is_leaf"])
    o.predecessors = _predecessors(it, refs or {})
    return o


def _plan_out(db: Session, plan: models.WbsPlan,
              rows: Optional[List[dict]] = None) -> schemas.WbsPlanOut:
    if rows is None:
        rows = _flatten(db.query(models.WbsItem)
                        .filter(models.WbsItem.plan_id == plan.id).all())
    o = schemas.WbsPlanOut.model_validate(plan)
    o.kind_label = enums.WBS_KIND_LABELS.get(plan.kind, plan.kind)
    o.ref_name = _ref_name(db, plan)
    roots = [r for r in rows if r["depth"] == 1]
    days = sum(r["roll_days"] for r in roots)
    weighted = sum(r["roll_days"] * r["roll_pct"] for r in roots)
    starts = [r["roll_start"] for r in roots if r["roll_start"]]
    ends = [r["roll_end"] for r in roots if r["roll_end"]]
    o.total_days = round(days, 2)
    o.progress_pct = int(round(weighted / days)) if days else 0
    o.leaf_count = sum(r["leaf_count"] for r in roots)
    o.row_count = len(rows)
    o.max_depth = max((r["depth"] for r in rows), default=0)
    o.excluded = sum(r["excluded"] for r in roots)
    o.excluded_days = round(sum(r["excluded_days"] for r in roots), 2)
    o.flagged = sum(1 for r in rows if _issues(r["item"], r["is_leaf"]))
    o.planned_start = min(starts) if starts else None
    o.planned_end = max(ends) if ends else None
    return o


def _ref_name(db: Session, plan: models.WbsPlan) -> str:
    """归属对象的显示名。查不到就留空——编一个名字比留空更糟。"""
    if plan.kind == "special" and plan.special_id:
        sp = db.get(models.Special, plan.special_id)
        return sp.name if sp else ""
    if plan.kind == "machine" and plan.machine_status_id:
        ms = db.get(models.CustomerStatus, plan.machine_status_id)
        if not ms:
            return ""
        cust = db.get(models.Customer, ms.customer_id) if ms.customer_id else None
        return f"{cust.name} {ms.machine_id}".strip() if cust else (ms.machine_id or "")
    return ""


# ─── 公共小工具 ────────────────────────────────────────────────────────────
def _get_plan(db: Session, plan_id: int) -> models.WbsPlan:
    plan = db.get(models.WbsPlan, plan_id)
    if plan is None:
        raise HTTPException(404, "WBS 不存在")
    return plan


def _get_item(db: Session, item_id: int) -> models.WbsItem:
    it = db.get(models.WbsItem, item_id)
    if it is None:
        raise HTTPException(404, "工作包不存在")
    return it


def _check_version(obj, incoming: Optional[int]) -> None:
    if incoming is not None and incoming != (obj.version or 0):
        raise HTTPException(409, "数据已被他人修改，请刷新后重试")


def _check_tree_version(plan: models.WbsPlan, incoming: int) -> None:
    if incoming != (plan.tree_version or 0):
        raise HTTPException(409, "WBS 结构已被他人修改，请刷新后重试")


def _tail_sort_order(db: Session, plan_id: int, parent_id: Optional[int]) -> int:
    """新行排到同级末位。不重算的话新增的行会插进中间，看着像随机落点。"""
    q = db.query(models.WbsItem).filter(models.WbsItem.plan_id == plan_id)
    q = q.filter(models.WbsItem.parent_id.is_(None) if parent_id is None
                 else models.WbsItem.parent_id == parent_id)
    return max((x.sort_order or 0 for x in q.all()), default=0) + 1


def _fill_snapshots(db: Session, data: dict) -> None:
    """FK → 字符串快照。快照留给前端在 FK 为空时回退显示（见 CLAUDE.md「主数据与 FK 反查」）。"""
    if "owner_user_id" in data:
        u = db.get(models.User, data["owner_user_id"]) if data["owner_user_id"] else None
        data["owner"] = ((u.full_name or "").strip() or u.username) if u else ""
    if "group_id" in data:
        g = db.get(models.ResourceGroup, data["group_id"]) if data["group_id"] else None
        data["owner_group"] = g.name if g else ""


def _validate_ref(db: Session, kind: str, special_id, machine_status_id) -> None:
    """归属必须真的指向一个存在的对象，且只填与 kind 相符的那一个。

    不校验的话会出现一份「挂在专项 3 上」而专项 3 从来不存在的 WBS，
    页面上归属那一栏是空的，看着像没填。
    """
    if kind == "special":
        if not special_id or db.get(models.Special, special_id) is None:
            raise HTTPException(400, "归属专项不存在")
    else:
        if not machine_status_id or db.get(models.CustomerStatus, machine_status_id) is None:
            raise HTTPException(400, "归属机台不存在")


# ─── WBS 计划 ──────────────────────────────────────────────────────────────
@router.get("/plans", response_model=List[schemas.WbsPlanOut])
def list_plans(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    """列表页：横着扫各份 WBS 的人天 / 完成度 / 待补录条数。

    汇总一次全查出来再在内存里分，不逐份查——N 份 WBS 就是 N 次查询。
    """
    plans = (db.query(models.WbsPlan)
             .order_by(models.WbsPlan.sort_order.asc(), models.WbsPlan.id.asc()).all())
    if not plans:
        return []
    all_items = (db.query(models.WbsItem)
                 .filter(models.WbsItem.plan_id.in_([p.id for p in plans])).all())
    by_plan: Dict[int, List[models.WbsItem]] = {}
    for it in all_items:
        by_plan.setdefault(it.plan_id, []).append(it)
    return [_plan_out(db, p, _flatten(by_plan.get(p.id, []))) for p in plans]


@router.post("/plans", response_model=schemas.WbsPlanDetail)
def create_plan(payload: schemas.WbsPlanCreate, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    _validate_ref(db, payload.kind, payload.special_id, payload.machine_status_id)
    data = payload.model_dump()
    # kind 决定填哪个归属外键，另一个一律清空——两个都填的话，改天 kind 一改，
    # 归属就悄悄换成了另一个对象
    if data["kind"] == "special":
        data["machine_status_id"] = None
    else:
        data["special_id"] = None
    _fill_snapshots(db, data)
    data["sort_order"] = (db.query(models.WbsPlan).count() or 0) + 1
    plan = models.WbsPlan(**data)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    log_op(db, action="create", target="wbs_plan", target_id=plan.id, detail=f"name={plan.name}", user=user)
    return _detail(db, plan)


@router.get("/plans/{plan_id}", response_model=schemas.WbsPlanDetail)
def get_plan(plan_id: int, db: Session = Depends(get_db),
             _: models.User = Depends(get_current_user)):
    return _detail(db, _get_plan(db, plan_id))


def _detail(db: Session, plan: models.WbsPlan) -> schemas.WbsPlanDetail:
    rows = _flatten(db.query(models.WbsItem)
                    .filter(models.WbsItem.plan_id == plan.id).all())
    base = _plan_out(db, plan, rows)
    refs = _ref_map(rows)
    return schemas.WbsPlanDetail(**base.model_dump(),
                                 items=[_item_out(r, refs) for r in rows])


@router.put("/plans/{plan_id}", response_model=schemas.WbsPlanDetail)
def update_plan(plan_id: int, payload: schemas.WbsPlanUpdate, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    plan = _get_plan(db, plan_id)
    _check_version(plan, payload.version)
    data = payload.model_dump(exclude_unset=True)
    data.pop("version", None)
    kind = data.get("kind", plan.kind)
    if {"kind", "special_id", "machine_status_id"} & set(data):
        sid = data.get("special_id", plan.special_id)
        mid = data.get("machine_status_id", plan.machine_status_id)
        _validate_ref(db, kind, sid, mid)
        data["special_id"] = sid if kind == "special" else None
        data["machine_status_id"] = mid if kind == "machine" else None
    _fill_snapshots(db, data)
    for k, v in data.items():
        setattr(plan, k, v)
    plan.version = (plan.version or 0) + 1
    db.commit()
    db.refresh(plan)
    log_op(db, action="update", target="wbs_plan", target_id=plan.id, detail=f"fields={','.join(sorted(data))}", user=user)
    return _detail(db, plan)


@router.delete("/plans/{plan_id}")
def delete_plan(plan_id: int, db: Session = Depends(get_db),
                user: models.User = Depends(require_admin)):
    """**仅 admin**：删掉的是别人跟了几个月的计划，与删一条日常填报不是一回事。"""
    plan = _get_plan(db, plan_id)
    name = plan.name
    db.delete(plan)          # items 由 cascade 一并删
    db.commit()
    log_op(db, action="delete", target="wbs_plan", target_id=plan_id, detail=f"name={name}", user=user)
    return {"ok": True}


@router.post("/plans/{plan_id}/apply-template", response_model=schemas.WbsPlanDetail)
def apply_template(plan_id: int, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)):
    """一键生成标准调试分组。**只增不删**（同专项模板的套用语义）：
    已有的行一律保留，重复点也不会把人填过的东西冲掉。
    """
    plan = _get_plan(db, plan_id)
    exist = {(x.name or "").strip() for x in db.query(models.WbsItem)
             .filter(models.WbsItem.plan_id == plan_id,
                     models.WbsItem.parent_id.is_(None)).all()}
    order = _tail_sort_order(db, plan_id, None)
    added = 0
    for name in enums.WBS_DEFAULT_TEMPLATE:
        if name in exist:
            continue
        db.add(models.WbsItem(plan_id=plan_id, parent_id=None, name=name,
                              sort_order=order, status=enums.PROGRESS_DEFAULT))
        order += 1
        added += 1
    plan.tree_version = (plan.tree_version or 0) + 1
    db.commit()
    log_op(db, action="update", target="wbs_plan", target_id=plan_id, detail=f"apply_template added={added}", user=user)
    return _detail(db, plan)


# ─── 工作包 ────────────────────────────────────────────────────────────────
@router.post("/plans/{plan_id}/items", response_model=schemas.WbsPlanDetail)
def create_item(plan_id: int, payload: schemas.WbsItemCreate, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    plan = _get_plan(db, plan_id)
    if payload.parent_id is not None:
        parent = _get_item(db, payload.parent_id)
        if parent.plan_id != plan_id:
            raise HTTPException(400, "上级行不属于这份 WBS")
    data = payload.model_dump()
    _fill_snapshots(db, data)
    data["plan_id"] = plan_id
    data["sort_order"] = _tail_sort_order(db, plan_id, payload.parent_id)
    it = models.WbsItem(**data)
    db.add(it)
    plan.tree_version = (plan.tree_version or 0) + 1
    db.commit()
    log_op(db, action="create", target="wbs_item", target_id=it.id, detail=f"plan={plan_id} name={it.name}", user=user)
    return _detail(db, plan)


@router.put("/items/{item_id}", response_model=schemas.WbsPlanDetail)
def update_item(item_id: int, payload: schemas.WbsItemUpdate, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    it = _get_item(db, item_id)
    _check_version(it, payload.version)
    data = payload.model_dump(exclude_unset=True)
    data.pop("version", None)
    # 有子行的时候，人天/完成度/状态/计划起止一律由汇总说了算——这里**默默丢掉**
    # 而不是报 400：前端本来就把这几格禁掉了，能走到这儿的多半是并发下别人刚加了
    # 子行，报错只会让人一脸茫然地丢掉整次保存。
    has_kids = db.query(models.WbsItem).filter(models.WbsItem.parent_id == item_id).count() > 0
    if has_kids:
        for f in ("man_days", "progress_pct", "status", "planned_start", "planned_end"):
            data.pop(f, None)
    if "predecessor_ids" in data:
        data["predecessor_ids"] = _norm_predecessors(db, it, data["predecessor_ids"])
    _fill_snapshots(db, data)
    for k, v in data.items():
        setattr(it, k, v)
    it.version = (it.version or 0) + 1
    db.commit()
    log_op(db, action="update", target="wbs_item", target_id=item_id, detail=f"fields={','.join(sorted(data))}", user=user)
    return _detail(db, _get_plan(db, it.plan_id))


@router.delete("/items/{item_id}", response_model=schemas.WbsPlanDetail)
def delete_item(item_id: int, payload: schemas.WbsDelete, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    """连同子树一起删（DB 侧 CASCADE）。写权限一档＝登录用户：自己拆的活自己改。"""
    it = _get_item(db, item_id)
    plan_id, name = it.plan_id, it.name
    plan = _get_plan(db, plan_id)
    _check_tree_version(plan, payload.tree_version)
    db.delete(it)
    plan.tree_version = (plan.tree_version or 0) + 1
    db.commit()
    log_op(db, action="delete", target="wbs_item", target_id=item_id, detail=f"plan={plan_id} name={name}", user=user)
    return _detail(db, _get_plan(db, plan_id))


@router.post("/plans/{plan_id}/reorder", response_model=schemas.WbsPlanDetail)
def reorder(plan_id: int, payload: schemas.WbsReorder, db: Session = Depends(get_db),
            user: models.User = Depends(get_current_user)):
    """整体重写某个父级下的顺序。混进别的父级的行返回 **400**——静默忽略会让人
    以为排序时灵时不灵（同版本三层的 /reorder）。列表里没提到的兄弟排到后面，
    别人刚新增的行不会被挤乱。
    """
    plan = _get_plan(db, plan_id)
    _check_tree_version(plan, payload.tree_version)
    q = db.query(models.WbsItem).filter(models.WbsItem.plan_id == plan_id)
    q = q.filter(models.WbsItem.parent_id.is_(None) if payload.parent_id is None
                 else models.WbsItem.parent_id == payload.parent_id)
    sibs = {x.id: x for x in q.all()}
    bad = [i for i in payload.ids if i not in sibs]
    if bad:
        raise HTTPException(400, f"这些行不在该层级下：{bad}")
    n = 0
    for i in payload.ids:
        n += 1
        sibs[i].sort_order = n
    for rest in sorted(set(sibs) - set(payload.ids)):
        n += 1
        sibs[rest].sort_order = n
    plan.tree_version = (plan.tree_version or 0) + 1
    db.commit()
    log_op(db, action="update", target="wbs_plan", target_id=plan_id, detail=f"reorder parent={payload.parent_id}", user=user)
    return _detail(db, plan)


@router.post("/items/{item_id}/move", response_model=schemas.WbsPlanDetail)
def move_item(item_id: int, payload: schemas.WbsMove, db: Session = Depends(get_db),
              user: models.User = Depends(get_current_user)):
    """改层级：连同子树挂到 new_parent_id 下（None＝提到最外层）。

    **必须防环**：把一行挂到自己的子孙下面，那棵子树就从根上够不着了——
    页面表现是"这几行凭空消失"，而库里一行没少，最难查的那类。
    """
    it = _get_item(db, item_id)
    plan = _get_plan(db, it.plan_id)
    new_parent = payload.new_parent_id
    _check_version(it, payload.version)
    _check_tree_version(plan, payload.tree_version)
    if new_parent is not None:
        parent = _get_item(db, new_parent)
        if parent.plan_id != it.plan_id:
            raise HTTPException(400, "目标层级不属于这份 WBS")
        if new_parent == item_id:
            raise HTTPException(400, "不能挂到自己下面")
        # 顺着 parent 往上走，撞见自己就是成环
        seen = {item_id}
        cur = parent
        while cur is not None:
            if cur.id in seen:
                raise HTTPException(400, "不能挂到自己的子孙下面")
            seen.add(cur.id)
            cur = db.get(models.WbsItem, cur.parent_id) if cur.parent_id else None
    it.parent_id = new_parent
    # 换了父级要重算成新父级的末位，带着旧 sort_order 过去会插进目标那一堆的中间
    it.sort_order = _tail_sort_order(db, it.plan_id, new_parent)
    it.version = (it.version or 0) + 1
    plan.tree_version = (plan.tree_version or 0) + 1
    db.commit()
    log_op(db, action="update", target="wbs_item", target_id=item_id, detail=f"move parent={new_parent}", user=user)
    return _detail(db, _get_plan(db, it.plan_id))


# ─── 导出：Excel 表 + 两张图 ────────────────────────────────────────────────
def _clip_depth(rows: List[dict], max_depth: Optional[int]) -> tuple:
    """只保留前 N 层，返回 (保留的行, 折叠掉的条数)。

    **汇总数字一个都不变**：人天 / 完成度 / 计划起止本来就是从叶子算上来的
    （`_rollup`），砍掉显示层级只是不再逐条列出来，第 N 层那一行显示的仍是
    它整棵子树的汇总。这也正是能这么砍的原因。

    **折叠了几条要如实报出来**——只筛不报的表现是「导出的表怎么少了一半」，
    而没人说得清少的是哪些（同 `excluded` / `unassigned` / `match_rate`）。
    """
    if not max_depth or max_depth <= 0:
        return rows, 0
    kept = [r for r in rows if r["depth"] <= max_depth]
    return kept, len(rows) - len(kept)


def _diagram_rows(rows: List[dict], today: Optional[date] = None) -> List[dict]:
    """拍平的树 → 框图要的纯字典。`wbs_diagram` 刻意不吃 ORM 对象，见那边的说明。

    **父行的延期是从叶子推上来的**，不是拿汇总的计划完成日再判一次：父行的日期本身
    就是汇总值，再判一遍会把「子任务都按期、只是整段跨到了今天之后」也标成延期。
    父行红 ＝ 它底下**真的有**延期的叶子。
    """
    late_by_code = {}
    for r in rows:
        n = _is_overdue(r["item"], r["is_leaf"], today)
        if n:
            late_by_code[r["code"]] = n

    def sub_late(code: str) -> int:
        pre = code + "."
        return max((v for k, v in late_by_code.items() if k == code or k.startswith(pre)),
                   default=0)

    # A 图的依赖线必须按稳定 id 找目标，不能存当前显示编号：编号会随着拖动排序改变。
    id_to_code = {r["item"].id: r["code"] for r in rows}
    out = []
    for r in rows:
        it, leaf = r["item"], r["is_leaf"]
        late = late_by_code.get(r["code"], 0) if leaf else sub_late(r["code"])
        out.append({
            "code": r["code"], "name": it.name or "", "depth": r["depth"],
            "status": (it.status or "") if leaf else "",
            "owner": (it.owner or "").strip(),
            "days": r["roll_days"], "pct": r["roll_pct"],
            "is_leaf": leaf, "leaf_count": r["leaf_count"],
            # 叶子用自己填的，父行用汇总——与表格里显示的那两列同一个口径
            "start": it.planned_start if leaf else r["roll_start"],
            "end": it.planned_end if leaf else r["roll_end"],
            "overdue": bool(late), "overdue_days": late,
            "predecessors": [id_to_code[int(token)]
                             for token in str(it.predecessor_ids or "").split(",")
                             if token.strip().isdigit() and int(token) in id_to_code],
        })
    return out


def _fold_counts(all_rows: List[dict], max_depth: Optional[int]) -> Dict[str, int]:
    """被 `max_depth` 折掉的子孙，按「折在谁身上」分别计数。

    总数（`folded`）回答"少了几条"，这一份回答"少的是谁底下的"——A 图把它画成
    名字后面的 `+N`。只给总数的话，看图的人知道有东西被折了，却不知道该点开哪个。
    """
    if not max_depth or max_depth <= 0:
        return {}
    out: Dict[str, int] = {}
    for r in all_rows:
        if r["depth"] != max_depth:
            continue
        pre = r["code"] + "."
        n = sum(1 for x in all_rows if x["code"].startswith(pre))
        if n:
            out[r["code"]] = n
    return out


def _timeline_view(db: Session, plan: models.WbsPlan, all_rows: List[dict],
                   max_depth: Optional[int]) -> dict:
    """A 图（时间轴嵌套框图）的版面。深度裁剪同样在这儿统一做一次。

    与调试框图**吃同一批行、同一份延期判定**（`_diagram_rows`），只是排法不同：
    那张按阶段分列、这张摊到真日期轴上。两张图的数对不上的话，看的人会以为
    其中一张是旧的。
    """
    kept, folded = _clip_depth(all_rows, max_depth)
    folds = _fold_counts(all_rows, max_depth)
    rows = _diagram_rows(kept)
    for r in rows:
        r["folded"] = folds.get(r["code"], 0)
    ref = _ref_name(db, plan)
    sub = " · ".join(x for x in (plan.name,
                                 enums.WBS_KIND_LABELS.get(plan.kind, plan.kind), ref) if x)
    return wbs_timeline.build_timeline(rows, subtitle=sub, max_depth=max_depth,
                                       folded=folded)


def _build_view(db: Session, plan: models.WbsPlan, rows: List[dict],
                max_depth: Optional[int], reference_start: Optional[str] = None,
                reference_end: Optional[str] = None) -> dict:
    """框图的版面。深度裁剪在这儿统一做一次——页面和导出各裁各的话，
    同一个「到第 2 层」在页面上是 8 个方框、在导出的图里是 11 个。
    """
    sub = f"{enums.WBS_KIND_LABELS.get(plan.kind, plan.kind)} · {_ref_name(db, plan)}".strip(" ·")
    kept, folded = _clip_depth(rows, max_depth)
    # 先算全树的颜色/延期，再裁剪显示；月份轴同样来自完整计划。
    chart_rows = _diagram_rows(rows)
    kept_codes = {r["code"] for r in kept}
    try:
        spec = wbs_diagram.build_diagram(
            [r for r in chart_rows if r["code"] in kept_codes], title=plan.name, subtitle=sub,
            reference_start=reference_start, reference_end=reference_end,
            reference_rows=chart_rows)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    spec["folded"] = folded
    spec["max_depth"] = max_depth or 0
    return spec


@router.get("/plans/{plan_id}/diagram")
def plan_diagram(plan_id: int, max_depth: Optional[int] = None,
                 reference_start: Optional[str] = None, reference_end: Optional[str] = None,
                 db: Session = Depends(get_db),
                 _: models.User = Depends(get_current_user)):
    """调试框图的**版面**（不是图片）：页面拿它画 SVG，Excel 导出拿同一份画 PNG。

    方框只显示任务名称和责任人，保留状态底色和延期红框；顶部按月展示全局日期参考。
    `max_depth` 只保留前 N 层（空＝全部），汇总数字不受影响。

    读权限一档＝登录用户，与详情页同档。版面算在服务端而不是前端，是为了让页面
    和导出的图长得一模一样——两边各排一次的话，同一份 WBS 在页面上 4 列、
    在导出的图里 5 列，而两边单独看都正常。
    """
    plan = _get_plan(db, plan_id)
    rows = _flatten(db.query(models.WbsItem)
                    .filter(models.WbsItem.plan_id == plan_id).all())
    return _build_view(db, plan, rows, max_depth, reference_start, reference_end)


@router.get("/plans/{plan_id}/timeline")
def plan_timeline(plan_id: int, max_depth: Optional[int] = None,
                  db: Session = Depends(get_db),
                  _: models.User = Depends(get_current_user)):
    """**A 图**的版面（不是图片）：一根真日期横轴 + 大框套中框套小框。

    与 `/diagram` 是两张图、两份版面，刻意不合并（见 `wbs_timeline` 模块说明）：
    框图答"这件事分几步走"，A 图答"每件事哪天该完、今天看拖了没有"。
    页面拿这份版面画 SVG，Excel 导出拿**同一份**画 PNG——两边各排一次的话，
    同一份 WBS 在页面上和导出的图里框的位置不一样，而两边单独看都正常。

    `max_depth` 只画到第 N 层（空＝全部），折掉的子孙数挂在上级名字后面的 `+N`，
    汇总数字不受影响。读权限一档＝登录用户，与详情页同档。
    """
    plan = _get_plan(db, plan_id)
    rows = _flatten(db.query(models.WbsItem)
                    .filter(models.WbsItem.plan_id == plan_id).all())
    return _timeline_view(db, plan, rows, max_depth)


def _xlsx_rows(rows: List[dict], refs: Dict[int, dict]) -> List[list]:
    def ymd(v):
        return str(v)[:10] if v else ""

    def pred(it) -> str:
        """前置那一格写**现算的编号**，不写库里存的 id——id 对看表的人没有意义。
        指向的行已经删掉时写明「已删除」，留空会被当成没填过。
        老写法（手填的编号串）还在的话一并带上，否则导出里看不到它。
        """
        parts = []
        for r in _predecessors(it, refs):
            parts.append(f"{r.code} {r.name}".strip() if not r.missing
                         else f"（已删除 #{r.id}）")
        txt = "；".join(parts)
        legacy = (it.predecessor or "").strip()
        if legacy:
            txt = (txt + " ") if txt else ""
            txt += f"（老写法：{legacy}）"
        return txt

    out = []
    for r in rows:
        it = r["item"]
        leaf = r["is_leaf"]
        out.append([
            r["code"],
            it.name or "",
            "工作包" if leaf else f"分组（汇总 {r['leaf_count']} 个叶子）",
            (it.owner or "").strip(),
            (it.owner_group or "").strip(),
            ymd(it.planned_start if leaf else r["roll_start"]),
            ymd(it.planned_end if leaf else r["roll_end"]),
            r["roll_days"] or "",
            r["roll_pct"],
            # 分组行的状态**留空**：状态是叶子填的，分组没有状态。
            # 随便填一个「进行中」会被当成有人标过（同「未指定领域」那行的采集问题单留空）
            (it.status or "") if leaf else "",
            (it.deliverable or "").strip(),
            (it.dod or "").strip(),
            pred(it),
            (it.remark or "").strip(),
            " · ".join(_issues(it, leaf)),
        ])
    return out


@router.get("/plans/{plan_id}/export.xlsx")
def export_xlsx(plan_id: int, max_depth: Optional[int] = None,
                reference_start: Optional[str] = None, reference_end: Optional[str] = None,
                db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    """整份 WBS 导出成 Excel：第 1 页是表、第 2 页是调试框图、第 3 页是 A 图。

    `max_depth` ＝**导出到第几层**（空＝全部）。深于它的行不再逐条列出，但
    **汇总数字一个都不变**——人天 / 完成度 / 计划起止本来就是从叶子算上来的，
    第 N 层那一行显示的仍是它整棵子树的汇总。折叠了几条在表尾如实写出来。
    两页吃的是**同一次裁剪**，各裁各的话同一个「导出到第 2 层」在表里是 8 行、
    在图里是 11 个方框。

    另外三条与页面一致的口径，**不在导出里另算一遍**（同专项总览 PPT 复用 overview()）：
    分组行的人天/完成度/计划起止是汇总值、状态留空；「已变更 / 不涉及」的行照导
    （那是计划的一部分），但排除了几条、多少人天在表尾如实写出来；
    **各级任务的字号跟着 `enums.wbs_level_font()` 走**，与页面表格同一份阶梯。
    """
    import io

    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    plan = _get_plan(db, plan_id)
    all_rows = _flatten(db.query(models.WbsItem)
                        .filter(models.WbsItem.plan_id == plan_id).all())
    # 合计走**全量**：砍的是"列出来的层级"，不是"算进去的活"。
    # 拿裁剪后的行去算合计，导出到第 1 层就会得到一个只数了 6 行的人天。
    base = _plan_out(db, plan, all_rows)
    rows, folded = _clip_depth(all_rows, max_depth)

    headers = ["编号", "工作包", "类型", "负责人", "PL组", "计划开始", "计划完成",
               "人天", "完成度%", "状态", "交付物", "完成标准（DoD）", "前置",
               "假设·范围外·风险", "待补录"]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "WBS"
    style_header(ws, headers)
    for line in _xlsx_rows(rows, _ref_map(all_rows)):
        ws.append(line)
    last = 1 + len(rows)
    ws.column_dimensions["B"].width = 42
    beautify(ws, last_row=last, center_cols={1, 3, 8, 9, 10})

    # ── beautify 之后再上层级字号：它把数据区的字统一刷成 11 号，
    #    先写后刷的话这一档分层会被它整段抹平 ──────────────────────────
    section = PatternFill("solid", fgColor=brand.SECTION_BG)
    for i, r in enumerate(rows):
        row_no = 2 + i
        fs = enums.wbs_level_font(r["depth"])
        f = Font(size=fs["pt"], bold=fs["bold"], color=fs["color"])
        ws.cell(row_no, 1).font = f
        c = ws.cell(row_no, 2)
        c.font = f
        # 缩进用 Alignment.indent 而不是往名字前面塞空格：塞空格的话，
        # 这一列复制出去、或者拿来筛选排序时，名字前面永远挂着几个空格
        c.alignment = Alignment(vertical="center", wrap_text=True, indent=r["depth"] - 1)
        ws.row_dimensions[row_no].height = max(18.0, fs["pt"] * 1.7)
        if not r["is_leaf"]:
            # 分组行整行上中灰，和它底下的叶子分开。只给**父行**上：
            # 父行的状态那格本来就是空的，不会盖掉叶子的状态点灯
            for j in range(1, len(headers) + 1):
                ws.cell(row_no, j).fill = section

    note = ws.max_row + 2
    ws.cell(note, 1, f"合计：计入统计 {base.total_days} 人天 / {base.leaf_count} 个叶子工作包，"
                     f"加权完成度 {base.progress_pct}%（Σ人天×完成度 ÷ Σ人天，只数叶子）")
    if base.excluded:
        ws.cell(note + 1, 1, f"已排除 {base.excluded} 条（状态为「已变更 / 不涉及」）、合计 "
                             f"{base.excluded_days} 人天，不计入上面的合计。这些行仍然留在表里。")
    else:
        ws.cell(note + 1, 1, "当前没有「已变更 / 不涉及」的行，上面的合计就是全量。")
    ws.cell(note + 2, 1, "分组行的人天 / 完成度 / 计划起止都是从叶子汇总来的；"
                         "状态一栏留空是因为状态由叶子填，分组没有状态。")
    ws.cell(note + 3, 1, f"待补录 {base.flagged} 条，见最后一列。字号按层级分档，"
                         f"第 1 层最大——与系统页面上同一份阶梯。")
    if folded:
        # 只筛不报的表现是「导出的表怎么少了一半」，而没人说得清少的是哪些
        ws.cell(note + 4, 1, f"本次只导出到第 {max_depth} 层，另有 {folded} 行在更深的层级上"
                             f"没有逐条列出。**上面的合计仍然把它们算在内**——"
                             f"人天与完成度本来就是从最底层的叶子汇总上来的。")

    _blocks_sheet(wb, db, plan, all_rows, folded, max_depth, reference_start, reference_end)
    _timeline_sheet(wb, db, plan, all_rows, max_depth)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"wbs-{plan_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.xlsx"
    log_op(db, action="导出Excel", target="wbs_plan", target_id=plan_id,
           detail=f"rows={len(rows)} folded={folded} max_depth={max_depth or 0}", user=user)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


def _place_png(ws, png: Optional[bytes], spec: dict, anchor_row: int) -> int:
    """把图贴进工作表，返回下一段文字该写在第几行。

    图片是**浮在格子上的、不占行**，必须按像素预留（同 `xlsx_utils._rows_for_px`）——
    少留的话下面那段说明会被图压住，看着像"这句话没导出来"。
    """
    import io

    if not png:
        return anchor_row + 2
    from openpyxl.drawing.image import Image as XLImage
    xi = XLImage(io.BytesIO(png))
    xi.width, xi.height = spec["width"], spec["height"]
    ws.add_image(xi, f"A{anchor_row}")
    return anchor_row + int(spec["height"] / 20) + 2


_NO_FONT = ("这台服务器上没找到能渲染中文的字体，图没有画出来。"
            "装一个中文字体（如 Noto Sans CJK / 微软雅黑）或设 APP_CJK_FONT 后重导即可；"
            "系统页面上的图不受影响，它是浏览器画的。")


def _blocks_sheet(wb, db: Session, plan: models.WbsPlan, rows: List[dict],
                  folded: int, max_depth: Optional[int], reference_start: Optional[str] = None,
                  reference_end: Optional[str] = None) -> None:
    """第 2 页：调试框图。版面与页面共用 wbs_diagram，这里只负责画。"""
    ws = wb.create_sheet("调试框图")
    ws.column_dimensions["A"].width = 120
    spec = _build_view(db, plan, rows, max_depth, reference_start, reference_end)
    ws.cell(1, 1, f"{plan.name} · 调试框图")
    ws.cell(2, 1, f"共 {spec['stage_count']} 个阶段 / {spec['box_count']} 个方框。"
                  + " ".join(spec["note_lines"]))
    if not spec["box_count"]:
        ws.cell(4, 1, "这份 WBS 还没有任何工作包，框图是空的。")
        return
    png = wbs_diagram.render_png(spec)
    tail = _place_png(ws, png, spec, 4)
    if not png:
        ws.cell(4, 1, _NO_FONT)
    if spec["skipped"]:
        ws.cell(tail, 1, f"另有 {spec['skipped']} 行没画进图里（整份 WBS 太大，"
                         f"画出来每个方框细得看不见）。第 1 页的表是全量的。")
        tail += 1
    if folded:
        ws.cell(tail, 1, f"本图只画到第 {max_depth} 层，另有 {folded} 行在更深的层级上"
                         f"没有画出来；它们的工期仍然算在上级方框的汇总里。")


def _timeline_sheet(wb, db: Session, plan: models.WbsPlan, all_rows: List[dict],
                    max_depth: Optional[int]) -> None:
    """第 3 页：A 图（时间轴嵌套框图）。版面与页面共用 `wbs_timeline`，这里只负责画。

    **不画标题**（现场要求："有这样的图后坐标的标题就不需要了"）——日期轴自己就说明了
    这是什么图；是哪份 WBS、截至哪天写在图底那段说明里，落单的一张截图仍找得回出处。
    """
    ws = wb.create_sheet("A图（时间轴）")
    ws.column_dimensions["A"].width = 120
    spec = _timeline_view(db, plan, all_rows, max_depth)
    ws.cell(1, 1, f"{plan.name} · A 图（时间轴嵌套框图）")
    ws.cell(2, 1, f"共 {spec['row_count']} 行 / {spec['box_count']} 个框。"
                  + " ".join(spec["note_lines"]))
    if not spec["row_count"]:
        ws.cell(4, 1, "这份 WBS 还没有任何工作包，A 图是空的。")
        return
    png = wbs_timeline.render_png(spec)
    tail = _place_png(ws, png, spec, 4)
    if not png:
        # 「这份 WBS 是空的」与「这台机器没字体」要分开说，混成一句会让人白装一遍字体
        ws.cell(4, 1, _NO_FONT)
    if not spec["dated"]:
        ws.cell(tail, 1, "这份 WBS 一行计划日期都没填，横轴上只剩「今天」那一根线。"
                         "A 图靠计划起止排版，填上日期之后再导一次就有内容了。")
