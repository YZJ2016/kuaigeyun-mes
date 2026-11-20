"""销售订单下游检测：忽略已软删节点，避免误拦删除。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from apps.kuaizhizao.services import sales_order_code_sync
from apps.kuaizhizao.services.sales_order_code_sync import (
    _flatten_active_downstream_nodes,
    filter_sales_order_capability_blocking_documents,
    format_sales_order_downstream_labels,
    sales_order_downstream_by_ids,
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


def test_capability_filter_ignores_orphan_demand_computation_only():
    docs = [
        {"document_type": "demand_computation", "document_id": 9, "document_code": "MRP0106"},
    ]
    assert filter_sales_order_capability_blocking_documents(docs) == []


def test_capability_filter_keeps_work_order_with_computation():
    docs = [
        {"document_type": "demand_computation", "document_id": 9, "document_code": "MRP0106"},
        {"document_type": "work_order", "document_id": 2, "document_code": "WO-1"},
    ]
    filtered = filter_sales_order_capability_blocking_documents(docs)
    assert len(filtered) == 1
    assert filtered[0]["document_type"] == "work_order"


def _relation_query(rows):
    query = MagicMock()
    query.values = AsyncMock(return_value=rows)
    return query


def test_downstream_map_ignores_demand_computation_relation_only():
    rows = [
        {
            "source_id": 11,
            "target_type": "demand_computation",
            "target_id": 50,
            "target_code": "MRP0106",
            "target_name": None,
        }
    ]
    with patch.object(
        sales_order_code_sync,
        "_SALES_ORDER_DOWNSTREAM_FK_SPECS",
        [],
    ), patch.object(
        sales_order_code_sync.DocumentRelation,
        "filter",
        return_value=_relation_query(rows),
    ):
        result = asyncio.run(sales_order_downstream_by_ids(1, [11]))

    assert result == {11: False}


def test_format_downstream_labels():
    labels = format_sales_order_downstream_labels(
        [
            {"document_type": "work_order", "document_code": "WO-1"},
            {"document_type": "shipment_notice", "document_code": "SN-2"},
        ]
    )
    assert labels == "生产工单WO-1、发货通知SN-2"
