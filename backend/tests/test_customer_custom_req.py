"""客户定制化需求：「预计合入版本」这一列的清空语义。

页面上这一列是个 clearable 的 el-select，清除时 Element Plus 把值置成 undefined，
而 undefined 会被 JSON.stringify 从请求体里整个丢掉。前端已把文本列折成空串再发，
这里钉住服务端那一半的契约：**传空串＝清掉，不传＝不修改**。
两者要是同义了，"清空保存后一刷新又回来了"这种事没人查得出来——页面还提示保存成功。
"""
import pytest


@pytest.fixture(scope="module")
def customer_id(client, admin_headers):
    r = client.post("/api/customers", headers=admin_headers,
                    json={"code": "CUSTREQ", "name": "定制化需求测试客户"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _make(client, headers, customer_id, **over):
    body = {"customer_id": customer_id, "description": "定制需求一",
            "planned_version": "C10SPC101", "involves_other": "是"}
    body.update(over)
    r = client.post("/api/customer-custom-reqs", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_empty_string_clears_but_omitting_keeps(client, admin_headers, customer_id):
    row = _make(client, admin_headers, customer_id)
    assert row["planned_version"] == "C10SPC101"

    # 只改别的字段：没提到的列必须原样留着
    r = client.put(f"/api/customer-custom-reqs/{row['id']}", headers=admin_headers,
                   json={"version": row["version"], "description": "改了描述"})
    assert r.status_code == 200
    assert r.json()["planned_version"] == "C10SPC101"
    assert r.json()["involves_other"] == "是"

    # 显式传空串：清掉
    cur = r.json()
    r2 = client.put(f"/api/customer-custom-reqs/{row['id']}", headers=admin_headers,
                    json={"version": cur["version"], "planned_version": "",
                          "involves_other": ""})
    assert r2.status_code == 200
    assert r2.json()["planned_version"] == ""
    assert r2.json()["involves_other"] == ""

    # 落库了才算数——上一步返回的是内存里的对象
    listed = client.get("/api/customer-custom-reqs", headers=admin_headers,
                        params={"customer_id": customer_id}).json()
    hit = next(x for x in listed if x["id"] == row["id"])
    assert hit["planned_version"] == "" and hit["involves_other"] == ""


def test_planned_version_takes_any_string(client, admin_headers, customer_id):
    """存的是版本号字符串不是 FK，下拉又允许自由输入：老数据里什么写法都有，
    服务端不能只收三层版本表里存在的值。"""
    row = _make(client, admin_headers, customer_id,
                description="定制需求二", planned_version="老口径 V3.2（待确认）")
    assert row["planned_version"] == "老口径 V3.2（待确认）"
