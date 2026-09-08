"""关键特性 × 项目 的 FO / SE / TFO：继承、判重、清空项目。

覆盖三件容易悄悄错掉的事：
1. FO/SE 留空时**继承特性级的值并标出来**——不标的话，改的人会以为自己在改本项目的值；
2. 同一个 (特性, 项目) 只能有一行——两行并存时页面上看着都对，谁也说不清哪个是最新的；
3. 把项目清空（project_id=None）要真的存进去——SQLite 里 NULL 互不相等，
   数据库唯一约束只挡得住一半，判重必须在路由里做。
"""
import pytest


@pytest.fixture()
def feature_id(client, admin_headers):
    """一条带特性级 FO/SE 的关键特性。"""
    resp = client.post("/api/key-features", headers=admin_headers, json={
        "name": "多机联动", "status": "分析", "fo": "特性级FO", "se": "特性级SE",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


@pytest.fixture()
def project_id(client, admin_headers):
    resp = client.post("/api/roadmap/projects", headers=admin_headers,
                       json={"name": "YLS3000-干系人用例"})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _rows(client, admin_headers):
    resp = client.get("/api/stakeholders/feature-owners", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_blank_fo_inherits_from_feature_and_says_so(client, admin_headers, feature_id, project_id):
    """FO 留空＝显示特性上那个值，且必须标成「继承」。"""
    resp = client.post("/api/stakeholders/feature-owners", headers=admin_headers, json={
        "key_feature_id": feature_id, "project_id": project_id, "fo": "", "se": "本项目SE", "tfo": "本项目TFO",
    })
    assert resp.status_code == 200, resp.text
    row = resp.json()

    # 继承来的
    assert row["fo"] == ""                     # 这一行自己没填
    assert row["fo_effective"] == "特性级FO"    # 显示的是特性上的
    assert row["fo_inherited"] is True
    # 本行自己填的不算继承
    assert row["se_effective"] == "本项目SE"
    assert row["se_inherited"] is False
    # TFO 在特性表里没有对应列，空就是空，不继承
    assert row["tfo"] == "本项目TFO"
    assert row["feature_name"] == "多机联动"
    assert row["project_name"] == "YLS3000-干系人用例"

    client.delete(f"/api/stakeholders/feature-owners/{row['id']}", headers=admin_headers)


def test_same_feature_and_project_twice_is_rejected(client, admin_headers, feature_id, project_id):
    """同一个 (特性, 项目) 第二行返回 400——两行并存时没人说得清哪个是最新的。"""
    first = client.post("/api/stakeholders/feature-owners", headers=admin_headers, json={
        "key_feature_id": feature_id, "project_id": project_id, "fo": "甲",
    })
    assert first.status_code == 200, first.text

    dup = client.post("/api/stakeholders/feature-owners", headers=admin_headers, json={
        "key_feature_id": feature_id, "project_id": project_id, "fo": "乙",
    })
    assert dup.status_code == 400

    # 换个项目（这里用「通用」那一档）就该放行
    generic = client.post("/api/stakeholders/feature-owners", headers=admin_headers, json={
        "key_feature_id": feature_id, "project_id": None, "fo": "乙",
    })
    assert generic.status_code == 200, generic.text
    # 通用那一行也只能有一条
    again = client.post("/api/stakeholders/feature-owners", headers=admin_headers, json={
        "key_feature_id": feature_id, "project_id": None, "fo": "丙",
    })
    assert again.status_code == 400

    for r in (first, generic):
        client.delete(f"/api/stakeholders/feature-owners/{r.json()['id']}", headers=admin_headers)


def test_clearing_project_is_persisted(client, admin_headers, feature_id, project_id):
    """把项目清成「通用」要真的落库——前端 clearable 清空后传的是 null 不是 undefined。"""
    row = client.post("/api/stakeholders/feature-owners", headers=admin_headers, json={
        "key_feature_id": feature_id, "project_id": project_id, "fo": "甲",
    }).json()

    resp = client.put(f"/api/stakeholders/feature-owners/{row['id']}", headers=admin_headers,
                      json={"project_id": None})
    assert resp.status_code == 200, resp.text
    assert resp.json()["project_id"] is None
    assert resp.json()["project_name"] == ""

    after = [r for r in _rows(client, admin_headers) if r["id"] == row["id"]][0]
    assert after["project_id"] is None

    client.delete(f"/api/stakeholders/feature-owners/{row['id']}", headers=admin_headers)


def test_unknown_feature_is_rejected(client, admin_headers):
    resp = client.post("/api/stakeholders/feature-owners", headers=admin_headers,
                       json={"key_feature_id": 999999, "fo": "甲"})
    assert resp.status_code == 400


def test_write_requires_admin(client, admin_headers, feature_id):
    """写入是主数据一档＝仅 admin；读对所有登录用户开放。"""
    client.post("/api/users", headers=admin_headers, json={
        "username": "fo_normal", "password": "pw123456", "full_name": "普通用户", "role": "normal",
    })
    token = client.post("/api/auth/login",
                        json={"username": "fo_normal", "password": "pw123456"}).json()["access_token"]
    normal = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/stakeholders/feature-owners", headers=normal).status_code == 200
    resp = client.post("/api/stakeholders/feature-owners", headers=normal,
                       json={"key_feature_id": feature_id, "fo": "甲"})
    assert resp.status_code == 403
