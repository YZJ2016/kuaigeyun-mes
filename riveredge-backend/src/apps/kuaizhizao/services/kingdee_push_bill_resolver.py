"""
外推金蝶单据号解析（读 DocumentRelation 真源，禁止头表冗余字段）。

落点须在 kuaizhizao：详情回显不依赖 kuaiConnect 包是否部署。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from apps.kuaizhizao.models.document_relation import DocumentRelation

KINGDEE_SURPLUS_TARGET = "kingdee_im_surplusbill"
KINGDEE_DEFICIT_TARGET = "kingdee_im_deficitbill"

# 外推金蝶且有打印模板的单据。打印变量与模板升级共用这一份。
KINGDEE_PRINT_SOURCE_TYPES = frozenset(
    {
        "purchase_receipt",
        "sales_delivery",
        "other_outbound",
        "other_inbound",
        "production_picking",
        "finished_goods_receipt",
        "sales_order",
        "purchase_order",
        "work_order",
    }
)


async def resolve_kingdee_push_bill_no(
    tenant_id: int,
    source_type: str,
    source_id: int,
    *,
    target_type: Optional[str] = None,
) -> Optional[str]:
    """最近一次成功外推的金蝶单号（target_code / FBillNo）。"""
    st = str(source_type or "").strip()
    if not st or source_id <= 0:
        return None
    q = DocumentRelation.filter(
        tenant_id=tenant_id,
        source_type=st,
        source_id=int(source_id),
        relation_mode="push",
    )
    if target_type:
        q = q.filter(target_type=str(target_type).strip())
    else:
        q = q.filter(target_type__startswith="kingdee_")
    rows = await q.order_by("-id").all()
    for rel in rows:
        code = str(rel.target_code or "").strip()
        if code:
            return code
    return None


@dataclass(frozen=True)
class KingdeeStocktakingPushBills:
    kingdee_surplus_bill_no: Optional[str]
    kingdee_deficit_bill_no: Optional[str]


async def resolve_kingdee_stocktaking_push_bills(
    tenant_id: int,
    stocktaking_id: int,
) -> KingdeeStocktakingPushBills:
    surplus = await resolve_kingdee_push_bill_no(
        tenant_id,
        "stocktaking",
        stocktaking_id,
        target_type=KINGDEE_SURPLUS_TARGET,
    )
    deficit = await resolve_kingdee_push_bill_no(
        tenant_id,
        "stocktaking",
        stocktaking_id,
        target_type=KINGDEE_DEFICIT_TARGET,
    )
    return KingdeeStocktakingPushBills(
        kingdee_surplus_bill_no=surplus,
        kingdee_deficit_bill_no=deficit,
    )