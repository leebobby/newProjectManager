"""整页存档：把某个对象**当时那一整页**存一份，每周自动 + 可手工。

与 `revisions.py` 是两种"回头看"，都要留着，别合并：
修订历史答「这一格之前写的是什么」（连续，精确到每次保存）；
整页存档答「那一周整页长什么样」（离散，但一眼看到全貌）。
只有修订历史的话，重建一张表要把行的创建时间与删除记录一起算——重建错了，
出来的还是一张看着挺正常的表，没人会去核。

### payload 存的是数据，不是画面

`payload_json` 里放的是**当时那一页的数据结构**，回看时喂给渲染函数现画。
存 HTML 的话，样式一改，老存档就永远停在旧版式上；而存数据的代价只是
"渲染函数改了，老存档跟着新版式显示"——那反而是对的。

### 专项的回看复用周报那一份渲染

`_render_special_html()` 把 payload 还原成一组鸭子类型对象，直接交给
`routers.specials._render_report_html()`。另写一套的表现是「加了一种分段，
页面和周报里都有、存档里没有」——正是 CLAUDE.md 里反复说的那类分叉。
还原用的是 `SimpleNamespace` 而不是 ORM 实例：存档是只读的，
造一批瞬态 ORM 对象反而要担心它们被 autoflush 写进库。

### 图片不进存档

`<img>` 按存档时记下的文件名去 `uploads/` 现取（内联成 data:，存档页才是自包含的）。
图片一起存的话一份档动辄几 MB，一年下来库就没法备份了。代价是图片被换掉之后
存档里也跟着变——这一条要在页面上写明白，不写的话没人知道图和文字不是同一时刻的。
"""
import base64
import json
import logging
from datetime import datetime
from types import SimpleNamespace
from typing import Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

import models

logger = logging.getLogger("archives")

# ─── payload 构造 ────────────────────────────────────────────────────────────

_CONTENT_COLS = (
    "goal", "progress_summary", "help_request", "panorama_image_path",
    "panorama_image_name", "milestones_json", "formation_json", "extra_grids_json",
    "section_order_json", "section_config_json", "overview_light",
)
_ITEM_COLS = ("id", "seq", "content", "progress", "owner", "planned_close_date",
              "status", "sort_order")


def _row(obj, cols) -> dict:
    out = {}
    for c in cols:
        v = getattr(obj, c, None)
        out[c] = v.isoformat(sep=" ", timespec="seconds") if isinstance(v, datetime) else v
    return out


def build_special(db: Session, sid: int) -> Optional[dict]:
    sp = db.query(models.Special).filter(models.Special.id == sid).first()
    if sp is None:
        return None
    content = (db.query(models.SpecialContent)
               .filter(models.SpecialContent.special_id == sid).first())
    def _items(model):
        return [_row(r, _ITEM_COLS) for r in
                db.query(model).filter(model.special_id == sid)
                  .order_by(model.sort_order, model.id).all()]
    return {
        "id": sp.id, "name": sp.name or "", "owner": sp.owner or "",
        "kind": sp.kind or "special",
        "content": _row(content, _CONTENT_COLS) if content is not None else {},
        "tasks": _items(models.SpecialTask),
        "risks": _items(models.SpecialRisk),
    }


def build_domain(db: Session, group_id: int) -> Optional[dict]:
    g = (db.query(models.ResourceGroup)
         .filter(models.ResourceGroup.id == group_id).first())
    if g is None:
        return None
    content = (db.query(models.DomainContent)
               .filter(models.DomainContent.group_id == group_id).first())
    try:
        risks = json.loads(content.risks_json) if content and content.risks_json else []
    except (TypeError, ValueError):
        risks = []
    names = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    tasks = (db.query(models.DomainRisk)
             .filter(models.DomainRisk.domain_id == group_id)
             .order_by(models.DomainRisk.sort_order, models.DomainRisk.id).all())
    legacy = (db.query(models.DomainLegacyIssue)
              .filter(models.DomainLegacyIssue.domain_id == group_id)
              .order_by(models.DomainLegacyIssue.sort_order,
                        models.DomainLegacyIssue.id).all())
    return {
        "group_id": g.id, "code": g.code or "", "name": g.name or "",
        "recent_work": (content.recent_work if content else "") or "",
        "risks": risks if isinstance(risks, list) else [],
        "tasks": [dict(_row(t, ("id", "seq", "content", "progress", "priority",
                                "risk_level", "status", "planned_close_date")),
                       owner=names.get(t.owner_id, "")) for t in tasks],
        "legacy": [dict(_row(l, ("id", "seq", "title", "progress", "status",
                                 "priority", "remark", "planned_date")),
                        owner=names.get(l.owner_id, "")) for l in legacy],
    }


def build_customer(db: Session, customer_id: int) -> Optional[dict]:
    c = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if c is None:
        return None
    groups = {g.id: g.name for g in db.query(models.ResourceGroup).all()}
    names = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    rows = (db.query(models.CustomerIssue)
            .filter(models.CustomerIssue.customer_id == customer_id)
            .order_by(models.CustomerIssue.sort_order, models.CustomerIssue.id).all())
    out = []
    for r in rows:
        m = r.machine_status
        out.append(dict(
            _row(r, ("id", "kind", "description", "issue_ref", "progress_note",
                     "urgency", "status", "category", "raised_at", "due_date", "closed_at")),
            machine=(m.machine_id if m else "") or "",
            owner=names.get(r.owner_user_id) or (r.owner_name or ""),
            group=groups.get(r.group_id) or (r.owner_group or ""),
        ))
    # 展示名可空，回退到 code（同页面的口径：未填 display_name 就显示 code）
    return {"customer_id": c.id, "name": (c.display_name or c.code or ""), "issues": out}


def build_hardware(db: Session, _ref: int = 0) -> Optional[dict]:
    """硬件清零是**一张全局表**，不按客户分——所以 ref_id 固定 0，一页存一份。"""
    machines = (db.query(models.CustomerStatus)
                .order_by(models.CustomerStatus.id).all())
    groups = {g.id: g.name for g in db.query(models.ResourceGroup).all()}
    names = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    rows = []
    for r in (db.query(models.HardwareIssue)
              .order_by(models.HardwareIssue.sort_order, models.HardwareIssue.id).all()):
        try:
            cells = json.loads(r.machine_cells_json or "{}")
        except (TypeError, ValueError):
            cells = {}
        rows.append(dict(
            _row(r, ("id", "source", "issue_ref", "summary", "replaced_part",
                     "issue_source", "ccb_conclusion", "ship_clear_from",
                     "clear_progress", "sop_status")),
            owner=names.get(r.owner_user_id) or (r.owner_name or ""),
            group=groups.get(r.group_id) or (r.owner_group or ""),
            machine_cells=cells if isinstance(cells, dict) else {},
        ))
    return {
        "machines": [{"id": m.id, "label": f"{m.battlefield or ''} {m.machine_id or ''}".strip()}
                     for m in machines],
        "rows": rows,
    }


# ─── 存档对象登记表 ──────────────────────────────────────────────────────────
# kind -> (中文名, payload 构造, 每周要存哪些对象, payload → 标题)

def _special_targets(db: Session) -> List[int]:
    return [r.id for r in db.query(models.Special.id).order_by(models.Special.id).all()]


def _domain_targets(db: Session) -> List[int]:
    """只存 PL 组（领域页就是按 PL 组铺的），隐藏的也存——隐藏是展示口径，不是删除。"""
    q = db.query(models.ResourceGroup).filter(models.ResourceGroup.kind == "PL")
    return [g.id for g in q.order_by(models.ResourceGroup.id).all()]


def _customer_targets(db: Session) -> List[int]:
    return [c.id for c in db.query(models.Customer).order_by(models.Customer.id).all()]


BUILDERS: Dict[str, Tuple[str, Callable, Callable, Callable]] = {
    "special":  ("专项", build_special,  _special_targets,  lambda p: p.get("name") or ""),
    "domain":   ("领域", build_domain,   _domain_targets,   lambda p: p.get("name") or ""),
    "customer": ("客户面", build_customer, _customer_targets, lambda p: p.get("name") or ""),
    "hardware": ("硬件清零", build_hardware, lambda db: [0],  lambda p: "硬件问题清零"),
}


def today_label() -> str:
    """存档日。本来就是本地日期，不做时区转换（见 CLAUDE.md「时间」）。"""
    return datetime.now().strftime("%Y-%m-%d")


def create_snapshot(db: Session, kind: str, ref_id: int, *, reason: str = "manual",
                    created_by: str = "", label: Optional[str] = None
                    ) -> Optional[models.PageSnapshot]:
    """存一份档。同一对象同一天**覆盖**而不是堆一摞（定时重跑、手工再存都一样）。

    调用方负责 commit——与 revisions 同理，存档要和它所属的事务一起成功。
    """
    spec = BUILDERS.get(kind)
    if not spec:
        raise ValueError(f"未知的存档类型：{kind}")
    payload = spec[1](db, ref_id)
    if payload is None:
        return None
    lbl = label or today_label()
    snap = (db.query(models.PageSnapshot)
            .filter(models.PageSnapshot.kind == kind,
                    models.PageSnapshot.ref_id == ref_id,
                    models.PageSnapshot.label == lbl).first())
    if snap is None:
        snap = models.PageSnapshot(kind=kind, ref_id=ref_id, label=lbl)
        db.add(snap)
    snap.title = (spec[3](payload) or "")[:256]
    snap.payload_json = json.dumps(payload, ensure_ascii=False)
    snap.reason = reason
    snap.created_by = created_by or ""
    snap.created_at = datetime.utcnow()
    return snap


def run_weekly(db: Session) -> Dict[str, int]:
    """每周把四类页面各存一份。单个对象失败只跳过它，不能让整轮停下来。

    失败**一定要打日志**：吞掉的话表现是「某一页从某周起就没有存档了」，
    而页面上一切正常，等到有人回头找那一周才发现，那时已经补不回来了。
    """
    counts: Dict[str, int] = {}
    for kind, spec in BUILDERS.items():
        n = 0
        try:
            targets = spec[2](db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("整页存档：%s 取对象清单失败：%s", kind, exc)
            targets = []
        for ref in targets:
            try:
                if create_snapshot(db, kind, ref, reason="weekly") is not None:
                    n += 1
                db.commit()
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                logger.warning("整页存档：%s#%s 失败：%s", kind, ref, exc)
        counts[kind] = n
    return counts


# ─── 回看渲染 ────────────────────────────────────────────────────────────────

def _e(s) -> str:
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


_CSS = ("font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC',"
        "'Microsoft YaHei',sans-serif;font-size:14px;color:#303133;line-height:1.7;")
_TABLE = ("width:100%;border-collapse:collapse;margin:6px 0 14px 0;"
          "font-size:13px;table-layout:fixed;word-break:break-word;")
_TH = "border:1px solid #dcdfe6;background:#eef2f7;padding:6px 8px;text-align:left;"
_TD = "border:1px solid #dcdfe6;padding:6px 8px;vertical-align:top;"


def _table(headers: List[str], rows: List[List[str]], *, raw_cols=()) -> str:
    """rows 里的值默认转义；raw_cols 里的列下标按已清洗过的富文本原样放行。"""
    if not rows:
        return ""
    head = "<tr>" + "".join(f'<th style="{_TH}">{_e(h)}</th>' for h in headers) + "</tr>"
    body = []
    for r in rows:
        tds = []
        for i, v in enumerate(r):
            cell = str(v or "") if i in raw_cols else _e(v)
            tds.append(f'<td style="{_TD}">{cell}</td>')
        body.append("<tr>" + "".join(tds) + "</tr>")
    return f'<table style="{_TABLE}">{head}{"".join(body)}</table>'


def _h(text: str) -> str:
    return (f'<div style="font-weight:600;font-size:15px;margin:16px 0 4px 0;'
            f'padding-left:8px;border-left:3px solid #4073BA;">{_e(text)}</div>')


def _page(title: str, subtitle: str, body: str) -> str:
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"></head>'
        f'<body style="{_CSS} margin:0;padding:0;background:#f5f7fa;">'
        '<div style="max-width:960px;margin:0 auto;background:#fff;">'
        '<div style="background:linear-gradient(135deg,#4073BA 0%,#2D4A6B 100%);'
        'color:#fff;padding:16px 22px;">'
        f'<div style="font-size:19px;font-weight:600;">{_e(title)}</div>'
        f'<div style="margin-top:5px;font-size:13px;opacity:.9;">{_e(subtitle)}</div>'
        '</div>'
        f'<div style="padding:6px 22px 24px 22px;">{body or "（这份存档没有内容）"}</div>'
        '</div></body></html>'
    )


def _inline_images(html: str, images: List[dict]) -> str:
    """把周报用的 cid: 引用换成 data:，存档页才是自包含的（浏览器不认 cid:）。"""
    for im in images:
        b64 = base64.b64encode(im["data"]).decode("ascii")
        html = html.replace(f'cid:{im["cid"]}', f'data:image/{im["subtype"]};base64,{b64}')
    return html


def _render_special_html(payload: dict, *, label: str = "", heading: str = "") -> str:
    """还原成鸭子类型对象，交给周报那一份渲染（见模块开头）。

    `label`（存档日）必须传进去：不传的话页头写的是**今天**，一份三个月前的存档
    看着像今天刚出的报告，而里面的内容是三个月前的——两下都对不上还没人说得清。
    """
    from routers.specials import _render_report_html  # 延迟导入：避免与 router 互相拉起

    content = SimpleNamespace(**{c: (payload.get("content") or {}).get(c)
                                 for c in _CONTENT_COLS})
    def _ns(rows):
        return [SimpleNamespace(**r) for r in (rows or [])]
    special = SimpleNamespace(
        id=payload.get("id") or 0, name=payload.get("name") or "",
        owner=payload.get("owner") or "", kind=payload.get("kind") or "special",
        content=content, tasks=_ns(payload.get("tasks")), risks=_ns(payload.get("risks")),
    )
    html, images = _render_report_html(
        special, today=label or None, heading=heading or None)
    return _inline_images(html, images)


def _rich(s) -> str:
    from routers.specials import _rich_to_html
    return _rich_to_html(s or "")


def _render_domain_html(payload: dict) -> str:
    parts = []
    if (payload.get("recent_work") or "").strip():
        parts.append(_h("最近主要工作") + f'<div>{_rich(payload["recent_work"])}</div>')
    risks = payload.get("risks") or []
    if risks:
        parts.append(_h("风险与求助") + _table(
            ["类型", "内容", "状态"],
            [[r.get("type", ""), r.get("content", ""), r.get("status", "")] for r in risks]))
    tasks = payload.get("tasks") or []
    if tasks:
        parts.append(_h("事务与风险") + _table(
            ["序号", "风险和事务", "当前进展", "优先级", "风险等级", "责任人", "计划闭环", "状态"],
            [[t.get("seq"), t.get("content"), _rich(t.get("progress")), t.get("priority"),
              t.get("risk_level"), t.get("owner"), t.get("planned_close_date"), t.get("status")]
             for t in tasks], raw_cols={2}))
    legacy = payload.get("legacy") or []
    if legacy:
        parts.append(_h("遗留问题") + _table(
            ["编号", "任务名称", "当前进展", "优先级", "责任人", "计划完成", "状态", "备注"],
            [[l.get("seq"), l.get("title"), _rich(l.get("progress")), l.get("priority"),
              l.get("owner"), l.get("planned_date"), l.get("status"), l.get("remark")]
             for l in legacy], raw_cols={2}))
    return "".join(parts)


_KIND_LABEL = {"issue": "软件类问题", "demand": "需求", "task": "现场关键事务"}


def _render_customer_html(payload: dict) -> str:
    rows = payload.get("issues") or []
    if not rows:
        return ""
    return _h("问题与关键事务") + _table(
        ["机台", "类型", "问题描述", "问题进展", "责任人", "责任领域",
         "紧急程度", "提出", "计划解决", "实际闭环", "状态"],
        [[r.get("machine"), _KIND_LABEL.get(r.get("kind"), r.get("kind")),
          r.get("description"), r.get("progress_note"), r.get("owner"), r.get("group"),
          r.get("urgency"), r.get("raised_at"), r.get("due_date"), r.get("closed_at"),
          r.get("status")] for r in rows])


def _render_hardware_html(payload: dict) -> str:
    rows = payload.get("rows") or []
    if not rows:
        return ""
    machines = payload.get("machines") or []
    headers = (["问题单号", "问题简述", "更换部件", "责任领域", "责任人",
                "CCB 清零结论", "清零进展", "SOP 情况"]
               + [m.get("label") or f"#{m.get('id')}" for m in machines])
    body = []
    for r in rows:
        cells = r.get("machine_cells") or {}
        body.append([r.get("issue_ref"), r.get("summary"), r.get("replaced_part"),
                     r.get("group"), r.get("owner"), r.get("ccb_conclusion"),
                     r.get("clear_progress"), r.get("sop_status")]
                    + [cells.get(str(m.get("id"))) or cells.get(m.get("id")) or ""
                       for m in machines])
    return _h("硬件问题清零") + _table(headers, body)


_RENDERERS = {
    "special": _render_special_html,
    "domain": _render_domain_html,
    "customer": _render_customer_html,
    "hardware": _render_hardware_html,
}


def render_html(snap: models.PageSnapshot) -> str:
    """一份存档 → 可直接看的 HTML。"""
    try:
        payload = json.loads(snap.payload_json or "{}")
    except (TypeError, ValueError):
        payload = {}
    label = (BUILDERS.get(snap.kind) or ("存档",))[0]
    body_fn = _RENDERERS.get(snap.kind)
    if snap.kind == "special":
        # 专项整页（含标题条）由周报那一份渲染出，不再套一层壳
        try:
            return _render_special_html(
                payload, label=snap.label,
                heading=f"【{label}存档】{payload.get('name') or snap.title}")
        except Exception as exc:  # noqa: BLE001  渲染不出来也要看得到是哪份档坏了
            return _page(f"{label}存档", f"{snap.title} · {snap.label}",
                         f'<div style="color:#F56C6C;">这份存档渲染失败：{_e(exc)}</div>')
    body = body_fn(payload) if body_fn else ""
    return _page(f"【{label}存档】{snap.title}",
                 f"存档日期：{snap.label} · "
                 f"{'每周自动' if snap.reason == 'weekly' else '手工存档'}"
                 + (f" · {snap.created_by}" if snap.created_by else ""),
                 body)
