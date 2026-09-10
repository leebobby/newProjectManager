"""客户面问题的状态四档：OPEN / CLOSED / 挂起 / **待升级版本**。

「待升级版本」＝问题在某个版本里已经改好、等现场升级上去才算完。加这一档时
容易漏掉的是它的**归属**，而漏掉之后每一处单独看都正常：

1. 它算**未闭环**——统计卡的 open、`include_closed=false` 的隐藏、到期提醒都得带上它；
2. 它算**逾期**（过了计划解决时间还没升上去，问题在客户那儿就还在）；
3. 它在默认排序里排在挂起之后、已闭环之前（越靠前越需要人推）；
4. 汇总里要能单独数出来——混在 open 里就分不出"还没人动"和"改好了等升级"。

另有一条边界：这一档**只属于客户面问题**，领域的事务/风险仍是三档。
"""
import datetime

import pytest


@pytest.fixture()
def yesterday():
    return (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")


def _create(client, headers, machine_id, **kw):
    body = {"machine_status_id": machine_id, "description": "状态用例"}
    body.update(kw)
    r = client.post("/api/customer-issues", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_pending_upgrade_is_accepted(client, admin_headers, machine_id):
    item = _create(client, admin_headers, machine_id, status="待升级版本",
                   description="待升级-可写入")
    assert item["status"] == "待升级版本"


def test_bogus_status_still_rejected(client, admin_headers, machine_id):
    """加了一档不等于放开校验——词表外的值照样 422。"""
    r = client.post("/api/customer-issues", headers=admin_headers, json={
        "machine_status_id": machine_id, "description": "非法状态", "status": "等版本",
    })
    assert r.status_code == 422, r.text


def test_pending_upgrade_counts_as_open_and_overdue(client, admin_headers, machine_id, yesterday):
    """未闭环 + 逾期都要算上它：开特例的话「逾期未闭环」会少一截，而没人说得清少的是哪些。"""
    item = _create(client, admin_headers, machine_id, status="待升级版本",
                   description="待升级-已过期", due_date=yesterday)

    rows = client.get("/api/customer-issues", headers=admin_headers,
                      params={"machine_status_id": machine_id}).json()
    row = next(x for x in rows if x["id"] == item["id"])
    assert row["overdue"] is True

    # include_closed=false ＝ 只看未闭环，它必须还在
    open_rows = client.get("/api/customer-issues", headers=admin_headers,
                           params={"machine_status_id": machine_id,
                                   "include_closed": False}).json()
    assert item["id"] in {x["id"] for x in open_rows}
    # overdue_only 同样捞得到
    od = client.get("/api/customer-issues", headers=admin_headers,
                    params={"machine_status_id": machine_id, "overdue_only": True}).json()
    assert item["id"] in {x["id"] for x in od}


def test_summary_counts_pending_upgrade_separately(client, admin_headers, machine_id):
    """汇总里单独一个数：混在 open 里就分不出"还没人动"和"改好了等升级"。"""
    before = client.get("/api/customer-issues/summary", headers=admin_headers).json()
    _create(client, admin_headers, machine_id, status="待升级版本", description="待升级-计数")
    after = client.get("/api/customer-issues/summary", headers=admin_headers).json()

    assert after["pending_upgrade"] == before["pending_upgrade"] + 1
    # 同时仍然计入未闭环
    assert after["open"] == before["open"] + 1
    assert after["closed"] == before["closed"]


def test_default_sort_puts_pending_upgrade_after_on_hold(client, admin_headers, machine_id):
    """默认排序按"离闭环还有多远"：OPEN → 挂起 → 待升级版本 → CLOSED。"""
    made = {}
    for st in ("CLOSED", "待升级版本", "挂起", "OPEN"):   # 故意乱序建
        made[st] = _create(client, admin_headers, machine_id, status=st,
                           description=f"排序-{st}", urgency="一般",
                           raised_at="2026-01-01")["id"]

    rows = client.get("/api/customer-issues", headers=admin_headers,
                      params={"machine_status_id": machine_id}).json()
    order = [x["id"] for x in rows if x["id"] in set(made.values())]
    assert order == [made["OPEN"], made["挂起"], made["待升级版本"], made["CLOSED"]]


def test_every_status_has_a_rank(client, admin_headers):
    """词表里每一档都要在排序表里有位置。

    加一档时最容易漏的就是 `CUSTOMER_ISSUE_STATUS_RANK`——漏了不报错，
    那一档静默落到兜底值 9，表现是"新状态的条目全被甩到列表最后面"，
    看着像排序坏了而不像少配了一个值。
    """
    import enums
    missing = [s for s in enums.CUSTOMER_ISSUE_STATUSES
               if s not in enums.CUSTOMER_ISSUE_STATUS_RANK]
    assert not missing, f"这些状态没有排序位置：{missing}"


def test_status_wordlist_is_customer_side_only(client, admin_headers):
    """「待升级版本」只属于客户面：领域的事务/风险没有"等现场升级"这一步。

    钉住这条是因为两张表的前三档一模一样，很容易被顺手同步过去，
    结果领域那边多出一个永远没人选的值。
    """
    import enums
    from routers.domains import _DOMAIN_RISK_STATUSES
    assert "待升级版本" in enums.CUSTOMER_ISSUE_STATUSES
    assert "待升级版本" not in _DOMAIN_RISK_STATUSES
