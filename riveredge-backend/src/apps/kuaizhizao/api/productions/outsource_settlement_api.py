"""委外结算 API"""

from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException as FastAPIHTTPException, Path, Query, status
from loguru import logger

from apps.kuaizhizao.api._kuaizhizao_route_access import require_kuaizhizao_module_access
from apps.kuaizhizao.schemas.outsource_settlement import (
    OutsourceMaterialDeductionPreviewResponse,
    OutsourceSettleableReceiptResponse,
    OutsourceSettlementAudit,
    OutsourceSettlementCreate,
    OutsourceSettlementDocumentChainResponse,
    OutsourceSettlementInvoicePreviewResponse,
    OutsourceSettlementListEnvelope,
    OutsourceSettlementReconciliationPreviewRequest,
    OutsourceSettlementReconciliationPreviewResponse,
    OutsourceSettlementReject,
    OutsourceSettlementResponse,
    OutsourceSettlementUpdate,
)
from apps.kuaizhizao.services.outsource_settlement_service import OutsourceSettlementService
from core.api.deps import get_current_tenant, get_current_user
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError, ValidationError
from infra.models.user import User

router = APIRouter(
    prefix="/outsource-settlements",
    tags=["App - Kuaige Zhizao - Outsource Settlement"],
    dependencies=[Depends(require_kuaizhizao_module_access("outsource-settlement"))],
)
_service = OutsourceSettlementService()


def _http_exception(status_code: int, message: str) -> FastAPIHTTPException:
    trace_id = uuid.uuid4().hex
    logger.warning(
        "outsource_settlement_api_error trace_id={} status_code={} message={}",
        trace_id,
        status_code,
        message,
    )
    return FastAPIHTTPException(status_code=status_code, detail={"message": message, "trace_id": trace_id})


@router.get("/deduction-preview", response_model=list[OutsourceMaterialDeductionPreviewResponse], summary="Preview material overrun deductions")
async def preview_deductions(
    supplier_id: int = Query(..., description="供应商ID"),
    work_order_ids: str = Query(..., description="委外工单ID，逗号分隔"),
    tenant_id: int = Depends(get_current_tenant),
):
    ids = [int(x.strip()) for x in work_order_ids.split(",") if x.strip()]
    return await _service.preview_deductions(tenant_id, supplier_id=supplier_id, work_order_ids=ids)


@router.post("/reconciliation-preview", response_model=OutsourceSettlementReconciliationPreviewResponse, summary="Preview supplier reconciliation")
async def reconciliation_preview(
    body: OutsourceSettlementReconciliationPreviewRequest,
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.reconciliation_preview(tenant_id, body)
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))


@router.get("/settleable-receipts", response_model=list[OutsourceSettleableReceiptResponse], summary="List settleable subcontract receipts")
async def list_settleable_receipts(
    supplier_id: int = Query(..., description="供应商ID"),
    exclude_settlement_id: Optional[int] = Query(None, description="编辑时排除当前结算单"),
    tenant_id: int = Depends(get_current_tenant),
):
    return await _service.list_settleable_receipts(
        tenant_id,
        supplier_id=supplier_id,
        exclude_settlement_id=exclude_settlement_id,
    )


@router.post("", response_model=OutsourceSettlementResponse, summary="Create outsource settlement")
async def create_settlement(
    body: OutsourceSettlementCreate,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.create(tenant_id, body, current_user)
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except BusinessLogicError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.get("", response_model=OutsourceSettlementListEnvelope, summary="List outsource settlements")
async def list_settlements(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    supplier_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    keyword: Optional[str] = Query(None),
    tenant_id: int = Depends(get_current_tenant),
):
    return await _service.list_settlements(
        tenant_id,
        skip=skip,
        limit=limit,
        supplier_id=supplier_id,
        status=status_filter,
        keyword=keyword,
    )


@router.get("/{settlement_id}/invoice-preview", response_model=OutsourceSettlementInvoicePreviewResponse, summary="Invoice preview for settlement payables")
async def invoice_preview(
    settlement_id: int = Path(..., description="结算单ID"),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.invoice_preview(tenant_id, settlement_id)
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))


@router.get("/{settlement_id}/document-chain", response_model=OutsourceSettlementDocumentChainResponse, summary="Document chain for settlement")
async def document_chain(
    settlement_id: int = Path(..., description="结算单ID"),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.document_chain(tenant_id, settlement_id)
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))


@router.get("/{settlement_id}", response_model=OutsourceSettlementResponse, summary="Get outsource settlement")
async def get_settlement(
    settlement_id: int = Path(..., description="结算单ID"),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.get(tenant_id, settlement_id)
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))


@router.put("/{settlement_id}", response_model=OutsourceSettlementResponse, summary="Update outsource settlement")
async def update_settlement(
    settlement_id: int,
    body: OutsourceSettlementUpdate,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.update(tenant_id, settlement_id, body, current_user)
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except BusinessLogicError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.post("/{settlement_id}/submit", response_model=OutsourceSettlementResponse, summary="Submit outsource settlement")
async def submit_settlement(
    settlement_id: int,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.submit(tenant_id, settlement_id, current_user)
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except BusinessLogicError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.post("/{settlement_id}/audit", response_model=OutsourceSettlementResponse, summary="Audit outsource settlement")
async def audit_settlement(
    settlement_id: int,
    body: OutsourceSettlementAudit,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.audit(tenant_id, settlement_id, body, current_user)
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except BusinessLogicError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.post("/{settlement_id}/reject", response_model=OutsourceSettlementResponse, summary="Reject outsource settlement")
async def reject_settlement(
    settlement_id: int,
    body: OutsourceSettlementReject,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.reject(tenant_id, settlement_id, body, current_user)
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except BusinessLogicError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.post("/{settlement_id}/revoke", response_model=OutsourceSettlementResponse, summary="Revoke outsource settlement audit")
async def revoke_settlement(
    settlement_id: int,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.revoke(tenant_id, settlement_id, current_user)
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except BusinessLogicError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.delete("/{settlement_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete outsource settlement")
async def delete_settlement(
    settlement_id: int,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        await _service.delete(tenant_id, settlement_id, current_user)
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except BusinessLogicError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))
