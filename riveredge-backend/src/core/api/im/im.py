"""IM 会话 API。"""

from fastapi import APIRouter, Depends, Query

from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant, get_current_user
from core.schemas.im import (
    ImConversationListResponse,
    ImConversationResponse,
    ImCreateDirectConversationRequest,
    ImCreateGroupConversationRequest,
    ImMemberListResponse,
    ImMessageListResponse,
    ImMessageResponse,
    ImSendMessageRequest,
    ImSetPinnedRequest,
    ImUpdateGroupConversationRequest,
)
from core.services.im.im_service import ImService
from infra.models.user import User

router = APIRouter(prefix="/im", tags=["Core - IM"])


@router.get("/conversations", response_model=ImConversationListResponse)
async def list_im_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _: None = Depends(require_permission_codes("system:user-message:read", check_abac=False)),
) -> ImConversationListResponse:
    skip = (page - 1) * page_size
    return await ImService.list_conversations(
        tenant_id=tenant_id,
        user_id=current_user.id,
        skip=skip,
        limit=page_size,
    )


@router.post("/conversations/direct", response_model=ImConversationResponse)
async def create_direct_conversation(
    body: ImCreateDirectConversationRequest,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _: None = Depends(require_permission_codes("system:user-message:update", check_abac=False)),
) -> ImConversationResponse:
    conv = await ImService.get_or_create_direct_conversation(
        tenant_id=tenant_id,
        user_id=current_user.id,
        peer_user_id=body.peer_user_id,
    )
    return await ImService.to_conversation_response(
        tenant_id=tenant_id,
        user_id=current_user.id,
        conv=conv,
    )


@router.post("/conversations/group", response_model=ImConversationResponse)
async def create_group_conversation(
    body: ImCreateGroupConversationRequest,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _: None = Depends(require_permission_codes("system:user-message:update", check_abac=False)),
) -> ImConversationResponse:
    conv = await ImService.create_group_conversation(
        tenant_id=tenant_id,
        user_id=current_user.id,
        request=body,
    )
    return await ImService.to_conversation_response(
        tenant_id=tenant_id,
        user_id=current_user.id,
        conv=conv,
    )


@router.patch("/conversations/{conversation_uuid}", response_model=ImConversationResponse)
async def update_group_conversation(
    conversation_uuid: str,
    body: ImUpdateGroupConversationRequest,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _: None = Depends(require_permission_codes("system:user-message:update", check_abac=False)),
) -> ImConversationResponse:
    conv = await ImService.update_group_conversation(
        tenant_id=tenant_id,
        user_id=current_user.id,
        conversation_uuid=conversation_uuid,
        request=body,
    )
    return await ImService.to_conversation_response(
        tenant_id=tenant_id,
        user_id=current_user.id,
        conv=conv,
    )


@router.get(
    "/conversations/{conversation_uuid}/members",
    response_model=ImMemberListResponse,
)
async def list_im_members(
    conversation_uuid: str,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _: None = Depends(require_permission_codes("system:user-message:read", check_abac=False)),
) -> ImMemberListResponse:
    return await ImService.list_members(
        tenant_id=tenant_id,
        user_id=current_user.id,
        conversation_uuid=conversation_uuid,
    )


@router.get(
    "/conversations/{conversation_uuid}/messages",
    response_model=ImMessageListResponse,
)
async def list_im_messages(
    conversation_uuid: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _: None = Depends(require_permission_codes("system:user-message:read", check_abac=False)),
) -> ImMessageListResponse:
    skip = (page - 1) * page_size
    return await ImService.list_messages(
        tenant_id=tenant_id,
        user_id=current_user.id,
        conversation_uuid=conversation_uuid,
        skip=skip,
        limit=page_size,
    )


@router.post(
    "/conversations/{conversation_uuid}/messages",
    response_model=ImMessageResponse,
)
async def send_im_message(
    conversation_uuid: str,
    body: ImSendMessageRequest,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _: None = Depends(require_permission_codes("system:user-message:update", check_abac=False)),
) -> ImMessageResponse:
    return await ImService.send_message(
        tenant_id=tenant_id,
        user_id=current_user.id,
        conversation_uuid=conversation_uuid,
        request=body,
    )


@router.post(
    "/conversations/{conversation_uuid}/messages/{message_uuid}/recall",
    status_code=204,
)
async def recall_im_message(
    conversation_uuid: str,
    message_uuid: str,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _: None = Depends(require_permission_codes("system:user-message:update", check_abac=False)),
) -> None:
    await ImService.recall_message(
        tenant_id=tenant_id,
        user_id=current_user.id,
        conversation_uuid=conversation_uuid,
        message_uuid=message_uuid,
    )


@router.post("/conversations/{conversation_uuid}/read", status_code=204)
async def mark_im_conversation_read(
    conversation_uuid: str,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _: None = Depends(require_permission_codes("system:user-message:update", check_abac=False)),
) -> None:
    await ImService.mark_conversation_read(
        tenant_id=tenant_id,
        user_id=current_user.id,
        conversation_uuid=conversation_uuid,
    )


@router.post("/conversations/{conversation_uuid}/pin", response_model=ImConversationResponse)
async def set_im_conversation_pinned(
    conversation_uuid: str,
    body: ImSetPinnedRequest,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _: None = Depends(require_permission_codes("system:user-message:update", check_abac=False)),
) -> ImConversationResponse:
    conv = await ImService.set_conversation_pinned(
        tenant_id=tenant_id,
        user_id=current_user.id,
        conversation_uuid=conversation_uuid,
        is_pinned=body.is_pinned,
    )
    return await ImService.to_conversation_response(
        tenant_id=tenant_id,
        user_id=current_user.id,
        conv=conv,
    )
