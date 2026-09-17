"""交付项目 API"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException as FastAPIHTTPException, Path, Query, status

from apps.kuaizhizao.api._kuaizhizao_route_access import require_kuaizhizao_module_access
from apps.kuaizhizao.schemas.delivery_project import (
    DeliveryProjectChangeTemplateRequest,
    DeliveryProjectCompleteRequest,
    DeliveryProjectCreate,
    DeliveryProjectListEnvelope,
    DeliveryProjectNodeDocumentCreate,
    DeliveryProjectNodeDocumentResponse,
    DeliveryProjectNodeResponse,
    DeliveryProjectNodeTaskCreate,
    DeliveryProjectNodeTaskResponse,
    DeliveryProjectNodeTaskUpdate,
    DeliveryTaskParticipantActionSubmit,
    DeliveryProjectNodeScheduleRevisionResponse,
    DeliveryProjectNodeUpdate,
    DeliveryProjectResponse,
    DeliveryProjectUpdate,
    DeliveryProjectWorkbenchResponse,
    DeliverySidelineCreate,
    DeliveryWorkshopBoardCell,
    DeliveryWorkshopBoardCellPatch,
    DeliveryWorkshopBoardEnvelope,
)
from apps.kuaizhizao.services.delivery_project_service import (
    DELIVERY_PROJECT_SORTABLE_FIELDS,
    DeliveryProjectService,
)
from core.api.deps import get_current_user, get_current_tenant
from infra.exceptions.exceptions import NotFoundError, ValidationError
from infra.models.user import User

router = APIRouter(
    prefix="/delivery-projects",
    tags=["App - Kuaige Zhizao - Delivery Projects"],
    dependencies=[Depends(require_kuaizhizao_module_access("delivery-project"))],
)

_service = DeliveryProjectService()


def _http_exception(status_code: int, message: str) -> FastAPIHTTPException:
    return FastAPIHTTPException(
        status_code=status_code,
        detail={"message": message, "trace_id": uuid.uuid4().hex},
    )


@router.post("", response_model=DeliveryProjectResponse, summary="Create delivery project")
async def create_project(
    body: DeliveryProjectCreate,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.create_project(tenant_id, body, current_user)
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.get("", response_model=DeliveryProjectListEnvelope, summary="List delivery projects")
async def list_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    keyword: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    sales_order_id: Optional[int] = Query(None),
    customer_id: Optional[int] = Query(None),
    current_node_key: Optional[str] = Query(None),
    board_section: Optional[str] = Query(None),
    order_by: Optional[str] = Query(None),
    tenant_id: int = Depends(get_current_tenant),
):
    safe_order_by = None
    if order_by:
        field = order_by.lstrip("-")
        if field in DELIVERY_PROJECT_SORTABLE_FIELDS:
            safe_order_by = order_by
    try:
        return await _service.list_projects(
            tenant_id,
            skip=skip,
            limit=limit,
            keyword=keyword,
            status=status,
            sales_order_id=sales_order_id,
            customer_id=customer_id,
            current_node_key=current_node_key,
            board_section=board_section,
            order_by=safe_order_by,
        )
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.get("/workshop-board", response_model=DeliveryWorkshopBoardEnvelope, summary="Workshop board")
async def list_workshop_board(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    keyword: Optional[str] = Query(None),
    board_section: Optional[str] = Query(None),
    project_status: Optional[str] = Query(None, alias="status"),
    process_template_id: Optional[int] = Query(None),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.list_workshop_board(
            tenant_id,
            skip=skip,
            limit=limit,
            keyword=keyword,
            board_section=board_section,
            status=project_status,
            process_template_id=process_template_id,
        )
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.patch(
    "/workshop-board/cells",
    response_model=DeliveryWorkshopBoardCell,
    summary="Patch workshop board cell",
)
async def patch_workshop_board_cell(
    body: DeliveryWorkshopBoardCellPatch,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.patch_workshop_board_cell(tenant_id, body, current_user)
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.get("/{project_id:int}/workbench", response_model=DeliveryProjectWorkbenchResponse, summary="Get delivery project workbench")
async def get_project_workbench(
    project_id: int = Path(...),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.get_workbench(tenant_id, project_id)
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))


@router.get(
    "/{project_id:int}/sidelines",
    response_model=DeliveryProjectListEnvelope,
    summary="List sideline delivery projects",
)
async def list_sidelines(
    project_id: int = Path(...),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.list_sidelines(tenant_id, project_id)
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))


@router.post(
    "/{project_id:int}/sidelines",
    response_model=DeliveryProjectResponse,
    summary="Create sideline delivery project",
)
async def create_sideline(
    body: DeliverySidelineCreate,
    project_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.create_sideline(tenant_id, project_id, body, current_user)
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.get("/{project_id:int}", response_model=DeliveryProjectResponse, summary="Get delivery project")
async def get_project(
    project_id: int = Path(...),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.get_project(tenant_id, project_id)
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))


@router.put("/{project_id:int}", response_model=DeliveryProjectResponse, summary="Update delivery project")
async def update_project(
    body: DeliveryProjectUpdate,
    project_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.update_project(tenant_id, project_id, body, current_user)
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.delete("/{project_id:int}", summary="Delete delivery project")
async def delete_project(
    project_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        await _service.delete_project(tenant_id, project_id, current_user)
        return {"success": True}
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))


@router.post("/{project_id:int}/start", response_model=DeliveryProjectResponse, summary="Start delivery project")
async def start_project(
    project_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.start_project(tenant_id, project_id, current_user)
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.post("/{project_id:int}/pause", response_model=DeliveryProjectResponse, summary="Pause delivery project")
async def pause_project(
    project_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.pause_project(tenant_id, project_id, current_user)
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.post("/{project_id:int}/resume", response_model=DeliveryProjectResponse, summary="Resume delivery project")
async def resume_project(
    project_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.resume_project(tenant_id, project_id, current_user)
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.post("/{project_id:int}/cancel", response_model=DeliveryProjectResponse, summary="Cancel delivery project")
async def cancel_project(
    project_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.cancel_project(tenant_id, project_id, current_user)
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.post(
    "/{project_id:int}/complete",
    response_model=DeliveryProjectResponse,
    summary="Complete delivery project",
)
async def complete_project(
    body: DeliveryProjectCompleteRequest,
    project_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.complete_project(
            tenant_id,
            project_id,
            current_user,
            force=body.force,
            reason=body.reason,
        )
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.post(
    "/{project_id:int}/change-template",
    response_model=DeliveryProjectResponse,
    summary="Change delivery project process template",
)
async def change_project_template(
    body: DeliveryProjectChangeTemplateRequest,
    project_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.change_template(
            tenant_id, project_id, body.process_template_id, current_user
        )
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.get(
    "/{project_id:int}/nodes/{node_id:int}/schedule-revisions",
    response_model=list[DeliveryProjectNodeScheduleRevisionResponse],
    summary="List delivery project node schedule revisions",
)
async def list_node_schedule_revisions(
    project_id: int = Path(...),
    node_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.list_node_schedule_revisions(tenant_id, project_id, node_id)
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))


@router.put(
    "/{project_id:int}/nodes/{node_id:int}",
    response_model=DeliveryProjectNodeResponse,
    summary="Update delivery project node",
)
async def update_project_node(
    body: DeliveryProjectNodeUpdate,
    project_id: int = Path(...),
    node_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.update_project_node(tenant_id, project_id, node_id, body, current_user)
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.post(
    "/{project_id:int}/nodes/{node_id:int}/start",
    response_model=DeliveryProjectNodeResponse,
    summary="Start delivery project node",
)
async def start_project_node(
    project_id: int = Path(...),
    node_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.start_project_node(tenant_id, project_id, node_id, current_user)
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.post(
    "/{project_id:int}/nodes/{node_id:int}/complete",
    response_model=DeliveryProjectNodeResponse,
    summary="Complete delivery project node",
)
async def complete_project_node(
    project_id: int = Path(...),
    node_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.complete_project_node(tenant_id, project_id, node_id, current_user)
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.get(
    "/{project_id:int}/node-documents",
    response_model=list[DeliveryProjectNodeDocumentResponse],
    summary="List delivery project node linked documents",
)
async def list_node_documents(
    project_id: int = Path(...),
    node_id: Optional[int] = Query(None),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.list_node_documents(tenant_id, project_id, node_id=node_id)
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))


@router.post(
    "/{project_id:int}/node-documents",
    response_model=DeliveryProjectNodeDocumentResponse,
    summary="Link document to delivery project node",
)
async def link_node_document(
    body: DeliveryProjectNodeDocumentCreate,
    project_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.link_node_document(tenant_id, project_id, body, current_user)
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.delete(
    "/{project_id:int}/node-documents/{link_id:int}",
    summary="Unlink document from delivery project node",
)
async def unlink_node_document(
    project_id: int = Path(...),
    link_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        await _service.unlink_node_document(tenant_id, project_id, link_id, current_user)
        return {"success": True}
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.post(
    "/{project_id:int}/node-tasks",
    response_model=DeliveryProjectNodeTaskResponse,
    summary="Create delivery project node task",
)
async def create_node_task(
    body: DeliveryProjectNodeTaskCreate,
    project_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.create_node_task(tenant_id, project_id, body, current_user)
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.put(
    "/{project_id:int}/node-tasks/{task_id:int}",
    response_model=DeliveryProjectNodeTaskResponse,
    summary="Update delivery project node task",
)
async def update_node_task(
    body: DeliveryProjectNodeTaskUpdate,
    project_id: int = Path(...),
    task_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.update_node_task(tenant_id, project_id, task_id, body, current_user)
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.post(
    "/{project_id:int}/node-tasks/{task_id:int}/participant-action",
    response_model=DeliveryProjectNodeTaskResponse,
    summary="Submit delivery project node task participant action",
)
async def submit_node_task_participant_action(
    body: DeliveryTaskParticipantActionSubmit,
    project_id: int = Path(...),
    task_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        return await _service.submit_node_task_participant_action(
            tenant_id, project_id, task_id, body, current_user
        )
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))


@router.delete(
    "/{project_id:int}/node-tasks/{task_id:int}",
    summary="Delete delivery project node task",
)
async def delete_node_task(
    project_id: int = Path(...),
    task_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    try:
        await _service.delete_node_task(tenant_id, project_id, task_id, current_user)
        return {"success": True}
    except NotFoundError as e:
        raise _http_exception(status.HTTP_404_NOT_FOUND, str(e))
    except ValidationError as e:
        raise _http_exception(status.HTTP_400_BAD_REQUEST, str(e))
