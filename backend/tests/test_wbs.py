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
                    json={"new_parent_id": child["id"], "tree_version": b["tree_version"]},
                    headers=admin_headers)
    assert r.status_code == 400
    r2 = client.post(f"/api/wbs/items/{parent['id']}/move",
                     json={"new_parent_id": parent["id"], "tree_version": b["tree_version"]},
                     headers=admin_headers)
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
                    json={"new_parent_id": None, "tree_version": b["tree_version"]},
                    headers=admin_headers)
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
                    json={"parent_id": None, "ids": roots[:2] + [deep],
                          "tree_version": d["tree_version"]},
                    headers=admin_headers)
    assert r.status_code == 400
    ok = client.post(f"/api/wbs/plans/{pid}/reorder",
                     json={"parent_id": None, "ids": list(reversed(roots)),
                           "tree_version": d["tree_version"]},
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


def test_stale_tree_version_rejects_reorder_delete_and_move(client, admin_headers, plan):
    """结构写入统一锁整棵树，而不是只锁被移动的那一行。"""
    pid = plan["id"]
    stale = plan["tree_version"]
    changed = _add(client, admin_headers, pid, name="并发新增")
    roots = [i for i in changed["items"] if i["depth"] == 1]
    victim = roots[-1]

    reorder = client.post(
        f"/api/wbs/plans/{pid}/reorder",
        json={"parent_id": None, "ids": [i["id"] for i in reversed(roots)],
              "tree_version": stale}, headers=admin_headers)
    assert reorder.status_code == 409

    delete = client.request("DELETE", f"/api/wbs/items/{victim['id']}",
                            json={"tree_version": stale}, headers=admin_headers)
    assert delete.status_code == 409

    move = client.post(
        f"/api/wbs/items/{victim['id']}/move",
        json={"new_parent_id": roots[0]["id"], "version": victim["version"],
              "tree_version": stale}, headers=admin_headers)
    assert move.status_code == 409


def test_successful_structure_operations_increment_tree_version(client, admin_headers, plan):
    """新增、排序、移动、删除和套模板每次成功提交都推进结构版本。"""
    pid = plan["id"]
    v = plan["tree_version"]

    created = _add(client, admin_headers, pid, name="待搬工作包")
    assert created["tree_version"] == v + 1
    v = created["tree_version"]
    row = next(i for i in created["items"] if i["name"] == "待搬工作包")
    roots = [i for i in created["items"] if i["depth"] == 1]

    ordered = client.post(
        f"/api/wbs/plans/{pid}/reorder",
        json={"parent_id": None, "ids": [i["id"] for i in reversed(roots)],
              "tree_version": v}, headers=admin_headers).json()
    assert ordered["tree_version"] == v + 1
    v = ordered["tree_version"]

    moved = client.post(
        f"/api/wbs/items/{row['id']}/move",
        json={"new_parent_id": roots[0]["id"], "version": row["version"],
              "tree_version": v}, headers=admin_headers).json()
    assert moved["tree_version"] == v + 1
    v = moved["tree_version"]

    deleted = client.request("DELETE", f"/api/wbs/items/{row['id']}",
                             json={"tree_version": v}, headers=admin_headers).json()
    assert deleted["tree_version"] == v + 1
    v = deleted["tree_version"]

    templated = client.post(f"/api/wbs/plans/{pid}/apply-template",
                            headers=admin_headers).json()
    assert templated["tree_version"] == v + 1


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
    assert client.request("DELETE", f"/api/wbs/items/{item_id}",
                          json={"tree_version": a.json()["tree_version"]}, headers=uh).status_code == 200

    assert client.delete(f"/api/wbs/plans/{pid}", headers=uh).status_code == 403
    assert client.delete(f"/api/wbs/plans/{pid}", headers=admin_headers).status_code == 200


# ─── 前置关联：存 id 不存编号 ───────────────────────────────────────────────
@pytest.fixture
def two(client, admin_headers, plan):
    """两个分组，拿来互相挂前置。"""
    pid = plan["id"]
    a = _add(client, admin_headers, pid, name="前一步")
    b = _add(client, admin_headers, pid, name="后一步")
    ids = {i["name"]: i["id"] for i in b["items"]}
    return pid, ids["前一步"], ids["后一步"]


def _link(client, headers, item_id, ids, version=0):
    r = client.put(f"/api/wbs/items/{item_id}",
                   json={"predecessor_ids": ids, "version": version}, headers=headers)
    return r


def test_predecessor_survives_a_reorder(client, admin_headers, two):
    """**存 id 不存编号**：编号是按位置现算的，上移一行之后存着的编号就指到
    另一件活上去了，而两行单独看都合法。关联跟着行走，显示的编号跟着位置走。"""
    pid, first, second = two
    d = _link(client, admin_headers, second, [first]).json()
    got = [i for i in d["items"] if i["id"] == second][0]
    assert [(p["id"], p["code"]) for p in got["predecessors"]] == [(first, "7")]

    # 把它挪到最前面：编号从 7 变成 1，关联一个字都不用改
    ids = [i["id"] for i in d["items"] if i["depth"] == 1]
    ids.remove(first)
    client.post(f"/api/wbs/plans/{pid}/reorder",
                json={"parent_id": None, "ids": [first] + ids,
                      "tree_version": d["tree_version"]}, headers=admin_headers)
    d = client.get(f"/api/wbs/plans/{pid}", headers=admin_headers).json()
    got = [i for i in d["items"] if i["id"] == second][0]
    assert [(p["id"], p["code"]) for p in got["predecessors"]] == [(first, "1")]


def test_predecessor_refuses_itself(client, admin_headers, two):
    """自己指自己 → 400。存进去的话页面上那条链接点了原地不动，看着像坏了。"""
    _pid, first, _second = two
    assert _link(client, admin_headers, first, [first]).status_code == 400


def test_predecessor_refuses_another_plan(client, admin_headers, two, special_id):
    """只认同一份 WBS 里的行：跨 WBS 的先后是两份计划之间的事，那条超链接也就
    不是"切到这棵树里的另一行"了。"""
    _pid, first, second = two
    other = client.post("/api/wbs/plans",
                        json={"name": "别的 WBS", "kind": "special", "special_id": special_id},
                        headers=admin_headers).json()
    alien = _add(client, admin_headers, other["id"], name="别人家的活")["items"][0]["id"]
    r = _link(client, admin_headers, second, [first, alien])
    assert r.status_code == 400
    # 整次保存被拒，不是"挂上一半"
    d = client.get(f"/api/wbs/plans/{_pid}", headers=admin_headers).json()
    assert [i for i in d["items"] if i["id"] == second][0]["predecessors"] == []


def test_predecessor_dedupes_and_keeps_order(client, admin_headers, two, plan):
    """去重保序：重复挂一条不报错（多半是点了两下），但也不该存两遍。"""
    pid, first, second = two
    third = [i for i in plan["items"] if i["depth"] == 1][0]["id"]
    d = _link(client, admin_headers, second, [third, first, third]).json()
    got = [i for i in d["items"] if i["id"] == second][0]
    assert [p["id"] for p in got["predecessors"]] == [third, first]


def test_deleted_predecessor_is_reported_not_swallowed(client, admin_headers, two):
    """指向的行被删掉时照样返回一条（missing=True）。悄悄滤掉的话，页面上那条
    前置凭空消失，填的人以为自己没填过，也就永远不会去修。"""
    _pid, first, second = two
    d = _link(client, admin_headers, second, [first]).json()
    ver = [i for i in d["items"] if i["id"] == second][0]["version"]
    d = client.request("DELETE", f"/api/wbs/items/{first}",
                       json={"tree_version": d["tree_version"]}, headers=admin_headers).json()
    got = [i for i in d["items"] if i["id"] == second][0]
    assert got["predecessors"] == [{"id": first, "code": "", "name": "", "missing": True}]
    # 清空是**传空列表**，不是把它藏起来
    d = _link(client, admin_headers, second, [], version=ver).json()
    assert [i for i in d["items"] if i["id"] == second][0]["predecessors"] == []
