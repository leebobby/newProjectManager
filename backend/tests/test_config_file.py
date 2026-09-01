"""`config.json` 不入版本库，缺失时回落到 `config.example.json`。

这份配置里是本机绝对路径与本部署要采集的项目，属于部署实例的状态。它曾经跟着代码走，
后果是每次 `git pull` 把线上配好的路径盖回某台开发机的 `D:\\...`——页面上一切正常，
只是问题单采集从此指向一个不存在的目录，没人会当 bug 报。
"""


def test_config_falls_back_to_the_example_when_absent(client, monkeypatch, tmp_path):
    from routers import config as config_router

    monkeypatch.setattr(config_router, "CONFIG_PATH", tmp_path / "config.json")
    cfg = config_router._load()

    # 回落到模板而不是回落到 {}：词表默认值也在这份配置里，空掉的话
    # 新装实例里那几个下拉是空的，看着像功能坏了
    assert cfg["hw_machine_cell_options"], "回落后词表不该是空的"
    assert cfg["hw_machine_cell_colors"]["已清零"]
    # 模板里的说明键不该漏进接口响应
    assert not [k for k in cfg if k.startswith("_")]


def test_saving_config_creates_the_real_file(client, admin_headers, monkeypatch, tmp_path):
    """页面上保存一次就该生成 config.json，而不是继续写模板。"""
    from routers import config as config_router

    real = tmp_path / "config.json"
    monkeypatch.setattr(config_router, "CONFIG_PATH", real)

    r = client.put("/api/config", headers=admin_headers, json={"current_stages": ["甲", "乙"]})
    assert r.status_code == 200, r.text
    assert real.exists(), "保存后没有生成 config.json"
    assert r.json()["current_stages"] == ["甲", "乙"]
    # 模板里的其余键要一并落进新文件，不能只剩刚提交的那一个
    assert real.exists() and "hw_machine_cell_options" in r.json()
