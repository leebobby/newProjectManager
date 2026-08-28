"""采集脚本翻页：拉不全就整次失败，绝不落一份短了一截的快照。

DTS 会话中途失效返回的是 **HTTP 200 + data:null**，`raise_for_status()` 拦不住。
以前 `(_page(n).get("data") or {}).get("data") or []` 把它吞成空页，于是少拉一页
（200 条）的快照看起来完全合法——而「解决」＝这一单从快照里消失（差分从不读状态），
第二天就凭空给出 200 条假解决。快照一旦落盘，差分还会被缓存进 issue_snapshot_flows，
事后修数据源也不会自动重算。所以这里的取舍是：**宁可这次采集失败，也不要写短快照**。
"""
import json

import pytest


@pytest.fixture(scope="module")
def fetcher():
    """按文件路径加载采集脚本（scripts/ 不是包）。它只依赖 json/os/sys，不碰库。"""
    import importlib.util
    import pathlib
    fp = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "fetch_issues_api.py"
    spec = importlib.util.spec_from_file_location("fetch_issues_api", fp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Resp:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None            # DTS 这几种坏返回都是 HTTP 200，这里正是拦不住的那一道

    def json(self):
        return self._body


def _pages(fetcher, monkeypatch, bodies):
    """把第 N 页的返回体按 pageNo 派发给 requests.post。"""
    import requests

    def fake_post(url, headers=None, data=None, timeout=None, **kw):
        page_no = int(json.loads(data)["pageNo"])
        return _Resp(bodies[page_no])
    monkeypatch.setattr(requests, "post", fake_post)


def _ok_page(rows, total):
    return {"data": {"total": total, "data": rows}}


def _rows(n, start=1):
    return [{"businessNo": f"SDTS2026010{i:04d}"} for i in range(start, start + n)]


# ── 正常路径 ───────────────────────────────────────────────────────────────

def test_full_fetch_returns_every_page(fetcher, monkeypatch):
    size = fetcher.PAGE_SIZE
    total = size + 7
    _pages(fetcher, monkeypatch, {
        1: _ok_page(_rows(size), total),
        2: _ok_page(_rows(7, start=size + 1), total),
    })
    out = fetcher.fetch_from_api("YLS3000")
    assert len(out) == total
    assert all(r["版本信息"] for r in out), "pbiName 兜底写进「版本信息」"


def test_single_page_is_fine(fetcher, monkeypatch):
    _pages(fetcher, monkeypatch, {1: _ok_page(_rows(3), 3)})
    assert len(fetcher.fetch_from_api("YLS3000")) == 3


def test_empty_result_is_not_an_error(fetcher, monkeypatch):
    """真的一条都没有，和"拉丢了"是两回事——前者正常返回空。"""
    _pages(fetcher, monkeypatch, {1: _ok_page([], 0)})
    assert fetcher.fetch_from_api("YLS3000") == []


# ── 这次要防的：翻页中途坏掉 ───────────────────────────────────────────────

def test_session_expired_midway_raises(fetcher, monkeypatch):
    """第 2 页 HTTP 200 + data:null（会话失效的典型返回）——必须抛，不能吞成空页。"""
    size = fetcher.PAGE_SIZE
    _pages(fetcher, monkeypatch, {
        1: _ok_page(_rows(size), size * 2),
        2: {"data": None, "message": "未登录"},
    })
    with pytest.raises(RuntimeError) as e:
        fetcher.fetch_from_api("YLS3000")
    assert "第 2 页" in str(e.value)
    assert "未登录" in str(e.value)


def test_blank_page_midway_raises(fetcher, monkeypatch):
    """结构合法但记录为空的一页，同样是分页中断。"""
    size = fetcher.PAGE_SIZE
    _pages(fetcher, monkeypatch, {
        1: _ok_page(_rows(size), size * 2),
        2: _ok_page([], size * 2),
    })
    with pytest.raises(RuntimeError, match="分页中断"):
        fetcher.fetch_from_api("YLS3000")


def test_short_fetch_raises_with_the_shortfall(fetcher, monkeypatch):
    """每页都"成功"了，但加起来少于 total —— 也不许落盘。"""
    size = fetcher.PAGE_SIZE
    total = size + 40
    _pages(fetcher, monkeypatch, {
        1: _ok_page(_rows(size), total),
        2: _ok_page(_rows(10, start=size + 1), total),   # 应有 40 条，只回了 10 条
    })
    with pytest.raises(RuntimeError) as e:
        fetcher.fetch_from_api("YLS3000")
    msg = str(e.value)
    assert f"{size + 10}/{total}" in msg and "差 30 条" in msg, msg


def test_surplus_is_warned_not_failed(fetcher, monkeypatch, capsys):
    """翻页期间有单增删会导致行位移、拉回来的比 total 多。

    多出来的是重复行，去重会处理，**不会**变成假解决——所以只提示，不失败。
    """
    size = fetcher.PAGE_SIZE
    total = size + 5
    _pages(fetcher, monkeypatch, {
        1: _ok_page(_rows(size), total),
        2: _ok_page(_rows(20, start=size + 1), total),
    })
    out = fetcher.fetch_from_api("YLS3000")
    assert len(out) == size + 20
    assert "多于 total" in capsys.readouterr().err
