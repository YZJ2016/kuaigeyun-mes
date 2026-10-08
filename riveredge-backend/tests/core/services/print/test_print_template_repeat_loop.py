"""批量资产卡 repeatCollection 不得重复包裹 for 循环。"""

from core.services.print.print_template_service import (
    _count_repeat_collection_loops,
    _unwrap_duplicate_collection_loops,
    _wrap_repeat_collection_body,
)


def test_wrap_repeat_collection_body_skips_when_loop_exists():
    inner = "{% for item in items %}<div class=\"card\">{{ item.code }}</div>{% endfor %}"
    wrapped = _wrap_repeat_collection_body(inner, "item", "items")
    assert wrapped == inner
    assert _count_repeat_collection_loops(wrapped, "item", "items") == 1


def test_wrap_repeat_collection_body_adds_single_loop():
    card = '<div class="card">{{ item.code }}</div>'
    wrapped = _wrap_repeat_collection_body(card, "item", "items")
    assert wrapped.count("{% for item in items %}") == 1
    assert "print-repeat-page" in wrapped


def test_unwrap_duplicate_collection_loops_removes_outer_shell():
    card = '<div class="card">{{ item.code }}</div>'
    single = _wrap_repeat_collection_body(card, "item", "items")
    # _wrap_repeat_collection_body 检测到已有循环时会原样返回；
    # 手工再包一层模拟历史脏数据产生的双层循环。
    double = '{% for item in items %}<div class="print-repeat-page">' + single + "</div>{% endfor %}"
    assert _count_repeat_collection_loops(double, "item", "items") == 2
    fixed = _unwrap_duplicate_collection_loops(double, "item", "items")
    assert _count_repeat_collection_loops(fixed, "item", "items") == 1
    assert card in fixed
