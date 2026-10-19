"""钉钉连接器公共能力（OAuth 唯一真源：IntegrationConfig type=dingtalk）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from core.models.integration_config import IntegrationConfig
from infra.domain.tenant_context import with_tenant


@dataclass(frozen=True)
class DingTalkCredentials:
    app_key: str
    app_secret: str
    corpid: str | None = None


async def get_active_dingtalk_integration(tenant_id: int) -> Optional[IntegrationConfig]:
    # 公开端点无 ambient 组织上下文，以 with_tenant 显式声明执行域。
    async with with_tenant(int(tenant_id), reason="钉钉连接器按组织读取"):
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
