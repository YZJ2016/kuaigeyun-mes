"""
资金调拨 API
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field, field_validator

from apps.kuaicaiwu.services.fund_transfer_service import FundTransferService
from apps.kuaicaiwu.utils.calendar_date_coerce import coerce_api_calendar_date
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from core.schemas.base import BaseSchema
from infra.api.deps.deps import get_current_user
from infra.exceptions.exceptions import NotFoundError, ValidationError
from infra.models.user import User

router = APIRouter(prefix="/fund-transfers", tags=["App - Kuaizhizao Finance - Fund Transfers"])
service = FundTransferService()


def _http_exception_with_trace(
    status_code: int,
    message: str,
    route: str,
    tenant_id: Optional[int] = None,
) -> HTTPException:
    trace_id = uuid.uuid4().hex
    return HTTPException(
        status_code=status_code,
        detail={"message": message, "trace_id": trace_id},
    )


class FundTransferCreate(BaseSchema):
    transfer_date: date
    transfer_type: str = Field(..., description="internal/external_out/external_in")
    amount: Decimal = Field(..., gt=0)
    from_bank_account_id: Optional[int] = None
    to_bank_account_id: Optional[int] = None
    external_account_name: Optional[str] = None
    external_bank_name: Optional[str] = None
    external_account_number: Optional[str] = None
    currency: Optional[str] = None
    notes: Optional[str] = None
    attachments: Optional[List[dict]] = None

    @field_validator("transfer_date", mode="before")
    @classmethod
    def coerce_transfer_date(cls, value: Any) -> Any:
        return coerce_api_calendar_date(value)


class FundTransferUpdate(BaseSchema):
    transfer_date: Optional[date] = None
    transfer_type: Optional[str] = None
    amount: Optional[Decimal] = Field(None, gt=0)
    from_bank_account_id: Optional[int] = None
    to_bank_account_id: Optional[int] = None
    external_account_name: Optional[str] = None
    external_bank_name: Optional[str] = None
    external_account_number: Optional[str] = None
    currency: Optional[str] = None
    notes: Optional[str] = None
    attachments: Optional[List[dict]] = None

    @field_validator("transfer_date", mode="before")
    @classmethod
    def coerce_transfer_date(cls, value: Any) -> Any:
        return coerce_api_calendar_date(value)


class FundTransferResponse(BaseSchema):
    id: int
    tenant_id: int
    transfer_code: str
    transfer_date: date
    transfer_type: str
    from_bank_account_id: Optional[int] = None
    to_bank_account_id: Optional[int] = None
    from_account_code: Optional[str] = None
    from_account_name: Optional[str] = None
    to_account_code: Optional[str] = None
    to_account_name: Optional[str] = None
    external_account_name: Optional[str] = None
    external_bank_name: Optional[str] = None
    external_account_number: Optional[str] = None
    amount: Decimal
    currency: str
    status: str
    review_status: str = "草稿"
    notes: Optional[str] = None
    attachments: Optional[List[dict]] = None
    created_at: Optional[Any] = None
    updated_at: Optional[Any] = None
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    updated_by: Optional[int] = None
    updated_by_name: Optional[str] = None


class FundTransferListResponse(BaseSchema):
    items: List[FundTransferResponse]
    total: int
    skip: int
    limit: int


async def _serialize_one(
    tenant_id: int, transfer_id: int, *, viewer_id: Optional[int] = None
) -> FundTransferResponse:
    from apps.kuaicaiwu.models.fund_transfer import FundTransfer
    from core.services.approval.audit_record_enricher import enrich_record

    row = await FundTransfer.get_or_none(
        tenant_id=tenant_id, id=int(transfer_id), deleted_at__isnull=True
    )
    if not row:
        raise NotFoundError(f"资金调拨单不存在: {transfer_id}")
    enriched = await service.enrich_rows(tenant_id, [row])
    resp = FundTransferResponse.model_validate(enriched[0])
    return await enrich_record(tenant_id, "fund_transfer", resp, viewer_id=viewer_id)


@router.post("", response_model=FundTransferResponse, status_code=status.HTTP_201_CREATED)
async def create_fund_transfer(
    data: FundTransferCreate,
    _auth: object = Depends(require_permission_codes("kuaicaiwu:fund-transfer:create")),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        row = await service.create(
            tenant_id,
            transfer_date=data.transfer_date,
            transfer_type=data.transfer_type,
            amount=data.amount,
            from_bank_account_id=data.from_bank_account_id,
            to_bank_account_id=data.to_bank_account_id,
            external_account_name=data.external_account_name,
            external_bank_name=data.external_bank_name,
            external_account_number=data.external_account_number,
            currency=data.currency,
            notes=data.notes,
            attachments=data.attachments,
            current_user=current_user,
        )
        return await _serialize_one(tenant_id, row.id, viewer_id=current_user.id)
    except ValidationError as exc:
        raise _http_exception_with_trace(400, str(exc), "/fund-transfers", tenant_id) from exc


@router.get("", response_model=FundTransferListResponse)
async def list_fund_transfers(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=500),
    keyword: Optional[str] = Query(None),
    transfer_code: Optional[str] = Query(None),
    transfer_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    transfer_date_start: Optional[str] = Query(None),
    transfer_date_end: Optional[str] = Query(None),
    sort_field: Optional[str] = Query(None),
    sort_order: Optional[str] = Query(None),
    _auth: object = Depends(require_permission_codes("kuaicaiwu:fund-transfer:read")),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    from core.services.approval.audit_record_enricher import enrich_items

    rows, total = await service.list(
        tenant_id,
        skip=skip,
        limit=limit,
        keyword=keyword,
        transfer_code=transfer_code,
        transfer_type=transfer_type,
        status=status,
        transfer_date_start=transfer_date_start,
        transfer_date_end=transfer_date_end,
        sort_field=sort_field,
        sort_order=sort_order,
    )
    items = await service.enrich_rows(tenant_id, rows)
    responses = [FundTransferResponse.model_validate(x) for x in items]
    enriched = await enrich_items(
        tenant_id, "fund_transfer", responses, viewer_id=current_user.id
    )
    return FundTransferListResponse(
        items=enriched,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{id}", response_model=FundTransferResponse)
async def get_fund_transfer(
    id: int,
    _auth: object = Depends(require_permission_codes("kuaicaiwu:fund-transfer:read")),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _serialize_one(tenant_id, id, viewer_id=current_user.id)
    except NotFoundError as exc:
        raise _http_exception_with_trace(404, str(exc), f"/fund-transfers/{id}", tenant_id) from exc


@router.put("/{id}", response_model=FundTransferResponse)
async def update_fund_transfer(
    id: int,
    data: FundTransferUpdate,
    _auth: object = Depends(require_permission_codes("kuaicaiwu:fund-transfer:update")),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    from infra.exceptions.exceptions import BusinessLogicError

    try:
        await service.update_draft(
            tenant_id,
            id,
            data=data.model_dump(exclude_unset=True),
            current_user=current_user,
        )
        return await _serialize_one(tenant_id, id, viewer_id=current_user.id)
    except NotFoundError as exc:
        raise _http_exception_with_trace(404, str(exc), f"/fund-transfers/{id}", tenant_id) from exc
    except (ValidationError, BusinessLogicError) as exc:
        raise _http_exception_with_trace(400, str(exc), f"/fund-transfers/{id}", tenant_id) from exc


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fund_transfer(
    id: int,
    _auth: object = Depends(require_permission_codes("kuaicaiwu:fund-transfer:delete")),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    from apps.kuaicaiwu.models.fund_transfer import FundTransfer
    from apps.kuaicaiwu.services.fund_transfer_audit_service import (
        assert_fund_transfer_review_editable,
    )
    from apps.common.audit_actor import apply_update_audit
    from core.utils.timezone_utils import now_utc
    from infra.exceptions.exceptions import BusinessLogicError

    row = await FundTransfer.get_or_none(
        tenant_id=tenant_id, id=int(id), deleted_at__isnull=True
    )
    if not row:
        raise _http_exception_with_trace(404, f"资金调拨单不存在: {id}", f"/fund-transfers/{id}", tenant_id)
    if row.status == "Confirmed":
        raise _http_exception_with_trace(
            400, "已确认调拨单须先撤回确认再删除", f"/fund-transfers/{id}", tenant_id
        )
    if row.status not in ("Draft", "Cancelled"):
        raise _http_exception_with_trace(
            400, f"当前状态不可删除: {row.status}", f"/fund-transfers/{id}", tenant_id
        )
    try:
        if row.status == "Draft":
            assert_fund_transfer_review_editable(row)
    except BusinessLogicError as exc:
        raise _http_exception_with_trace(400, str(exc), f"/fund-transfers/{id}", tenant_id) from exc
    payload = {"deleted_at": now_utc()}
    apply_update_audit(payload, current_user)
    await FundTransfer.filter(id=row.id).update(**payload)


@router.post("/{id}/confirm", response_model=FundTransferResponse)
async def confirm_fund_transfer(
    id: int,
    _auth: object = Depends(require_permission_codes("kuaicaiwu:fund-transfer:audit")),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    from infra.exceptions.exceptions import BusinessLogicError

    try:
        await service.confirm(tenant_id, id, operator=current_user)
        return await _serialize_one(tenant_id, id, viewer_id=current_user.id)
    except NotFoundError as exc:
        raise _http_exception_with_trace(404, str(exc), f"/fund-transfers/{id}/confirm", tenant_id) from exc
    except (ValidationError, BusinessLogicError) as exc:
        raise _http_exception_with_trace(400, str(exc), f"/fund-transfers/{id}/confirm", tenant_id) from exc


@router.post("/{id}/unconfirm", response_model=FundTransferResponse)
async def unconfirm_fund_transfer(
    id: int,
    _auth: object = Depends(require_permission_codes("kuaicaiwu:fund-transfer:revoke")),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        await service.unconfirm(tenant_id, id, operator=current_user)
        return await _serialize_one(tenant_id, id, viewer_id=current_user.id)
    except NotFoundError as exc:
        raise _http_exception_with_trace(404, str(exc), f"/fund-transfers/{id}/unconfirm", tenant_id) from exc
    except ValidationError as exc:
        raise _http_exception_with_trace(400, str(exc), f"/fund-transfers/{id}/unconfirm", tenant_id) from exc


@router.post("/{id}/cancel", response_model=FundTransferResponse)
async def cancel_fund_transfer(
    id: int,
    _auth: object = Depends(require_permission_codes("kuaicaiwu:fund-transfer:revoke")),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        await service.cancel(tenant_id, id, operator=current_user)
        return await _serialize_one(tenant_id, id, viewer_id=current_user.id)
    except NotFoundError as exc:
        raise _http_exception_with_trace(404, str(exc), f"/fund-transfers/{id}/cancel", tenant_id) from exc
    except ValidationError as exc:
        raise _http_exception_with_trace(400, str(exc), f"/fund-transfers/{id}/cancel", tenant_id) from exc
