"""采购申请取单开口行：同物料多行独立展示（服务层实测）。"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.kuaizhizao.services.purchase_requisition_service import PurchaseRequisitionService


def _req():
    return SimpleNamespace(
        id=100,
        requisition_code="CGSQ20261122001",
        status="已审核",
        review_status="approved",
        requisition_date=date(2026, 11, 20),
        applicant_name="测试员",
        department_id=1,
        department_name="采购部",
        order_type="标准采购",
    )


def _item(*, item_id: int, qty: str, required: date, supplier_id: int | None = None):
    return SimpleNamespace(
        id=item_id,
        requisition_id=100,
        material_id=888,
        material_code="WL-001",
        material_name="同一物料",
        material_spec="规格A",
        quantity=Decimal(qty),
        unit="件",
        required_date=required,
        notes="",
        supplier_id=supplier_id,
        aux_quantity=None,
        aux_unit=None,
    )


class _AwaitableList:
    def __init__(self, items):
        self._items = items

    def __await__(self):
        async def _go():
            return self._items

        return _go().__await__()


class _ReqQuery:
    def filter(self, *args, **kwargs):
        return self

    def only(self, *args):
        return _AwaitableList([_req()])


class _ItemQuery:
    def __init__(self, items):
        self._items = items

    def filter(self, *args, **kwargs):
        return self

    async def all(self):
        return self._items


@pytest.mark.asyncio
async def test_list_purchase_order_pull_lines_same_material_two_independent_rows():
    """同申请同物料两行：建议/已转/可取按行不同，预交日各自独立（禁止组内 16/2/14 合并展示）。"""
    item_a = _item(item_id=501, qty="10", required=date(2026, 12, 1), supplier_id=42)
    item_b = _item(item_id=502, qty="6", required=date(2026, 12, 20))
    service = PurchaseRequisitionService()

    async def fake_occ(_tenant_id, _item_ids):
        return ({501: Decimal("0"), 502: Decimal("2")}, {})

    async def fake_stock(_tenant_id):
        return {888: Decimal("100")}

    async def fake_paginate(_tenant_id, lines, skip, limit, **kwargs):
        return {"data": lines[skip : skip + limit], "total": len(lines)}

    async def fake_supplier_names(_tenant_id, _ids):
        return {42: "默认供应商样例"}

    with (
        patch(
            "apps.kuaizhizao.services.purchase_requisition_service.PurchaseRequisition"
        ) as ReqModel,
        patch(
            "apps.kuaizhizao.services.purchase_requisition_service.PurchaseRequisitionItem"
        ) as ItemModel,
        patch.object(
            service,
            "_occupied_purchase_order_qty_by_requisition_item_ids",
            fake_occ,
        ),
        patch(
            "apps.kuaizhizao.services.purchase_requisition_service.aggregate_on_hand_qty_by_material",
            fake_stock,
        ),
        patch(
            "apps.kuaizhizao.utils.inventory_helper.paginate_pull_lines_with_stock",
            fake_paginate,
        ),
        patch.object(service, "_batch_supplier_names", fake_supplier_names),
    ):
        ReqModel.filter.return_value = _ReqQuery()
        ItemModel.filter.return_value = _ItemQuery([item_a, item_b])

        result = await service.list_purchase_order_pull_lines(1, skip=0, limit=50)

    assert result["total"] == 2
    by_id = {row["id"]: row for row in result["data"]}

    assert by_id[501]["suggested_quantity"] == 10.0
    assert by_id[501]["pushed_quantity"] == 0.0
    assert by_id[501]["remaining_quantity"] == 10.0
    assert by_id[501]["required_date"] == "2026-12-01"
    assert by_id[501]["supplier_name"] == "默认供应商样例"
    assert by_id[502].get("supplier_name") is None

    assert by_id[502]["suggested_quantity"] == 6.0
    assert by_id[502]["pushed_quantity"] == 2.0
    assert by_id[502]["remaining_quantity"] == 4.0
    assert by_id[502]["required_date"] == "2026-12-20"

    # 旧逻辑会把组建议量 16 打到两行上
    assert by_id[501]["suggested_quantity"] != 16.0
    assert by_id[502]["suggested_quantity"] != 16.0