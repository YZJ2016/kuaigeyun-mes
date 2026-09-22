"""委外结算 Schema"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import Field, model_validator

from core.schemas.base import BaseSchema


class OutsourceSettlementItemCreate(BaseSchema):
    line_type: str = Field(default="processing", description="行类型 processing/material_deduction")
    outsource_material_receipt_id: Optional[int] = Field(None, description="委外收货单ID")
    outsource_work_order_id: Optional[int] = Field(None, description="委外工单ID（扣款行）")
    settlement_quantity: Decimal = Field(..., description="结算数量（扣款行为超耗量，须>0）")
    unit_price: Decimal = Field(..., ge=0, description="结算单价")
    deduction_basis_qty: Optional[Decimal] = Field(None, description="超耗扣款标准/实际快照")
    deduction_basis_amount: Optional[Decimal] = Field(None, description="超耗扣款金额快照")
    notes: Optional[str] = Field(None, description="备注")

    @model_validator(mode="after")
    def validate_line(self):
        lt = (self.line_type or "processing").strip()
        if lt == "processing":
            if self.outsource_material_receipt_id is None:
                raise ValueError("加工费行须指定委外收货单")
            if self.settlement_quantity <= 0:
                raise ValueError("加工费结算数量须大于 0")
        elif lt == "material_deduction":
            if self.outsource_work_order_id is None:
                raise ValueError("材料扣款行须指定委外工单")
            if self.settlement_quantity <= 0:
                raise ValueError("扣款数量须大于 0")
            if self.deduction_basis_qty is None or self.deduction_basis_amount is None:
                raise ValueError("材料扣款行须携带超耗计算快照")
        else:
            raise ValueError(f"不支持的行类型: {lt}")
        return self


class OutsourceSettlementItemResponse(BaseSchema):
    id: int
    line_no: int
    line_type: str
    outsource_material_receipt_id: Optional[int] = None
    receipt_code: Optional[str] = None
    outsource_work_order_id: Optional[int] = None
    outsource_work_order_code: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    unit: Optional[str] = None
    outsource_product_return_id: Optional[int] = None
    deduction_basis_qty: Optional[Decimal] = None
    deduction_basis_amount: Optional[Decimal] = None
    settlement_quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    notes: Optional[str] = None


class OutsourceSettlementCreate(BaseSchema):
    supplier_id: int = Field(..., description="供应商ID")
    business_date: Optional[date] = Field(None, description="业务日期")
    notes: Optional[str] = Field(None, description="备注")
    items: List[OutsourceSettlementItemCreate] = Field(default_factory=list, description="结算明细")


class OutsourceSettlementUpdate(BaseSchema):
    business_date: Optional[date] = Field(None, description="业务日期")
    notes: Optional[str] = Field(None, description="备注")
    items: Optional[List[OutsourceSettlementItemCreate]] = Field(None, description="结算明细")


class OutsourceSettlementAudit(BaseSchema):
    review_remarks: Optional[str] = Field(None, description="审核备注")


class OutsourceSettlementReject(BaseSchema):
    review_remarks: str = Field(..., min_length=1, description="驳回原因")


class OutsourceSettlementPayableLink(BaseSchema):
    payable_id: int
    payable_code: Optional[str] = None
    source_type: str
    total_amount: Decimal
    invoice_status: Optional[str] = None


class OutsourceSettlementResponse(BaseSchema):
    id: int
    settlement_code: str
    supplier_id: int
    supplier_code: str
    supplier_name: str
    business_date: Optional[date] = None
    total_amount: Decimal
    status: str
    settlement_kind: str = "normal"
    auto_generated: bool = False
    source_doc_type: Optional[str] = None
    source_doc_id: Optional[int] = None
    reviewer_id: Optional[int] = None
    reviewer_name: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_remarks: Optional[str] = None
    payable_id: Optional[int] = None
    payable_code: Optional[str] = None
    invoice_status: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None
    items: List[OutsourceSettlementItemResponse] = Field(default_factory=list)
    payables: List[OutsourceSettlementPayableLink] = Field(default_factory=list)


class OutsourceSettlementListEnvelope(BaseSchema):
    items: List[OutsourceSettlementResponse]
    total: int


class OutsourceSettleableReceiptResponse(BaseSchema):
    id: int
    code: str
    outsource_work_order_id: int
    outsource_work_order_code: str
    supplier_id: int
    supplier_code: str
    supplier_name: str
    product_code: str
    product_name: str
    unit: str
    qualified_quantity: Decimal
    returned_quantity: Decimal
    settled_quantity: Decimal
    pending_settlement_quantity: Decimal
    settleable_quantity: Decimal
    unit_price: Decimal
    received_at: Optional[str] = None


class OutsourceMaterialDeductionPreviewResponse(BaseSchema):
    outsource_work_order_id: int
    outsource_work_order_code: str
    material_id: int
    material_code: str
    material_name: str
    standard_qty: Decimal
    actual_qty: Decimal
    overrun_qty: Decimal
    unit_price: Decimal
    deduction_amount: Decimal


class OutsourceSettlementReconciliationPreviewRequest(BaseSchema):
    supplier_id: int
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    outsource_work_order_ids: Optional[List[int]] = None


class OutsourceSettlementReconciliationPreviewResponse(BaseSchema):
    supplier_id: int
    supplier_name: str
    processing_total: Decimal
    deduction_total: Decimal
    settled_total: Decimal
    unsettled_total: Decimal
    provisional_payable_total: Decimal
    settlement_payable_total: Decimal


class OutsourceSettlementInvoicePreviewItem(BaseSchema):
    payable_id: int
    payable_code: Optional[str] = None
    source_type: str
    amount: Decimal
    description: str


class OutsourceSettlementInvoicePreviewResponse(BaseSchema):
    settlement_id: int
    supplier_id: int
    supplier_name: str
    items: List[OutsourceSettlementInvoicePreviewItem]
    total_amount: Decimal


class OutsourceSettlementDocumentChainStep(BaseSchema):
    step: str
    doc_type: str
    doc_id: Optional[int] = None
    doc_code: Optional[str] = None
    status: Optional[str] = None


class OutsourceSettlementDocumentChainResponse(BaseSchema):
    settlement_id: int
    steps: List[OutsourceSettlementDocumentChainStep]
