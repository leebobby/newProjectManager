"""关键特性目录：CRUD + 机台多对多关联 + by-machine 查询。"""


def test_catalog_crud_and_machine_binding(client, admin_headers, machine_id):
    r = client.post("/api/key-features", headers=admin_headers, json={
        "name": "回归-特性A", "status": "开发", "total_sr": 10, "accepted_sr": 3, "to_test_sr": 5,
        "fo": "张三", "se": "李四"})
    assert r.status_code == 200, r.text
    feat = r.json()
    assert feat["status"] == "开发" and feat["machine_ids"] == []

    r = client.put(f"/api/key-features/{feat['id']}", headers=admin_headers, json={
        "version": feat["version"], "status": "测试"})
    assert r.status_code == 200 and r.json()["status"] == "测试"

    # 机台绑定
    r = client.put(f"/api/key-features/machine/{machine_id}", headers=admin_headers,
                   json={"feature_ids": [feat["id"]]})
    assert r.status_code == 200, r.text
    by_machine = client.get("/api/key-features/by-machine", headers=admin_headers).json()
    bound = by_machine.get(str(machine_id), [])
    assert any(f["id"] == feat["id"] and f["status"] == "测试" for f in bound)

    # 解绑
    r = client.put(f"/api/key-features/machine/{machine_id}", headers=admin_headers,
                   json={"feature_ids": []})
    assert r.status_code == 200
    by_machine = client.get("/api/key-features/by-machine", headers=admin_headers).json()
    assert not any(f["id"] == feat["id"] for f in by_machine.get(str(machine_id), []))


def test_invalid_status_rejected(client, admin_headers):
    r = client.post("/api/key-features", headers=admin_headers,
                    json={"name": "坏状态", "status": "不存在的状态"})
    assert r.status_code == 422
