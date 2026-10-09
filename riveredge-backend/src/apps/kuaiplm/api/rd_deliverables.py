"""研发交付物（租户级，支持无项目归档）。"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from loguru import logger

from apps.kuaiplm.schemas.rd_project import (
    RdProjectDeliverableCreate,
    RdProjectDeliverableIssueRequest,
    RdProjectDeliverableListResponse,
    RdProjectDeliverableRejectRequest,
    RdProjectDeliverableResponse,
    RdProjectDeliverableReviseRequest,
    RdProjectDeliverableUpdate,
    RdProjectDeliverableVersionListResponse,
)
from apps.kuaiplm.services.rd_project_service import RdProjectService
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from core.services.authorization.user_permission_service import UserPermissionService
from infra.api.deps.deps import get_current_user
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError, ValidationError
from infra.models.user import User

router = APIRouter(prefix="/rd-deliverables", tags=["App - Kuaiplm - RD Deliverables"])
service = RdProjectService()


def _err(status_code: int, message: str, route: str, tenant_id: Optional[int] = None) -> HTTPException:
    trace_id = uuid.uuid4().hex
    logger.warning(
        "kuaiplm_rd_deliverables_api_error trace_id={} route={} message={}",
        trace_id,
        route,
        message,
    )
    return HTTPException(status_code=status_code, detail={"message": message, "trace_id": trace_id})


async def _permission_codes(user: User, tenant_id: int) -> list[str]:
    return sorted(
        await UserPermissionService.get_user_permissions(
            user_id=user.id,
            tenant_id=tenant_id,
        )
    )


@router.get("", response_model=RdProjectDeliverableListResponse, summary="List deliverables")
async def list_rd_deliverables(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    deliverable_type: Optional[str] = Query(None),
    types: Optional[str] = Query(
        None, description="逗号分隔的交付物类型码，与 deliverable_type 二选一"
    ),
    material_code: Optional[str] = Query(None),
    project_id: Optional[int] = Query(None),
    unlinked_only: bool = Query(False),
    linked_only: bool = Query(False),
    current_user: User = Depends(get_current_user),
    _auth=Depends(require_permission_codes("kuaiplm:project:read")),
    tenant_id: int = Depends(get_current_tenant),
):
    codes = await _permission_codes(current_user, tenant_id)
    return await service.list_deliverables(
        tenant_id,
        skip=skip,
        limit=limit,
        keyword=keyword,
        deliverable_type=deliverable_type,
        deliverable_types=types,
        material_code=material_code,
        project_id=project_id,
        unlinked_only=unlinked_only,
        linked_only=linked_only,
        current_user_id=current_user.id,
        permission_codes=codes,
    )


@router.post(
    "",
    response_model=RdProjectDeliverableResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create deliverable (optional project)",
)
async def create_rd_deliverable(
    data: RdProjectDeliverableCreate,
    current_user: User = Depends(get_current_user),
    _auth=Depends(
        require_permission_codes(
            "kuaiplm:project:create",
            "kuaiplm:project:upload-part-spec",
        )
    ),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        codes = await _permission_codes(current_user, tenant_id)
        return await service.create_deliverable(
            tenant_id,
            data,
            current_user.id,
            permission_codes=codes,
        )
    except NotFoundError as e:
        raise _err(404, str(e), "/rd-deliverables", tenant_id)
    except (BusinessLogicError, ValidationError) as e:
        raise _err(422, str(e), "/rd-deliverables", tenant_id)


@router.get(
    "/{deliverable_id}",
    response_model=RdProjectDeliverableResponse,
    summary="Get deliverable",
)
async def get_rd_deliverable(
    deliverable_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    _auth=Depends(require_permission_codes("kuaiplm:project:read")),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        codes = await _permission_codes(current_user, tenant_id)
        return await service.get_deliverable(
            tenant_id,
            deliverable_id,
            current_user_id=current_user.id,
            permission_codes=codes,
        )
    except NotFoundError as e:
        raise _err(404, str(e), f"/rd-deliverables/{deliverable_id}", tenant_id)


@router.put(
    "/{deliverable_id}",
    response_model=RdProjectDeliverableResponse,
    summary="Update deliverable",
)
async def update_rd_deliverable(
    data: RdProjectDeliverableUpdate,
    deliverable_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    _auth=Depends(
        require_permission_codes(
            "kuaiplm:project:update",
            "kuaiplm:project:upload-part-spec",
        )
    ),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        codes = await _permission_codes(current_user, tenant_id)
        return await service.update_deliverable(
            tenant_id,
            deliverable_id,
            data,
            current_user.id,
            permission_codes=codes,
        )
    except NotFoundError as e:
        raise _err(404, str(e), f"/rd-deliverables/{deliverable_id}", tenant_id)
    except (BusinessLogicError, ValidationError) as e:
        raise _err(422, str(e), f"/rd-deliverables/{deliverable_id}", tenant_id)


@router.delete(
    "/{deliverable_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete deliverable",
)
async def delete_rd_deliverable(
    deliverable_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    _auth=Depends(require_permission_codes("kuaiplm:project:delete")),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        await service.delete_deliverable(tenant_id, deliverable_id, current_user.id)
    except NotFoundError as e:
        raise _err(404, str(e), f"/rd-deliverables/{deliverable_id}", tenant_id)
    except BusinessLogicError as e:
        raise _err(422, str(e), f"/rd-deliverables/{deliverable_id}", tenant_id)


@router.get(
    "/{deliverable_id}/versions",
    response_model=RdProjectDeliverableVersionListResponse,
    summary="List deliverable versions",
)
async def list_rd_deliverable_versions(
    deliverable_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    _auth=Depends(require_permission_codes("kuaiplm:project:read")),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        permission_codes = sorted(
            await UserPermissionService.get_user_permissions(
                user_id=current_user.id,
                tenant_id=tenant_id,
            )
        )
        return await service.list_deliverable_versions(
            tenant_id,
            deliverable_id,
            current_user_id=current_user.id,
            permission_codes=permission_codes,
        )
    except NotFoundError as e:
        raise _err(404, str(e), f"/rd-deliverables/{deliverable_id}/versions", tenant_id)


@router.post(
    "/{deliverable_id}/revise",
    response_model=RdProjectDeliverableResponse,
    summary="Revise approved deliverable",
)
async def revise_rd_deliverable(
    data: RdProjectDeliverableReviseRequest,
    deliverable_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    _auth=Depends(
        require_permission_codes(
            "kuaiplm:project:update",
            "kuaiplm:project:upload-part-spec",
        )
    ),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        codes = await _permission_codes(current_user, tenant_id)
        return await service.revise_deliverable(
            tenant_id,
            deliverable_id,
            data,
            actor_id=current_user.id,
            permission_codes=codes,
        )
    except NotFoundError as e:
        raise _err(404, str(e), f"/rd-deliverables/{deliverable_id}/revise", tenant_id)
    except (BusinessLogicError, ValidationError) as e:
        raise _err(422, str(e), f"/rd-deliverables/{deliverable_id}/revise", tenant_id)


@router.post(
    "/{deliverable_id}/submit",
    response_model=RdProjectDeliverableResponse,
    summary="Submit deliverable",
)
async def submit_rd_deliverable(
    deliverable_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    _auth=Depends(require_permission_codes("kuaiplm:project:submit")),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await service.submit_deliverable(tenant_id, deliverable_id, current_user)
    except NotFoundError as e:
        raise _err(404, str(e), f"/rd-deliverables/{deliverable_id}/submit", tenant_id)
    except (BusinessLogicError, ValidationError) as e:
        raise _err(400, str(e), f"/rd-deliverables/{deliverable_id}/submit", tenant_id)


@router.post(
    "/{deliverable_id}/approve",
    response_model=RdProjectDeliverableResponse,
    summary="Approve deliverable",
)
async def approve_rd_deliverable(
    deliverable_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    _auth=Depends(require_permission_codes("kuaiplm:project:approve")),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await service.approve_deliverable(tenant_id, deliverable_id, current_user)
    except NotFoundError as e:
        raise _err(404, str(e), f"/rd-deliverables/{deliverable_id}/approve", tenant_id)
    except BusinessLogicError as e:
        raise _err(400, str(e), f"/rd-deliverables/{deliverable_id}/approve", tenant_id)


@router.post(
    "/{deliverable_id}/issue",
    response_model=RdProjectDeliverableResponse,
    summary="Issue approved deliverable to selected targets",
)
async def issue_rd_deliverable(
    data: RdProjectDeliverableIssueRequest,
    deliverable_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    _auth=Depends(require_permission_codes("kuaiplm:project:update")),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await service.issue_deliverable(
            tenant_id, deliverable_id, data, current_user
        )
    except NotFoundError as e:
        raise _err(404, str(e), f"/rd-deliverables/{deliverable_id}/issue", tenant_id)
    except (BusinessLogicError, ValidationError) as e:
        raise _err(422, str(e), f"/rd-deliverables/{deliverable_id}/issue", tenant_id)


@router.post(
    "/{deliverable_id}/reject",
    response_model=RdProjectDeliverableResponse,
    summary="Reject deliverable",
)
async def reject_rd_deliverable(
    data: RdProjectDeliverableRejectRequest,
    deliverable_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    _auth=Depends(require_permission_codes("kuaiplm:project:update")),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await service.reject_deliverable(
            tenant_id,
            deliverable_id,
            data,
            actor_id=current_user.id,
        )
    except NotFoundError as e:
        raise _err(404, str(e), f"/rd-deliverables/{deliverable_id}/reject", tenant_id)
    except BusinessLogicError as e:
        raise _err(400, str(e), f"/rd-deliverables/{deliverable_id}/reject", tenant_id)
