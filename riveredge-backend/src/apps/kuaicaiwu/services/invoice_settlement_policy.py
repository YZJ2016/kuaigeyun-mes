"""租户发票开立粒度：系统参数 finance.invoice_settlement_mode 唯一真源。"""

from __future__ import annotations

from typing import Optional

from apps.kuaicaiwu.config.finance_settlement_contract import (
    SETTLEMENT_MODE_DETAIL,
    SETTLEMENT_MODE_SUMMARY,
)
from apps.kuaicaiwu.services.invoice_settlement_guard import normalize_settlement_mode
from infra.exceptions.exceptions import ValidationError


async def get_tenant_invoice_settlement_mode(tenant_id: int) -> str:
    from infra.services.business_config_service import BusinessConfigService

    cfg = await BusinessConfigService().get_business_config(tenant_id)
    fin = (cfg.get("parameters") or {}).get("finance") or {}
    return normalize_settlement_mode(fin.get("invoice_settlement_mode"))


async def assert_invoice_settlement_mode_allowed(
    tenant_id: int,
    requested: Optional[str],
) -> str:
    """返回租户锁定粒度；客户端传入不一致时拒绝。"""
    allowed = await get_tenant_invoice_settlement_mode(tenant_id)
    if requested is None:
        return allowed
    mode = normalize_settlement_mode(requested)
    if mode != allowed:
        label = "明细发票" if allowed == SETTLEMENT_MODE_DETAIL else "汇总发票"
        raise ValidationError(f"本组织系统参数已锁定为{label}模式，不可使用另一种开立粒度")
    return allowed


async def validate_invoice_settlement_mode_change(tenant_id: int, new_mode: str) -> None:
    mode = normalize_settlement_mode(new_mode)
    current = await get_tenant_invoice_settlement_mode(tenant_id)
    if mode == current:
        return
    opposite = (
        SETTLEMENT_MODE_DETAIL if mode == SETTLEMENT_MODE_SUMMARY else SETTLEMENT_MODE_SUMMARY
    )
    from apps.kuaicaiwu.models.invoice import Invoice
    from apps.kuaicaiwu.models.purchase_invoice import PurchaseInvoice

    has_purchase = await PurchaseInvoice.filter(
        tenant_id=tenant_id,
        settlement_mode=opposite,
        deleted_at__isnull=True,
    ).exists()
    has_sales = await Invoice.filter(
        tenant_id=tenant_id,
        category="OUT",
        settlement_mode=opposite,
        deleted_at__isnull=True,
    ).exists()
    if has_purchase or has_sales:
        raise ValidationError("已存在另一种粒度的发票单据，禁止切换发票开立模式")