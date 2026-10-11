"""销售订单下游检测：忽略已软删节点，避免误拦删除。"""

from types import SimpleNamespace

from apps.kuaizhizao.services.sales_order_code_sync import (
    _flatten_active_downstream_nodes,
    format_sales_order_downstream_labels,
)


def test_flatten_skips_deleted_leaf_but_keeps_live_sibling():
    tree = [
        SimpleNamespace(
            document_type="work_order",
            document_id=1,
            document_code="WO-DEL",
            document_name="deleted",
            is_deleted=True,
            children=[],
        ),
        SimpleNamespace(
            document_type="work_order",
            document_id=2,
            document_code="WO-LIVE",
            document_name="live",
            is_deleted=False,
            children=[],
        ),
    ]
    collected = _flatten_active_downstream_nodes(tree)
    assert set(collected.keys()) == {("work_order", 2)}
    assert collected[("work_order", 2)]["document_code"] == "WO-LIVE"


def test_flatten_ignores_demand_but_keeps_its_live_children():
    tree = [
        SimpleNamespace(
            document_type="demand",
            document_id=9,
            document_code="D-1",
            document_name="demand",
            is_deleted=False,
            children=[
                SimpleNamespace(
                    document_type="demand_computation",
                    document_id=3,
                    document_code="DC-1",
                    document_name="comp",
                    is_deleted=False,
                    children=[],
                )
            ],
        )
    ]
    collected = _flatten_active_downstream_nodes(tree)
    assert set(collected.keys()) == {("demand_computation", 3)}


def test_flatten_drills_into_deleted_parent_for_live_child():
    tree = [
        SimpleNamespace(
            document_type="work_order",
            document_id=1,
            document_code="WO-DEL",
            document_name="deleted",
            is_deleted=True,
            children=[
                SimpleNamespace(
                    document_type="sales_delivery",
                    document_id=8,
                    document_code="SD-1",
                    document_name=None,
                    is_deleted=False,
                    children=[],
                )
            ],
        )
    ]
    collected = _flatten_active_downstream_nodes(tree)
    assert set(collected.keys()) == {("sales_delivery", 8)}


def test_format_downstream_labels():
    labels = format_sales_order_downstream_labels(
        [
            {"document_type": "work_order", "document_code": "WO-1"},
            {"document_type": "shipment_notice", "document_code": "SN-2"},
        ]
    )
    assert labels == "工单WO-1、发货通知SN-2"
