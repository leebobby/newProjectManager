"""回归测试公共夹具。

原则：每个测试会话在临时目录里起一个**全新**数据库——
import main 时 create_all 建表 + seed 注入 admin/admin123 与两台示例机台，
automigrate 自动追平 Alembic head。不碰开发库 app.db，可重复、无脏数据。

跑法（backend/ 下）：
    python -m pytest tests -q
"""
import os
import pathlib
import sys

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    """TestClient，背后是临时目录里的全新 SQLite 库。"""
    workdir = tmp_path_factory.mktemp("db")
    os.chdir(workdir)  # database.py 的 sqlite:///./app.db 相对 cwd
    from fastapi.testclient import TestClient
    import main
    return TestClient(main.app)


@pytest.fixture(scope="session")
def admin_headers(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, f"seed admin 登录失败: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="session")
def machine_id(client, admin_headers):
    """seed 的第一台机台（customer_status.id）。"""
    rows = client.get("/api/customer-status", headers=admin_headers).json()
    assert rows, "seed 应注入示例机台"
    return rows[0]["id"]
