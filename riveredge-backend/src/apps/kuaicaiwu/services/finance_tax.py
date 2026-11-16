"""发票税额：后端统一按未税金额 × 税率计算。"""

from __future__ import annotations

from decimal import Decimal

_MONEY_SCALE = Decimal("0.01")


def quantize_money(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(_MONEY_SCALE)


def money_exceeds_max(total_incl: Decimal, max_total_incl: Decimal) -> bool:
    """价税合计是否超过可开票上限（两侧先量化到分）。"""
    return quantize_money(total_incl) > quantize_money(max_total_incl)


def money_to_json_float(value: Decimal) -> float:
    """分位金额序列化为 JSON number，经 str 避免二进制浮点毛刺。"""
    return float(str(quantize_money(value)))


def compute_purchase_order_header_amounts(
    total_excl: Decimal | str | int | float,
    tax_rate_decimal: Decimal | str | int | float,
) -> tuple[Decimal, Decimal, Decimal]:
    """
    采购订单头：未税合计 × 税率（小数，如 0.13）→ 税额、价税合计。
    与前端 calcDocumentLineAmountsFromExclTotal 同口径（分位量化）。
    多税率订单请用 compute_purchase_order_header_amounts_from_lines。
    """
    excl = quantize_money(total_excl)
    rate = Decimal(str(tax_rate_decimal or 0))
    tax = quantize_money(excl * rate)
    net = quantize_money(excl + tax)
    return excl, tax, net


def compute_purchase_order_header_amounts_from_lines(
    line_excl_and_tax_percent: list[tuple[Decimal | str | int | float, Decimal | str | int | float]],
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """
    按行未税 + 行税率（百分比）汇总头表：未税合计、税额、价税合计，以及代表税率（小数）。

    代表税率取首个非零行税率 / 100，供头表 tax_rate 兼容下游单税率字段；
    税额与价税合计始终按行汇总，多税率时与代表税率重算结果可不一致。
    """
    total_excl = Decimal("0")
    total_tax = Decimal("0")
    first_pct = Decimal("0")
    for excl_raw, pct_raw in line_excl_and_tax_percent:
        excl = quantize_money(excl_raw)
        pct = Decimal(str(pct_raw or 0))
        if pct < 0:
            pct = Decimal("0")
        _, tax, _ = compute_tax_from_excluding(excl, pct)
        total_excl += excl
        total_tax += tax
        if first_pct <= 0 and pct > 0:
            first_pct = pct
    total_excl = quantize_money(total_excl)
    total_tax = quantize_money(total_tax)
    net = quantize_money(total_excl + total_tax)
    header_rate = (
        (first_pct / Decimal("100")).quantize(Decimal("0.01"))
        if first_pct > 0
        else Decimal("0")
    )
    return total_excl, total_tax, net, header_rate


def compute_tax_from_excluding(
    amount_excl: Decimal,
    tax_rate_percent: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    """
    按未税金额与税率（百分比 0–100）计算税额与价税合计。

    销项发票 API 入参 tax_rate 为百分比；进项发票 PurchaseInvoice.tax_rate 同为百分比。
    销项落库 Invoice.tax_rate 为小数（API 层除以 100），本函数仅处理百分比口径。
    """
    excl = quantize_money(amount_excl)
    rate = Decimal(tax_rate_percent) / Decimal("100")
    tax = (excl * rate).quantize(_MONEY_SCALE)
    total = (excl + tax).quantize(_MONEY_SCALE)
    return excl, tax, total


def compute_tax_from_including(
    amount_incl: Decimal,
    tax_rate_percent: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    """按价税合计与税率（百分比 0–100）反算未税金额与税额。"""
    total = quantize_money(amount_incl)
    factor = Decimal("1") + Decimal(tax_rate_percent) / Decimal("100")
    excl = (total / factor).quantize(_MONEY_SCALE)
    tax = (total - excl).quantize(_MONEY_SCALE)
    return excl, tax, total


def resolve_invoice_amounts_for_create(
    invoice_amount: Decimal,
    tax_rate_percent: Decimal,
    total_amount: Decimal | None = None,
) -> tuple[Decimal, Decimal, Decimal]:
    """
    开票价税拆分。

    含税录入时客户端显式传入价税合计，以合计为真源反算未税/税额，避免
    「先除税率再乘税率」产生 0.01 漂移（如 60000/1.13→53097.35→60000.01）。
    不含税录入时按未税金额正算。
    """
    if total_amount is not None:
        return compute_tax_from_including(total_amount, tax_rate_percent)
    return compute_tax_from_excluding(invoice_amount, tax_rate_percent)
