"""修订留痕：协作编辑的字段一旦被覆盖，改之前写的是什么就再也找不回来了。

这个模块是**唯一一份实现**——哪些实体、哪些列留痕、留成什么样，都收口在 `TRACKED`。
各 router 只调 `snapshot()` + `record()` 两个函数，不要在自己那边另写一套判断，
否则同一次保存在两张表上留下的痕迹深浅不一，而两边看着都对。

### 用法（必须在 `db.commit()` 之前调）

    before = revisions.snapshot(obj)      # 改之前的值
    ...  改字段  ...
    revisions.record(db, obj, before, user=current_user)
    db.commit()                           # 留痕与改动同一个事务，一起成功或一起没有

**不在这里 commit**（与 `op_log.log_op` 不同）：审计日志晚一点写没关系，
而"改前是 X"这条痕迹如果能脱离改动单独存在，就会出现「历史里写着改过、
数据却没改」——那种记录比没有更糟。所以它搭调用方的车。

### 只记改动，不记新增

行自己的 `created_at` 已经说明了"那时它还不存在"。再补一条 create 记录，
只是让每张表的历史掺进一半噪声，翻的时候还得跳过。

删除**要记**（`action="delete"`，`field=""`，`old_value` 是整行 JSON）：
误删掉的是别人跟了几周的进展，"删之前长什么样"正是这张表该答的问题。

### 大块 JSON 不进这里

自由表格 / 阵型 / 里程碑这几列一次保存动辄几十 KB，逐次留痕会把库撑大好几倍，
而它们的回看诉求本来就是"那一周整页长什么样"——那是 `archives.py` 的整页存档在答。
`machine_cells_json` / `risks_json` 是例外：它们是一小串状态，且正是天天在改的那部分。
"""
import json
import re
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

import models

# ─── 留痕登记表 ───────────────────────────────────────────────────────────────
# entity -> (中文名, 模型, 留痕的列, 归属对象 scope_key 的算法, 行标题的算法)
#
# scope_key 让「这个专项/这个领域的全部历史」能一次查完并按时间排好。分三次查再在
# 前端并起来的话，分页会立刻失真（每张表各取 20 条，合出来的 20 条不是最新的 20 条）。


def _txt(v) -> str:
    """任意列值 → 可比较、可存的文本。None 与空串是同一件事（都是「没填」）。"""
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.isoformat(sep=" ", timespec="seconds")
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def _head(v, n: int = 120) -> str:
    """取一行标题用的首句：去标签、压空白、截断。"""
    s = re.sub(r"<[^>]+>", " ", _txt(v))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:n]


TRACKED: Dict[str, dict] = {
    "special_content": {
        "label": "专项内容",
        "model": models.SpecialContent,
        "fields": ("goal", "progress_summary", "help_request", "overview_light"),
        "scope": lambda o: f"special:{o.special_id}",
        "title": lambda o: "",
    },
    "special_task": {
        "label": "专项事务",
        "model": models.SpecialTask,
        "fields": ("content", "progress", "owner", "planned_close_date", "status"),
        "scope": lambda o: f"special:{o.special_id}",
        "title": lambda o: _head(o.content),
    },
    "special_risk": {
        "label": "专项风险",
        "model": models.SpecialRisk,
        "fields": ("content", "progress", "owner", "planned_close_date", "status"),
        "scope": lambda o: f"special:{o.special_id}",
        "title": lambda o: _head(o.content),
    },
    "domain_content": {
        "label": "领域内容",
        "model": models.DomainContent,
        "fields": ("recent_work", "risks_json"),
        "scope": lambda o: f"domain:{o.group_id}",
        "title": lambda o: "",
    },
    "domain_risk": {
        "label": "领域事务/风险",
        "model": models.DomainRisk,
        "fields": ("content", "progress", "priority", "risk_level", "status",
                   "planned_close_date"),
        "scope": lambda o: f"domain:{o.domain_id or 0}",
        "title": lambda o: _head(o.content),
    },
    "domain_legacy_issue": {
        "label": "领域遗留问题",
        "model": models.DomainLegacyIssue,
        "fields": ("title", "progress", "status", "priority", "remark", "planned_date"),
        "scope": lambda o: f"domain:{o.domain_id or 0}",
        "title": lambda o: _head(o.title),
    },
    "customer_issue": {
        "label": "客户面问题条目",
        "model": models.CustomerIssue,
        "fields": ("description", "progress_note", "urgency", "status",
                   "due_date", "closed_at", "issue_ref", "owner_name"),
        "scope": lambda o: f"customer:{o.customer_id or 0}",
        "title": lambda o: _head(o.description),
    },
    "hardware_issue": {
        "label": "硬件清零",
        "model": models.HardwareIssue,
        # machine_cells_json 是一小串「机台 → 清零状态」，正是天天在改的那部分，
        # 与自由表格那种大块 JSON 不是一回事，所以它留痕
        "fields": ("summary", "clear_progress", "ccb_conclusion", "sop_status",
                   "replaced_part", "ship_clear_from", "machine_cells_json"),
        "scope": lambda o: "hardware:0",
        "title": lambda o: _head(o.summary),
    },
}

SCOPE_LABELS = {"special": "专项", "domain": "领域", "customer": "客户面", "hardware": "硬件清零"}

# 列名默认取模型上的 `comment`（见 field_label）。少数列的注释写的是**取值范围**
# 而不是列名——那是给开发看的，直接拿来当标题会变成「状态: OPEN / CLOSED / 挂起」
# 这种一看就不像人话的东西。只有这几处单独指定，其余仍然跟着注释走。
_LABELS = {
    ("special_content", "overview_light"): "总览点灯",
    ("special_task", "status"): "状态",
    ("special_risk", "status"): "状态",
    ("domain_content", "risks_json"): "风险与求助",
    ("domain_risk", "priority"): "优先级",
    ("domain_risk", "risk_level"): "风险等级",
    ("domain_risk", "status"): "状态",
    ("domain_legacy_issue", "priority"): "优先级",
    ("domain_legacy_issue", "status"): "状态",
    ("customer_issue", "description"): "问题描述",
    ("customer_issue", "urgency"): "紧急程度",
    ("customer_issue", "status"): "状态",
    ("customer_issue", "owner_name"): "责任人",
    ("hardware_issue", "machine_cells_json"): "各机台清零状态",
}


def entity_of(obj) -> Optional[str]:
    """ORM 对象 → 登记表里的 entity 名；没登记的返回 None（＝这张表不留痕）。"""
    for name, spec in TRACKED.items():
        if type(obj) is spec["model"]:
            return name
    return None


def field_label(entity: str, field: str) -> str:
    """列名 → 中文名，直接取模型上的 `comment`。

    另建一张「列名→中文」的对照表的话，加一列时总有一处会忘，表现是历史里
    孤零零一个英文列名。列注释本来就得写，让它当这一份。
    """
    fixed = _LABELS.get((entity, field))
    if fixed:
        return fixed
    spec = TRACKED.get(entity)
    if not spec:
        return field
    col = spec["model"].__table__.columns.get(field)
    text = (col.comment or "").strip() if col is not None else ""
    if not text:
        return field
    # 注释多是「当前进展（富文本 HTML；老行是纯文本）」这种，括号后面是给开发看的
    for sep in ("（", "(", "，", ",", ";", "；"):
        text = text.split(sep)[0]
    text = re.sub(r"\s*YYYY[-/]MM[-/]DD.*$", "", text)
    return text.strip() or field


def snapshot(obj) -> Dict[str, str]:
    """改之前先拍一份：{列名: 文本值}。没登记的实体返回空字典。"""
    entity = entity_of(obj)
    if not entity:
        return {}
    return {f: _txt(getattr(obj, f, None)) for f in TRACKED[entity]["fields"]}


def record(db: Session, obj, before: Dict[str, str], *, user=None,
           username: str = "") -> int:
    """比对 before 与当前值，逐个改动的列写一条。返回写了几条。

    只 `db.add`，**不 commit**：留痕要和改动在同一个事务里，见模块开头。
    """
    entity = entity_of(obj)
    if not entity or not before:
        return 0
    spec = TRACKED[entity]
    rows = []
    for f in spec["fields"]:
        old = before.get(f, "")
        new = _txt(getattr(obj, f, None))
        if old == new:
            continue
        rows.append(models.FieldRevision(
            entity=entity, entity_id=obj.id, scope_key=_scope(spec, obj),
            entity_title=_title(spec, obj), field=f,
            old_value=old, new_value=new, action="update",
            user_id=getattr(user, "id", None),
            username=(getattr(user, "username", "") or username or ""),
        ))
    for r in rows:
        db.add(r)
    return len(rows)


def record_delete(db: Session, obj, *, user=None, username: str = "") -> bool:
    """删除前调：把整行留痕的列打成 JSON 存进 old_value。"""
    entity = entity_of(obj)
    if not entity:
        return False
    spec = TRACKED[entity]
    db.add(models.FieldRevision(
        entity=entity, entity_id=obj.id, scope_key=_scope(spec, obj),
        entity_title=_title(spec, obj), field="",
        old_value=json.dumps(snapshot(obj), ensure_ascii=False),
        new_value="", action="delete",
        user_id=getattr(user, "id", None),
        username=(getattr(user, "username", "") or username or ""),
    ))
    return True


def _scope(spec: dict, obj) -> str:
    try:
        return spec["scope"](obj) or ""
    except Exception:  # noqa: BLE001  归属算不出来不该拖垮保存
        return ""


def _title(spec: dict, obj) -> str:
    try:
        return spec["title"](obj) or ""
    except Exception:  # noqa: BLE001
        return ""


# ─── 回看 ────────────────────────────────────────────────────────────────────

def born_at(obj) -> Optional[datetime]:
    """这一行是什么时候建的——**按行号翻历史时必须拿它当下界**。

    SQLite 的 `INTEGER PRIMARY KEY` 不带 AUTOINCREMENT 时会**复用**已删除行的
    id（删掉表里最后一行，下一条新增就顶上那个号）。不设下界的话，新建的那一行
    会把前一个同号行的历史整段认领过来：页面上是一条刚建的空事务，历史里却写着
    别人三周前的进展，而两边看着都对。

    没有 `created_at` 的实体（如 1:1 的内容表）返回 None——它们跟着主对象走，
    不会被删，也就没有复用这回事。
    """
    v = getattr(obj, "created_at", None)
    return v if isinstance(v, datetime) else None


def value_at(db: Session, entity: str, entity_id: int, field: str,
             when: datetime, current: str = "", since: Optional[datetime] = None) -> str:
    """这一格在 `when` 那一刻写的是什么。

    往后找**第一条**发生在 `when` 之后的改动，它的 old_value 就是那会儿的值；
    一条都没有＝从那时到现在没被动过，值就是现在这个。
    （`when` 是朴素 UTC，与 `created_at` 同一口径，见 CLAUDE.md「时间」。）
    `since` 是这一行自己的建行时间，见 `born_at()`。
    """
    q = (
        db.query(models.FieldRevision)
        .filter(models.FieldRevision.entity == entity,
                models.FieldRevision.entity_id == entity_id,
                models.FieldRevision.field == field,
                models.FieldRevision.action == "update",
                models.FieldRevision.created_at > when)
    )
    if since is not None:
        q = q.filter(models.FieldRevision.created_at >= since)
    rev = q.order_by(models.FieldRevision.created_at.asc(),
                     models.FieldRevision.id.asc()).first()
    return rev.old_value if rev is not None else current


def row_at(db: Session, obj, when: datetime) -> Dict[str, str]:
    """整行在 `when` 那一刻的样子：{列名: 值}。行本身还得存在（删掉的看删除记录）。"""
    entity = entity_of(obj)
    if not entity:
        return {}
    cur = snapshot(obj)
    since = born_at(obj)
    return {f: value_at(db, entity, obj.id, f, when, cur.get(f, ""), since=since)
            for f in TRACKED[entity]["fields"]}


def query(db: Session, *, scope_key: str = "", entity: str = "",
          entity_id: Optional[int] = None, fields: Iterable[str] = (),
          since: Optional[datetime] = None, until: Optional[datetime] = None):
    """按对象 / 按行 / 按列翻历史，倒序。返回的是未分页的 query，由调用方 limit。"""
    q = db.query(models.FieldRevision)
    if scope_key:
        q = q.filter(models.FieldRevision.scope_key == scope_key)
    if entity:
        q = q.filter(models.FieldRevision.entity == entity)
    if entity_id is not None:
        q = q.filter(models.FieldRevision.entity_id == entity_id)
    flds: List[str] = [f for f in fields if f]
    if flds:
        # 删除记录的 field 是空串，按列筛时不该把它筛掉——整行没了当然也包括这一列
        q = q.filter(models.FieldRevision.field.in_(flds + [""]))
    if since is not None:
        q = q.filter(models.FieldRevision.created_at >= since)
    if until is not None:
        q = q.filter(models.FieldRevision.created_at <= until)
    return q.order_by(models.FieldRevision.created_at.desc(), models.FieldRevision.id.desc())
