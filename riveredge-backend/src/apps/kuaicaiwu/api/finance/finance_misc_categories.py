"""
其他收支类别 API 路由（income/expense 分表）。
"""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from loguru import logger

from apps.kuaicaiwu.schemas.finance import (
    MiscCategoryCreate,
    MiscCategoryResponse,
    MiscCategoryUpdate,
)
from apps.kuaicaiwu.services.misc_voucher_service import MiscCategoryService
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from infra.api.deps.deps import get_current_user
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError, ValidationError
from infra.models.user import User

router = APIRouter(
    prefix="/finance-misc-categories", tags=["App - Kuaicaiwu - Finance"]
)
service = MiscCategoryService()
_RESOURCE = "kuaicaiwu:finance-misc-category"


def _http_exception_with_trace(
    status_code: int,
    message: str,
    route: str,
    tenant_id: Optional[int] = None,
) -> HTTPException:
    trace_id = uuid.uuid4().hex
    logger.warning(
        "kuaicaiwu_misc_category_api_error trace_id={} tenant_id={} route={} status_code={} message={}",
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


@router.get("/{kind}", response_model=List[MiscCategoryResponse])
async def list_categories(
    kind: str = Path(..., pattern="^(income|expense)$"),
    keyword: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    ensure_defaults: bool = Query(False),
    _auth: object = Depends(require_permission_codes(f"{_RESOURCE}:read")),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        rows = await service.list(
            tenant_id,
            kind,
            keyword=keyword,
            is_active=is_active,
            ensure_defaults=ensure_defaults,
        )
    except Exception as exc:
        raise _raise_mapped(exc, "/finance-misc-categories/{kind}", tenant_id) from exc
    return [MiscCategoryResponse.model_validate(r) for r in rows]


@router.post(
    "/{kind}",
    response_model=MiscCategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_category(
    data: MiscCategoryCreate,
    kind: str = Path(..., pattern="^(income|expense)$"),
    _auth: object = Depends(require_permission_codes(f"{_RESOURCE}:create")),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        cat = await service.create(tenant_id, kind, data, current_user)
    except Exception as exc:
        raise _raise_mapped(exc, "/finance-misc-categories/{kind}", tenant_id) from exc
    return MiscCategoryResponse.model_validate(cat)


@router.put("/{kind}/{cat_id}", response_model=MiscCategoryResponse)
async def update_category(
    data: MiscCategoryUpdate,
    kind: str = Path(..., pattern="^(income|expense)$"),
    cat_id: int = Path(...),
    _auth: object = Depends(require_permission_codes(f"{_RESOURCE}:update")),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        cat = await service.update(tenant_id, kind, cat_id, data, current_user)
    except Exception as exc:
        raise _raise_mapped(
            exc, "/finance-misc-categories/{kind}/{id}", tenant_id
        ) from exc
    return MiscCategoryResponse.model_validate(cat)


@router.delete("/{kind}/{cat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    kind: str = Path(..., pattern="^(income|expense)$"),
    cat_id: int = Path(...),
    _auth: object = Depends(require_permission_codes(f"{_RESOURCE}:delete")),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        await service.delete(tenant_id, kind, cat_id)
    except Exception as exc:
        raise _raise_mapped(
            exc, "/finance-misc-categories/{kind}/{id}", tenant_id
        ) from exc
