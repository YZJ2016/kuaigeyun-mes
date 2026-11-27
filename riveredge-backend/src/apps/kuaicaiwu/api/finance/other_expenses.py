"""其他费用支出 API"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from apps.kuaicaiwu.schemas.other_voucher import (
    OtherExpenseCreate,
    OtherExpenseResponse,
    OtherExpenseUpdate,
    ReviewActionBody,
)
from apps.kuaicaiwu.services.misc_voucher_posting_service import MiscVoucherPostingService
from apps.kuaicaiwu.services.other_expense_service import OtherExpenseService
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from infra.api.deps.deps import get_current_user
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError, ValidationError
from infra.models.user import User

router = APIRouter(prefix="/other-expenses", tags=["App - Kuaicaiwu - Other Expense"])
service = OtherExpenseService()
posting = MiscVoucherPostingService()


def _http(status_code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)


@router.get("", response_model=dict)
async def list_other_expenses(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    status: Optional[str] = None,
    review_status: Optional[str] = None,
    keyword: Optional[str] = None,
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense:read")),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    return await service.list_expenses(
        tenant_id,
        skip=skip,
        limit=limit,
        status=status,
        review_status=review_status,
        keyword=keyword,
        viewer_id=current_user.id,
    )


@router.post("", response_model=OtherExpenseResponse, status_code=status.HTTP_201_CREATED)
async def create_other_expense(
    body: OtherExpenseCreate,
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense:create")),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await service.create_expense(tenant_id, body, current_user.id)
    except (ValidationError, BusinessLogicError) as exc:
        raise _http(400, str(exc)) from exc


@router.get("/pull-candidates/other-expense-applications", response_model=dict)
async def list_other_expense_application_pull_candidates(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense:read")),
    tenant_id: int = Depends(get_current_tenant),
):
    from apps.kuaicaiwu.services.other_expense_application_pull_service import (
        OtherExpenseApplicationPullService,
    )

    return await OtherExpenseApplicationPullService().list_for_expense_pull(
        tenant_id, skip=skip, limit=limit, keyword=keyword
    )


@router.get("/from-other-expense-application/{application_id}/pull-preview", response_model=dict)
async def preview_pull_other_expense_from_application(
    application_id: int,
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense:read")),
    tenant_id: int = Depends(get_current_tenant),
):
    from apps.kuaicaiwu.services.other_expense_application_pull_service import (
        OtherExpenseApplicationPullService,
    )

    try:
        return await OtherExpenseApplicationPullService().preview_pull_for_expense(
            tenant_id, application_id
        )
    except NotFoundError as exc:
        raise _http(404, str(exc)) from exc


@router.get("/pull-candidates/purchase-receipts", response_model=dict)
async def list_other_expense_purchase_receipt_link_candidates(
    supplier_id: int = Query(..., ge=1, description="供应商ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense:read")),
    tenant_id: int = Depends(get_current_tenant),
):
    """其他费用支出关联采购入库：按供应商列出可关联入库单。"""
    try:
        return await service.list_purchase_receipt_link_candidates(
            tenant_id,
            supplier_id=supplier_id,
            skip=skip,
            limit=limit,
            keyword=keyword,
        )
    except ValidationError as exc:
        raise _http(400, str(exc)) from exc


@router.get("/{expense_id}", response_model=OtherExpenseResponse)
async def get_other_expense(
    expense_id: int,
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense:read")),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await service.get_by_id(
            tenant_id, expense_id, viewer_id=current_user.id
        )
    except NotFoundError as exc:
        raise _http(404, str(exc)) from exc


@router.put("/{expense_id}", response_model=OtherExpenseResponse)
async def update_other_expense(
    expense_id: int,
    body: OtherExpenseUpdate,
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense:update")),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await service.update_expense(tenant_id, expense_id, body, current_user.id)
    except (NotFoundError, ValidationError, BusinessLogicError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise _http(code, str(exc)) from exc


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_other_expense(
    expense_id: int,
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense:delete")),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        await service.delete_expense(tenant_id, expense_id)
    except (NotFoundError, BusinessLogicError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise _http(code, str(exc)) from exc


@router.post("/{expense_id}/submit", response_model=OtherExpenseResponse)
async def submit_other_expense(
    expense_id: int,
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense:submit")),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await service.submit_expense(tenant_id, expense_id, current_user.id)
    except (NotFoundError, BusinessLogicError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise _http(code, str(exc)) from exc


@router.post("/{expense_id}/approve", response_model=OtherExpenseResponse)
async def approve_other_expense(
    expense_id: int,
    body: ReviewActionBody,
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense:approve")),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await service.approve_expense(
            tenant_id,
            expense_id,
            approved=body.approved,
            operator_id=current_user.id,
            review_remarks=body.review_remarks,
        )
    except (NotFoundError, BusinessLogicError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise _http(code, str(exc)) from exc


@router.post("/{expense_id}/reject", response_model=OtherExpenseResponse)
async def reject_other_expense(
    expense_id: int,
    body: ReviewActionBody,
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense:reject")),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await service.approve_expense(
            tenant_id,
            expense_id,
            approved=False,
            operator_id=current_user.id,
            review_remarks=body.review_remarks,
        )
    except (NotFoundError, BusinessLogicError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise _http(code, str(exc)) from exc


@router.post("/{expense_id}/confirm", response_model=OtherExpenseResponse)
async def confirm_other_expense(
    expense_id: int,
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense:audit")),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        await posting.post_other_expense(
            tenant_id, expense_id, operator=current_user
        )
        return await service.get_by_id(tenant_id, expense_id)
    except (NotFoundError, ValidationError, BusinessLogicError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise _http(code, str(exc)) from exc


@router.post("/{expense_id}/unconfirm", response_model=OtherExpenseResponse)
async def unconfirm_other_expense(
    expense_id: int,
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense:revoke")),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        await posting.unpost_other_expense(
            tenant_id, expense_id, operator_id=current_user.id
        )
        return await service.get_by_id(tenant_id, expense_id)
    except (NotFoundError, ValidationError, BusinessLogicError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise _http(code, str(exc)) from exc


@router.post("/{expense_id}/cancel", response_model=OtherExpenseResponse)
async def cancel_other_expense(
    expense_id: int,
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense:revoke")),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await service.cancel_expense(tenant_id, expense_id, current_user.id)
    except (NotFoundError, BusinessLogicError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise _http(code, str(exc)) from exc


@router.get("/{expense_id}/print", summary="打印其他费用支出")
async def print_other_expense(
    expense_id: int = Path(..., ge=1),
    template_code: Optional[str] = Query(None, description="打印模板代码"),
    template_uuid: Optional[str] = Query(None, description="打印模板UUID"),
    output_format: str = Query("html", description="输出格式"),
    response_format: str = Query("json", description="响应格式"),
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense:print")),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    import base64

    from apps.kuaizhizao.services.print_service import DocumentPrintService
    from fastapi.responses import HTMLResponse, JSONResponse, Response

    try:
        result = await DocumentPrintService().print_document(
            tenant_id=tenant_id,
            document_type="other_expense",
            document_id=expense_id,
            template_code=template_code,
            template_uuid=template_uuid,
            output_format=output_format,
        )
    except NotFoundError as exc:
        raise _http(404, str(exc)) from exc
    except (ValidationError, BusinessLogicError) as exc:
        raise _http(400, str(exc)) from exc

    if (
        (output_format or "html").lower() == "pdf"
        and (response_format or "json").lower() in {"pdf", "binary", "raw"}
        and result.get("mime_type") == "application/pdf"
    ):
        raw = base64.b64decode(result.get("content") or "")
        return Response(
            content=raw,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="other-expense-{expense_id}.pdf"'
            },
        )
    if response_format == "html":
        return HTMLResponse(content=result.get("content", ""), status_code=200)
    return JSONResponse(content=result, status_code=200)
