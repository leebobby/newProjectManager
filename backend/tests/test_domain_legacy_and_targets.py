"""领域管理：遗留问题 + 问题单目标 + 按项目取快照。

这三块容易出错的地方，也是本文件盯着的：
1. 遗留问题状态 "pending" 是小写字面量。写成 PENDING 落库后，页面下拉与统计
   按字面量比对就成了两档，谁都不会当 bug 去查——所以入口必须归一。
2. 目标值是"管理口径"，仅 admin 可写；普通用户能读（页面要显示达成情况）。
3. 问题单情况改成读**问题单管理的快照**并按项目分。指定了一个没有快照的项目时，
   必须如实说"没采集过"，绝不能悄悄换成别的项目的数字——那种错看不出来。
"""
import json

import pytest


@pytest.fixture(scope="module")
def domain_env(client, admin_headers, tmp_path_factory):
    """两个 PL 组 + 两个项目的快照。快照根目录指到临时目录，别写进仓库。"""
    import models
    from database import SessionLocal
    import routers.issues as ri

    root = tmp_path_factory.mktemp("domain_snapshots")
    ri._snapshot_root = lambda: root

    dept = client.post("/api/resource-groups", headers=admin_headers,
                       json={"code": "DTDEPT", "name": "领域测试部", "kind": "dept"}).json()
    ga = client.post("/api/resource-groups", headers=admin_headers,
                     json={"code": "DTGA", "name": "领域测试组甲", "kind": "pl",
                           "parent_id": dept["id"]}).json()
    gb = client.post("/api/resource-groups", headers=admin_headers,
                     json={"code": "DTGB", "name": "领域测试组乙", "kind": "pl",
                           "parent_id": dept["id"]}).json()

    # 甲：A 项目 3 单（严重1 一般2 → 3+1+1=5.0 分）、B 项目 1 单；乙：A 项目 1 单
    days = {
        "DOMPROJA": [
            {"issue_id": "D1", "severity": "严重", "group": "领域测试组甲"},
            {"issue_id": "D2", "severity": "一般", "group": "领域测试组甲"},
            {"issue_id": "D3", "severity": "一般", "group": "领域测试组甲"},
            {"issue_id": "D4", "severity": "提示", "group": "领域测试组乙"},
        ],
        "DOMPROJB": [
            {"issue_id": "D9", "severity": "致命", "group": "领域测试组甲"},
        ],
    }
    db = SessionLocal()
    for project, rows in days.items():
        rel = f"{project}/2026-04-01.json"
        fp = root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        db.add(models.IssueSnapshot(project=project, snapshot_date="2026-04-01",
                                    total=len(rows), data_file=rel, source="api"))
    db.commit()
    db.close()
    return {"ga": ga["id"], "gb": gb["id"], "ga_name": ga["name"], "gb_name": gb["name"]}


def _row(client, headers, group_id, **params):
    d = client.get("/api/domains", headers=headers, params=params).json()
    return d, next(r for r in d["rows"] if r["group_id"] == group_id)


# ─── 问题单：按项目取快照 ─────────────────────────────────────────────────────
def test_project_options_include_snapshot_projects(client, admin_headers, domain_env):
    d = client.get("/api/domains", headers=admin_headers).json()
    projects = {p["project"]: p for p in d["projects"]}
    assert "DOMPROJA" in projects and "DOMPROJB" in projects
    assert projects["DOMPROJA"]["latest_date"] == "2026-04-01"
    # 省略 project 时后端挑一个有快照的，并把它回给前端填选择器
    assert d["selected_project"] in {p for p, o in projects.items() if o["latest_date"]}


def test_summary_counts_per_project(client, admin_headers, domain_env):
    _, ga = _row(client, admin_headers, domain_env["ga"], project="DOMPROJA")
    s = ga["issue_summary"]
    assert s["available"] and s["source"] == "snapshot" and s["project"] == "DOMPROJA"
    assert s["total"] == 3
    assert s["score"] == 5.0                      # 严重3 + 一般1 + 一般1
    assert s["by_severity"] == {"严重": 1, "一般": 2}
    assert s["file_mtime"] == "2026-04-01"        # 快照源的"时间"是采集日

    _, ga_b = _row(client, admin_headers, domain_env["ga"], project="DOMPROJB")
    assert ga_b["issue_summary"]["total"] == 1
    assert ga_b["issue_summary"]["score"] == 10.0  # 致命


def test_rows_are_split_by_group(client, admin_headers, domain_env):
    _, gb = _row(client, admin_headers, domain_env["gb"], project="DOMPROJA")
    assert gb["issue_summary"]["total"] == 1       # 乙组只认自己名下那条
    assert gb["issue_summary"]["by_severity"] == {"提示": 1}


def test_unknown_project_says_so_instead_of_silently_switching(client, admin_headers, domain_env):
    """指定了没有快照的项目：整列显示"未接入"并给出原因，而不是换成别的项目的数字。"""
    _, ga = _row(client, admin_headers, domain_env["ga"], project="DOMPROJ_NOPE")
    assert ga["issue_summary"]["available"] is False
    assert "DOMPROJ_NOPE" in (ga["issue_summary"]["note"] or "")


def test_drilldown_follows_the_same_project(client, admin_headers, domain_env):
    r = client.get(f"/api/domains/{domain_env['ga']}/issues", headers=admin_headers,
                   params={"project": "DOMPROJB"})
    d = r.json()
    assert d["available"] and d["project"] == "DOMPROJB"
    assert [x["issue_id"] for x in d["rows"]] == ["D9"]


# ─── 问题单目标 ──────────────────────────────────────────────────────────────
def test_target_requires_admin(client, admin_headers, domain_env):
    """普通用户能读目标，不能写。"""
    client.post("/api/users", headers=admin_headers, json={
        "username": "domtester", "password": "domtest123", "full_name": "领域测试员",
        "role": "normal", "can_login": True,
    })
    tok = client.post("/api/auth/login", json={"username": "domtester",
                                               "password": "domtest123"}).json()["access_token"]
    normal = {"Authorization": f"Bearer {tok}"}

    assert client.get("/api/domains/issue-targets", headers=normal,
                      params={"project": "DOMPROJA"}).status_code == 200
    r = client.put("/api/domains/issue-targets", headers=normal, json={
        "project": "DOMPROJA",
        "items": [{"group_id": domain_env["ga"], "target_total": 1}],
    })
    assert r.status_code == 403


def test_target_marks_over_and_can_be_cleared(client, admin_headers, domain_env):
    ga = domain_env["ga"]
    r = client.put("/api/domains/issue-targets", headers=admin_headers, json={
        "project": "DOMPROJA",
        "items": [{"group_id": ga, "target_total": 2, "target_score": 9.0}],
    })
    assert r.status_code == 200, r.text

    _, row = _row(client, admin_headers, ga, project="DOMPROJA")
    s = row["issue_summary"]
    assert s["target_total"] == 2 and s["target_score"] == 9.0
    assert s["over_total"] is True      # 实际 3 > 目标 2
    assert s["over_score"] is False     # 实际 5.0 ≤ 目标 9.0

    # 目标是按项目存的：另一个项目不该被带上
    _, other = _row(client, admin_headers, ga, project="DOMPROJB")
    assert other["issue_summary"]["target_total"] is None

    # 两个目标都留空＝删除该行
    client.put("/api/domains/issue-targets", headers=admin_headers, json={
        "project": "DOMPROJA", "items": [{"group_id": ga}],
    })
    _, cleared = _row(client, admin_headers, ga, project="DOMPROJA")
    assert cleared["issue_summary"]["target_total"] is None
    assert cleared["issue_summary"]["over_total"] is False


def test_generic_target_is_inherited_until_project_target_exists(client, admin_headers, domain_env):
    """project="" 的通用目标兜底；一旦设了项目专属目标，专属优先。"""
    gb = domain_env["gb"]
    client.put("/api/domains/issue-targets", headers=admin_headers, json={
        "project": "", "items": [{"group_id": gb, "target_total": 0}],
    })
    _, row = _row(client, admin_headers, gb, project="DOMPROJA")
    assert row["issue_summary"]["target_total"] == 0
    assert row["issue_summary"]["over_total"] is True    # 实际 1 > 0

    items = client.get("/api/domains/issue-targets", headers=admin_headers,
                       params={"project": "DOMPROJA"}).json()["items"]
    entry = next(i for i in items if i["group_id"] == gb)
    assert entry["inherited"] is True                    # 标出来，免得管理员以为改的是本项目

    client.put("/api/domains/issue-targets", headers=admin_headers, json={
        "project": "DOMPROJA", "items": [{"group_id": gb, "target_total": 5}],
    })
    _, row2 = _row(client, admin_headers, gb, project="DOMPROJA")
    assert row2["issue_summary"]["target_total"] == 5
    assert row2["issue_summary"]["over_total"] is False


# ─── 遗留问题 ────────────────────────────────────────────────────────────────
def _make_legacy(client, headers, **over):
    body = {"title": "遗留：老库缺列", "status": "OPEN", "priority": "高"}
    body.update(over)
    r = client.post("/api/domains/legacy-issues", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_legacy_seq_auto_increments(client, admin_headers, domain_env):
    a = _make_legacy(client, admin_headers, title="遗留一")
    b = _make_legacy(client, admin_headers, title="遗留二")
    assert b["seq"] == a["seq"] + 1


def test_legacy_resolves_people_names(client, admin_headers, domain_env):
    users = client.get("/api/users/options", headers=admin_headers).json()
    ids = [u["id"] for u in users][:3]
    row = _make_legacy(
        client, admin_headers, title="遗留：三种角色",
        owner_id=ids[0], reporter_id=ids[0],
        confirmer_id=ids[-1], participants=ids,
        domain_id=domain_env["ga"],
    )
    assert row["owner_name"] and row["confirmer_name"]
    assert row["participants"] == ids
    assert len(row["participant_names"]) == len(ids)
    assert row["domain_name"] == domain_env["ga_name"]


def test_legacy_status_is_normalized_not_stored_as_typed(client, admin_headers, domain_env):
    """大小写不同的 pending 必须归一——否则统计按字面量分组会分成好几档。"""
    for typed in ("pending", "Pending", "PENDING"):
        row = _make_legacy(client, admin_headers, title=f"遗留 {typed}", status=typed)
        assert row["status"] == "pending"
    r = client.post("/api/domains/legacy-issues", headers=admin_headers,
                    json={"title": "非法状态", "status": "挂起"})
    assert r.status_code == 422


def test_legacy_optimistic_lock(client, admin_headers, domain_env):
    row = _make_legacy(client, admin_headers, title="遗留：并发")
    ok = client.put(f"/api/domains/legacy-issues/{row['id']}", headers=admin_headers,
                    json={"version": row["version"], "status": "CLOSED"})
    assert ok.status_code == 200 and ok.json()["status"] == "CLOSED"
    assert ok.json()["version"] == row["version"] + 1
    stale = client.put(f"/api/domains/legacy-issues/{row['id']}", headers=admin_headers,
                       json={"version": row["version"], "status": "OPEN"})
    assert stale.status_code == 409


def test_legacy_participants_can_be_emptied(client, admin_headers, domain_env):
    users = client.get("/api/users/options", headers=admin_headers).json()
    row = _make_legacy(client, admin_headers, title="遗留：清空参与人",
                       participants=[u["id"] for u in users][:2])
    assert row["participants"]
    r = client.put(f"/api/domains/legacy-issues/{row['id']}", headers=admin_headers,
                   json={"version": row["version"], "participants": []})
    assert r.status_code == 200
    assert r.json()["participants"] == [] and r.json()["participant_names"] == []


def test_legacy_filters_and_delete(client, admin_headers, domain_env):
    row = _make_legacy(client, admin_headers, title="遗留：待删", domain_id=domain_env["gb"])
    client.put(f"/api/domains/legacy-issues/{row['id']}", headers=admin_headers,
               json={"version": row["version"], "status": "CLOSED"})

    open_only = client.get("/api/domains/legacy-issues", headers=admin_headers,
                           params={"include_done": False}).json()
    assert row["id"] not in [r["id"] for r in open_only]
    # pending 不算"已关闭"，仍要出现在待办列表里
    assert any(r["status"] == "pending" for r in open_only)

    by_domain = client.get("/api/domains/legacy-issues", headers=admin_headers,
                           params={"domain_id": domain_env["gb"]}).json()
    assert [r["id"] for r in by_domain] == [row["id"]]

    assert client.delete(f"/api/domains/legacy-issues/{row['id']}",
                         headers=admin_headers).status_code == 200
    after = client.get("/api/domains/legacy-issues", headers=admin_headers).json()
    assert row["id"] not in [r["id"] for r in after]


# ─── 事务/风险：责任人与风险等级 ─────────────────────────────────────────────
def _make_task(client, headers, **over):
    body = {"content": "风险：老库缺列", "priority": "高"}
    body.update(over)
    r = client.post("/api/domains/risks", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_task_owner_resolves_to_name(client, admin_headers, domain_env):
    """责任领域是个组，组不会去闭环一条风险——责任人要能落到具体的人。"""
    users = client.get("/api/users/options", headers=admin_headers).json()
    uid = users[0]["id"]
    row = _make_task(client, admin_headers, content="风险：有主的",
                     owner_id=uid, domain_id=domain_env["ga"])
    assert row["owner_id"] == uid and row["owner_name"]
    assert row["domain_name"] == domain_env["ga_name"]

    # 列表口径必须与单条一致：一次取名字映射，别逐行 join
    listed = client.get("/api/domains/risks", headers=admin_headers).json()
    hit = next(r for r in listed if r["id"] == row["id"])
    assert hit["owner_name"] == row["owner_name"]


def test_task_risk_level_is_independent_of_priority(client, admin_headers, domain_env):
    """低优先级 + 高等级是常态（短期不动、但爆了很惨）。两列合一就表达不出来。"""
    row = _make_task(client, admin_headers, content="风险：先不动但很疼",
                     priority="低", risk_level="高")
    assert row["priority"] == "低" and row["risk_level"] == "高"


def test_task_risk_level_blank_is_legal_and_never_defaults(client, admin_headers, domain_env):
    """事务行没有风险等级。默认成「中」会让半屏事务挂上一个凭空捏的等级。"""
    row = _make_task(client, admin_headers, content="事务：只是件活儿")
    assert row["risk_level"] == ""

    # 评过等级后又想清掉：空串是"清掉"，不是"不修改"
    r = client.put(f"/api/domains/risks/{row['id']}", headers=admin_headers,
                   json={"version": row["version"], "risk_level": "中"})
    assert r.status_code == 200 and r.json()["risk_level"] == "中"
    cleared = client.put(f"/api/domains/risks/{row['id']}", headers=admin_headers,
                         json={"version": r.json()["version"], "risk_level": ""})
    assert cleared.status_code == 200 and cleared.json()["risk_level"] == ""


def test_task_risk_level_rejects_off_whitelist(client, admin_headers, domain_env):
    r = client.post("/api/domains/risks", headers=admin_headers,
                    json={"content": "风险：错等级", "risk_level": "P1"})
    assert r.status_code == 422


# ─── 遗留问题：当前进展（富文本）────────────────────────────────────────────
def test_legacy_progress_keeps_formatting_but_drops_script(client, admin_headers, domain_env):
    """页面用 v-html 渲染这一列，所以写库前就得洗——只在导出时洗等于只保护了收件人。"""
    row = _make_legacy(
        client, admin_headers, title="遗留：带格式的进展",
        progress='<p><strong>已定位</strong>到 <span style="color:#F56C6C">驱动层</span></p>'
                 '<script>alert(1)</script>',
    )
    assert "<strong>" in row["progress"]
    assert "color" in row["progress"]
    assert "script" not in row["progress"].lower()
    assert "alert(1)" not in row["progress"]      # script 连内容一起丢


def test_legacy_progress_sanitized_on_update_too(client, admin_headers, domain_env):
    row = _make_legacy(client, admin_headers, title="遗留：改进展")
    assert row["progress"] == ""
    r = client.put(f"/api/domains/legacy-issues/{row['id']}", headers=admin_headers,
                   json={"version": row["version"],
                         "progress": '<b>推进中</b><img src=x onerror="alert(1)">'})
    assert r.status_code == 200
    assert "<b>" in r.json()["progress"]
    assert "onerror" not in r.json()["progress"]


def test_task_progress_keeps_formatting_but_drops_script(client, admin_headers, domain_env):
    row = _make_task(
        client, admin_headers, content="风险：带格式的进展",
        progress='<p><b>已定位</b>到 <span style="color:#F56C6C">驱动层</span></p>'
                 '<script>alert(1)</script>',
    )
    assert "<b>" in row["progress"] and "color" in row["progress"]
    assert "script" not in row["progress"].lower()
    assert "alert(1)" not in row["progress"]

    r = client.put(f"/api/domains/risks/{row['id']}", headers=admin_headers,
                   json={"version": row["version"],
                         "progress": '<b>推进中</b><img src=x onerror="alert(1)">'})
    assert r.status_code == 200 and "onerror" not in r.json()["progress"]


def test_task_legacy_plaintext_progress_survives_switch_to_v_html(client, admin_headers,
                                                                  domain_env):
    """这一列改富文本前存了多年纯文本。直接丢给 v-html 会吃掉 < 、压平换行。

    所以出口过 _rich_to_html()：老行显示成什么样，和改造前一模一样。
    """
    import models
    from database import SessionLocal

    db = SessionLocal()
    obj = models.DomainRisk(content="风险：老库纯文本进展",
                            progress="第一行\n第二行 a<b 的比较")
    db.add(obj)
    db.commit()
    rid = obj.id
    db.close()

    rows = client.get("/api/domains/risks", headers=admin_headers).json()
    hit = next(r for r in rows if r["id"] == rid)
    assert "<br>" in hit["progress"]              # 换行还在
    assert "a&lt;b" in hit["progress"]            # < 被转义，不会被当成标签吃掉
    assert "第二行" in hit["progress"]


def test_task_legacy_markup_in_plaintext_column_is_defanged(client, admin_headers, domain_env):
    """入口清洗是这次才加的：之前存进来的值没洗过，出口得挡住。"""
    import models
    from database import SessionLocal

    db = SessionLocal()
    obj = models.DomainRisk(content="风险：老库脏值",
                            progress='<p>进展</p><script>alert(1)</script>')
    db.add(obj)
    db.commit()
    rid = obj.id
    db.close()

    rows = client.get("/api/domains/risks", headers=admin_headers).json()
    hit = next(r for r in rows if r["id"] == rid)
    assert "script" not in hit["progress"].lower()
    assert "alert(1)" not in hit["progress"]
    assert "进展" in hit["progress"]
