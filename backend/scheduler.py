"""后台调度：APScheduler 跑定时任务。

当前任务：
- daily_ddl_scan：每天 08:00 扫描 special_tasks / special_risks（按 planned_close_date）
  与 customer_issues（按 due_date），对未关闭、落在未来 3 天内/已逾期的，
  给 owner_user_id 发通知。
- daily_issue_snapshot：每天定时采集各项目问题单快照。执行时刻由
  config.issue_snapshot_time（HH:MM，默认 07:30）决定，可在问题单管理「配置」中改；
  改完由 config 路由调 apply_issue_snapshot_schedule() 热更新，不用重启。

设计原则：
- 任何异常吞掉，不能阻塞 FastAPI
- 同一条记录每天最多发一条（用一个简单内存去重，进程重启会重置；够用）
- 调度器作用域是进程内，未来上多 worker 需要换 Redis 锁
"""
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler

import models
from database import SessionLocal
from notify import dispatch

logger = logging.getLogger("scheduler")

_DATE_RE = re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")

_sent_today: set[tuple[str, int, str]] = set()  # (source_type, id, "soon"|"overdue") for dedupe per process-day


def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    m = _DATE_RE.search(s)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _scan_specials(db, today: date) -> int:
    soon_threshold = today + timedelta(days=3)
    cnt = 0

    for model, source_type, kind_label in (
        (models.SpecialTask, "special_task", "事务"),
        (models.SpecialRisk, "special_risk", "风险"),
    ):
        rows = db.query(model).filter(model.status == "open").all()
        for r in rows:
            if not r.owner_user_id:
                continue
            d = _parse_date(r.planned_close_date)
            if d is None:
                continue
            link = f"/specials/{r.special_id}"
            preview = (r.content or "").strip().splitlines()[0][:60] if r.content else ""

            if d < today:
                key = (source_type, r.id, "overdue")
                if key in _sent_today:
                    continue
                _sent_today.add(key)
                dispatch(
                    db, kind="overdue",
                    title=f"[已逾期] {kind_label}：{preview}",
                    body=f"计划闭环日期 {r.planned_close_date}，已逾期 {(today - d).days} 天",
                    link=link, source_type=source_type, source_id=r.id,
                    recipient_ids=[r.owner_user_id], extra_subs=True,
                )
                cnt += 1
            elif d <= soon_threshold:
                key = (source_type, r.id, "soon")
                if key in _sent_today:
                    continue
                _sent_today.add(key)
                dispatch(
                    db, kind="due_soon",
                    title=f"[临期提醒] {kind_label}：{preview}",
                    body=f"计划闭环日期 {r.planned_close_date}，剩 {(d - today).days} 天",
                    link=link, source_type=source_type, source_id=r.id,
                    recipient_ids=[r.owner_user_id], extra_subs=True,
                )
                cnt += 1
    return cnt


def _scan_customer_issues(db, today: date) -> int:
    """客户面问题/关键事务：以 due_date（预计闭环）为基准做临期/逾期提醒。

    只提醒未闭环且有责任人的条目。挂起同样会提醒——挂起只是没在推进，
    不代表这个日期不算数，正是需要有人来决定要不要重排的时候。
    """
    soon_threshold = today + timedelta(days=3)
    cnt = 0
    rows = (
        db.query(models.CustomerIssue)
        .filter(models.CustomerIssue.status != "CLOSED")
        .all()
    )
    for r in rows:
        if not r.owner_user_id:
            continue
        d = _parse_date(r.due_date or "")
        if d is None:
            continue
        label = {"issue": "问题", "demand": "需求"}.get(r.kind, "关键事务")
        m = r.machine_status
        where = f"{(m.battlefield if m else '') or ''} {(m.machine_id if m else '') or ''}".strip()
        preview = (r.description or "").strip().splitlines()[0][:60] if r.description else ""

        if d < today:
            key = ("customer_issue", r.id, "overdue")
            if key in _sent_today:
                continue
            _sent_today.add(key)
            dispatch(
                db, kind="overdue",
                title=f"[已逾期] {label}：{preview}",
                body=f"{where}｜预计闭环 {r.due_date}，已逾期 {(today - d).days} 天",
                link="/customer-issues", source_type="customer_issue", source_id=r.id,
                recipient_ids=[r.owner_user_id],
            )
            cnt += 1
        elif d <= soon_threshold:
            key = ("customer_issue", r.id, "soon")
            if key in _sent_today:
                continue
            _sent_today.add(key)
            dispatch(
                db, kind="due_soon",
                title=f"[临期提醒] {label}：{preview}",
                body=f"{where}｜预计闭环 {r.due_date}，剩 {(d - today).days} 天",
                link="/customer-issues", source_type="customer_issue", source_id=r.id,
                recipient_ids=[r.owner_user_id],
            )
            cnt += 1
    return cnt


def daily_ddl_scan() -> None:
    """每天 08:00 跑一次。"""
    global _sent_today
    today = date.today()
    # 每天清空一次去重集合（按日期）
    if not _sent_today or any(
        # 偷个懒：直接清；日期切换交给 scheduler 时间触发即可
        True for _ in [None]
    ):
        _sent_today = set()

    db = SessionLocal()
    try:
        n = _scan_specials(db, today) + _scan_customer_issues(db, today)
        logger.info("daily_ddl_scan: %s 条通知已发", n)
    except Exception as e:
        logger.exception("daily_ddl_scan 失败: %s", e)
    finally:
        db.close()


def daily_issue_snapshot() -> None:
    """每天定时采集各项目问题单快照：维度数字入库、明细落文件。

    未配置 API 脚本或项目列表则跳过；单项目失败不影响其它项目。
    每次执行（成败）都会在 issue_collect_logs 留一条日志，供页面「采集日志」查看。
    """
    from routers.config import _load as _load_config  # 延迟导入避免循环依赖
    cfg = _load_config()
    projects = cfg.get("issue_api_projects") or []
    if not (cfg.get("issue_api_script_path") or "").strip() or not projects:
        return
    from routers.issues import collect_with_log  # 延迟导入
    db = SessionLocal()
    try:
        ok = sum(1 for p in projects if collect_with_log(db, p, source="auto")["ok"])
        logger.info("daily_issue_snapshot: %s/%s 个项目已采集", ok, len(projects))
    except Exception as e:
        logger.exception("daily_issue_snapshot 失败: %s", e)
    finally:
        db.close()


# ─── 采集时刻可配置 ──────────────────────────────────────────────────────────
DEFAULT_SNAPSHOT_TIME = "07:30"
_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _snapshot_schedule() -> tuple[bool, int, int]:
    """读取 config：(是否启用, 时, 分)。解析失败回退默认时刻。"""
    try:
        from routers.config import _load as _load_config
        cfg = _load_config()
    except Exception:
        cfg = {}
    enabled = cfg.get("issue_snapshot_enabled")
    enabled = True if enabled is None else bool(enabled)
    m = _TIME_RE.match(str(cfg.get("issue_snapshot_time") or "").strip())
    if not m:
        m = _TIME_RE.match(DEFAULT_SNAPSHOT_TIME)
    return enabled, int(m.group(1)), int(m.group(2))


_scheduler: Optional[BackgroundScheduler] = None


def apply_issue_snapshot_schedule() -> str:
    """按当前 config 重建每日采集任务。改完配置立即调用，无需重启后端。

    返回一句人话描述，方便调用方回给前端。
    """
    if _scheduler is None:
        return "调度器未启动"
    enabled, hour, minute = _snapshot_schedule()
    if not enabled:
        try:
            _scheduler.remove_job("daily_issue_snapshot")
        except Exception:
            pass
        logger.info("daily_issue_snapshot 已停用")
        return "每日自动采集已停用"
    _scheduler.add_job(daily_issue_snapshot, "cron", hour=hour, minute=minute,
                       id="daily_issue_snapshot", replace_existing=True)
    logger.info("daily_issue_snapshot 已排期 @%02d:%02d", hour, minute)
    return f"每日自动采集时间已设为 {hour:02d}:{minute:02d}"


def start() -> None:
    """在 main.py 启动时调用一次。"""
    global _scheduler
    if _scheduler is not None:
        return
    sched = BackgroundScheduler(timezone="Asia/Shanghai")
    # 每天早上 8:00：临期/逾期扫描
    sched.add_job(daily_ddl_scan, "cron", hour=8, minute=0, id="daily_ddl_scan",
                  replace_existing=True)
    sched.start()
    _scheduler = sched
    # 问题单快照采集：时刻来自 config，可在页面「配置」中改
    apply_issue_snapshot_schedule()
    logger.info("APScheduler started; daily_ddl_scan@08:00")
