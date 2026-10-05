"""销售订单币种/汇率下推携带。

销售侧下游用 currency_code；采购订单模型字段为 currency。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional, Tuple


def extract_sales_order_currency(order: Any) -> Tuple[str, Decimal]:
    """从销售订单（或兼容 dict）取出规范化币种与汇率。"""
    if order is None:
        return "CNY", Decimal("1")
    if isinstance(order, dict):
        raw_code = order.get("currency_code") or order.get("currency")
        raw_rate = order.get("exchange_rate")
    else:
        raw_code = getattr(order, "currency_code", None) or getattr(order, "currency", None)
        raw_rate = getattr(order, "exchange_rate", None)
    code = str(raw_code or "CNY").strip().upper() or "CNY"
    try:
        rate = Decimal(str(raw_rate if raw_rate is not None else 1))
    except Exception:
        rate = Decimal("1")
    if rate <= 0:
        rate = Decimal("1")
    return code, rate


def currency_fields_for_sales_doc(
    order: Any,
    *,
    override_code: Optional[str] = None,
    override_rate: Optional[Decimal] = None,
) -> Dict[str, Any]:
    """销售下游单据写入字段：currency_code + exchange_rate。"""
    code, rate = extract_sales_order_currency(order)
    if override_code is not None and str(override_code).strip():
        code = str(override_code).strip().upper()
    if override_rate is not None:
        try:
            rate = Decimal(str(override_rate))
        except Exception:
            pass
        if rate <= 0:
            rate = Decimal("1")
    return {"currency_code": code, "exchange_rate": rate}


def currency_fields_for_purchase_doc(order: Any) -> Dict[str, Any]:
    """采购订单写入字段：currency + exchange_rate。"""
    code, rate = extract_sales_order_currency(order)
    return {"currency": code, "exchange_rate": rate}


async def resolve_sales_order_currency_for_tenant(
    tenant_id: int,
    sales_order_id: Optional[int],
) -> Tuple[str, Decimal]:
    """按销售订单 ID 解析币种；订单不存在时回退 CNY / 1。"""
    if not sales_order_id or int(sales_order_id) <= 0:
        return "CNY", Decimal("1")
    from apps.kuaizhizao.models.sales_order import SalesOrder

    order = await SalesOrder.get_or_none(
        tenant_id=tenant_id,
        id=int(sales_order_id),
        deleted_at__isnull=True,
    )
    return extract_sales_order_currency(order)
