"""客户面分类：带编号的客户名不能互相吃掉。

`"1号机" in "11号机"` 是真的（从第二个字符起就是），所以标题里的「11号机」曾经会被
「1号机」认走。表现是同一台机器的单子散在两行、或者两台机器的单子混进一行——
数字还是那些数字，加起来也对得上，没人会当 bug 报上来。

这里钉住两件事：
1. 两台机器都登记时，「11号机」的单子归「11号机」（长度降序 + 数字边界）；
2. **只登记了「1号机」时，「11号机」的单子也不许被它吃掉**——宁可落到「研发问题」
   里等人去补客户主数据，也不要挂到一台错的机器上：前者页面上看得见，后者看不见。
"""
import pytest


@pytest.fixture(scope="module")
def ri(client):
    """routers.issues。**必须依赖 client 之后再 import**：conftest 的 client 夹具
    先 os.chdir 到临时库目录，模块顶层 import 会赶在 chdir 之前把引擎连上仓库里的
    backend/app.db。
    """
    import routers.issues as ri
    return ri


def _m(*names):
    """[(匹配文本, 展示名)]，照 _load_customer_matchers 的规矩按长度降序。"""
    return sorted([(n.lower(), n) for n in names], key=lambda x: len(x[0]), reverse=True)


@pytest.mark.parametrize("title, expected", [
    ("西安厂11号机 光刻异常", "11号机"),
    ("西安厂1号机 光刻异常", "1号机"),
    # 一条单只有一个客户面字段，两台都提到时取**更具体的那个**（长度降序的既有口径），
    # 不按标题里谁先出现——出现顺序是文案习惯，不是信息。
    ("1号机与11号机同时告警", "11号机"),
])
def test_numbered_machines_do_not_swallow_each_other(ri, title, expected):
    assert ri._match_customer(title, _m("1号机", "11号机")) == expected


def test_unregistered_machine_is_not_absorbed_by_a_shorter_one(ri):
    """「11号机」没登记时，宁可不匹配，也不要挂到「1号机」上。"""
    assert ri._match_customer("西安厂11号机 光刻异常", _m("1号机")) == ""
    assert ri._match_customer("西安厂1号机 光刻异常", _m("1号机")) == "1号机"


def test_trailing_digits_are_bounded_too(ri):
    """名字以数字结尾的同理：C10 不能认走 C100。"""
    assert ri._match_customer("产线 C100 停机", _m("C10")) == ""
    assert ri._match_customer("产线 C10 停机", _m("C10")) == "C10"
    assert ri._match_customer("产线 C100 停机", _m("C10", "C100")) == "C100"


def test_normal_matching_still_works(ri):
    """边界只拒绝「数字被切开」，中文/英文边界不管——客户名混在标题里没有分隔符。"""
    assert ri._match_customer("长江存储产线异常", _m("长江存储")) == "长江存储"
    assert ri._match_customer("无关标题", _m("长江存储")) == ""
    assert ri._match_customer("", _m("长江存储")) == ""
