"""修订留痕的回归：改之前写的是什么，得能翻回来。

这套测试防的是「改动进了库、痕迹没进」——那种情况页面上一切正常，
只有在有人回头找上周写了什么的时候才发现历史是空的，而那时已经晚了。

注意：不要在模块顶层 import 应用模块（见 CLAUDE.md）——顶层 import 会赶在
conftest 的 os.chdir 之前把引擎连到仓库里的 backend/app.db 上。
"""
import pytest


@pytest.fixture(scope="module")
def special_id(client, admin_headers):
    r = client.post("/api/specials", json={"name": "留痕专项", "kind": "special"},
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _content(client, headers, sid):
    return client.get(f"/api/specials/{sid}", headers=headers).json()["content"]


def test_editing_progress_leaves_the_old_text_behind(client, admin_headers, special_id):
    """整体进展被覆盖之后，改之前那段话还找得回来。"""
    cur = _content(client, admin_headers, special_id)
    r = client.put(f"/api/specials/{special_id}/content",
                   json={"progress_summary": "第一周：完成方案评审", "version": cur["version"]},
                   headers=admin_headers)
    assert r.status_code == 200, r.text
    r = client.put(f"/api/specials/{special_id}/content",
                   json={"progress_summary": "第二周：联调中", "version": r.json()["version"]},
                   headers=admin_headers)
    assert r.status_code == 200, r.text

    hist = client.get("/api/history", params={"scope": f"special:{special_id}",
                                              "field": ["progress_summary"]},
                      headers=admin_headers).json()
    assert hist["total"] == 2
    newest = hist["items"][0]
    assert newest["old_value"] == "第一周：完成方案评审"
    assert newest["new_value"] == "第二周：联调中"
    assert newest["field_label"] == "整体进展"      # 列名取自模型注释，不另建对照表
    assert newest["entity_label"] == "专项内容"
    assert newest["username"] == "admin"


def test_unchanged_fields_leave_no_trace(client, admin_headers, special_id):
    """原样再存一次不该留痕：否则历史里全是「从 X 改成 X」，真正的改动被淹掉。"""
    cur = _content(client, admin_headers, special_id)
    before = client.get("/api/history", params={"scope": f"special:{special_id}"},
                        headers=admin_headers).json()["total"]
    r = client.put(f"/api/specials/{special_id}/content",
                   json={"progress_summary": cur["progress_summary"],
                         "version": cur["version"]}, headers=admin_headers)
    assert r.status_code == 200
    after = client.get("/api/history", params={"scope": f"special:{special_id}"},
                       headers=admin_headers).json()["total"]
    assert after == before


def test_a_rejected_save_leaves_no_trace(client, admin_headers, special_id):
    """乐观锁挡下来的保存不能留痕——不然历史里写着改过、数据却没改。"""
    before = client.get("/api/history", params={"scope": f"special:{special_id}"},
                        headers=admin_headers).json()["total"]
    r = client.put(f"/api/specials/{special_id}/content",
                   json={"progress_summary": "并发写入", "version": 99999},
                   headers=admin_headers)
    assert r.status_code == 409
    after = client.get("/api/history", params={"scope": f"special:{special_id}"},
                       headers=admin_headers).json()["total"]
    assert after == before


def test_task_row_history_and_delete_snapshot(client, admin_headers, special_id):
    """事务行：改动逐列留痕，删除留一份整行。"""
    r = client.post(f"/api/specials/{special_id}/tasks",
                    json={"content": "打通链路", "progress": "已排期"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    tid = r.json()["id"]

    client.put(f"/api/specials/tasks/{tid}",
               json={"progress": "已完成 80%", "status": "closed"}, headers=admin_headers)
    hist = client.get("/api/history",
                      params={"entity": "special_task", "entity_id": tid},
                      headers=admin_headers).json()
    changed = {i["field"]: i for i in hist["items"]}
    assert changed["progress"]["old_value"] == "已排期"
    assert changed["progress"]["new_value"] == "已完成 80%"
    assert changed["status"]["new_value"] == "closed"
    # 行标题冗余下来，删掉之后还认得出是哪一条
    assert changed["progress"]["entity_title"] == "打通链路"

    assert client.delete(f"/api/specials/tasks/{tid}", headers=admin_headers).status_code == 200
    hist = client.get("/api/history",
                      params={"entity": "special_task", "entity_id": tid},
                      headers=admin_headers).json()
    dele = [i for i in hist["items"] if i["action"] == "delete"]
    assert len(dele) == 1
    import json
    row = json.loads(dele[0]["old_value"])
    assert row["content"] == "打通链路" and row["progress"] == "已完成 80%"
    assert dele[0]["field_label"] == "整条记录"


def test_value_at_a_point_in_time(client, admin_headers, special_id):
    """/history/at：这一行在某个时刻是什么样。"""
    from datetime import datetime, timedelta, timezone

    from timeutil import CN_TZ

    # 接口收的是**本地（北京）时间**，服务端用 local_to_utc 换算后才和 created_at 比。
    # 这里按同一口径造时间点，测试才不会跟着跑测机器的时区飘（容器是 UTC）。
    def _local_now():
        return datetime.now(timezone.utc).astimezone(CN_TZ).replace(tzinfo=None)

    r = client.post(f"/api/specials/{special_id}/tasks",
                    json={"content": "回看用例", "progress": "第一版"}, headers=admin_headers)
    tid = r.json()["id"]
    mark = _local_now()
    client.put(f"/api/specials/tasks/{tid}", json={"progress": "第二版"}, headers=admin_headers)

    # mark 那一刻还是第一版
    at = client.get("/api/history/at",
                    params={"entity": "special_task", "entity_id": tid,
                            "at": mark.isoformat()}, headers=admin_headers).json()
    assert at["exists"] is True
    vals = {f["field"]: f["value"] for f in at["fields"]}
    assert vals["progress"] == "第一版"

    # 往后一小时＝到现在都没再动过，取当前值
    later = (_local_now() + timedelta(hours=1)).isoformat()
    at2 = client.get("/api/history/at",
                     params={"entity": "special_task", "entity_id": tid, "at": later},
                     headers=admin_headers).json()
    assert {f["field"]: f["value"] for f in at2["fields"]}["progress"] == "第二版"


def test_history_needs_a_scope(client, admin_headers):
    """不给 scope 也不给 entity ＝ 全库拉，没有使用场景，直接 400。"""
    assert client.get("/api/history", headers=admin_headers).status_code == 400


def test_entities_registry_is_served_from_the_backend(client, admin_headers):
    """实体/列名对照由服务端给：前端各存一份的话，加一列就有一处会漏。"""
    data = client.get("/api/history/entities", headers=admin_headers).json()
    names = {e["entity"]: e for e in data["entities"]}
    assert "customer_issue" in names and "hardware_issue" in names
    labels = {f["field"]: f["label"] for f in names["customer_issue"]["fields"]}
    assert labels["progress_note"] == "问题进展"
    assert labels["status"] == "状态"          # 注释写的是取值范围，得单独指定


def test_domain_and_customer_pages_are_covered(client, admin_headers, machine_id):
    """领域与客户面这两条写路径也要留痕——漏挂一条不会报错，只是那页没有历史。"""
    r = client.post("/api/domains/risks",
                    json={"content": "领域风险一条", "progress": "刚提出"},
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    rid, ver = r.json()["id"], r.json()["version"]
    client.put(f"/api/domains/risks/{rid}",
               json={"progress": "已定位", "version": ver}, headers=admin_headers)
    hist = client.get("/api/history", params={"entity": "domain_risk", "entity_id": rid},
                      headers=admin_headers).json()
    assert [i for i in hist["items"] if i["field"] == "progress"][0]["old_value"] == "刚提出"

    r = client.post("/api/customer-issues",
                    json={"machine_status_id": machine_id, "kind": "issue",
                          "description": "现场问题", "progress_note": "已复现"},
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    iid, ver = r.json()["id"], r.json()["version"]
    client.put(f"/api/customer-issues/{iid}",
               json={"progress_note": "已定位到驱动", "version": ver}, headers=admin_headers)
    hist = client.get("/api/history", params={"entity": "customer_issue", "entity_id": iid},
                      headers=admin_headers).json()
    got = [i for i in hist["items"] if i["field"] == "progress_note"][0]
    assert got["old_value"] == "已复现" and got["field_label"] == "问题进展"


def test_a_reused_row_id_does_not_inherit_the_old_rows_history(client, admin_headers,
                                                               special_id):
    """SQLite 会把删掉的行号让给下一条新增——新行不能认领旧行的历史。

    不设下界的话，页面上是一条刚建的空事务，历史里却写着别人三周前的进展，
    而两边看着都对，没人会当 bug 报。见 revisions.born_at()。
    """
    r = client.post(f"/api/specials/{special_id}/tasks",
                    json={"content": "先建后删", "progress": "旧的进展"},
                    headers=admin_headers)
    old_id = r.json()["id"]
    client.put(f"/api/specials/tasks/{old_id}",
               json={"progress": "旧的进展（改过）"}, headers=admin_headers)
    client.delete(f"/api/specials/tasks/{old_id}", headers=admin_headers)

    r = client.post(f"/api/specials/{special_id}/tasks",
                    json={"content": "新建的一条", "progress": ""}, headers=admin_headers)
    new_id = r.json()["id"]
    if new_id != old_id:
        import pytest
        pytest.skip("这一版 SQLite 没有复用行号，这条用例只在复用时有意义")

    hist = client.get("/api/history",
                      params={"entity": "special_task", "entity_id": new_id},
                      headers=admin_headers).json()
    assert hist["total"] == 0, "新行认领了旧行的历史"

    at = client.get("/api/history/at",
                    params={"entity": "special_task", "entity_id": new_id,
                            "at": "2000-01-01T00:00:00"}, headers=admin_headers).json()
    assert {f["field"]: f["value"] for f in at["fields"]}["progress"] == ""
