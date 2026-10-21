"""KU-AI 助手对话历史读写。"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

from infra.exceptions.exceptions import NotFoundError, ValidationError

from core.ai.schemas.kuaiai_conversation import (
    KuAiConversationCreateBody,
    KuAiConversationDetailSchema,
    KuAiConversationListResponse,
    KuAiConversationSummarySchema,
    KuAiStoredMessageSchema,
)
from core.models.kuaiai_assistant_conversation import KuaiaiAssistantConversation
from core.utils.timezone_utils import to_api_isoformat

MAX_CONVERSATIONS_PER_USER = 80
_ALLOWED_ROLES = frozenset({"user", "assistant", "system"})


def _validate_messages(messages: Sequence[KuAiStoredMessageSchema]) -> List[dict[str, Any]]:
    if len(messages) > 500:
        raise ValidationError("单会话消息条数不能超过 500")
    normalized: List[dict[str, Any]] = []
    for item in messages:
        role = item.role.strip()
        if role not in _ALLOWED_ROLES:
            raise ValidationError(f"不支持的消息角色: {role}")
        entry: dict[str, Any] = {"role": role, "content": item.content}
        if item.speaker_name is not None:
            speaker = item.speaker_name.strip()
            if speaker:
                entry["speaker_name"] = speaker
        if item.spoken_at is not None:
            spoken = item.spoken_at.strip()
            if spoken:
                entry["spoken_at"] = spoken
        normalized.append(entry)
    return normalized


def _parse_stored_message(entry: dict[str, Any]) -> Optional[KuAiStoredMessageSchema]:
    role = entry.get("role")
    content = entry.get("content")
    if not isinstance(role, str) or not isinstance(content, str):
        return None
    speaker_name = entry.get("speaker_name")
    spoken_at = entry.get("spoken_at")
    return KuAiStoredMessageSchema(
        role=role,
        content=content,
        speaker_name=speaker_name if isinstance(speaker_name, str) else None,
        spoken_at=spoken_at if isinstance(spoken_at, str) else None,
    )


def _inquirer_name(row: KuaiaiAssistantConversation) -> Optional[str]:
    raw_messages = row.messages if isinstance(row.messages, list) else []
    for entry in raw_messages:
        if not isinstance(entry, dict):
            continue
        role = entry.get("role")
        if role != "user":
            continue
        content = entry.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        speaker_name = entry.get("speaker_name")
        if isinstance(speaker_name, str) and speaker_name.strip():
            return speaker_name.strip()
        return None
    return None


def _last_message_meta(row: KuaiaiAssistantConversation) -> Tuple[Optional[str], Optional[str]]:
    raw_messages = row.messages if isinstance(row.messages, list) else []
    for entry in reversed(raw_messages):
        if not isinstance(entry, dict):
            continue
        content = entry.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        speaker_name = entry.get("speaker_name")
        spoken_at = entry.get("spoken_at")
        return (
            speaker_name if isinstance(speaker_name, str) and speaker_name.strip() else None,
            spoken_at if isinstance(spoken_at, str) and spoken_at.strip() else None,
        )
    return None, None


def _summary(row: KuaiaiAssistantConversation) -> KuAiConversationSummarySchema:
    last_speaker_name, last_spoken_at = _last_message_meta(row)
    return KuAiConversationSummarySchema(
        id=row.uuid,
        title=row.title,
        updated_at=to_api_isoformat(row.updated_at),
        last_speaker_name=last_speaker_name,
        last_spoken_at=last_spoken_at,
        inquirer_name=_inquirer_name(row),
    )


def _detail(row: KuaiaiAssistantConversation) -> KuAiConversationDetailSchema:
    raw_messages = row.messages if isinstance(row.messages, list) else []
    messages: List[KuAiStoredMessageSchema] = []
    for entry in raw_messages:
        if not isinstance(entry, dict):
            continue
        parsed = _parse_stored_message(entry)
        if parsed is not None:
            messages.append(parsed)
    last_speaker_name, last_spoken_at = _last_message_meta(row)
    return KuAiConversationDetailSchema(
        id=row.uuid,
        title=row.title,
        updated_at=to_api_isoformat(row.updated_at),
        messages=messages,
        last_speaker_name=last_speaker_name,
        last_spoken_at=last_spoken_at,
        inquirer_name=_inquirer_name(row),
    )


async def _trim_excess(tenant_id: int, user_id: int) -> None:
    rows = (
        await KuaiaiAssistantConversation.filter(tenant_id=tenant_id, user_id=user_id)
        .order_by("-updated_at")
        .all()
    )
    if len(rows) <= MAX_CONVERSATIONS_PER_USER:
        return
    for stale in rows[MAX_CONVERSATIONS_PER_USER:]:
        await stale.delete()


class KuaiaiConversationService:
    @staticmethod
    async def list_conversations(tenant_id: int, user_id: int) -> KuAiConversationListResponse:
        rows = (
            await KuaiaiAssistantConversation.filter(tenant_id=tenant_id, user_id=user_id)
            .order_by("-updated_at")
            .limit(MAX_CONVERSATIONS_PER_USER)
            .all()
        )
        return KuAiConversationListResponse(items=[_summary(row) for row in rows])

    @staticmethod
    async def get_conversation(
        tenant_id: int,
        user_id: int,
        conversation_uuid: str,
    ) -> KuAiConversationDetailSchema:
        row = await KuaiaiAssistantConversation.get_or_none(
            tenant_id=tenant_id,
            user_id=user_id,
            uuid=conversation_uuid,
        )
        if row is None:
            raise NotFoundError("会话不存在或无权访问")
        return _detail(row)

    @staticmethod
    async def create_conversation(
        tenant_id: int,
        user_id: int,
        body: KuAiConversationCreateBody,
    ) -> KuAiConversationDetailSchema:
        exists = await KuaiaiAssistantConversation.get_or_none(
            tenant_id=tenant_id,
            user_id=user_id,
            uuid=body.id,
        )
        if exists is not None:
            raise ValidationError("会话 ID 已存在")
        messages = _validate_messages(body.messages)
        row = await KuaiaiAssistantConversation.create(
            tenant_id=tenant_id,
            user_id=user_id,
            uuid=body.id,
            title=body.title.strip(),
            messages=messages,
        )
        await _trim_excess(tenant_id, user_id)
        return _detail(row)

    @staticmethod
    async def upsert_conversation(
        tenant_id: int,
        user_id: int,
        conversation_uuid: str,
        *,
        title: str,
        messages: Sequence[KuAiStoredMessageSchema],
    ) -> KuAiConversationDetailSchema:
        normalized = _validate_messages(messages)
        row = await KuaiaiAssistantConversation.get_or_none(
            tenant_id=tenant_id,
            user_id=user_id,
            uuid=conversation_uuid,
        )
        clean_title = title.strip()
        if not clean_title:
            raise ValidationError("会话标题不能为空")
        if row is None:
            row = await KuaiaiAssistantConversation.create(
                tenant_id=tenant_id,
                user_id=user_id,
                uuid=conversation_uuid,
                title=clean_title,
                messages=normalized,
            )
        else:
            row.title = clean_title
            row.messages = normalized
            await row.save(update_fields=["title", "messages", "updated_at"])
        await _trim_excess(tenant_id, user_id)
        return _detail(row)

    @staticmethod
    async def delete_conversation(
        tenant_id: int,
        user_id: int,
        conversation_uuid: str,
    ) -> None:
        deleted = await KuaiaiAssistantConversation.filter(
            tenant_id=tenant_id,
            user_id=user_id,
            uuid=conversation_uuid,
        ).delete()
        if deleted == 0:
            raise NotFoundError("会话不存在或无权访问")

    @staticmethod
    async def import_conversations(
        tenant_id: int,
        user_id: int,
        items: Sequence[KuAiConversationCreateBody],
    ) -> KuAiConversationListResponse:
        if not items:
            return await KuaiaiConversationService.list_conversations(tenant_id, user_id)
        for body in items:
            existing = await KuaiaiAssistantConversation.get_or_none(
                tenant_id=tenant_id,
                user_id=user_id,
                uuid=body.id,
            )
            messages = _validate_messages(body.messages)
            title = body.title.strip()
            if not title:
                raise ValidationError("会话标题不能为空")
            if existing is None:
                await KuaiaiAssistantConversation.create(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    uuid=body.id,
                    title=title,
                    messages=messages,
                )
            else:
                existing.title = title
                existing.messages = messages
                await existing.save(update_fields=["title", "messages", "updated_at"])
        await _trim_excess(tenant_id, user_id)
        return await KuaiaiConversationService.list_conversations(tenant_id, user_id)
