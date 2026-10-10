"""钉钉连接器公共能力（OAuth 唯一真源：IntegrationConfig type=dingtalk）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from core.models.integration_config import IntegrationConfig


@dataclass(frozen=True)
class DingTalkCredentials:
    app_key: str
    app_secret: str
    corpid: str | None = None


async def get_active_dingtalk_integration(tenant_id: int) -> Optional[IntegrationConfig]:
    return (
        await IntegrationConfig.filter(
            tenant_id=tenant_id,
            type="dingtalk",
            is_active=True,
            deleted_at__isnull=True,
        )
        .order_by("-updated_at")
        .first()
    )


async def get_dingtalk_credentials(tenant_id: int) -> Optional[DingTalkCredentials]:
    integration = await get_active_dingtalk_integration(tenant_id)
    if not integration:
        return None
    config: dict[str, Any] = integration.get_config()
    app_key = str(config.get("app_key") or "").strip()
    app_secret = str(config.get("app_secret") or "").strip()
    if not app_key or not app_secret:
        return None
    corpid = str(config.get("corpid") or "").strip() or None
    return DingTalkCredentials(app_key=app_key, app_secret=app_secret, corpid=corpid)
