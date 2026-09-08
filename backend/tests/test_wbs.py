"""WBS：层数不限的树、逐层汇总、以及「拆开之后父行自己填的数就让位」。

三条口径是这套东西的全部意义，坏了不会报错，只是数字对不上：
1. 能不能填看有没有子行，不看在第几层；
2. 完成度按人天加权；
3. 「已变更 / 不涉及」整行不进统计，但排除多少条要报出来。

**模块顶层不 import 应用模块**（见 CLAUDE.md）：conftest 的 client 夹具靠 os.chdir
把 sqlite:///./app.db 指到临时目录，收集阶段的顶层 import 会赶在 chdir 之前
把引擎连上仓库里的 backend/app.db。
"""
import pytest


@pytest.fixture(scope="module")
def special_id(client, admin_headers):
    r = client.post("/api/specials", json={"name": "视觉标定精度提升"}, headers=admin_headers)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


@pytest.fixture
def plan(client, admin_headers, special_id):
    """每个用例一份**全新**的 WBS，并套好标准模板（6 个分组）。

    共用一份的话用例之间就靠执行顺序传状态了：单跑某一个会挂，而且改动一个
    用例会莫名其妙弄坏另一个。
    """
    r = client.post("/api/wbs/plans",
                    json={"name": "视觉标定特性调试 WBS", "kind": "special",
                          "special_id": special_id},
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    return client.post(f"/api/wbs/plans/{pid}/apply-template", headers=admin_headers).json()


def _add(client, headers, plan_id, parent_id=None, **kw):
    body = {"parent_id": parent_id, "name": kw.pop("name", "行")}
    body.update(kw)
    r = client.post(f"/api/wbs/plans/{plan_id}/items", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _by_code(detail):
    return {i["code"]: i for i in detail["items"]}


def test_plan_carries_its_ref(client, plan):
    assert plan["kind"] == "special"
    assert plan["ref_name"] == "视觉标定精度提升"
    assert plan["kind_label"] == "专项"


def test_ref_must_actually_exist(client, admin_headers):
    """归属指向一个不存在的对象 → 400。不拦的话页面上归属那栏是空的，看着像没填。"""
    r = client.post("/api/wbs/plans",
                    json={"name": "野 WBS", "kind": "special", "special_id": 99999},
                    headers=admin_headers)
    assert r.status_code == 400


def test_template_is_add_only(client, admin_headers, plan):
    """套模板只增不删，重复套幂等（同专项模板的语义）。"""
    assert len(plan["items"]) == 6
    _add(client, admin_headers, plan["id"], None, name="自己加的分组")
    again = client.post(f"/api/wbs/plans/{plan['id']}/apply-template",
                        headers=admin_headers).json()
    names = [i["name"] for i in again["items"]]
    assert len(again["items"]) == 7, "重复套用不该再加一遍模板里的分组"
    assert "自己加的分组" in names, "模板外的行一律保留"


def test_codes_follow_position_not_storage(client, admin_headers, plan):
    """编号按 parent + sort_order 现算：加子项、改层级之后自动重排。"""
    pid = plan["id"]
    g2 = _by_code(plan)["2"]     # 标定与参数整定
    a = _add(client, admin_headers, pid, g2["id"], name="相机标定")
    codes = [i["code"] for i in a["items"]]
    assert "2.1" in codes
    b = _add(client, admin_headers, pid, _by_code(a)["2.1"]["id"], name="内参标定",
             man_days=2, progress_pct=100, status="已完成", owner_user_id=1)
    assert "2.1.1" in [i["code"] for i in b["items"]], "层数不限，第三层要出得来"


def test_rollup_replaces_what_the_parent_had_filled(client, admin_headers, plan):
    """把一行拆开的那一刻，它自己填的人天让位给子行加出来的数。

    这是「能不能填看有没有子行」的核心：父子两个数不可能对不上，因为父的数
    根本不是填出来的。
    """
    pid = plan["id"]
    g3 = _by_code(plan)["3"]
    leaf = _add(client, admin_headers, pid, g3["id"], name="单站功能验证",
                man_days=8, progress_pct=50, status="进行中", owner_user_id=1)
    node = _by_code(leaf)["3.1"]
    assert node["is_leaf"] is True and node["roll_days"] == 8

    # 给它加一个 3 人天的子项 → 自己那 8 人天让位
    after = _add(client, admin_headers, pid, node["id"], name="子任务",
                 man_days=3, progress_pct=100, status="已完成", owner_user_id=1)
    parent = _by_code(after)["3.1"]
    assert parent["is_leaf"] is False
    assert parent["roll_days"] == 3, "父行的人天只能是子行加出来的"
    assert parent["roll_pct"] == 100
    assert _by_code(after)["3"]["roll_days"] == 3, "汇总要一路加到顶"


def test_writes_to_a_parent_row_are_ignored(client, admin_headers, plan):
    """有子行之后再写父行的人天/状态，服务端丢掉——不然父子两个数会对不上。"""
    pid = plan["id"]
    g3 = _by_code(plan)["3"]
    a = _add(client, admin_headers, pid, g3["id"], name="单站功能验证", man_days=8)
    _add(client, admin_headers, pid, _by_code(a)["3.1"]["id"], name="子", man_days=3,
         progress_pct=100, status="已完成", owner_user_id=1)
    d = client.get(f"/api/wbs/plans/{pid}", headers=admin_headers).json()
    parent = _by_code(d)["3.1"]
    r = client.put(f"/api/wbs/items/{parent['id']}",
                   json={"man_days": 99, "progress_pct": 5, "name": "单站功能验证（改名）"},
                   headers=admin_headers)
    assert r.status_code == 200
    now = _by_code(r.json())["3.1"]
    assert now["name"] == "单站功能验证（改名）", "非汇总字段照常改"
    assert now["roll_days"] == 3, "人天仍然是子行加出来的，写入被忽略"


def test_progress_is_weighted_by_man_days(client, admin_headers, plan):
    """完成度按人天加权，不按条数：20 人天的包和 1 人天的包不该各算一条。"""
    pid = plan["id"]
    g4 = _by_code(plan)["4"]
    _add(client, admin_headers, pid, g4["id"], name="大包", man_days=20,
         progress_pct=100, status="已完成", owner_user_id=1)
    a = _add(client, admin_headers, pid, g4["id"], name="小包", man_days=1,
             progress_pct=0, status="未开始", owner_user_id=1)
    node = _by_code(a)["4"]
    assert node["roll_days"] == 21
    assert node["roll_pct"] == 95, "Σ(人天×完成度)÷Σ人天 = 2000/21 ≈ 95，按条数算会得 50"


def test_uncounted_rows_are_excluded_and_reported(client, admin_headers, plan):
    """「已变更 / 不涉及」不进统计，但排除了几条、多少人天要如实报出来。"""
    pid = plan["id"]
    before_days = plan["total_days"]
    g5 = _by_code(plan)["5"]
    a = _add(client, admin_headers, pid, g5["id"], name="不做了", man_days=7,
             progress_pct=0, status="已变更", owner_user_id=1)
    assert a["total_days"] == before_days, "已变更的人天不该加进总数"
    assert a["excluded"] >= 1
    assert a["excluded_days"] >= 7, "排除了多少人天要报出来"
    assert _by_code(a)["5.1"]["issues"] == [], "不计入的行不该再提示补录"


def test_flagged_rows_are_leaves_only(client, admin_headers, plan):
    """待补录只判叶子：父行那几项本来就是汇总来的，判它等于骂错人。"""
    pid = plan["id"]
    a = _add(client, admin_headers, pid, None, name="缺东西的分组")
    node = next(i for i in a["items"] if i["name"] == "缺东西的分组")
    assert node["is_leaf"] is True
    assert "没填负责人" in node["issues"] and "没填工期" in node["issues"]
    kid = _add(client, admin_headers, pid, node["id"], name="子", man_days=1,
               progress_pct=0, status="未开始", owner_user_id=1)
    parent = next(i for i in kid["items"] if i["id"] == node["id"])
    assert parent["issues"] == [], "有了子行之后，父行不再被判缺工期"


def test_move_refuses_to_create_a_cycle(client, admin_headers, plan):
    """把一行挂到自己的子孙下面 → 400。

    不拦的话那棵子树从根上够不着，页面表现是"这几行凭空消失"，而库里一行没少。
    """
    pid = plan["id"]
    g3 = _by_code(plan)["3"]
    a = _add(client, admin_headers, pid, g3["id"], name="父")
    parent = _by_code(a)["3.1"]
    b = _add(client, admin_headers, pid, parent["id"], name="子")
    child = _by_code(b)["3.1.1"]
    r = client.post(f"/api/wbs/items/{parent['id']}/move",
                    json={"new_parent_id": child["id"]}, headers=admin_headers)
    assert r.status_code == 400
    r2 = client.post(f"/api/wbs/items/{parent['id']}/move",
                     json={"new_parent_id": parent["id"]}, headers=admin_headers)
    assert r2.status_code == 400


def test_move_promotes_with_its_subtree(client, admin_headers, plan):
    """升级：连同子树一起搬，编号跟着位置重排。"""
    pid = plan["id"]
    g3 = _by_code(plan)["3"]
    a = _add(client, admin_headers, pid, g3["id"], name="父")
    node = _by_code(a)["3.1"]
    b = _add(client, admin_headers, pid, node["id"], name="子")
    kid_id = _by_code(b)["3.1.1"]["id"]
    r = client.post(f"/api/wbs/items/{node['id']}/move",
                    json={"new_parent_id": None}, headers=admin_headers)
    assert r.status_code == 200
    items = {i["id"]: i for i in r.json()["items"]}
    assert items[node["id"]]["depth"] == 1
    assert items[kid_id]["parent_id"] == node["id"], "子树跟着走"
    assert items[kid_id]["depth"] == 2


def test_reorder_rejects_rows_from_another_level(client, admin_headers, plan):
    """混进别的父级的行 → 400。静默忽略会让人以为排序时灵时不灵。"""
    pid = plan["id"]
    g1 = _by_code(plan)["1"]
    _add(client, admin_headers, pid, g1["id"], name="深一层")
    d = client.get(f"/api/wbs/plans/{pid}", headers=admin_headers).json()
    roots = [i["id"] for i in d["items"] if i["depth"] == 1]
    deep = next(i["id"] for i in d["items"] if i["depth"] == 2)
    r = client.post(f"/api/wbs/plans/{pid}/reorder",
                    json={"parent_id": None, "ids": roots[:2] + [deep]},
                    headers=admin_headers)
    assert r.status_code == 400
    ok = client.post(f"/api/wbs/plans/{pid}/reorder",
                     json={"parent_id": None, "ids": list(reversed(roots))},
                     headers=admin_headers)
    assert ok.status_code == 200
    new_roots = [i["id"] for i in ok.json()["items"] if i["depth"] == 1]
    assert new_roots[:len(roots)] == list(reversed(roots))


def test_optimistic_lock(client, admin_headers, plan):
    """带着过期的 version 保存 → 409（前端拦截器统一弹提示）。"""
    pid = plan["id"]
    item = plan["items"][0]
    r1 = client.put(f"/api/wbs/items/{item['id']}",
                    json={"name": "改一次", "version": item["version"]}, headers=admin_headers)
    assert r1.status_code == 200
    r2 = client.put(f"/api/wbs/items/{item['id']}",
                    json={"name": "再改一次", "version": item["version"]}, headers=admin_headers)
    assert r2.status_code == 409


def test_only_admin_can_delete_a_whole_plan(client, admin_headers, special_id):
    """删整份 WBS ＝ 仅 admin（删掉的是别人跟了几个月的计划）；
    树里的增删改 ＝ 登录用户。"""
    r = client.post("/api/wbs/plans",
                    json={"name": "临时 WBS", "kind": "special", "special_id": special_id},
                    headers=admin_headers)
    pid = r.json()["id"]
    client.post("/api/users", json={"username": "wbsuser", "password": "pw123456",
                                    "full_name": "普通用户", "role": "normal",
                                    "can_login": True}, headers=admin_headers)
    tok = client.post("/api/auth/login",
                      json={"username": "wbsuser", "password": "pw123456"}).json()["access_token"]
    uh = {"Authorization": f"Bearer {tok}"}

    a = client.post(f"/api/wbs/plans/{pid}/items", json={"name": "普通用户加的"}, headers=uh)
    assert a.status_code == 200, "树里的增删改：登录用户就够"
    item_id = a.json()["items"][0]["id"]
    assert client.delete(f"/api/wbs/items/{item_id}", headers=uh).status_code == 200

    assert client.delete(f"/api/wbs/plans/{pid}", headers=uh).status_code == 403
    assert client.delete(f"/api/wbs/plans/{pid}", headers=admin_headers).status_code == 200
