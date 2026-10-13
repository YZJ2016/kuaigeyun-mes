"""
其他费用收入/支出单据 API 路由（收入/支出共享实现）。
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from datetime import date
from loguru import logger

from apps.kuaicaiwu.schemas.finance import (
    OtherVoucherCreate,
    OtherVoucherListResponse,
    OtherVoucherResponse,
    OtherVoucherReviewAction,
    OtherVoucherUpdate,
)
from apps.kuaicaiwu.services.misc_voucher_service import (
    EXPENSE_SPEC,
    INCOME_SPEC,
    MiscVoucherService,
    MiscVoucherSpec,
)
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from infra.api.deps.deps import get_current_user
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError, ValidationError
from infra.models.user import User


def _http_exception_with_trace(
    status_code: int,
    message: str,
    route: str,
    tenant_id: Optional[int] = None,
) -> HTTPException:
    trace_id = uuid.uuid4().hex
    logger.warning(
        "kuaicaiwu_misc_voucher_api_error trace_id={} tenant_id={} route={} status_code={} message={}",
        trace_id,
        tenant_id,
        route,
        status_code,
        message,
    )
    return HTTPException(
        status_code=status_code,
        detail={"message": message, "trace_id": trace_id},
    )


def _raise_mapped(exc: Exception, route: str, tenant_id: int) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return _http_exception_with_trace(404, str(exc), route, tenant_id)
    if isinstance(exc, (BusinessLogicError, ValidationError)):
        return _http_exception_with_trace(400, str(exc), route, tenant_id)
    return _http_exception_with_trace(500, "内部错误", route, tenant_id)


def _build_router(spec: MiscVoucherSpec) -> APIRouter:
    service = MiscVoucherService(spec)
    resource = f"kuaicaiwu:other-{spec.voucher_type.split('_', 1)[1]}"
    router = APIRouter(
        prefix=f"/other-{spec.voucher_type.split('_', 1)[1]}s",
        tags=["App - Kuaicaiwu - Finance"],
    )

    async def _serialize(tenant_id: int, doc, *, with_lines: bool) -> OtherVoucherResponse:
        payload = OtherVoucherResponse.model_validate(doc).model_dump()
        if with_lines:
            lines = await spec.line_model.filter(
                tenant_id=tenant_id, **{spec.fk_field: int(doc.id)}
            ).order_by("line_no", "id").all()
            payload["lines"] = lines
        else:
            payload["lines"] = []
        payload["capabilities"] = service.capabilities(
            doc, audit_required=await service.audit_required(tenant_id)
        )
        return OtherVoucherResponse.model_validate(payload)

    @router.post(
        "", response_model=OtherVoucherResponse, status_code=status.HTTP_201_CREATED
    )
    async def create_voucher(
        data: OtherVoucherCreate,
        _auth: object = Depends(require_permission_codes(f"{resource}:create")),
        current_user: User = Depends(get_current_user),
        tenant_id: int = Depends(get_current_tenant),
    ):
        try:
            doc = await service.create(tenant_id, data, current_user)
        except Exception as exc:
            raise _raise_mapped(exc, router.prefix, tenant_id) from exc
        return await _serialize(tenant_id, doc, with_lines=True)

    @router.get("", response_model=OtherVoucherListResponse)
    async def list_vouchers(
        skip: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=200),
        status: Optional[str] = None,
        counterparty_id: Optional[int] = None,
        counterparty_kind: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        keyword: Optional[str] = Query(None),
        doc_code: Optional[str] = Query(None),
        counterparty_name: Optional[str] = Query(None),
        created_start_date: Optional[str] = Query(None),
        created_end_date: Optional[str] = Query(None),
        updated_start_date: Optional[str] = Query(None),
        updated_end_date: Optional[str] = Query(None),
        sort_field: Optional[str] = Query(None),
        sort_order: Optional[str] = Query(None),
        _auth: object = Depends(require_permission_codes(f"{resource}:read")),
        tenant_id: int = Depends(get_current_tenant),
        current_user: User = Depends(get_current_user),
    ):
        from apps.kuaicaiwu.services.finance_list_core import (
            apply_finance_voucher_list_filters,
        )

        query = spec.model.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if status:
            query = query.filter(status=status)
        if counterparty_id:
            query = query.filter(counterparty_id=counterparty_id)
        if counterparty_kind:
            query = query.filter(counterparty_kind=counterparty_kind)

        query, order_expr = apply_finance_voucher_list_filters(
            query,
            doc_code_field=spec.code_field,
            partner_name_field="counterparty_name",
            doc_date_field="business_date",
            keyword=keyword,
            doc_code=doc_code,
            partner_name=counterparty_name,
            doc_date_start=start_date.isoformat() if start_date else None,
            doc_date_end=end_date.isoformat() if end_date else None,
            created_start_date=created_start_date,
            created_end_date=created_end_date,
            updated_start_date=updated_start_date,
            updated_end_date=updated_end_date,
            sort_field=sort_field,
            sort_order=sort_order,
            default_sort_col="business_date",
        )

        total = await query.count()
        items = await query.order_by(order_expr, "-id").offset(skip).limit(limit).all()
        serialized = [
            await _serialize(tenant_id, doc, with_lines=False) for doc in items
        ]
        return OtherVoucherListResponse(
            items=serialized, total=total, skip=skip, limit=limit
        )

    @router.get("/{doc_id}", response_model=OtherVoucherResponse)
    async def get_voucher(
        doc_id: int,
        _auth: object = Depends(require_permission_codes(f"{resource}:read")),
        tenant_id: int = Depends(get_current_tenant),
        current_user: User = Depends(get_current_user),
    ):
        try:
            doc = await service.get_or_404(tenant_id, doc_id)
        except Exception as exc:
            raise _raise_mapped(exc, f"{router.prefix}/{{id}}", tenant_id) from exc
        return await _serialize(tenant_id, doc, with_lines=True)

    @router.put("/{doc_id}", response_model=OtherVoucherResponse)
    async def update_voucher(
        doc_id: int,
        data: OtherVoucherUpdate,
        _auth: object = Depends(require_permission_codes(f"{resource}:update")),
        current_user: User = Depends(get_current_user),
        tenant_id: int = Depends(get_current_tenant),
    ):
        try:
            doc = await service.update(tenant_id, doc_id, data, current_user)
        except Exception as exc:
            raise _raise_mapped(exc, f"{router.prefix}/{{id}}", tenant_id) from exc
        return await _serialize(tenant_id, doc, with_lines=True)

    @router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_voucher(
        doc_id: int,
        _auth: object = Depends(require_permission_codes(f"{resource}:delete")),
        current_user: User = Depends(get_current_user),
        tenant_id: int = Depends(get_current_tenant),
    ):
        try:
            await service.delete(tenant_id, doc_id)
        except Exception as exc:
            raise _raise_mapped(exc, f"{router.prefix}/{{id}}", tenant_id) from exc

    @router.post("/{doc_id}/submit", response_model=OtherVoucherResponse)
    async def submit_voucher(
        doc_id: int,
        _auth: object = Depends(require_permission_codes(f"{resource}:submit")),
        current_user: User = Depends(get_current_user),
        tenant_id: int = Depends(get_current_tenant),
    ):
        try:
            doc = await service.submit(tenant_id, doc_id, current_user)
        except Exception as exc:
            raise _raise_mapped(exc, f"{router.prefix}/{{id}}/submit", tenant_id) from exc
        return await _serialize(tenant_id, doc, with_lines=True)

    @router.post("/{doc_id}/approve", response_model=OtherVoucherResponse)
    async def approve_voucher(
        doc_id: int,
        body: Optional[OtherVoucherReviewAction] = None,
        _auth: object = Depends(require_permission_codes(f"{resource}:approve")),
        current_user: User = Depends(get_current_user),
        tenant_id: int = Depends(get_current_tenant),
    ):
        try:
            doc = await service.approve(
                tenant_id,
                doc_id,
                current_user,
                remarks=body.review_remarks if body else None,
            )
        except Exception as exc:
            raise _raise_mapped(exc, f"{router.prefix}/{{id}}/approve", tenant_id) from exc
        return await _serialize(tenant_id, doc, with_lines=True)

    @router.post("/{doc_id}/reject", response_model=OtherVoucherResponse)
    async def reject_voucher(
        doc_id: int,
        body: Optional[OtherVoucherReviewAction] = None,
        _auth: object = Depends(require_permission_codes(f"{resource}:reject")),
        current_user: User = Depends(get_current_user),
        tenant_id: int = Depends(get_current_tenant),
    ):
        try:
            doc = await service.reject(
                tenant_id,
                doc_id,
                current_user,
                remarks=body.review_remarks if body else None,
            )
        except Exception as exc:
            raise _raise_mapped(exc, f"{router.prefix}/{{id}}/reject", tenant_id) from exc
        return await _serialize(tenant_id, doc, with_lines=True)

    @router.post("/{doc_id}/confirm", response_model=OtherVoucherResponse)
    async def confirm_voucher(
        doc_id: int,
        _auth: object = Depends(require_permission_codes(f"{resource}:audit")),
        current_user: User = Depends(get_current_user),
        tenant_id: int = Depends(get_current_tenant),
    ):
        try:
            doc = await service.confirm(tenant_id, doc_id, current_user)
        except Exception as exc:
            raise _raise_mapped(exc, f"{router.prefix}/{{id}}/confirm", tenant_id) from exc
        return await _serialize(tenant_id, doc, with_lines=True)

    @router.post("/{doc_id}/unconfirm", response_model=OtherVoucherResponse)
    async def unconfirm_voucher(
        doc_id: int,
        _auth: object = Depends(require_permission_codes(f"{resource}:revoke")),
        current_user: User = Depends(get_current_user),
        tenant_id: int = Depends(get_current_tenant),
    ):
        try:
            doc = await service.unconfirm(tenant_id, doc_id, current_user)
        except Exception as exc:
            raise _raise_mapped(
                exc, f"{router.prefix}/{{id}}/unconfirm", tenant_id
            ) from exc
        return await _serialize(tenant_id, doc, with_lines=True)

    @router.post("/{doc_id}/cancel", response_model=OtherVoucherResponse)
    async def cancel_voucher(
        doc_id: int,
        _auth: object = Depends(require_permission_codes(f"{resource}:revoke")),
        current_user: User = Depends(get_current_user),
        tenant_id: int = Depends(get_current_tenant),
    ):
        try:
            doc = await service.cancel(tenant_id, doc_id, current_user)
        except Exception as exc:
            raise _raise_mapped(exc, f"{router.prefix}/{{id}}/cancel", tenant_id) from exc
        return await _serialize(tenant_id, doc, with_lines=True)

    return router


other_incomes_router = _build_router(INCOME_SPEC)
other_expenses_router = _build_router(EXPENSE_SPEC)
