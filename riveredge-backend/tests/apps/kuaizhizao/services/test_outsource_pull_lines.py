"""工序委外取单开口行（服务端分页）。"""

from types import SimpleNamespace

from apps.kuaizhizao.services.outsource_service import (
    _outsource_pull_line_matches_keyword,
    _OUTSOURCE_PULL_WO_STATUSES,
)


def test_outsource_pull_wo_statuses_include_released():
    assert "released" in _OUTSOURCE_PULL_WO_STATUSES
    assert "已下达" in _OUTSOURCE_PULL_WO_STATUSES


def test_outsource_pull_line_matches_keyword_on_operation():
    wo = SimpleNamespace(
        code="WO-001",
        name="测试工单",
        product_code="M1",
        product_name="产品",
    )
    op = SimpleNamespace(
        operation_code="OP20",
        operation_name="铣削",
    )
    assert _outsource_pull_line_matches_keyword("铣削", work_order=wo, operation=op) is True
    assert _outsource_pull_line_matches_keyword("wo-001", work_order=wo, operation=op) is True
    assert _outsource_pull_line_matches_keyword("不存在", work_order=wo, operation=op) is False
