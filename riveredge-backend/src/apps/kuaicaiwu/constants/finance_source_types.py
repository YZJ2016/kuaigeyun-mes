"""Unified receivable/payable source_type strings (creation, idempotency, document trace)."""

RECEIVABLE_SOURCE_SALES_DELIVERY = "销售出库"
RECEIVABLE_SOURCE_SALES_INVOICE = "SalesInvoice"
RECEIVABLE_SOURCE_SALES_RETURN = "销售退货"
RECEIVABLE_SOURCE_CONTRACT_MILESTONE = "合同里程碑"
RECEIVABLE_SOURCE_ORDER_MILESTONE = "订单里程碑"
RECEIVABLE_SOURCE_PRICE_SETTLEMENT = "销售调价"

PAYABLE_SOURCE_PURCHASE_RECEIPT = "采购入库"
PAYABLE_SOURCE_PURCHASE_INVOICE = "PurchaseInvoice"
PAYABLE_SOURCE_OUTSOURCE_RECEIPT = "委外收货"
PAYABLE_SOURCE_OUTSOURCE_SETTLEMENT = "委外结算"
PAYABLE_SOURCE_OUTSOURCE_SETTLEMENT_CREDIT = "委外结算红字"
PAYABLE_SOURCE_OUTSOURCE_RETURN = "委外退货"
PAYABLE_SOURCE_PURCHASE_RETURN = "采购退货"
PAYABLE_SOURCE_PRICE_SETTLEMENT = "采购调价"
PAYABLE_SOURCE_ORDER_MILESTONE = "订单里程碑"


def is_sales_return_offset_receivable(source_type: str | None) -> bool:
    """销售退货确认生成的红字/冲减应收（往来贷方冲减，非正向待收款）。"""
    return str(source_type or "").strip() == RECEIVABLE_SOURCE_SALES_RETURN


def is_purchase_return_offset_payable(source_type: str | None) -> bool:
    """采购退货关联的红字/冲减应付。"""
    return str(source_type or "").strip() == PAYABLE_SOURCE_PURCHASE_RETURN


def is_outsource_return_offset_payable(source_type: str | None) -> bool:
    """委外退货或委外结算红字关联的冲减应付。"""
    st = str(source_type or "").strip()
    return st in (PAYABLE_SOURCE_OUTSOURCE_RETURN, PAYABLE_SOURCE_OUTSOURCE_SETTLEMENT_CREDIT)


def is_outsource_settlement_credit_payable(source_type: str | None) -> bool:
    """委外结算审核生成的红字差额应付。"""
    return str(source_type or "").strip() == PAYABLE_SOURCE_OUTSOURCE_SETTLEMENT_CREDIT


def is_payable_red_total_source(source_type: str | None) -> bool:
    """应付总额允许为负的来源（红字/冲减/降价调价）。"""
    st = str(source_type or "").strip()
    return (
        is_purchase_return_offset_payable(st)
        or is_outsource_return_offset_payable(st)
        or is_outsource_settlement_credit_payable(st)
        or st == PAYABLE_SOURCE_PRICE_SETTLEMENT
    )


def payable_total_must_be_negative(source_type: str | None) -> bool:
    """业务上须为负数的红字应付（不含可正可负的采购调价）。"""
    st = str(source_type or "").strip()
    return (
        is_purchase_return_offset_payable(st)
        or is_outsource_return_offset_payable(st)
        or is_outsource_settlement_credit_payable(st)
    )
