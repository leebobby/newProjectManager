"""客户面问题的**统计口径**：一处实现，汇总页的统计卡与度量看板的问题看板共用。

两处各写一份的表现是同一批条目在两个页面上给出不同的「逾期」「未闭环」条数，
而两边看着都对——这正是最难被当成 bug 报上来的那类。

三条口径写死在这里，改之前先读 CLAUDE.md「枚举：单一来源」里客户面状态那一条：

- **未闭环 ＝ `status != "CLOSED"`**。四档状态里 OPEN / 挂起 / 待升级版本都算未闭环，
  新增状态档天然落在这一边，不用回来改。
- **逾期 ＝ 有预计闭环时间、已过期、且还没闭环**。「超过」才算，当天到期不算——
  记成超期会让人白紧张一天（同 `_issue_source.overdue_stats`）。
- **没填预计闭环时间的条数要一起报**（`overdue_unknown`）。那一列是选填的，
  整组都没填时「逾期 0」会被读成"一条都没超期"，所以要能分出"没超期"和"算不出来"。
"""
from datetime import date

import enums


def _today() -> str:
    return date.today().strftime("%Y-%m-%d")


def is_open(row) -> bool:
    """还没闭环。四档状态里只有 CLOSED 不算。"""
    return row.status != "CLOSED"


def is_overdue(row, today: str = None) -> bool:
    """逾期＝有预计闭环时间、已过期、且还没闭环。

    **只有 CLOSED 不算逾期**，挂起与待升级版本都算：挂起只是没在推进，
    待升级版本是改好了但现场还没升上去——问题在客户那儿都还在。给这两档开特例
    的话，「逾期未闭环」会少一截，而没人说得清少的是哪些。
    """
    if not is_open(row) or not (row.due_date or "").strip():
        return False
    return row.due_date.strip() < (today or _today())


def summarize(rows, today: str = None) -> dict:
    """一批条目的统计口径。分组看板按维度切完之后对每一组调它，保证各组与合计同口径。"""
    today = today or _today()
    open_rows = [r for r in rows if is_open(r)]
    return {
        "total": len(rows),
        "open": len(open_rows),
        "closed": sum(1 for r in rows if r.status == "CLOSED"),
        "on_hold": sum(1 for r in rows if r.status == "挂起"),
        "pending_upgrade": sum(1 for r in rows if r.status == "待升级版本"),
        "critical": sum(1 for r in open_rows if r.urgency == enums.CUSTOMER_ISSUE_URGENCIES[0]),
        "overdue": sum(1 for r in open_rows if is_overdue(r, today)),
        # 未闭环里没填预计闭环时间的条数：整组都没填时「逾期 0」不能读成"没超期"
        "overdue_unknown": sum(1 for r in open_rows if not (r.due_date or "").strip()),
    }
