"""
财务协同模块数据验证schema

提供财务协同相关的数据验证和序列化。

Author: Luigi Lu
Date: 2025-12-30
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pydantic import Field, model_validator
from core.schemas.base import BaseSchema
from apps.kuaicaiwu.constants.finance_source_types import (
    PAYABLE_SOURCE_PRICE_SETTLEMENT,
    PAYABLE_SOURCE_PURCHASE_INVOICE_DISCOUNT,
    PAYABLE_SOURCE_PURCHASE_RETURN,
    is_payable_red_total_source,
    payable_total_must_be_negative,
)


# === 应付单 ===

class PayableBase(BaseSchema):
    """应付单基础schema"""
    payable_code: str = Field(..., max_length=50, description="应付单编码")
    source_type: str = Field(..., max_length=20, description="来源单据类型")
    source_id: int = Field(..., description="来源单据ID")
    source_code: str = Field(..., max_length=50, description="来源单据编码")
    supplier_id: int = Field(..., description="供应商ID")
    supplier_name: str = Field(..., max_length=200, description="供应商名称")
    total_amount: Decimal = Field(..., description="应付总金额（红字/冲减来源可为负）")
    paid_amount: Decimal = Field(Decimal("0"), ge=0, description="已付金额")
    remaining_amount: Decimal = Field(..., description="剩余金额（红字应付可为负或零）")
    due_date: date = Field(..., description="到期日期")
    payment_terms: Optional[str] = Field(None, max_length=100, description="付款条件")
    status: str = Field("未付款", max_length=20, description="付款状态")
    refunded_amount: Decimal = Field(Decimal("0"), ge=0, description="已确认退款冲回合计")
    refund_execution_status: str = Field("未退款", max_length=20, description="退款执行状态")
    business_date: date = Field(..., description="业务日期")
    invoice_received: bool = Field(False, description="是否收到发票")
    invoice_number: Optional[str] = Field(None, max_length=100, description="发票号")
    reviewer_id: Optional[int] = Field(None, description="审核人ID")
    reviewer_name: Optional[str] = Field(None, max_length=100, description="审核人姓名")
    review_time: Optional[datetime] = Field(None, description="审核时间")
    review_status: str = Field("草稿", max_length=20, description="审核状态")
    review_remarks: Optional[str] = Field(None, description="审核备注")
    notes: Optional[str] = Field(None, description="备注")
    attachments: Optional[List[dict]] = Field(None, description="附件列表")

    @model_validator(mode="after")
    def _validate_payable_total_amount_sign(self) -> "PayableBase":
        src = str(self.source_type or "").strip()
        amt = Decimal(str(self.total_amount or 0))
        remaining = Decimal(str(self.remaining_amount or 0))
        if payable_total_must_be_negative(src):
            if amt >= 0:
                if src == PAYABLE_SOURCE_PURCHASE_RETURN:
                    raise ValueError("采购退货红字应付金额须为负数")
                raise ValueError("红字应付金额须为负数")
        elif src in (PAYABLE_SOURCE_PRICE_SETTLEMENT, PAYABLE_SOURCE_PURCHASE_INVOICE_DISCOUNT):
            if amt == 0:
                raise ValueError("应付金额不能为 0")
        elif not is_payable_red_total_source(src) and amt <= 0:
            raise ValueError("应付总金额须大于 0")
        if amt > 0 and remaining < 0:
            raise ValueError("剩余金额不能为负")
        if amt < 0 and remaining > 0:
            raise ValueError("红字应付剩余金额不能为正")
        return self


class PurchaseReceiptLinePullSelection(BaseSchema):
    """从采购入库行加载应付/进项时的行级金额选择"""

    purchase_receipt_item_id: int = Field(..., description="采购入库明细ID")
    amount: Decimal = Field(..., gt=0, description="本单占用金额")


class PayableCreate(PayableBase):
    """应付单创建schema"""
    payable_code: Optional[str] = Field(None, max_length=50, description="应付单编码（可选，如果不提供则自动生成）")
    pull_source_type: Optional[str] = Field(
        None,
        description="加载源单类型 purchase_order|purchase_receipt（与 source_type 手工创建区分）",
    )
    pull_source_id: Optional[int] = Field(None, description="加载源单ID")
    pull_source_ids: Optional[List[int]] = Field(
        None, description="加载源单ID列表（同供应商多入库单合并应付）"
    )
    pull_receipt_lines: Optional[List[PurchaseReceiptLinePullSelection]] = Field(
        None, description="入库行级占用金额（source=purchase_receipt 时可选；未传则按序占用）"
    )


class PayableUpdate(BaseSchema):
    """应付单更新schema（可纠错字段；未传字段保持原值）"""
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = Field(None, max_length=200)
    total_amount: Optional[Decimal] = Field(None, gt=0)
    due_date: Optional[date] = None
    payment_terms: Optional[str] = Field(None, max_length=100)
    business_date: Optional[date] = None
    notes: Optional[str] = None
    attachments: Optional[List[dict]] = None


class PayableResponse(PayableBase):
    """应付单响应schema"""
    id: int = Field(..., description="应付单ID")
    tenant_id: int = Field(..., description="租户ID")
    invoiced_amount: Decimal = Field(Decimal("0"), description="已收票金额（列表聚合，含红字为负的净值）")
    remaining_invoice_amount: Decimal = Field(Decimal("0"), ge=0, description="未收票金额（列表聚合）")
    invoice_status: str = Field("未收票", max_length=20, description="收票状态（列表聚合）")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    created_by_name: Optional[str] = Field(None, description="创建人姓名")
    updated_by_name: Optional[str] = Field(None, description="更新人姓名")
    capabilities: Optional[dict] = Field(None, description="下推能力（如 push_payment）")

    class Config:
        from_attributes = True


class PayableListResponse(BaseSchema):
    """应付单列表响应schema"""
    items: List[PayableResponse] = Field(..., description="应付单列表")
    total: int = Field(..., description="总数量")
    skip: int = Field(..., description="跳过数量")
    limit: int = Field(..., description="限制数量")


# === 采购发票 ===

class PurchaseInvoiceBase(BaseSchema):
    """采购发票基础schema"""
    invoice_code: Optional[str] = Field(None, max_length=50, description="发票编码")
    purchase_order_id: Optional[int] = Field(None, description="采购订单ID")
    purchase_order_code: Optional[str] = Field(None, max_length=50, description="采购订单编码")
    supplier_id: int = Field(..., description="供应商ID")
    supplier_name: str = Field(..., max_length=200, description="供应商名称")
    invoice_number: str = Field(..., max_length=100, description="发票号码")
    invoice_date: date = Field(..., description="发票日期")
    invoice_type: str = Field(..., max_length=20, description="发票类型")
    tax_rate: Decimal = Field(..., ge=0, le=100, description="税率（百分比，如 13 表示 13%）")
    invoice_amount: Decimal = Field(..., ge=0, description="未税金额")
    tax_amount: Decimal = Field(..., ge=0, description="税额（服务端按未税金额×税率计算，入参可忽略）")
    total_amount: Decimal = Field(..., ge=0, description="价税合计（服务端计算，入参可忽略）")
    discount_amount: Decimal = Field(
        Decimal("0"), description="收票优惠金额(含税,可正可负);占用源单=W=价税合计+优惠"
    )
    adjust_payable: bool = Field(
        False, description="从应付单收票且优惠非零时，审核通过后生成优惠调整应付"
    )
    status: str = Field("未审核", max_length=20, description="发票状态")
    reviewer_id: Optional[int] = Field(None, description="审核人ID")
    reviewer_name: Optional[str] = Field(None, max_length=100, description="审核人姓名")
    review_time: Optional[datetime] = Field(None, description="审核时间")
    review_status: str = Field("草稿", max_length=20, description="审核状态")
    review_remarks: Optional[str] = Field(None, description="审核备注")
    payable_id: Optional[int] = Field(None, description="应付单ID")
    payable_code: Optional[str] = Field(None, max_length=50, description="应付单编码")
    attachment_path: Optional[str] = Field(None, max_length=500, description="附件路径")
    notes: Optional[str] = Field(None, description="备注")
    attachments: Optional[List[dict]] = Field(None, description="附件列表")
    tax_period: Optional[str] = Field(None, max_length=7, description="税务属期")
    verification_status: Optional[str] = Field(None, max_length=32, description="认证状态")
    verification_date: Optional[date] = Field(None, description="认证日期")
    transfer_out_reason: Optional[str] = Field(None, description="转出原因")
    original_invoice_id: Optional[int] = Field(None, description="原蓝字发票ID")
    red_flush_invoice_id: Optional[int] = Field(None, description="红字发票ID")


class ConcurrentSettlementCreate(BaseSchema):
    """开票同时收款/付款（仅拉单自应收/应付时生效）"""

    enabled: bool = Field(False, description="是否同时生成收/付款单")
    total_amount: Optional[Decimal] = Field(None, gt=0, description="收/付款金额（可与开票价税合计不同）")
    payment_method: Optional[str] = Field(None, max_length=50, description="收/付款方式")
    bank_account_id: Optional[int] = Field(None, description="入账/出款账户ID")
    bank_account: Optional[str] = Field(None, max_length=100, description="账户备注")
    voucher_date: Optional[date] = Field(None, description="收/付款日期")
    notes: Optional[str] = Field(None, description="收/付款备注")


class PurchaseInvoiceCreate(PurchaseInvoiceBase):
    """采购发票创建schema"""

    tax_amount: Optional[Decimal] = Field(
        None, ge=0, description="税额（服务端按未税金额×税率计算，入参可忽略）"
    )
    total_amount: Optional[Decimal] = Field(
        None, ge=0, description="价税合计（含税录入时须传入，服务端据此反算未税/税额）"
    )
    source_type: Optional[str] = Field(None, description="加载源单类型 purchase_order|purchase_receipt|payable")
    source_id: Optional[int] = Field(None, description="加载源单ID")
    source_ids: Optional[List[int]] = Field(
        None, description="加载源单ID列表（同供应商多单合并开票）"
    )
    pull_receipt_lines: Optional[List[PurchaseReceiptLinePullSelection]] = Field(
        None, description="入库行级占用金额（source=purchase_receipt 时可选；未传则按 FIFO）"
    )
    concurrent_settlement: Optional[ConcurrentSettlementCreate] = Field(
        None, description="从应付开票时可选：同时生成付款单"
    )
    partner_statement_ids: Optional[List[int]] = Field(
        None,
        description="从往来对账单（按发票立账）加载入库开票时须传入对账单ID，用于放行月结阻断",
    )


class PurchaseInvoiceUpdate(BaseSchema):
    """采购发票更新（部分字段）；已审核仅允许补全发票号码与附件"""

    invoice_number: Optional[str] = Field(None, max_length=100, description="发票号码")
    invoice_date: Optional[date] = None
    invoice_type: Optional[str] = Field(None, max_length=20)
    tax_rate: Optional[Decimal] = Field(None, ge=0, le=100, description="税率（百分比）")
    invoice_amount: Optional[Decimal] = Field(None, ge=0, description="未税金额")
    tax_amount: Optional[Decimal] = Field(None, ge=0, description="税额")
    total_amount: Optional[Decimal] = Field(None, ge=0, description="价税合计")
    discount_amount: Optional[Decimal] = Field(
        None, description="收票优惠金额(含税,可正可负)"
    )
    adjust_payable: Optional[bool] = Field(
        None, description="从应付收票是否生成优惠调整应付"
    )
    notes: Optional[str] = None
    attachments: Optional[List[dict]] = Field(None, description="附件列表")
    attachment_path: Optional[str] = Field(None, max_length=500)

class PurchaseInvoiceResponse(PurchaseInvoiceBase):
    """采购发票响应schema"""
    id: int = Field(..., description="发票ID")
    tenant_id: int = Field(..., description="租户ID")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    created_by_name: Optional[str] = Field(None, description="创建人姓名")
    updated_by_name: Optional[str] = Field(None, description="更新人姓名")

    class Config:
        from_attributes = True


class PurchaseInvoiceListResponse(BaseSchema):
    """采购发票列表响应schema"""
    items: List[PurchaseInvoiceResponse] = Field(..., description="发票列表")
    total: int = Field(..., description="总数量")
    skip: int = Field(..., description="跳过数量")
    limit: int = Field(..., description="限制数量")


# === 应收单 ===

class ReceivableBase(BaseSchema):
    """应收单基础schema"""
    receivable_code: str = Field(..., max_length=50, description="应收单编码")
    source_type: str = Field(..., max_length=20, description="来源单据类型")
    source_id: int = Field(..., description="来源单据ID")
    source_code: str = Field(..., max_length=50, description="来源单据编码")
    customer_id: int = Field(..., description="客户ID")
    customer_name: str = Field(..., max_length=200, description="客户名称")
    total_amount: Decimal = Field(..., gt=0, description="应收总金额")
    received_amount: Decimal = Field(Decimal("0"), ge=0, description="已收金额")
    remaining_amount: Decimal = Field(..., ge=0, description="剩余金额")
    due_date: date = Field(..., description="到期日期")
    payment_terms: Optional[str] = Field(None, max_length=100, description="收款条件")
    status: str = Field("未收款", max_length=20, description="收款状态")
    refunded_amount: Decimal = Field(Decimal("0"), ge=0, description="已确认退款冲回合计")
    refund_execution_status: str = Field("未退款", max_length=20, description="退款执行状态")
    business_date: date = Field(..., description="业务日期")
    invoice_issued: bool = Field(False, description="是否开具发票")
    invoice_number: Optional[str] = Field(None, max_length=100, description="发票号")
    reviewer_id: Optional[int] = Field(None, description="审核人ID")
    reviewer_name: Optional[str] = Field(None, max_length=100, description="审核人姓名")
    review_time: Optional[datetime] = Field(None, description="审核时间")
    review_status: str = Field("草稿", max_length=20, description="审核状态")
    review_remarks: Optional[str] = Field(None, description="审核备注")
    notes: Optional[str] = Field(None, description="备注")
    attachments: Optional[List[dict]] = Field(None, description="附件列表")


class ReceivableCreate(ReceivableBase):
    """应收单创建schema"""
    receivable_code: Optional[str] = Field(None, max_length=50, description="应收单编码（可选，如果不提供则自动生成）")
    pull_source_type: Optional[str] = Field(
        None,
        description="加载源单类型 sales_order|sales_delivery（与 source_type 手工创建区分）",
    )
    pull_source_id: Optional[int] = Field(None, description="加载源单ID")


class ReceivableUpdate(BaseSchema):
    """应收单更新schema（可纠错字段；未传字段保持原值）"""
    customer_id: Optional[int] = None
    customer_name: Optional[str] = Field(None, max_length=200)
    total_amount: Optional[Decimal] = Field(None, gt=0)
    due_date: Optional[date] = None
    payment_terms: Optional[str] = Field(None, max_length=100)
    business_date: Optional[date] = None
    notes: Optional[str] = None
    attachments: Optional[List[dict]] = None


class ReceivableResponse(ReceivableBase):
    """应收单响应schema"""
    id: int = Field(..., description="应收单ID")
    tenant_id: int = Field(..., description="租户ID")
    invoiced_amount: Decimal = Field(Decimal("0"), description="已开票金额（列表聚合，含红字为负的净值）")
    remaining_invoice_amount: Decimal = Field(Decimal("0"), ge=0, description="未开票金额（列表聚合）")
    invoice_status: str = Field("未开票", max_length=20, description="开票状态（列表聚合）")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    created_by_name: Optional[str] = Field(None, description="创建人姓名")
    updated_by_name: Optional[str] = Field(None, description="更新人姓名")
    capabilities: Optional[dict] = Field(None, description="下推能力（如 push_receipt）")

    class Config:
        from_attributes = True


class ReceivableListResponse(BaseSchema):
    """应收单列表响应schema"""
    items: List[ReceivableResponse] = Field(..., description="应收单列表")
    total: int = Field(..., description="总数量")
    skip: int = Field(..., description="跳过数量")
    limit: int = Field(..., description="限制数量")


# === 付款记录和收款记录 ===

class PaymentRecordBase(BaseSchema):
    """付款记录基础schema"""
    payable_id: int = Field(..., description="应付单ID")
    payment_amount: Decimal = Field(..., gt=0, description="付款金额")
    payment_date: date = Field(..., description="付款日期")
    payment_method: str = Field(..., max_length=50, description="付款方式")
    reference_number: Optional[str] = Field(None, max_length=100, description="参考号")
    notes: Optional[str] = Field(None, description="备注")


class PaymentRecordCreate(PaymentRecordBase):
    """付款记录创建schema"""
    pass


class ReceiptRecordBase(BaseSchema):
    """收款记录基础schema"""
    receivable_id: int = Field(..., description="应收单ID")
    receipt_amount: Decimal = Field(..., gt=0, description="收款金额")
    receipt_date: date = Field(..., description="收款日期")
    receipt_method: str = Field(..., max_length=50, description="收款方式")
    reference_number: Optional[str] = Field(None, max_length=100, description="参考号")
    notes: Optional[str] = Field(None, description="备注")


class ReceiptRecordCreate(ReceiptRecordBase):
    """收款记录创建schema"""
    pass


# === 付款单（独立凭证）===

class FinanceVoucherLinkRef(BaseSchema):
    """关联收/付款凭证简要引用"""
    id: int
    code: str


class PartnerStatementBriefRef(BaseSchema):
    """往来对账单简要引用"""
    id: int
    statement_code: str
    statement_period: str
    status: str


class LinkedSourceDocumentRef(BaseSchema):
    """收/付款单加载来源单据引用（应付单 / 应收单 / 付款申请）"""
    source_type: str
    id: int
    code: str


class ReceiptPullLineCreate(BaseSchema):
    """收款单加载明细行（创建/更新）"""

    source_type: str = Field(..., max_length=50, description="receivable|sales_order")
    source_id: int = Field(..., gt=0, description="来源单据ID")
    source_code: Optional[str] = Field(None, max_length=50, description="来源单号")
    amount: Decimal = Field(..., gt=0, description="本次收款金额")


class ReceiptPullLineResponse(BaseSchema):
    """收款单加载明细行（读）"""

    line_no: int
    source_type: str
    source_id: int
    source_code: Optional[str] = None
    amount: Decimal
    max_amount: Optional[Decimal] = Field(None, description="可收上限（草稿读侧 enrich）")


class PaymentPullLineCreate(BaseSchema):
    """付款单加载明细行（创建/更新）"""

    source_type: str = Field(..., max_length=50, description="payable|payment_application")
    source_id: int = Field(..., gt=0, description="来源单据ID")
    source_code: Optional[str] = Field(None, max_length=50, description="来源单号")
    amount: Decimal = Field(..., gt=0, description="本次付款金额")


class PaymentPullLineResponse(BaseSchema):
    """付款单加载明细行（读）"""

    line_no: int
    source_type: str
    source_id: int
    source_code: Optional[str] = None
    amount: Decimal
    max_amount: Optional[Decimal] = Field(None, description="可付上限（草稿读侧 enrich）")


class PaymentOffsetPrepaymentLineCreate(BaseSchema):
    """预付抵扣：预付款付款单扣减行（创建/更新）"""

    prepayment_payment_id: int = Field(..., gt=0, description="预付款付款单ID")
    source_code: Optional[str] = Field(None, max_length=50, description="预付款单号")
    amount: Decimal = Field(..., gt=0, description="本次抵扣金额")


class PaymentOffsetPrepaymentLineResponse(BaseSchema):
    """预付抵扣：预付款付款单扣减行（读）"""

    line_no: int
    prepayment_payment_id: int
    source_code: Optional[str] = None
    amount: Decimal
    purchase_order_id: Optional[int] = Field(None, description="关联采购订单ID")
    purchase_order_code: Optional[str] = Field(None, description="关联采购订单号")
    unsettled_amount: Optional[Decimal] = Field(None, description="预付款单未核销余额（草稿 enrich）")


class PaymentVoucherBase(BaseSchema):
    """付款单基础schema"""
    supplier_id: int = Field(..., description="供应商ID")
    supplier_name: str = Field(..., max_length=200, description="供应商名称")
    total_amount: Decimal = Field(..., gt=0, description="付款总额")
    payment_date: date = Field(..., description="付款日期")
    payment_method: str = Field(..., max_length=50, description="付款方式")
    bank_account: Optional[str] = Field(None, max_length=100, description="出款账号")
    bank_account_id: Optional[int] = Field(None, description="银行账户ID")
    counterparty_account_name: Optional[str] = Field(None, max_length=200, description="对方收款户名")
    counterparty_bank_name: Optional[str] = Field(None, max_length=200, description="对方收款开户行")
    counterparty_bank_account: Optional[str] = Field(None, max_length=64, description="对方收款账号")
    advance_payee_id: Optional[int] = Field(None, description="员工垫付领款人ID")
    advance_payee_name: Optional[str] = Field(None, max_length=100, description="员工垫付领款人姓名")
    settlement_type: str = Field("normal", max_length=20, description="结算类型 normal/prepayment/refund")
    notes: Optional[str] = Field(None, description="备注")
    require_payment_voucher: bool = Field(
        False, description="是否必须上传付款凭证（来自付款申请要求）"
    )
    attachments: Optional[List[dict]] = Field(None, description="附件列表")


class PaymentVoucherCreate(PaymentVoucherBase):
    """付款单创建schema"""

    source_type: Optional[str] = Field(None, description="加载源单类型 payable|payment（与 pull_lines 二选一）")
    source_id: Optional[int] = Field(None, description="加载源单ID（单源兼容，与 pull_lines 二选一）")
    source_ids: Optional[List[int]] = Field(None, description="加载源付款单ID列表（多源一起退款）")
    pull_lines: Optional[List[PaymentPullLineCreate]] = Field(
        None, description="加载明细行（与 source_type/source_id 二选一）"
    )
    offset_prepayment_lines: Optional[List[PaymentOffsetPrepaymentLineCreate]] = Field(
        None, description="预付抵扣：指定预付款付款单及扣减金额"
    )


class PaymentVoucherUpdate(BaseSchema):
    """付款单更新schema"""
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = Field(None, max_length=200)
    total_amount: Optional[Decimal] = Field(None, gt=0)
    payment_date: Optional[date] = None
    payment_method: Optional[str] = Field(None, max_length=50)
    bank_account: Optional[str] = Field(None, max_length=100)
    bank_account_id: Optional[int] = None
    counterparty_account_name: Optional[str] = Field(None, max_length=200)
    counterparty_bank_name: Optional[str] = Field(None, max_length=200)
    counterparty_bank_account: Optional[str] = Field(None, max_length=64)
    advance_payee_id: Optional[int] = None
    advance_payee_name: Optional[str] = Field(None, max_length=100)
    settlement_type: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = None
    attachments: Optional[List[dict]] = Field(None, description="附件列表")
    pull_lines: Optional[List[PaymentPullLineCreate]] = Field(
        None, description="替换加载明细（仅草稿）"
    )
    offset_prepayment_lines: Optional[List[PaymentOffsetPrepaymentLineCreate]] = Field(
        None, description="替换预付抵扣预付款明细（仅草稿）"
    )


class PaymentVoucherResponse(PaymentVoucherBase):
    """付款单响应schema"""
    # 读侧允许 0：align_draft_payments_to_payable_remaining 会把超出应付剩余的草稿压到 0
    total_amount: Decimal = Field(..., ge=0, description="付款总额")
    id: int
    tenant_id: int
    payment_code: str
    settled_amount: Decimal = Decimal("0")
    unsettled_amount: Decimal = Decimal("0")
    refunded_amount: Decimal = Decimal("0")
    refund_execution_status: str = "未退款"
    status: str = "Draft"
    review_status: Optional[str] = "草稿"
    created_at: datetime
    updated_at: datetime
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None
    source_voucher_id: Optional[int] = Field(None, description="退款源付款单ID（首张）")
    source_voucher_code: Optional[str] = Field(None, description="退款源付款单号（多源时拼接）")
    source_vouchers: Optional[List["FinanceVoucherLinkRef"]] = Field(
        None, description="退款关联的全部源付款单"
    )
    linked_refund_vouchers: Optional[List["FinanceVoucherLinkRef"]] = None
    linked_partner_statements: Optional[List["PartnerStatementBriefRef"]] = None
    linked_source_documents: Optional[List["LinkedSourceDocumentRef"]] = Field(
        None, description="加载来源单据（应付单 / 付款申请）"
    )
    pull_lines: Optional[List[PaymentPullLineResponse]] = None
    offset_prepayment_lines: Optional[List[PaymentOffsetPrepaymentLineResponse]] = None
    capabilities: Optional[Dict[str, Any]] = None
    linked_payable_total_amount: Optional[Decimal] = Field(
        None, description="列表 enrichment：关联应付单应付总额合计"
    )
    linked_payable_remaining_amount: Optional[Decimal] = Field(
        None, description="列表 enrichment：关联应付单剩余金额合计"
    )

    class Config:
        from_attributes = True


class PaymentVoucherListResponse(BaseSchema):
    """付款单列表响应schema"""
    items: List[PaymentVoucherResponse]
    total: int
    skip: int
    limit: int


# === 收款单（独立凭证）===

class ReceiptVoucherBase(BaseSchema):
    """收款单基础schema"""
    customer_id: int = Field(..., description="客户ID")
    customer_name: str = Field(..., max_length=200, description="客户名称")
    total_amount: Decimal = Field(..., gt=0, description="收款总额")
    receipt_date: date = Field(..., description="收款日期")
    payment_method: str = Field(..., max_length=50, description="收款方式")
    bank_account: Optional[str] = Field(None, max_length=100, description="收款账号")
    bank_account_id: Optional[int] = Field(None, description="银行账户ID")
    counterparty_account_name: Optional[str] = Field(
        None, max_length=200, description="对方付款户名"
    )
    counterparty_bank_name: Optional[str] = Field(
        None, max_length=200, description="对方付款开户行"
    )
    counterparty_bank_account: Optional[str] = Field(
        None, max_length=64, description="对方付款账号"
    )
    settlement_type: str = Field("normal", max_length=20, description="结算类型 normal/prepayment/refund")
    notes: Optional[str] = Field(None, description="备注")
    attachments: Optional[List[dict]] = Field(None, description="附件列表")


class ReceiptVoucherCreate(ReceiptVoucherBase):
    """收款单创建schema"""

    source_type: Optional[str] = Field(None, description="加载源单类型 receivable|receipt（与 pull_lines 二选一）")
    source_id: Optional[int] = Field(None, description="加载源单ID（单源兼容）")
    source_ids: Optional[List[int]] = Field(None, description="加载源收款单ID列表（多源一起退款）")
    pull_lines: Optional[List[ReceiptPullLineCreate]] = Field(
        None, description="加载明细行（与 source_type/source_id 二选一）"
    )


class ReceiptVoucherUpdate(BaseSchema):
    """收款单更新schema"""
    customer_id: Optional[int] = None
    customer_name: Optional[str] = Field(None, max_length=200)
    total_amount: Optional[Decimal] = Field(None, gt=0)
    receipt_date: Optional[date] = None
    payment_method: Optional[str] = Field(None, max_length=50)
    bank_account: Optional[str] = Field(None, max_length=100)
    bank_account_id: Optional[int] = None
    counterparty_account_name: Optional[str] = Field(None, max_length=200)
    counterparty_bank_name: Optional[str] = Field(None, max_length=200)
    counterparty_bank_account: Optional[str] = Field(None, max_length=64)
    settlement_type: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = None
    attachments: Optional[List[dict]] = Field(None, description="附件列表")
    pull_lines: Optional[List[ReceiptPullLineCreate]] = Field(
        None, description="替换加载明细（仅草稿）"
    )


class ReceiptVoucherResponse(ReceiptVoucherBase):
    """收款单响应schema"""
    # 读侧允许 0：align_draft_receipts_to_receivable_remaining 会把超出应收剩余的草稿压到 0
    total_amount: Decimal = Field(..., ge=0, description="收款总额")
    id: int
    tenant_id: int
    receipt_code: str
    settled_amount: Decimal = Decimal("0")
    unsettled_amount: Decimal = Decimal("0")
    refunded_amount: Decimal = Decimal("0")
    refund_execution_status: str = "未退款"
    status: str = "Draft"
    review_status: Optional[str] = "草稿"
    created_at: datetime
    updated_at: datetime
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None
    source_voucher_id: Optional[int] = Field(None, description="退款源收款单ID（首张）")
    source_voucher_code: Optional[str] = Field(None, description="退款源收款单号（多源时拼接）")
    source_vouchers: Optional[List[FinanceVoucherLinkRef]] = Field(
        None, description="退款关联的全部源收款单"
    )
    linked_refund_vouchers: Optional[List[FinanceVoucherLinkRef]] = None
    linked_partner_statements: Optional[List[PartnerStatementBriefRef]] = None
    pull_lines: Optional[List[ReceiptPullLineResponse]] = None
    capabilities: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class ReceiptVoucherListResponse(BaseSchema):
    """收款单列表响应schema"""
    items: List[ReceiptVoucherResponse]
    total: int
    skip: int
    limit: int


# === 销售发票 ===

class SalesInvoiceBase(BaseSchema):
    """销售发票基础schema"""
    sales_order_id: Optional[int] = Field(None, description="销售订单ID")
    sales_order_code: Optional[str] = Field(None, max_length=50, description="销售订单编码")
    customer_id: int = Field(..., description="客户ID")
    customer_name: str = Field(..., max_length=200, description="客户名称")
    invoice_number: str = Field(default="", max_length=50, description="发票号码（手工录入；草稿可为空，与库字段长度一致）")
    invoice_date: date = Field(..., description="开票日期")
    invoice_type: str = Field("增值税专用发票", max_length=50, description="发票类型")
    tax_rate: Decimal = Field(..., ge=0, le=100, description="税率（%，必填）")
    invoice_amount: Decimal = Field(..., description="不含税金额（红字发票为负）")
    tax_amount: Decimal = Field(..., description="税额（红字发票为负）")
    total_amount: Decimal = Field(..., description="价税合计（红字发票为负）")
    receivable_id: Optional[int] = Field(None, description="关联应收单ID")
    receivable_code: Optional[str] = Field(None, max_length=50, description="关联应收单编码")
    attachment_path: Optional[str] = Field(None, max_length=500, description="附件路径")
    attachments: Optional[List[dict]] = Field(None, description="附件列表")
    notes: Optional[str] = Field(None, description="备注")
    partner_tax_no: Optional[str] = Field(None, max_length=50, description="购方税号")
    partner_bank_info: Optional[str] = Field(None, max_length=200, description="购方开户行及账号")
    partner_address_phone: Optional[str] = Field(None, max_length=200, description="购方地址及电话")


class SalesInvoiceCreate(SalesInvoiceBase):
    """销售发票创建schema"""

    invoice_amount: Decimal = Field(..., ge=0, description="不含税金额")
    tax_amount: Optional[Decimal] = Field(
        None, ge=0, description="税额（服务端按未税金额×税率计算，入参可忽略）"
    )
    total_amount: Optional[Decimal] = Field(
        None, ge=0, description="价税合计（含税录入时须传入，服务端据此反算未税/税额）"
    )
    source_type: Optional[str] = Field(None, description="加载源单类型 sales_order|sales_delivery|receivable")
    source_id: Optional[int] = Field(None, description="加载源单ID")
    concurrent_settlement: Optional[ConcurrentSettlementCreate] = Field(
        None, description="从应收开票时可选：同时生成收款单"
    )
    partner_statement_ids: Optional[List[int]] = Field(
        None,
        description="从往来对账单（按发票立账）加载出库开票时须传入对账单ID",
    )


class SalesInvoiceUpdate(BaseSchema):
    """销售发票更新schema；已审核仅允许补全发票号码与附件"""
    invoice_number: Optional[str] = Field(None, max_length=100)
    invoice_date: Optional[date] = None
    invoice_type: Optional[str] = Field(None, max_length=50)
    tax_rate: Optional[Decimal] = None
    invoice_amount: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None
    notes: Optional[str] = None
    attachments: Optional[List[dict]] = Field(None, description="附件列表")
    partner_tax_no: Optional[str] = Field(None, max_length=50)
    partner_bank_info: Optional[str] = Field(None, max_length=200)
    partner_address_phone: Optional[str] = Field(None, max_length=200)


class SalesInvoiceLineResponse(BaseSchema):
    """销售发票明细行"""

    id: int
    item_name: str
    spec_model: Optional[str] = None
    unit: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    amount: Optional[Decimal] = None
    tax_rate: Decimal
    tax_amount: Optional[Decimal] = None


class SalesInvoiceVoidRequest(BaseSchema):
    """作废请求（当月未抵扣、开票有误等实务场景由企业自行合规）"""

    reason: str = Field(..., min_length=1, max_length=2000, description="作废原因")


class SalesInvoiceRedLetterRequest(BaseSchema):
    """开具红字发票申请（税务红字信息表等线下流程由企业完成，系统生成负数金额蓝字对应的红票草稿）"""

    reason: str = Field(..., min_length=1, max_length=2000, description="红冲原因")


class SalesInvoiceResponse(SalesInvoiceBase):
    """销售发票响应schema"""
    invoice_amount: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None
    customer_name: Optional[str] = Field(None, max_length=200, description="客户名称")
    id: int
    tenant_id: int
    invoice_code: str
    original_invoice_id: Optional[int] = None
    red_flush_invoice_id: Optional[int] = None
    tax_period: Optional[str] = None
    invoice_color: Optional[str] = None
    void_reason: Optional[str] = None
    voided_at: Optional[datetime] = None
    status: str = "未审核"
    reviewer_id: Optional[int] = None
    reviewer_name: Optional[str] = None
    review_time: Optional[datetime] = None
    review_status: str = "草稿"
    review_remarks: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    updated_by: Optional[int] = None
    updated_by_name: Optional[str] = None

    class Config:
        from_attributes = True


class SalesInvoiceListResponse(BaseSchema):
    """销售发票列表响应schema"""
    items: List[SalesInvoiceResponse]
    total: int
    skip: int
    limit: int


class SalesInvoiceDetailResponse(SalesInvoiceResponse):
    """销售发票详情（含明细行）"""

    items: List[SalesInvoiceLineResponse] = Field(default_factory=list)


# === 往来对账单 ===

class PartnerStatementLineResponse(BaseSchema):
    date: str
    doc_type: str
    doc_code: str
    summary: Optional[str] = None
    debit: float = 0
    credit: float = 0
    balance: float = 0
    doc_id: Optional[int] = None
    doc_amount: Optional[float] = Field(None, description="单据金额")
    prior_stated_amount: Optional[float] = Field(None, description="已对金额（其它对账单累计）")
    remaining_amount: Optional[float] = Field(None, description="未对金额")
    statement_amount: Optional[float] = Field(None, description="本次对账金额")
    tree_level: Optional[int] = Field(
        0, description="层级：0=应收/应付等主单据，1=其下核销的收/付款单"
    )
    parent_doc_id: Optional[int] = Field(None, description="父级应收/应付单 ID")
    parent_doc_code: Optional[str] = Field(None, description="父级应收/应付单号")
    inbound_detail_doc_type: Optional[str] = Field(
        None, description="可展开入库明细类型：purchase_receipt / outsource_material_receipt"
    )
    inbound_detail_doc_id: Optional[int] = Field(None, description="可展开入库明细单据 ID")
    invoice_date: Optional[str] = Field(
        None, description="关联发票开票日期（应付→采购收票，应收→销项发票）"
    )


class PartnerStatementLineAmountInput(BaseSchema):
    doc_type: str
    doc_id: int
    statement_amount: float = Field(..., gt=0, description="本次对账金额")


class PartnerStatementUpdateLinesRequest(BaseSchema):
    lines: List[PartnerStatementLineAmountInput] = Field(..., min_length=1)


class PartnerStatementUpdateHeaderRequest(BaseSchema):
    ledger_posting_mode: Optional[str] = Field(
        None, description="立账方式 immediate 或 by_invoice"
    )


class PartnerStatementRefreshPreviewRequest(BaseSchema):
    amount_basis: str = Field(..., description="tax_inclusive 或 tax_exclusive")


class PartnerStatementRefreshPreviewResponse(BaseSchema):
    warnings: List[str] = Field(default_factory=list)
    statement: "PartnerStatementResponse"


class PartnerStatementLineDetailItemResponse(BaseSchema):
    material_code: str
    material_name: str
    material_spec: Optional[str] = None
    unit: str
    quantity: float
    unit_price: float
    amount: float
    inspection_quantity: Optional[float] = Field(None, description="质检数量")
    qualified_quantity: Optional[float] = None
    unqualified_quantity: Optional[float] = None
    quality_status: Optional[str] = None
    inspection_date: Optional[str] = Field(None, description="送检/检验日期")
    inspection_passed: Optional[bool] = None
    defect_reason: Optional[str] = None
    process_waste_qty: Optional[float] = Field(None, description="工废数量")
    material_waste_qty: Optional[float] = Field(None, description="料废数量")


class PartnerStatementLineDetailResponse(BaseSchema):
    doc_type: str
    doc_id: int
    doc_code: str
    partner_name: Optional[str] = None
    items: List[PartnerStatementLineDetailItemResponse] = Field(default_factory=list)


class PartnerStatementSummaryResponse(BaseSchema):
    opening_balance: float
    debit_total: float
    credit_total: float
    closing_balance: float


class PartnerStatementPreviewResponse(BaseSchema):
    partner_id: int
    partner_name: str
    partner_type: str
    start_date: str
    end_date: str
    company_name: str
    balance_label: str
    summary: PartnerStatementSummaryResponse
    lines: List[PartnerStatementLineResponse]
    partner_snapshot: dict = Field(default_factory=dict)
    excluded_from_period: int = Field(
        0, description="本期因已纳入其它对账单而排除的明细行数"
    )
    existing_period_statement_id: Optional[int] = Field(
        None, description="同一往来同一 YYYY-MM 已存在的未删除对账单"
    )
    existing_period_statement_code: Optional[str] = None
    existing_period: Optional[str] = None
    partner_uses_statement_ledger: bool = Field(
        False,
        description="是否展示立账方式（客商按月结或明细含月结业务源单）",
    )


class PartnerStatementCreate(BaseSchema):
    partner_id: int
    partner_type: str = Field(..., description="Customer、Supplier 或 Outsource")
    statement_period: str = Field(..., description="YYYY-MM")
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = None
    attachments: Optional[List[dict]] = Field(None, description="附件列表")
    line_amounts: Optional[List[PartnerStatementLineAmountInput]] = Field(
        None, description="勾选纳入的单据及本次对账金额；有值时仅生成列表中的单据"
    )
    ledger_posting_mode: Optional[str] = Field(
        "immediate", description="立账方式 immediate 或 by_invoice（按对账单立账客商）"
    )
    amount_basis: Optional[str] = Field(
        "tax_inclusive", description="对账金额口径 tax_inclusive 或 tax_exclusive"
    )


class PartnerStatementMarkSentRequest(BaseSchema):
    channel: str = Field(..., description="export/print/wechat_manual/email_manual/other")
    notes: Optional[str] = None


class PartnerStatementDisputeRequest(BaseSchema):
    reason: str = Field(..., min_length=1)


class PartnerStatementResponse(BaseSchema):
    id: int
    statement_code: str
    partner_id: int
    partner_name: str
    partner_type: str
    statement_period: str
    start_date: date
    end_date: date
    opening_balance: Decimal
    debit_total: Decimal
    credit_total: Decimal
    closing_balance: Decimal
    status: str
    review_status: str = "草稿"
    reviewer_id: Optional[int] = None
    reviewer_name: Optional[str] = None
    review_time: Optional[datetime] = None
    review_remarks: Optional[str] = None
    company_name: Optional[str] = None
    transaction_details: Optional[dict] = None
    confirmed_at: Optional[datetime] = None
    confirmed_by: Optional[int] = None
    sent_at: Optional[datetime] = None
    sent_by: Optional[int] = None
    sent_channel: Optional[str] = None
    dispute_reason: Optional[str] = None
    disputed_at: Optional[datetime] = None
    notes: Optional[str] = None
    attachments: Optional[List[dict]] = Field(None, description="附件列表")
    ledger_posting_mode: Optional[str] = "immediate"
    ledger_posted_at: Optional[datetime] = None
    ledger_posted_by: Optional[int] = None
    partner_uses_statement_ledger: Optional[bool] = Field(
        None, description="往来是否启用按月结对账单立账（仅 API 组装）"
    )
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    updated_by: Optional[int] = None
    updated_by_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PartnerStatementListResponse(BaseSchema):
    items: List[PartnerStatementResponse]
    total: int
    skip: int
    limit: int


# === 合并收款 / 合并付款 / 合并开票 ===


class MergeFinanceAllocationLine(BaseSchema):
    """合并分摊行：源单 + 本次金额"""

    source_id: int = Field(..., description="源单ID（应收或应付）")
    amount: Decimal = Field(..., gt=0, description="本次分摊金额（收款/付款为余额口径；开票为价税合计）")


class MergeReceiptCreate(BaseSchema):
    """多应收合并创建一张收款单"""

    allocations: List[MergeFinanceAllocationLine] = Field(..., min_length=1)
    receipt_date: date = Field(..., description="收款日期")
    payment_method: str = Field(..., max_length=50, description="收款方式")
    bank_account: Optional[str] = Field(None, max_length=100, description="收款账号")
    bank_account_id: Optional[int] = Field(None, description="银行账户ID")
    settlement_type: str = Field("normal", max_length=20, description="结算类型 normal/prepayment/refund")
    notes: Optional[str] = Field(None, description="备注")
    attachments: Optional[List[dict]] = Field(None, description="附件列表")


class MergePaymentCreate(BaseSchema):
    """多应付合并创建一张付款单"""

    allocations: List[MergeFinanceAllocationLine] = Field(..., min_length=1)
    payment_date: date = Field(..., description="付款日期")
    payment_method: str = Field(..., max_length=50, description="付款方式")
    bank_account: Optional[str] = Field(None, max_length=100, description="付款账号")
    bank_account_id: Optional[int] = Field(None, description="银行账户ID")
    settlement_type: str = Field("normal", max_length=20, description="结算类型 normal/prepayment/refund")
    notes: Optional[str] = Field(None, description="备注")
    attachments: Optional[List[dict]] = Field(None, description="附件列表")


class MergeSalesInvoiceCreate(BaseSchema):
    """多应收合并创建一张销售发票"""

    allocations: List[MergeFinanceAllocationLine] = Field(..., min_length=1)
    invoice_date: date = Field(..., description="开票日期")
    invoice_number: str = Field(default="", max_length=50, description="发票号码")
    invoice_type: str = Field("增值税专用发票", max_length=50, description="发票类型")
    tax_rate: Decimal = Field(..., ge=0, le=100, description="税率（%，必填）")
    notes: Optional[str] = Field(None, description="备注")


class MergePurchaseInvoiceCreate(BaseSchema):
    """多应付合并创建一张采购发票"""

    allocations: List[MergeFinanceAllocationLine] = Field(..., min_length=1)
    invoice_date: date = Field(..., description="发票日期")
    invoice_number: str = Field(..., max_length=100, description="发票号码")
    invoice_type: str = Field("增值税专用发票", max_length=20, description="发票类型")
    tax_rate: Decimal = Field(..., ge=0, le=100, description="税率（%，必填）")
    notes: Optional[str] = Field(None, description="备注")


class MergeFinanceVoucherResponse(BaseSchema):
    """合并创建凭证响应"""

    voucher_type: str
    voucher_id: int
    voucher_code: str
    total_amount: float
    partner_id: int
    partner_name: str
    allocations: List[dict]


# === 往来核销记录 ===

class SettlementRecordResponse(BaseSchema):
    """核销记录响应"""

    id: int
    tenant_id: int
    settlement_code: str
    partner_id: int
    partner_name: str
    debit_doc_type: str
    debit_doc_id: int
    debit_doc_code: str
    credit_doc_type: str
    credit_doc_id: int
    credit_doc_code: str
    amount: Decimal
    currency: str
    settlement_date: date
    operator_id: Optional[int] = None
    operator_name: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SettlementRecordListResponse(BaseSchema):
    """核销记录列表"""

    items: List[SettlementRecordResponse]
    total: int
    skip: int
    limit: int


# === 其他收支类别 ===

class MiscCategoryCreate(BaseSchema):
    """其他收支类别创建schema（快捷创建仅传 name）"""
    code: Optional[str] = Field(None, max_length=50, description="类别编码（留空自动分配）")
    name: str = Field(..., min_length=1, max_length=200, description="类别名称")
    is_active: bool = Field(True, description="是否启用")
    default_gl_account_code: Optional[str] = Field(None, max_length=20, description="默认会计科目编码")
    sort_order: int = Field(0, description="排序")


class MiscCategoryUpdate(BaseSchema):
    """其他收支类别更新schema"""
    code: Optional[str] = Field(None, max_length=50)
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    is_active: Optional[bool] = None
    default_gl_account_code: Optional[str] = Field(None, max_length=20)
    sort_order: Optional[int] = None


class MiscCategoryResponse(BaseSchema):
    """其他收支类别响应schema"""
    id: int
    code: str
    name: str
    is_active: bool = True
    default_gl_account_code: Optional[str] = None
    sort_order: int = 0

    class Config:
        from_attributes = True


# === 其他费用收入/支出 ===

class OtherVoucherLineIn(BaseSchema):
    """其他收支明细行入参"""
    category_code: str = Field(..., max_length=50, description="收支类别编码")
    category_name: Optional[str] = Field(None, max_length=200, description="收支类别名称（留空按编码带出）")
    amount: Decimal = Field(..., gt=0, description="金额")
    description: Optional[str] = Field(None, description="说明")
    gl_account_code: Optional[str] = Field(None, max_length=20, description="会计科目编码")
    # 其他费用支出 + 员工垫付时由服务端校验必填；收入侧忽略
    payee_id: Optional[int] = None
    payee_name: Optional[str] = Field(None, max_length=100)


class RelatedPurchaseReceiptRef(BaseSchema):
    id: int
    code: str = Field(..., max_length=50)


class OtherVoucherLineOut(OtherVoucherLineIn):
    """其他收支明细行出参"""
    id: int
    line_no: int

    class Config:
        from_attributes = True


class OtherVoucherCreate(BaseSchema):
    """其他费用收入/支出创建schema"""
    business_date: date = Field(..., description="业务日期")
    counterparty_kind: str = Field("none", max_length=20, description="往来对象类型 none/customer/supplier/employee/other")
    counterparty_id: Optional[int] = Field(None, description="往来对象ID")
    counterparty_name: Optional[str] = Field(None, max_length=200, description="往来对象名称")
    payment_method: str = Field(..., max_length=50, description="收/付款方式")
    bank_account_id: Optional[int] = Field(None, description="收/付款账户ID")
    bank_account: Optional[str] = Field(None, max_length=100, description="收/付款账户")
    department_id: Optional[int] = Field(None, description="部门ID")
    department_name: Optional[str] = Field(None, max_length=200, description="部门名称")
    project_id: Optional[int] = Field(None, description="项目ID")
    project_name: Optional[str] = Field(None, max_length=200, description="项目名称")
    notes: Optional[str] = Field(None, description="备注")
    attachments: Optional[List[dict]] = Field(None, description="附件列表")
    related_purchase_receipts: Optional[List[RelatedPurchaseReceiptRef]] = None
    revenue_recognition: Optional[str] = Field(
        None, max_length=32, description="立账策略（应收确认时点，仅其他费用收入）"
    )
    payable_recognition: Optional[str] = Field(
        None, max_length=32, description="立账策略（应付确认时点，仅其他费用支出）"
    )
    lines: List[OtherVoucherLineIn] = Field(..., min_length=1, description="明细行")


class OtherVoucherUpdate(BaseSchema):
    """其他费用收入/支出更新schema"""
    business_date: Optional[date] = None
    counterparty_kind: Optional[str] = Field(None, max_length=20)
    counterparty_id: Optional[int] = None
    counterparty_name: Optional[str] = Field(None, max_length=200)
    payment_method: Optional[str] = Field(None, max_length=50)
    bank_account_id: Optional[int] = None
    bank_account: Optional[str] = Field(None, max_length=100)
    department_id: Optional[int] = None
    department_name: Optional[str] = Field(None, max_length=200)
    project_id: Optional[int] = None
    project_name: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = None
    attachments: Optional[List[dict]] = None
    related_purchase_receipts: Optional[List[RelatedPurchaseReceiptRef]] = None
    revenue_recognition: Optional[str] = Field(None, max_length=32)
    payable_recognition: Optional[str] = Field(None, max_length=32)
    lines: Optional[List[OtherVoucherLineIn]] = Field(None, min_length=1)


class OtherVoucherReviewAction(BaseSchema):
    """审核动作入参"""
    approved: Optional[bool] = Field(None, description="是否通过（approve/reject 端点兼容字段）")
    review_remarks: Optional[str] = Field(None, description="审核备注")


class OtherVoucherSubmitAction(BaseSchema):
    """提交审核入参（发起人自选审批人，与统一审核入口语义一致）"""
    selected_approver_user_ids: Optional[List[int]] = Field(
        None, description="提交时选定的审批人用户ID列表"
    )
    selected_approver_by_node: Optional[Dict[str, List[int]]] = Field(
        None, description="按审批节点选定的审批人用户ID映射"
    )


class OtherVoucherResponse(BaseSchema):
    """其他费用收入/支出响应schema（income_code/expense_code 二选一返回）"""
    id: int
    income_code: Optional[str] = None
    expense_code: Optional[str] = None
    business_date: date
    counterparty_kind: str = "none"
    counterparty_id: Optional[int] = None
    counterparty_name: Optional[str] = None
    total_amount: Decimal = Decimal("0")
    payment_method: Optional[str] = None
    bank_account_id: Optional[int] = None
    bank_account: Optional[str] = None
    status: str = "Draft"
    reviewer_id: Optional[int] = None
    reviewer_name: Optional[str] = None
    review_time: Optional[datetime] = None
    review_remarks: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    notes: Optional[str] = None
    attachments: Optional[List[dict]] = None
    related_purchase_receipts: Optional[List[RelatedPurchaseReceiptRef]] = None
    revenue_recognition: Optional[str] = None
    payable_recognition: Optional[str] = None
    lines: List[OtherVoucherLineOut] = []
    capabilities: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None

    class Config:
        from_attributes = True


class OtherVoucherListResponse(BaseSchema):
    """其他费用收入/支出列表响应schema"""
    items: List[OtherVoucherResponse]
    total: int
    skip: int
    limit: int
