"""其他费用支出申请 Schema"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field, field_validator

from core.schemas.base import BaseSchema
from apps.kuaicaiwu.schemas.other_voucher import (
    OtherVoucherLineInput,
    OtherVoucherLineResponse,
    RelatedPurchaseReceiptRef,
)


class OtherExpenseApplicationCreate(BaseSchema):
    application_code: Optional[str] = None
    business_date: date
    counterparty_kind: str = "none"
    counterparty_id: Optional[int] = None
    counterparty_name: Optional[str] = None
    counterparty_account_name: Optional[str] = None
    counterparty_bank_name: Optional[str] = None
    counterparty_bank_account: Optional[str] = None
    payment_method: str
    bank_account_id: Optional[int] = None
    bank_account: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    notes: Optional[str] = None
    attachments: Optional[List[Any]] = None
    payable_recognition: Optional[str] = Field(
        None,
        max_length=32,
        description="立账策略（应付确认时点）",
    )
    related_purchase_receipts: Optional[List[RelatedPurchaseReceiptRef]] = None
    lines: List[OtherVoucherLineInput]

    @field_validator("lines")
    @classmethod
    def _lines_non_empty(cls, v: List[OtherVoucherLineInput]) -> List[OtherVoucherLineInput]:
        if not v:
            raise ValueError("至少一行明细")
        return v


class OtherExpenseApplicationUpdate(BaseSchema):
    business_date: Optional[date] = None
    counterparty_kind: Optional[str] = None
    counterparty_id: Optional[int] = None
    counterparty_name: Optional[str] = None
    counterparty_account_name: Optional[str] = None
    counterparty_bank_name: Optional[str] = None
    counterparty_bank_account: Optional[str] = None
    payment_method: Optional[str] = None
    bank_account_id: Optional[int] = None
    bank_account: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    notes: Optional[str] = None
    attachments: Optional[List[Any]] = None
    payable_recognition: Optional[str] = Field(
        None,
        max_length=32,
        description="立账策略（应付确认时点）",
    )
    related_purchase_receipts: Optional[List[RelatedPurchaseReceiptRef]] = None
    lines: Optional[List[OtherVoucherLineInput]] = None


class OtherExpenseApplicationResponse(BaseSchema):
    id: int
    application_code: str
    business_date: date
    counterparty_kind: str
    counterparty_id: Optional[int] = None
    counterparty_name: Optional[str] = None
    counterparty_account_name: Optional[str] = None
    counterparty_bank_name: Optional[str] = None
    counterparty_bank_account: Optional[str] = None
    total_amount: Decimal
    pushed_amount: Decimal
    remaining_amount: Decimal
    payment_method: str
    bank_account_id: Optional[int] = None
    bank_account: Optional[str] = None
    status: str
    review_status: str = "草稿"
    reviewer_id: Optional[int] = None
    reviewer_name: Optional[str] = None
    review_time: Optional[datetime] = None
    review_remarks: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    notes: Optional[str] = None
    attachments: Optional[List[Any]] = None
    payable_recognition: Optional[str] = Field(
        None,
        max_length=32,
        description="立账策略（应付确认时点）",
    )
    related_purchase_receipts: Optional[List[RelatedPurchaseReceiptRef]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None
    lines: List[OtherVoucherLineResponse] = Field(default_factory=list)
    capabilities: Optional[Dict[str, Any]] = None
    linked_expenses: Optional[List[Dict[str, Any]]] = None


class OtherExpenseApplicationListResponse(BaseSchema):
    items: List[OtherExpenseApplicationResponse]
    total: int


class ApproveOtherExpenseApplicationRequest(BaseSchema):
    approved: bool = True
    review_remarks: Optional[str] = Field(None, alias="reviewRemarks")

    model_config = ConfigDict(populate_by_name=True)


class PushOtherExpenseApplicationRequest(BaseSchema):
    business_date: Optional[date] = Field(None, alias="businessDate")
    line_ids: Optional[List[int]] = Field(None, alias="lineIds")
    total_amount: Optional[Decimal] = Field(None, alias="totalAmount", gt=0)
    notes: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)
