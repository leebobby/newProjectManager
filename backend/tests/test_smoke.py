"""全局冒烟：健康检查、登录、鉴权、导出可用性。"""
import io

import openpyxl


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_auth_required(client):
    assert client.get("/api/customer-status").status_code == 401


def test_alembic_tracked(client, admin_headers):
    """automigrate 应把新库 stamp 到 head（间接验证：迁移覆盖的表都在）。"""
    r = client.get("/api/customer-issues", headers=admin_headers)
    assert r.status_code == 200


def test_customer_issues_export_styled(client, admin_headers):
    r = client.get("/api/customer-issues/export.xlsx", headers=admin_headers)
    assert r.status_code == 200
    ws = openpyxl.load_workbook(io.BytesIO(r.content)).active
    assert ws.cell(1, 1).value == "客户 / 战场"
    assert ws.freeze_panes == "A2"          # xlsx_io.beautify 冻结表头


def test_special_export_ok(client, admin_headers):
    specials = client.get("/api/specials", headers=admin_headers).json()
    if not specials:  # 新库无专项则跳过
        return
    r = client.get(f"/api/specials/{specials[0]['id']}/export.xlsx", headers=admin_headers)
    assert r.status_code == 200
