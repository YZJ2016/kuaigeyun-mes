"""汇率设置 API（总账参数域）。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import Field

from apps.kuaicaiwu.api._kuaicaiwu_route_access import require_kuaicaiwu_module_access
from apps.kuaicaiwu.services.exchange_rate_service import ExchangeRateService
from core.api.deps.access import AuthContext, ensure_permission_codes, get_auth_context
from core.api.deps.deps import get_current_tenant, get_current_user
from core.schemas.base import BaseSchema
from infra.exceptions.exceptions import NotFoundError, ValidationError

router = APIRouter(
    prefix="/exchange-rates",
    tags=["App - Kuaicaiwu - Exchange Rates"],
)
_gl_access = Depends(require_kuaicaiwu_module_access("gl"))
service = ExchangeRateService()


class ExchangeRateCreate(BaseSchema):
    currency_code: str = Field(..., max_length=10)
    effective_date: date
    rate: Decimal = Field(..., gt=0)
    notes: Optional[str] = None


class ExchangeRateUpdate(BaseSchema):
    currency_code: Optional[str] = Field(None, max_length=10)
    effective_date: Optional[date] = None
    rate: Optional[Decimal] = Field(None, gt=0)
    notes: Optional[str] = None


class ExchangeRateResponse(BaseSchema):
    id: int
    tenant_id: int
    currency_code: str
    effective_date: date
    rate: Decimal
    notes: Optional[str] = None
    created_at: Optional[Any] = None
    updated_at: Optional[Any] = None
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    updated_by: Optional[int] = None
    updated_by_name: Optional[str] = None

    class Config:
        from_attributes = True


class ExchangeRateListResponse(BaseSchema):
    items: List[ExchangeRateResponse]
    total: int
    skip: int
    limit: int


class ExchangeRateLookupResponse(BaseSchema):
    currency_code: str
    as_of_date: date
    found: bool
    rate: Optional[Decimal] = None


async def _require_exchange_rate_lookup_access(
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    tenant_id: int = Depends(get_current_tenant),
) -> AuthContext:
    await ensure_permission_codes(
        auth,
        tenant_id,
        request,
        ["kuaicaiwu:gl:read", "kuaizhizao:sales-order:read"],
        require_all=False,
    )
    auth.tenant_id = tenant_id
    return auth


@router.get("/lookup", response_model=ExchangeRateLookupResponse)
async def lookup_exchange_rate(
    currency_code: str = Query(..., min_length=1, max_length=10),
    as_of_date: date = Query(..., description="业务日期（订单日等）"),
    tenant_id: int = Depends(get_current_tenant),
    _auth: AuthContext = Depends(_require_exchange_rate_lookup_access),
):
    try:
        found, rate, code = await service.lookup_rate(
            tenant_id, currency_code=currency_code, as_of_date=as_of_date
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ExchangeRateLookupResponse(
        currency_code=code,
        as_of_date=as_of_date,
        found=found,
        rate=rate,
    )


@router.post(
    "",
    response_model=ExchangeRateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_gl_access],
)
async def create_exchange_rate(
    data: ExchangeRateCreate,
    tenant_id: int = Depends(get_current_tenant),
    current_user: Any = Depends(get_current_user),
):
    try:
        row = await service.create(
            tenant_id,
            currency_code=data.currency_code,
            effective_date=data.effective_date,
            rate=data.rate,
            notes=data.notes,
            current_user=current_user,
        )
        return ExchangeRateResponse.model_validate(row)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class ExchangeRateBatchResult(BaseSchema):
    effective_date: str
    base_currency: str
    source: Optional[str] = None
    created: int
    updated: int
    skipped: int
    unavailable: List[str] = Field(default_factory=list)


class ExchangeRateFetchReferenceBody(BaseSchema):
    effective_date: Optional[date] = None
    currency_codes: Optional[List[str]] = None
    source: Optional[str] = None


class ExchangeRatePresetBody(BaseSchema):
    source: Optional[str] = None


class ExchangeRateSourceItem(BaseSchema):
    code: str
    label: str
    description: str
    is_default: bool = False


class ExchangeRateSourceListResponse(BaseSchema):
    items: List[ExchangeRateSourceItem]
    default: str


@router.get(
    "/reference-sources",
    response_model=ExchangeRateSourceListResponse,
    dependencies=[_gl_access],
)
async def list_exchange_rate_reference_sources():
    """参考汇率来源清单（国内中间价优先）。"""
    items = service.list_reference_sources()
    return ExchangeRateSourceListResponse(
        items=[ExchangeRateSourceItem.model_validate(i) for i in items],
        default=next((i["code"] for i in items if i.get("is_default")), "cfets"),
    )


@router.post(
    "/preset-common",
    response_model=ExchangeRateBatchResult,
    dependencies=[_gl_access],
)
async def preset_common_exchange_rates(
    body: ExchangeRatePresetBody = Body(default_factory=ExchangeRatePresetBody),
    tenant_id: int = Depends(get_current_tenant),
    current_user: Any = Depends(get_current_user),
):
    """预置常见外币当日参考汇率（已存在则跳过）。"""
    try:
        result = await service.preset_common_currencies(
            tenant_id, current_user=current_user, source=body.source
        )
        return ExchangeRateBatchResult.model_validate(result)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post(
    "/fetch-reference",
    response_model=ExchangeRateBatchResult,
    dependencies=[_gl_access],
)
async def fetch_reference_exchange_rates(
    body: ExchangeRateFetchReferenceBody = Body(default_factory=ExchangeRateFetchReferenceBody),
    tenant_id: int = Depends(get_current_tenant),
    current_user: Any = Depends(get_current_user),
):
    """从选定公开牌价源拉取参考汇率并写入/覆盖当日记录。"""
    try:
        result = await service.import_reference_rates(
            tenant_id,
            current_user=current_user,
            effective_date=body.effective_date,
            currency_codes=body.currency_codes,
            source=body.source,
        )
        return ExchangeRateBatchResult.model_validate(result)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("", response_model=ExchangeRateListResponse, dependencies=[_gl_access])
async def list_exchange_rates(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    currency_code: Optional[str] = None,
    effective_start: Optional[date] = None,
    effective_end: Optional[date] = None,
    keyword: Optional[str] = None,
    sort_field: Optional[str] = None,
    sort_order: Optional[str] = None,
    tenant_id: int = Depends(get_current_tenant),
):
    items, total = await service.list_rows(
        tenant_id,
        skip=skip,
        limit=limit,
        currency_code=currency_code,
        effective_start=effective_start,
        effective_end=effective_end,
        keyword=keyword,
        sort_field=sort_field,
        sort_order=sort_order,
    )
    return ExchangeRateListResponse(
        items=[ExchangeRateResponse.model_validate(r) for r in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{row_id}", response_model=ExchangeRateResponse, dependencies=[_gl_access])
async def get_exchange_rate(
    row_id: int,
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        row = await service.get_by_id(tenant_id, row_id)
        return ExchangeRateResponse.model_validate(row)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/{row_id}", response_model=ExchangeRateResponse, dependencies=[_gl_access])
async def update_exchange_rate(
    row_id: int,
    data: ExchangeRateUpdate,
    tenant_id: int = Depends(get_current_tenant),
    current_user: Any = Depends(get_current_user),
):
    try:
        row = await service.update(
            tenant_id,
            row_id,
            data.model_dump(exclude_unset=True, exclude={"audit"}),
            current_user=current_user,
        )
        return ExchangeRateResponse.model_validate(row)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/{row_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[_gl_access])
async def delete_exchange_rate(
    row_id: int,
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        await service.delete(tenant_id, row_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
