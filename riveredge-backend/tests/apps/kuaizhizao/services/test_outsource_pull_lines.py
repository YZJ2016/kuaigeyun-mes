"""工序委外取单开口行（服务端分页）。"""

from types import SimpleNamespace

from apps.kuaizhizao.schemas.outsource_order import OutsourceOptionResponse
from apps.kuaizhizao.services.outsource_service import (
    _outsource_pull_line_matches_keyword,
    OutsourceService,
    _OUTSOURCE_PULL_WO_STATUSES,
)
from decimal import Decimal


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
    opt = OutsourceOptionResponse(
        work_order_operation_id=10,
        operation_id=1,
        operation_code="OP20",
        operation_name="铣削",
        sequence=20,
        work_order_code="WO-001",
        material_code="M1",
        material_name="产品",
        specification=None,
        quantity=Decimal("100"),
        prev_operation_reported_quantity=Decimal("0"),
        max_quantity=Decimal("100"),
        completed_quantity=Decimal("0"),
        already_outsourced_quantity=Decimal("0"),
        outsourceable_quantity=Decimal("50"),
    )
    assert _outsource_pull_line_matches_keyword("铣削", work_order=wo, option=opt) is True
    assert _outsource_pull_line_matches_keyword("不存在", work_order=wo, option=opt) is False


def test_outsource_option_to_pull_line_shape():
    wo = SimpleNamespace(id=5, name="N", product_name="P")
    opt = OutsourceOptionResponse(
        work_order_operation_id=99,
        operation_id=1,
        operation_code="OP",
        operation_name="工序",
        sequence=1,
        work_order_code="WO",
        material_code="C",
        material_name="产品",
        specification="S",
        quantity=Decimal("10"),
        prev_operation_reported_quantity=Decimal("8"),
        max_quantity=Decimal("10"),
        completed_quantity=Decimal("2"),
        already_outsourced_quantity=Decimal("3"),
        outsourceable_quantity=Decimal("5"),
    )
    line = OutsourceService._outsource_option_to_pull_line(wo, opt)
    assert line["pull_row_key"] == "5-99"
    assert line["occupied_quantity"] == 5.0
    assert line["outsourceable_quantity"] == 5.0