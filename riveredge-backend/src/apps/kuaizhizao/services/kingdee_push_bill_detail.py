"""详情响应挂载金蝶外推单号（读 DocumentRelation）。"""

from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")


async def attach_kingdee_bill_no_detail(
    resp: T,
    *,
    tenant_id: int,
    source_type: str,
    source_id: int,
) -> T:
    from apps.kuaizhizao.services.kingdee_push_bill_resolver import resolve_kingdee_push_bill_no

    bill_no = await resolve_kingdee_push_bill_no(tenant_id, source_type, int(source_id))
    return resp.model_copy(update={"kingdee_bill_no": bill_no})


async def attach_stocktaking_kingdee_bills_detail(
    resp: T,
    *,
    tenant_id: int,
    stocktaking_id: int,
) -> T:
    from apps.kuaizhizao.services.kingdee_push_bill_resolver import (
        resolve_kingdee_stocktaking_push_bills,
    )

    bills = await resolve_kingdee_stocktaking_push_bills(tenant_id, int(stocktaking_id))
    return resp.model_copy(
        update={
            "kingdee_surplus_bill_no": bills.kingdee_surplus_bill_no,
            "kingdee_deficit_bill_no": bills.kingdee_deficit_bill_no,
        }
    )