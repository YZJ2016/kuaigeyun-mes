"""采购询价需方 API"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from apps.kuaizhizao.schemas.purchase_demand_party import (
    PurchaseDemandPartyCreate,
    PurchaseDemandPartyResponse,
    PurchaseDemandPartyUpdate,
)
from apps.kuaizhizao.services.purchase_demand_party_service import PurchaseDemandPartyService
from core.api.deps.access import AuthContext, ensure_permission_codes, get_auth_context
from core.api.deps.deps import get_current_tenant
from core.config.permission_contract import build_permission_code
from infra.api.deps.deps import get_current_user
from infra.exceptions.exceptions import NotFoundError, ValidationError
from infra.models.user import User

router = APIRouter(
    prefix="/purchase-demand-parties",
    tags=["App - Kuaige Zhizao - Purchase Demand Party"],
)
service = PurchaseDemandPartyService()


def _err(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


async def _require_demand_party_read(
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    tenant_id: int = Depends(get_current_tenant),
) -> AuthContext:
    """维护页 read，或询价单宿主 read 均可拉取需方下拉。"""
    await ensure_permission_codes(
        auth,
        tenant_id,
        request,
        [
            build_permission_code("kuaizhizao", "purchase-demand-party", "read"),
            build_permission_code("kuaizhizao", "purchase-inquiry", "read"),
        ],
        require_all=False,
        check_abac=False,
    )
    auth.tenant_id = tenant_id
    return auth


async def _require_demand_party_action(
    action: str,
    request: Request,
    auth: AuthContext,
    tenant_id: int,
) -> AuthContext:
    await ensure_permission_codes(
        auth,
        tenant_id,
        request,
        [build_permission_code("kuaizhizao", "purchase-demand-party", action)],
        require_all=True,
        check_abac=False,
    )
    auth.tenant_id = tenant_id
    return auth


@router.get("")
async def list_parties(
    keyword: Optional[str] = None,
    is_active: Optional[bool] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    tenant_id: int = Depends(get_current_tenant),
    _auth: AuthContext = Depends(_require_demand_party_read),
):
    return await service.list_parties(
        tenant_id,
        keyword=keyword,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )


@router.get("/{party_id}", response_model=PurchaseDemandPartyResponse)
async def get_party(
    party_id: int,
    tenant_id: int = Depends(get_current_tenant),
    _auth: AuthContext = Depends(_require_demand_party_read),
):
    try:
        return await service.get_party(tenant_id, party_id)
    except (NotFoundError, ValidationError) as exc:
        raise _err(exc) from exc


@router.post("", response_model=PurchaseDemandPartyResponse, status_code=status.HTTP_201_CREATED)
async def create_party(
    body: PurchaseDemandPartyCreate,
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    await _require_demand_party_action("create", request, auth, tenant_id)
    try:
        return await service.create_party(tenant_id, body.model_dump(), current_user)
    except (NotFoundError, ValidationError) as exc:
        raise _err(exc) from exc


@router.put("/{party_id}", response_model=PurchaseDemandPartyResponse)
async def update_party(
    party_id: int,
    body: PurchaseDemandPartyUpdate,
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    await _require_demand_party_action("update", request, auth, tenant_id)
    try:
        return await service.update_party(
            tenant_id,
            party_id,
            body.model_dump(exclude_unset=True),
            current_user,
        )
    except (NotFoundError, ValidationError) as exc:
        raise _err(exc) from exc


@router.delete("/{party_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_party(
    party_id: int,
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    await _require_demand_party_action("delete", request, auth, tenant_id)
    try:
        await service.delete_party(tenant_id, party_id, current_user)
    except (NotFoundError, ValidationError) as exc:
        raise _err(exc) from exc
