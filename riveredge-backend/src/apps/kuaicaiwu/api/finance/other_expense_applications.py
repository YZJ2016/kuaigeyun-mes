"""其他费用支出申请 API"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from apps.kuaicaiwu.schemas.other_expense_application import (
    ApproveOtherExpenseApplicationRequest,
    OtherExpenseApplicationCreate,
    OtherExpenseApplicationListResponse,
    OtherExpenseApplicationResponse,
    OtherExpenseApplicationUpdate,
    PushOtherExpenseApplicationRequest,
)
from apps.kuaicaiwu.services.other_expense_application_push_service import (
    OtherExpenseApplicationPushService,
)
from apps.kuaicaiwu.services.other_expense_application_service import OtherExpenseApplicationService
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from infra.api.deps.deps import get_current_user
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError, ValidationError
from infra.models.user import User

router = APIRouter(
    prefix="/other-expense-applications",
    tags=["App - Kuaicaiwu - Other Expense Application"],
)

_svc = OtherExpenseApplicationService()
_push = OtherExpenseApplicationPushService()


def _http(status_code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)


@router.get("", response_model=OtherExpenseApplicationListResponse)
async def list_other_expense_applications(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    status: Optional[str] = None,
    review_status: Optional[str] = None,
    keyword: Optional[str] = None,
    approved_only: bool = Query(False),
    with_remaining: bool = Query(False),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense-application:read")),
):
    result = await _svc.list_applications(
        tenant_id,
        skip=skip,
        limit=limit,
        status=status,
        review_status=review_status,
        keyword=keyword,
        approved_only=approved_only,
        with_remaining=with_remaining,
        viewer_id=current_user.id,
    )
    return OtherExpenseApplicationListResponse(**result)


@router.post("", response_model=OtherExpenseApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_other_expense_application(
    body: OtherExpenseApplicationCreate,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense-application:create")),
):
    try:
        return await _svc.create_application(tenant_id, body, current_user.id)
    except (ValidationError, BusinessLogicError) as exc:
        raise _http(400, str(exc)) from exc


@router.get("/{application_id}", response_model=OtherExpenseApplicationResponse)
async def get_other_expense_application(
    application_id: int = Path(..., ge=1),
    tenant_id: int = Depends(get_current_tenant),
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense-application:read")),
):
    try:
        return await _svc.get_by_id(tenant_id, application_id)
    except NotFoundError as exc:
        raise _http(404, str(exc)) from exc


@router.put("/{application_id}", response_model=OtherExpenseApplicationResponse)
async def update_other_expense_application(
    application_id: int,
    body: OtherExpenseApplicationUpdate,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense-application:update")),
):
    try:
        return await _svc.update_application(tenant_id, application_id, body, current_user.id)
    except NotFoundError as exc:
        raise _http(404, str(exc)) from exc
    except (ValidationError, BusinessLogicError) as exc:
        raise _http(400, str(exc)) from exc


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_other_expense_application(
    application_id: int,
    tenant_id: int = Depends(get_current_tenant),
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense-application:delete")),
):
    try:
        await _svc.delete_application(tenant_id, application_id)
    except NotFoundError as exc:
        raise _http(404, str(exc)) from exc
    except BusinessLogicError as exc:
        raise _http(400, str(exc)) from exc


@router.post("/{application_id}/submit", response_model=OtherExpenseApplicationResponse)
async def submit_other_expense_application(
    application_id: int,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense-application:submit")),
):
    try:
        return await _svc.submit_application(tenant_id, application_id, current_user.id)
    except NotFoundError as exc:
        raise _http(404, str(exc)) from exc
    except BusinessLogicError as exc:
        raise _http(400, str(exc)) from exc


@router.post("/{application_id}/approve", response_model=OtherExpenseApplicationResponse)
async def approve_other_expense_application(
    application_id: int,
    body: ApproveOtherExpenseApplicationRequest,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense-application:approve")),
):
    try:
        return await _svc.approve_application(
            tenant_id,
            application_id,
            approved=body.approved,
            operator_id=current_user.id,
            review_remarks=body.review_remarks,
        )
    except NotFoundError as exc:
        raise _http(404, str(exc)) from exc
    except BusinessLogicError as exc:
        raise _http(400, str(exc)) from exc


@router.post("/{application_id}/reject", response_model=OtherExpenseApplicationResponse)
async def reject_other_expense_application(
    application_id: int,
    body: ApproveOtherExpenseApplicationRequest,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense-application:reject")),
):
    try:
        return await _svc.approve_application(
            tenant_id,
            application_id,
            approved=False,
            operator_id=current_user.id,
            review_remarks=body.review_remarks,
        )
    except NotFoundError as exc:
        raise _http(404, str(exc)) from exc
    except BusinessLogicError as exc:
        raise _http(400, str(exc)) from exc


@router.post("/{application_id}/withdraw-submit", response_model=OtherExpenseApplicationResponse)
async def withdraw_other_expense_application_submit(
    application_id: int,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense-application:revoke")),
):
    try:
        return await _svc.withdraw_application_submit(tenant_id, application_id, current_user.id)
    except NotFoundError as exc:
        raise _http(404, str(exc)) from exc
    except BusinessLogicError as exc:
        raise _http(400, str(exc)) from exc


@router.post("/{application_id}/push-other-expense")
async def push_other_expense_application(
    application_id: int,
    body: PushOtherExpenseApplicationRequest,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _auth: object = Depends(require_permission_codes("kuaicaiwu:other-expense-application:push")),
):
    try:
        return await _push.push_to_other_expense(tenant_id, application_id, body, current_user)
    except NotFoundError as exc:
        raise _http(404, str(exc)) from exc
    except (ValidationError, BusinessLogicError) as exc:
        raise _http(400, str(exc)) from exc
