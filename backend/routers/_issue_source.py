"""问题单数据源：把「这次统计该读哪一份问题单明细」收口在一处。

领域总览与度量看板都要按领域切问题单，判断逻辑（快照优先、无快照回退老 Excel、
指定项目没快照时如实报不可用）**只能有一份实现**——两处各写一份的表现是
同一个领域在两个页面上问题单数不一样，而两边看着都像对的。

数据源有两个，优先级固定：
1. `issue_snapshots` 里选定项目的**最新一次快照**（问题单管理采集的结果）。
   只看最新一份——趋势属于问题单管理，别在别处再造一套。
2. 一份快照都没有时读老的问题单 Excel（`config.issue_report_path`）。
   保留它只是为了不让还没接 API 采集的部署丢掉这一列。
"""
import json
from datetime import date, datetime
from typing import List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

import models
import schemas
from routers.config import _load as _load_config

# 问题单加权分值：致命10 严重3 一般1 提示0.1（未列出的级别记 0 分，仍计入数量）。
# 领域总览与度量看板共用——两处各写一份，同一批单在两个页面上会得出不同的分数。
SEVERITY_WEIGHTS = {"致命": 10.0, "严重": 3.0, "一般": 1.0, "提示": 0.1}


def weighted_score(rows: List[dict]) -> float:
    return round(sum(SEVERITY_WEIGHTS.get((r.get("severity") or "").strip(), 0.0)
                     for r in rows), 1)


# ─── 超期未处理 ────────────────────────────────────────────────────────────
# 「预计闭环时间」（DTS 的 planCloseTime）是自由格式的字符串：不同来源见过
# 2026-09-15、2026/9/15、2026-09-15 00:00:00、13 位毫秒时间戳。**认不出来的一律
# 算"没填"而不是算"没超期"**——后者会把一批读不懂的日期悄悄记成达标，数字看着还挺好。
_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y-%m-%d %H:%M:%S",
                 "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y年%m月%d日")


def parse_plan_date(value) -> Optional[date]:
    """把「预计闭环时间」解析成日期；认不出返回 None。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    # 纯数字：秒 / 毫秒时间戳
    if s.isdigit() and len(s) in (10, 13):
        try:
            return datetime.fromtimestamp(int(s) / (1000 if len(s) == 13 else 1)).date()
        except (ValueError, OSError, OverflowError):
            return None
    head = s.replace("T", " ").split(" ")[0] if " " in s or "T" in s else s
    for fmt in _DATE_FORMATS:
        for cand in (s, head):
            try:
                return datetime.strptime(cand, fmt).date()
            except ValueError:
                continue
    return None


def is_overdue(row: dict, today: Optional[date] = None) -> bool:
    """这一单是否**超过预计闭环时间还没处理**。

    「没处理」不用读状态：快照里本来就只有当天还开着的单（关闭/撤销在采集时就剔掉了），
    在快照里 ＝ 还没处理。这与「解决＝从快照里消失」是同一套口径，两处必须一致，
    否则会出现"已解决的单还挂在超期数里"。
    """
    d = parse_plan_date(row.get("estimated_close"))
    return bool(d and d < (today or date.today()))


def overdue_stats(rows: List[dict], today: Optional[date] = None) -> Tuple[int, int]:
    """(超期未处理条数, 没填预计闭环时间因而算不出的条数)。

    第二个数必须一起报出去：DTS 那边这一列是选填的，没接上时全库都是空，
    此时「超期 0」会被读成"一条都没超期"，而实际是"这个数算不出来"。
    """
    today = today or date.today()
    overdue = no_date = 0
    for r in rows:
        d = parse_plan_date(r.get("estimated_close"))
        if d is None:
            no_date += 1
        elif d < today:
            overdue += 1
    return overdue, no_date


# ─── Excel 回退 ────────────────────────────────────────────────────────────
def load_issue_raw() -> Tuple[Optional[List[dict]], Optional[str], Optional[str]]:
    """读取最新问题单 Excel 的原始行。

    返回 (raw_rows, file_mtime, note)；不可用时 raw_rows 为 None、note 给出原因。
    """
    cfg = _load_config()
    path_str = (cfg.get("issue_report_path") or "").strip()
    if not path_str:
        return None, None, "未配置问题单报表路径"
    try:
        from routers.issues import _parse_excel_cached, _resolve_for_date

        target = _resolve_for_date(path_str)
        # 复用问题单模块的 mtime 缓存解析：文件没变时不重读 Excel（领域总览每次打开都会调这里）
        parsed = _parse_excel_cached(str(target))
        raw = parsed.get("raw") or []
        return raw, parsed.get("file_mtime"), None
    except HTTPException as exc:
        return None, None, str(exc.detail)
    except Exception as exc:
        return None, None, f"读取问题单失败：{exc}"


def issue_rows_for_group(raw: List[dict], g: models.ResourceGroup) -> List[dict]:
    """按「责任人所属小组」切出某个领域的问题单行。组名与组编码都认。"""
    keys = {k for k in (g.name, g.code) if k}
    return [r for r in raw if (r.get("group") or "").strip() in keys]


# ─── 快照（问题单管理的采集结果，按项目）──────────────────────────────────
def latest_snapshot(db: Session, project: str) -> Optional[models.IssueSnapshot]:
    """某项目最新一次快照。只看最新一份——趋势属于问题单管理，不在这里重造。"""
    return (
        db.query(models.IssueSnapshot)
        .filter(models.IssueSnapshot.project == project)
        .order_by(models.IssueSnapshot.snapshot_date.desc())
        .first()
    )


def snapshot_rows(snap: models.IssueSnapshot) -> List[dict]:
    """读快照明细 JSON。文件缺失/损坏时返回空列表而不是报错——

    快照元数据在库里、明细在文件，两者可能不同步（目录被清理、迁移漏拷）。
    这时页面显示 0 条比整页 500 有用得多。
    """
    from routers.issues import _snapshot_root

    try:
        fp = _snapshot_root() / (snap.data_file or "")
        if snap.data_file and fp.exists():
            data = json.loads(fp.read_text(encoding="utf-8"))
            return [r for r in data if isinstance(r, dict)]
    except Exception:
        pass
    return []


def issue_projects(db: Session) -> List[schemas.DomainProjectOpt]:
    """可选项目 = 配置的采集项目 ∪ 已有快照的项目；按配置顺序在前、其余字典序。"""
    cfg = _load_config()
    configured = [str(x).strip() for x in (cfg.get("issue_api_projects") or []) if str(x).strip()]
    snap_projects = [
        r[0] for r in db.query(models.IssueSnapshot.project).distinct().all() if r[0]
    ]
    ordered = configured + sorted(p for p in snap_projects if p not in configured)
    out: List[schemas.DomainProjectOpt] = []
    for proj in ordered:
        snap = latest_snapshot(db, proj)
        out.append(schemas.DomainProjectOpt(
            project=proj,
            latest_date=snap.snapshot_date if snap else None,
            total=snap.total if snap else 0,
        ))
    return out


class IssueSource:
    """一次请求内的问题单数据源：明细行 + 出处标记，供各领域行复用。"""

    def __init__(self, rows: Optional[List[dict]], stamp: Optional[str],
                 note: Optional[str], source: str, project: Optional[str]):
        self.rows = rows            # None＝不可用
        self.stamp = stamp          # 快照日 / Excel 文件时间
        self.note = note
        self.source = source        # snapshot / excel
        self.project = project


def resolve_issue_source(db: Session, project: Optional[str]) -> IssueSource:
    """选定问题单数据源：指定项目的最新快照 →（无任何快照时）回退老的 Excel 报表。

    回退是为了不让还没接 API 采集的部署丢掉这一列；一旦有快照就以快照为准，
    因为只有快照带项目维度，Excel 报表是"全部混在一起"的。
    """
    opts = issue_projects(db)
    with_snap = [o for o in opts if o.latest_date]
    picked = None
    if project:
        picked = next((o for o in with_snap if o.project == project), None)
        if picked is None:
            # 指定了项目但它没有快照：如实说明，不要静默换成别的项目的数字
            known = next((o for o in opts if o.project == project), None)
            note = f"项目「{project}」还没有采集过快照" if known else f"未知项目「{project}」"
            return IssueSource(None, None, note, "snapshot", project)
    elif with_snap:
        picked = with_snap[0]
    if picked is not None:
        snap = latest_snapshot(db, picked.project)
        return IssueSource(snapshot_rows(snap) if snap else [],
                           snap.snapshot_date if snap else None,
                           None, "snapshot", picked.project)
    raw, mtime, note = load_issue_raw()
    return IssueSource(raw, mtime, note, "excel", None)
