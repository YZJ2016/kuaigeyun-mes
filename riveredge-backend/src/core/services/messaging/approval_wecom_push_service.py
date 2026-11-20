"""审批站内信配套的企微应用消息（走消息配置 push + provider=wecom）。"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from loguru import logger

from core.models.message_config import MessageConfig
from core.schemas.message_template import SendMessageRequest
from core.services.messaging.message_service import MessageService

_WECOM_PROVIDERS = frozenset({"wecom", "wechat_work", "企业微信"})
_UPDATABLE_CARD_ACTIONS = frozenset({"pending", "urge"})


def _config_provider_wecom(config: MessageConfig | None) -> bool:
    if not config:
        return False
    raw = config.config if isinstance(config.config, dict) else {}
    provider = str(raw.get("provider") or raw.get("connection_type") or "").strip().lower()
    return provider in _WECOM_PROVIDERS


def _config_sync_approval_wecom(config: MessageConfig | None) -> bool:
    """消息配置须为企微 push 且勾选 sync_approval_notifications。"""
    if not _config_provider_wecom(config):
        return False
    raw = config.config if isinstance(config.config, dict) else {}
    return bool(raw.get("sync_approval_notifications"))


async def resolve_active_wecom_push_config(tenant_id: int) -> MessageConfig | None:
    """启用且勾选「同步推送审批通知」的企微 push；优先默认渠道，否则最近更新。"""
    rows = await MessageConfig.filter(
        tenant_id=tenant_id,
        type="push",
        is_active=True,
        deleted_at__isnull=True,
    ).order_by("-is_default", "-updated_at")
    for row in rows:
        if _config_sync_approval_wecom(row):
            return row
    return None


def _mobile_approval_public_path(variables: dict[str, Any], *, tenant_id: int) -> str:
    """企微卡片打开手机 H5（Caddy /mobile），带 tenant_id 供 OAuth 自举。"""
    uuid = str(variables.get("approval_instance_uuid") or "").strip()
    if uuid:
        return (
            f"/mobile/approval/detail?uuid={quote(uuid, safe='')}"
            f"&tenant_id={int(tenant_id)}"
        )

    mobile_path = str(variables.get("mobile_path") or variables.get("mobile_route") or "").strip()
    if mobile_path.startswith("/"):
        # Expo 路由组 (tabs)/(auth) 不出现在浏览器 path
        clean = mobile_path.replace("/(tabs)", "").replace("/(auth)", "")
        if not clean.startswith("/"):
            clean = f"/{clean}"
        sep = "&" if "?" in clean else "?"
        return f"/mobile{clean}{sep}tenant_id={int(tenant_id)}"

    return f"/mobile/?tenant_id={int(tenant_id)}"


async def ensure_approval_document_url(
    tenant_id: int,
    variables: dict[str, Any],
) -> None:
    """为企微审批卡片生成手机 H5 打开链接（/mobile，非 PC 组织入口）。"""
    if str(variables.get("document_url") or "").strip():
        return

    from core.services.integration.wecom_public_base_url import resolve_wecom_public_base_url

    origin = await resolve_wecom_public_base_url(tenant_id)
    if not origin:
        return

    variables["document_url"] = f"{origin}{_mobile_approval_public_path(variables, tenant_id=tenant_id)}"


async def send_approval_wecom_push(
    *,
    tenant_id: int,
    user_id: int,
    subject: str,
    content: str,
    variables: dict[str, Any] | None,
    trigger_action: str | None = None,
) -> None:
    """向审批收件人发送企微应用消息；无配置或未绑定 userid 时仅记日志。"""
    push_config = await resolve_active_wecom_push_config(tenant_id)
    if not push_config:
        logger.debug(
            "审批企微推送跳过：租户 {} 无启用且勾选 sync_approval_notifications 的企微 push",
            tenant_id,
        )
        return

    vars_payload = dict(variables or {})
    vars_payload.setdefault("message_category", "approval")
    await ensure_approval_document_url(tenant_id, vars_payload)

    body = (content or subject or "").strip()
    if not body:
        return

    action = str(trigger_action or vars_payload.get("trigger_action") or "pending").strip() or "pending"
    from core.services.messaging.approval_wecom_card_service import (
        parse_approval_instance_id,
        send_and_track_approval_pending_card,
    )

    instance_id = parse_approval_instance_id(vars_payload)
    instance_uuid = str(vars_payload.get("approval_instance_uuid") or "").strip() or None

    # 待审/催办：可更新模板卡（撤回时更新为已失效，避免重复待审堆叠）
    if action in _UPDATABLE_CARD_ACTIONS:
        document_url = str(vars_payload.get("document_url") or "").strip()
        if instance_id and document_url:
            sent = await send_and_track_approval_pending_card(
                tenant_id=tenant_id,
                approval_instance_id=instance_id,
                recipient_user_id=user_id,
                subject=(subject or "待审批").strip()[:200],
                content=body,
                document_url=document_url,
            )
            if sent:
                return
            logger.warning(
                "审批可更新卡发送失败，回落普通 push tenant={} user={} instance={}",
                tenant_id,
                user_id,
                instance_id,
            )

    result = await MessageService.send_message(
        tenant_id,
        SendMessageRequest(
            type="push",
            config_uuid=push_config.uuid,
            recipient=str(user_id),
            subject=(subject or "待审批").strip()[:200],
            content=body,
            variables=vars_payload,
            business_document="approval",
            business_action=action,
            entity_type="approval_instance" if instance_id else None,
            entity_id=instance_id,
            entity_uuid=instance_uuid,
        ),
    )
    if not result.success:
        logger.warning(
            "审批企微推送失败 tenant={} user={} err={}",
            tenant_id,
            user_id,
            result.error,
        )
