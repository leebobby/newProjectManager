"""专项版式模板：套用语义、幂等、只增不删，以及导出/周报是否跟着版式走。

重点不是 CRUD 能不能跑，而是三条容易回归的约定：
1. 套模板**不删数据**——已填的行、模板没提到的分段都要留着；
2. 重复套同一模板是幂等的（按 tkey 认领，不会越套越多分段）；
3. 分段改名/停用后，Excel 与周报必须跟着变，否则页面和汇报口径又会分叉。
"""
import io
import json

import pytest


def _content(client, headers, sid):
    return client.get(f"/api/specials/{sid}", headers=headers).json()["content"]


def _cfg(content):
    return json.loads(content["section_config_json"])


def _blocks(content):
    return json.loads(content["extra_grids_json"])


@pytest.fixture(scope="module")
def solution_tpl(client, admin_headers):
    """seed 注入的「解决方案专项」模板。"""
    rows = client.get("/api/special-templates", headers=admin_headers).json()
    tpl = next((t for t in rows if t["name"] == "解决方案专项"), None)
    assert tpl, f"seed 应注入解决方案专项模板，实际：{[t['name'] for t in rows]}"
    return tpl


def test_seed_templates_present(client, admin_headers):
    rows = client.get("/api/special-templates", headers=admin_headers).json()
    names = {t["name"] for t in rows}
    assert {"标准专项", "解决方案专项"} <= names


def test_builtin_sections_endpoint(client, admin_headers):
    data = client.get("/api/special-templates/sections", headers=admin_headers).json()
    keys = [s["key"] for s in data["sections"]]
    # 顺序即默认显示顺序，须与前端 FIXED_KEYS 一致
    assert keys == ["goal", "plan", "progress", "help", "panorama",
                    "risks", "tasks", "formation"]
    assert "light" in data["col_types"], "点灯列格式应对前端可见"


def test_create_with_template_applies_layout(client, admin_headers, solution_tpl):
    resp = client.post("/api/specials", headers=admin_headers, json={
        "name": "某解决方案专项", "kind": "special", "owner": "admin",
        "template_id": solution_tpl["id"],
    })
    assert resp.status_code == 200, resp.text
    sid = resp.json()["id"]
    content = _content(client, admin_headers, sid)

    cfg = _cfg(content)
    assert cfg["template_name"] == "解决方案专项"
    assert cfg["sections"]["goal"]["title"] == "解决方案专项目标"
    assert cfg["sections"]["progress"]["title"] == "整体进展和关键风险"
    assert cfg["sections"]["risks"]["title"] == "关键问题跟踪"
    # 这类专项不按里程碑/阵型汇报
    for k in ("plan", "panorama", "tasks", "formation"):
        assert cfg["sections"][k]["enabled"] is False, k

    blocks = _blocks(content)
    assert [b["title"] for b in blocks] == [
        "测试详细进展和点灯", "战场关键风险评估", "需求转测和规范度评估"]
    lights = blocks[0]
    assert lights["colTypes"][-1] == "light"
    # 点灯列没配候选项时自动给一份红黄绿
    assert lights["colOptions"][-1] == ["绿", "黄", "红"]
    assert len(lights["rows"]) == 3 and len(lights["rows"][0]) == 5

    order = json.loads(content["section_order_json"])
    gids = [f"grid:{b['gid']}" for b in blocks]
    assert order[:7] == ["goal", "progress", gids[0], gids[1],
                         "risks", gids[2], "help"]
    # 停用的内置分段仍留在顺序里（只是不显示），不会凭空消失
    assert set(order[7:]) == {"plan", "help", "panorama", "tasks", "formation"} - {"help"}


def test_reapply_is_idempotent_and_keeps_data(client, admin_headers, solution_tpl):
    """重复套用不该新增分段，也不该动已经填进去的行。"""
    sid = client.post("/api/specials", headers=admin_headers, json={
        "name": "复用模板的专项", "kind": "special",
        "template_id": solution_tpl["id"],
    }).json()["id"]

    content = _content(client, admin_headers, sid)
    blocks = _blocks(content)
    blocks[0]["rows"][0][0] = {"text": "手填的测试项", "align": "left",
                               "color": "", "bold": False}
    # 再挂一个模板里没有的自定义分段，验证套用不会把它删掉
    blocks.append({"gid": "usergid01", "kind": "text",
                   "title": "自己加的文本框", "html": "<p>保留我</p>"})
    resp = client.put(f"/api/specials/{sid}/content", headers=admin_headers, json={
        "version": content["version"],
        "extra_grids_json": json.dumps(blocks, ensure_ascii=False),
    })
    assert resp.status_code == 200, resp.text
    version = resp.json()["version"]

    resp = client.post(f"/api/specials/{sid}/apply-template", headers=admin_headers,
                       json={"template_id": solution_tpl["id"], "version": version})
    assert resp.status_code == 200, resp.text
    after = _blocks(resp.json())

    assert len(after) == 4, "模板 3 段 + 用户自加 1 段，重复套用不应新增"
    assert after[0]["rows"][0][0]["text"] == "手填的测试项", "已填数据被覆盖了"
    assert any(b["title"] == "自己加的文本框" for b in after), "模板外的分段被删了"


def test_apply_template_rejects_stale_version(client, admin_headers, solution_tpl):
    sid = client.post("/api/specials", headers=admin_headers, json={
        "name": "版本冲突验证", "kind": "special",
    }).json()["id"]
    resp = client.post(f"/api/specials/{sid}/apply-template", headers=admin_headers,
                       json={"template_id": solution_tpl["id"], "version": 999})
    assert resp.status_code == 409


def test_invalid_layout_rejected(client, admin_headers):
    bad = [
        ({"order": ["不存在的分段"], "config": {}, "blocks": []}, "未知 order key"),
        ({"order": [], "config": {"nope": {}}, "blocks": []}, "未知内置分段"),
        ({"order": [], "config": {}, "blocks": [{"kind": "grid"}]}, "缺 tkey"),
        ({"order": [], "config": {}, "blocks": [
            {"tkey": "a", "kind": "grid", "colTypes": ["bogus"]}]}, "非法列格式"),
    ]
    for layout, why in bad:
        resp = client.post("/api/special-templates", headers=admin_headers, json={
            "name": f"非法模板-{why}",
            "layout_json": json.dumps(layout, ensure_ascii=False),
        })
        assert resp.status_code == 400, f"{why} 应被拒：{resp.text}"


def test_export_and_report_follow_layout(client, admin_headers, solution_tpl):
    """分段改名/停用后，Excel 与周报要跟着变。"""
    sid = client.post("/api/specials", headers=admin_headers, json={
        "name": "导出口径验证", "kind": "special",
        "template_id": solution_tpl["id"],
    }).json()["id"]
    content = _content(client, admin_headers, sid)
    blocks = _blocks(content)
    # 点灯表填一行：模板预留的空行是没有内容的，空段本就不该进周报
    blocks[0]["rows"][0] = [
        {"text": t, "align": "left", "color": "", "bold": False}
        for t in ("冒烟测试", "张三", "2026-08-20", "全部通过", "绿")
    ]
    client.put(f"/api/specials/{sid}/content", headers=admin_headers, json={
        "version": content["version"],
        "goal": "<p>目标正文</p>",
        "progress_summary": "<p>进展正文</p>",
        "extra_grids_json": json.dumps(blocks, ensure_ascii=False),
    })

    draft = client.get(f"/api/specials/{sid}/report-draft", headers=admin_headers).json()
    body = draft["body"]
    assert "解决方案专项目标" in body, "周报标题没跟随分段配置"
    assert "整体进展和关键风险" in body
    assert "专项计划" not in body, "停用的分段不该出现在周报里"
    assert "专项阵型" not in body
    # 自定义分段进周报了，且只进填过内容的那张表
    assert "三、测试详细进展和点灯" in body, "自定义分段没进周报"
    assert "冒烟测试" in body
    assert "战场关键风险评估" not in body, "整表空白的自定义分段不该占一节"
    # 编号按实际启用且有内容的分段连续排，不是写死的一~六
    assert "四、求助" not in body and "四、" not in body

    resp = client.post(f"/api/specials/{sid}/report.eml", headers=admin_headers, json={})
    assert resp.status_code == 200
    eml = resp.content.decode("utf-8", "replace")
    assert "测试详细进展和点灯" in eml
    assert "#F0F9EB" in eml or "F0F9EB" in eml, "点灯「绿」应在 HTML 里着色"

    resp = client.get(f"/api/specials/{sid}/export.xlsx", headers=admin_headers)
    assert resp.status_code == 200
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(resp.content))
    # 自定义表格走独立工作表，页签按分段序号命名 → 页签顺序＝页面分段顺序
    assert wb.sheetnames == ["专项", "3.测试详细进展和点灯"], wb.sheetnames
    heads = [str(c[0].value) for c in wb["专项"].iter_rows(max_col=1) if c[0].value]
    assert "一、解决方案专项目标" in heads
    assert "二、整体进展和关键风险" in heads
    assert "三、测试详细进展和点灯" in heads
    assert not any("专项计划" in h or "专项阵型" in h for h in heads), \
        "停用的分段不该出现在 Excel 里"
