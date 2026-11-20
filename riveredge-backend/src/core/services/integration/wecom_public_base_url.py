"""企微卡片 / 部署说明用的公网站点根地址（连接器 base_url → 环境 BASE_URL）。"""

from __future__ import annotations

from typing import Any


def normalize_wecom_public_base_url(raw: Any) -> str:
    """须为 http(s)，去掉末尾斜杠；非法则空串。"""
    text = str(raw or "").strip().rstrip("/")
    if not text:
        return ""
    lower = text.lower()
    if not (lower.startswith("http://") or lower.startswith("https://")):
        return ""
    return text


async def resolve_wecom_public_base_url(tenant_id: int) -> str:
    """
    优先取当前租户启用企微连接器 config.base_url；
    未填再回落环境变量 BASE_URL。
    """
    from core.services.integration.wecom_integration import get_active_wecom_integration
    from infra.config.infra_config import infra_settings

    integration = await get_active_wecom_integration(tenant_id)
    if integration:
        cfg = integration.get_config() if hasattr(integration, "get_config") else {}
        if isinstance(cfg, dict):
            from_conn = normalize_wecom_public_base_url(
                cfg.get("base_url") or cfg.get("public_base_url")
            )
            if from_conn:
                return from_conn
    return normalize_wecom_public_base_url(infra_settings.BASE_URL)
