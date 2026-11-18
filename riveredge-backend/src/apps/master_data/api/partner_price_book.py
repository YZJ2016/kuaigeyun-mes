"""客户供应商价格本 API"""

import json
import uuid
from datetime import date
from typing import Annotated, Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from loguru import logger

from apps.master_data.schemas.partner_price_book_schemas import (
    PartnerMaterialLinePriceBatchRequest,
    PartnerMaterialLinePriceBatchResponse,
    PartnerMaterialLinePriceResolveRequest,
    PartnerMaterialLinePriceResolveResponse,
    PartnerPriceBookBulkCreate,
    PartnerPriceBookBulkResponse,
    PartnerPriceBookCreate,
    PartnerPriceBookFilterPartnerListResponse,
    PartnerPriceBookListResponse,
    PartnerPriceBookResponse,
    PartnerPriceBookUpdate,
    PartnerPriceResolveBatchRequest,
    PartnerPriceResolveBatchResponse,
    PartnerPriceResolveRequest,
    PartnerPriceResolveResponse,
)
from apps.master_data.services.partner_material_price_resolver import PartnerMaterialPriceResolver
from apps.master_data.services.partner_price_book_service import PartnerPriceBookService
from apps.master_data.api._master_data_route_access import require_master_data_module_access
from core.api.deps.access import ensure_permission_codes, get_auth_context
from core.api.deps.deps import get_current_tenant, get_current_user
from core.config.permission_contract import build_permission_code
from core.api.deps.access import AuthContext
from infra.exceptions.exceptions import NotFoundError, ValidationError
from infra.models.user import User

router = APIRouter(prefix="/supply-chain", tags=["App - Master Data - Supply Chain"])


def _http_exception(status_code: int, message: str, route: str = "/supply-chain"):
    from fastapi import HTTPException

    trace_id = uuid.uuid4().hex
    logger.warning(
        "partner_price_book_api_error trace_id={} route={} status_code={} message={}",
        trace_id,
        route,
        status_code,
        message,
    )
    return HTTPException(status_code=status_code, detail={"message": message, "trace_id": trace_id})


def _register_price_book_routes(partner_type: str, resource: str) -> None:
    base = f"/{resource}"
    module_name = f"supply-chain:{'customer-price-book' if partner_type == 'customer' else 'supplier-price-book'}"
    module_dep = Depends(require_master_data_module_access(module_name))

    @router.post(base, response_model=PartnerPriceBookResponse, dependencies=[module_dep])
    async def create_price_book(
        data: PartnerPriceBookCreate,
        current_user: Annotated[User, Depends(get_current_user)],
        tenant_id: Annotated[int, Depends(get_current_tenant)],
        _partner_type: str = partner_type,
    ):
        try:
            return await PartnerPriceBookService.create(
                tenant_id, _partner_type, data, current_user=current_user
            )
        except ValidationError as e:
            raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))

    @router.post(f"{base}/bulk", response_model=PartnerPriceBookBulkResponse, dependencies=[module_dep])
    async def bulk_register_price_books(
        data: PartnerPriceBookBulkCreate,
        current_user: Annotated[User, Depends(get_current_user)],
        tenant_id: Annotated[int, Depends(get_current_tenant)],
        _partner_type: str = partner_type,
    ):
        try:
            return await PartnerPriceBookService.bulk_register(
                tenant_id, _partner_type, data, current_user=current_user
            )
        except ValidationError as e:
            raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))

    @router.get(base, response_model=PartnerPriceBookListResponse, dependencies=[module_dep])
    async def list_price_books(
        current_user: Annotated[User, Depends(get_current_user)],
        tenant_id: Annotated[int, Depends(get_current_tenant)],
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
        partner_id: Optional[int] = Query(None, alias="partnerId"),
        material_id: Optional[int] = Query(None, alias="materialId"),
        keyword: Optional[str] = Query(None),
        active_only: Optional[bool] = Query(None, alias="activeOnly"),
        effective_on: Optional[date] = Query(None, alias="effectiveOn"),
        sort_by: Optional[str] = Query(None, alias="sortBy"),
        sort_order: Optional[str] = Query(None, alias="sortOrder"),
        created_start_date: Optional[str] = Query(None, description="创建开始日期 YYYY-MM-DD"),
        created_end_date: Optional[str] = Query(None, description="创建结束日期 YYYY-MM-DD"),
        updated_start_date: Optional[str] = Query(None, description="更新开始日期 YYYY-MM-DD"),
        updated_end_date: Optional[str] = Query(None, description="更新结束日期 YYYY-MM-DD"),
        _partner_type: str = partner_type,
    ):
        items, total = await PartnerPriceBookService.list_rows(
            tenant_id,
            _partner_type,
            skip,
            limit,
            partner_id,
            material_id,
            keyword,
            active_only,
            effective_on,
            sort_by=sort_by,
            sort_order=sort_order,
            created_start_date=created_start_date,
            created_end_date=created_end_date,
            updated_start_date=updated_start_date,
            updated_end_date=updated_end_date,
        )
        return PartnerPriceBookListResponse(data=items, total=total)

    @router.get(
        f"{base}/partners-with-data",
        response_model=PartnerPriceBookFilterPartnerListResponse,
        dependencies=[module_dep],
    )
    async def list_partners_with_price_book_data(
        current_user: Annotated[User, Depends(get_current_user)],
        tenant_id: Annotated[int, Depends(get_current_tenant)],
        _partner_type: str = partner_type,
    ):
        """列表筛选下拉：仅返回价格本中已有数据的客户/供应商。"""
        try:
            data = await PartnerPriceBookService.list_partners_with_data(
                tenant_id, _partner_type
            )
            return PartnerPriceBookFilterPartnerListResponse(data=data)
        except ValidationError as e:
            raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))

    def _parse_variant_attributes_query(raw: Optional[str]) -> Optional[Dict[str, Any]]:
        if not raw or not str(raw).strip():
            return None
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None

    @router.get(f"{base}/resolve", response_model=PartnerPriceResolveResponse, dependencies=[module_dep])
    async def resolve_price(
        current_user: Annotated[User, Depends(get_current_user)],
        tenant_id: Annotated[int, Depends(get_current_tenant)],
        partner_id: int = Query(..., alias="partnerId"),
        material_id: Optional[int] = Query(None, alias="materialId"),
        partner_material_code: Optional[str] = Query(None, alias="partnerMaterialCode"),
        variant_attributes: Optional[str] = Query(None, alias="variantAttributes"),
        as_of: Optional[date] = Query(None, alias="asOf"),
        _partner_type: str = partner_type,
    ):
        try:
            return await PartnerPriceBookService.resolve(
                tenant_id,
                _partner_type,
                PartnerPriceResolveRequest(
                    partner_id=partner_id,
                    material_id=material_id,
                    partner_material_code=partner_material_code,
                    variant_attributes=_parse_variant_attributes_query(variant_attributes),
                    as_of=as_of,
                ),
            )
        except ValidationError as e:
            raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))

    @router.post(f"{base}/resolve", response_model=PartnerPriceResolveResponse, dependencies=[module_dep])
    async def resolve_price_post(
        data: PartnerPriceResolveRequest,
        current_user: Annotated[User, Depends(get_current_user)],
        tenant_id: Annotated[int, Depends(get_current_tenant)],
        _partner_type: str = partner_type,
    ):
        try:
            return await PartnerPriceBookService.resolve(tenant_id, _partner_type, data)
        except ValidationError as e:
            raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))

    @router.post(
        f"{base}/resolve-batch",
        response_model=PartnerPriceResolveBatchResponse,
        dependencies=[module_dep],
    )
    async def resolve_prices_batch(
        data: PartnerPriceResolveBatchRequest,
        current_user: Annotated[User, Depends(get_current_user)],
        tenant_id: Annotated[int, Depends(get_current_tenant)],
        _partner_type: str = partner_type,
    ):
        items = await PartnerPriceBookService.resolve_batch(tenant_id, _partner_type, data)
        return PartnerPriceResolveBatchResponse(items=items)

    # 必须用 :uuid 约束，否则会把 partners-with-data / resolve 等静态段当成详情 UUID 打进 PG
    @router.get(f"{base}/{{book_uuid:uuid}}", response_model=PartnerPriceBookResponse, dependencies=[module_dep])
    async def get_price_book(
        book_uuid: UUID,
        current_user: Annotated[User, Depends(get_current_user)],
        tenant_id: Annotated[int, Depends(get_current_tenant)],
        _partner_type: str = partner_type,
    ):
        try:
            return await PartnerPriceBookService.get_by_uuid(
                tenant_id, _partner_type, str(book_uuid)
            )
        except NotFoundError as e:
            raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))

    @router.put(f"{base}/{{book_uuid:uuid}}", response_model=PartnerPriceBookResponse, dependencies=[module_dep])
    async def update_price_book(
        book_uuid: UUID,
        data: PartnerPriceBookUpdate,
        current_user: Annotated[User, Depends(get_current_user)],
        tenant_id: Annotated[int, Depends(get_current_tenant)],
        _partner_type: str = partner_type,
    ):
        try:
            return await PartnerPriceBookService.update(
                tenant_id, _partner_type, str(book_uuid), data, current_user=current_user
            )
        except NotFoundError as e:
            raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
        except ValidationError as e:
            raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))

    @router.delete(f"{base}/{{book_uuid:uuid}}", dependencies=[module_dep])
    async def delete_price_book(
        book_uuid: UUID,
        current_user: Annotated[User, Depends(get_current_user)],
        tenant_id: Annotated[int, Depends(get_current_tenant)],
        _partner_type: str = partner_type,
    ):
        try:
            await PartnerPriceBookService.delete(tenant_id, _partner_type, str(book_uuid))
        except NotFoundError as e:
            raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))


_register_price_book_routes("customer", "customer-price-books")
_register_price_book_routes("supplier", "supplier-price-books")


def _line_price_resolve_permission_codes(side: str) -> list[str]:
    if side == "sales":
        return [
            build_permission_code("master-data", "supply-chain:customer-price-book", "read"),
            build_permission_code("kuaizhizao", "sales-order", "read"),
            build_permission_code("kuaizhizao", "quotation", "read"),
            build_permission_code("kuaizhizao", "sales-contract", "read"),
            build_permission_code("kuaizhizao", "sales-return", "read"),
            build_permission_code("kuaizhizao", "sales-delivery", "read"),
        ]
    return [
        build_permission_code("master-data", "supply-chain:supplier-price-book", "read"),
        build_permission_code("kuaizhizao", "purchase-order", "read"),
        build_permission_code("kuaizhizao", "purchase-requisition", "read"),
        build_permission_code("kuaizhizao", "purchase-return", "read"),
        build_permission_code("kuaizhizao", "purchase-receipt", "read"),
    ]


def _partner_material_line_price_response(result) -> PartnerMaterialLinePriceResolveResponse:
    return PartnerMaterialLinePriceResolveResponse(
        found=result.found,
        unit_price=result.unit_price if result.found else None,
        tax_rate=result.tax_rate,
        price_source=result.price_source,
        currency_code=result.currency_code,
        partner_material_code=result.partner_material_code,
        partner_material_name=result.partner_material_name,
    )


@router.post(
    "/resolve-partner-material-line-price",
    response_model=PartnerMaterialLinePriceResolveResponse,
)
async def resolve_partner_material_line_price(
    data: PartnerMaterialLinePriceResolveRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    tenant_id: Annotated[int, Depends(get_current_tenant)],
):
    await ensure_permission_codes(
        auth,
        tenant_id,
        request,
        _line_price_resolve_permission_codes(data.side),
        require_all=False,
        check_abac=False,
    )
    result = await PartnerMaterialPriceResolver.resolve(
        tenant_id,
        data.side,
        data.partner_id,
        data.material_id,
        quantity=data.quantity,
        as_of=data.as_of,
        variant_attributes=data.variant_attributes,
    )
    return _partner_material_line_price_response(result)


@router.post(
    "/resolve-partner-material-line-price-batch",
    response_model=PartnerMaterialLinePriceBatchResponse,
)
async def resolve_partner_material_line_price_batch(
    data: PartnerMaterialLinePriceBatchRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_current_tenant)],
    tenant_id: Annotated[int, Depends(get_current_tenant)],
):
    await ensure_permission_codes(
        auth,
        tenant_id,
        request,
        _line_price_resolve_permission_codes(data.side),
        require_all=False,
        check_abac=False,
    )
    items: list[PartnerMaterialLinePriceResolveResponse] = []
    for line in data.items:
        result = await PartnerMaterialPriceResolver.resolve(
            tenant_id,
            data.side,
            data.partner_id,
            line.material_id,
            quantity=line.quantity,
            as_of=data.as_of,
            variant_attributes=line.variant_attributes,
        )
        items.append(_partner_material_line_price_response(result))
    return PartnerMaterialLinePriceBatchResponse(items=items)
