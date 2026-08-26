"""客户面条目的新增：汇总页「新增」按钮走的就是这条接口。

条目在库里**始终挂在机台上**（`machine_status_id` 必填，`customer_id` 由机台推导），
所以汇总页新增必须先选客户再选机台——总览页天然带着机台上下文，汇总页没有。
这里钉住三件事：

1. 新增是**协作编辑域**（登录用户即可），不是 admin 专属——
   做成 admin 才能建的话，现场的人只能干看着；
2. `customer_id` 跟着机台走，前端传什么都不算数（否则汇总页按战场分组会对不上）；
3. 三种 kind（问题 / 需求 / 事务）都能建，且建完就出现在汇总列表里——
   汇总页三类都显示，只让建「问题」等于没解决问题。
"""
import pytest


@pytest.fixture(scope="module")
def member_headers(client, admin_headers):
    """一个普通登录用户（非 admin）。"""
    client.post("/api/users", headers=admin_headers,
                json={"username": "cifield", "password": "field123",
                      "full_name": "现场同学", "role": "normal", "can_login": True})
    r = client.post("/api/auth/login", json={"username": "cifield", "password": "field123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.parametrize("kind", ["issue", "demand", "task"])
def test_member_can_create_each_kind(client, member_headers, machine_id, kind):
    r = client.post("/api/customer-issues", headers=member_headers,
                    json={"machine_status_id": machine_id, "kind": kind,
                          "description": f"新增-{kind}"})
    assert r.status_code == 200, r.text
    item = r.json()
    assert item["kind"] == kind
    rows = client.get("/api/customer-issues", headers=member_headers).json()
    assert item["id"] in {x["id"] for x in rows}, "建完要能在汇总页看到"


def test_customer_id_follows_machine(client, admin_headers, machine_id):
    """前端传的 customer_id 一律不算数——跟着机台走，否则汇总页按战场分组会对不上。"""
    machine = next(m for m in client.get("/api/customer-status", headers=admin_headers).json()
                   if m["id"] == machine_id)
    r = client.post("/api/customer-issues", headers=admin_headers,
                    json={"machine_status_id": machine_id, "description": "跟随机台",
                          "customer_id": 999999})
    assert r.status_code == 200, r.text
    assert r.json()["customer_id"] == machine["customer_id"]


def test_unknown_machine_404(client, admin_headers):
    r = client.post("/api/customer-issues", headers=admin_headers,
                    json={"machine_status_id": 999999, "description": "没有这台机器"})
    assert r.status_code == 404


def test_raised_at_defaults_to_today(client, admin_headers, machine_id):
    """提出时间留空由服务端盖当天——前端弹窗也默认填今天，两边同款。"""
    import datetime
    r = client.post("/api/customer-issues", headers=admin_headers,
                    json={"machine_status_id": machine_id, "description": "默认提出时间"})
    assert r.json()["raised_at"] == datetime.date.today().strftime("%Y-%m-%d")
