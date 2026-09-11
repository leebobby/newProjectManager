"""度量看板 · 客户面问题看板：按战场 / 业务组 / 分类专项三个维度。

钉住三件会悄悄错掉的事：
1. **各行相加＝合计**——分组与合计共用同一份 summarize，不然"分项加起来和总数对不上"；
2. **没填该维度的行要有自己那一桶并排最后**，不能藏起来（那批正是最该被捞出来补录的）；
3. **逾期口径与汇总页一致**：只有 CLOSED 不算逾期，挂起与待升级版本都算。
"""
import datetime

import pytest


@pytest.fixture(scope="module")
def yesterday():
    return (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")


@pytest.fixture(scope="module")
def seeded(client, admin_headers, machine_id, yesterday):
    """五条条目：两条有分类、一条没分类、一条已闭环、一条待升级版本且已过期。"""
    def add(**kw):
        body = {"machine_status_id": machine_id, "description": "看板用例"}
        body.update(kw)
        r = client.post("/api/customer-issues", headers=admin_headers, json=body)
        assert r.status_code == 200, r.text
        return r.json()

    add(description="板-上电专项-开着", category="上电专项", urgency="重要紧急")
    add(description="板-上电专项-已闭环", category="上电专项", status="CLOSED")
    add(description="板-联调专项", category="联调专项")
    add(description="板-没分类")
    add(description="板-待升级已过期", category="联调专项",
        status="待升级版本", due_date=yesterday)
    return True


def _board(client, headers):
    r = client.get("/api/metrics/customer-issues", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_rows_add_up_to_the_summary(client, admin_headers, seeded):
    """三个维度各自相加都要等于合计——差一点就说明分组和合计不是同一份口径。"""
    b = _board(client, admin_headers)
    for dim in ("battlefield", "group", "category"):
        for field in ("total", "open", "closed", "overdue", "pending_upgrade"):
            got = sum(r[field] for r in b[dim])
            assert got == b["summary"][field], f"{dim}.{field} 相加 {got} ≠ 合计 {b['summary'][field]}"


def test_unassigned_bucket_is_shown_and_sorted_last(client, admin_headers, seeded):
    """没填分类的行要有自己那一桶，并且无论多少条都排最后。"""
    b = _board(client, admin_headers)
    cats = b["category"]
    unset = [r for r in cats if r["unassigned"]]
    assert len(unset) == 1, "没填分类的行必须单独成一桶，不能并进别的行"
    assert unset[0]["name"] == "未分类"
    assert cats[-1]["unassigned"] is True, "兜底桶排最后"
    assert unset[0]["total"] >= 1


def test_category_split(client, admin_headers, seeded):
    b = _board(client, admin_headers)
    by_name = {r["name"]: r for r in b["category"]}
    assert by_name["上电专项"]["total"] == 2
    assert by_name["上电专项"]["closed"] == 1
    assert by_name["上电专项"]["open"] == 1
    assert by_name["上电专项"]["critical"] == 1
    assert by_name["联调专项"]["total"] == 2


def test_pending_upgrade_counts_as_open_and_overdue(client, admin_headers, seeded):
    """待升级版本＋已过期：既在 open 里，也在 overdue 里——与汇总页同口径。"""
    b = _board(client, admin_headers)
    by_name = {r["name"]: r for r in b["category"]}
    row = by_name["联调专项"]
    assert row["pending_upgrade"] == 1
    assert row["open"] == 2          # 两条都没闭环
    assert row["overdue"] == 1


def test_board_matches_the_tracking_page_summary(client, admin_headers, seeded):
    """看板合计与汇总页统计卡必须是同一批数字：两处各写一份迟早分叉。"""
    b = _board(client, admin_headers)
    s = client.get("/api/customer-issues/summary", headers=admin_headers).json()
    for field in ("total", "open", "closed", "critical", "overdue", "pending_upgrade", "on_hold"):
        assert b["summary"][field] == s[field], f"{field} 对不上"
