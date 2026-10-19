"""飞书连接器公共能力（OAuth 唯一真源：IntegrationConfig type=feishu）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from core.models.integration_config import IntegrationConfig
from infra.domain.tenant_context import with_tenant


@dataclass(frozen=True)
class FeishuCredentials:
    app_id: str
    app_secret: str


async def get_active_feishu_integration(tenant_id: int) -> Optional[IntegrationConfig]:
    # 公开端点无 ambient 组织上下文，以 with_tenant 显式声明执行域。
    async with with_tenant(int(tenant_id), reason="飞书连接器按组织读取"):
        return (
            await IntegrationConfig.filter(
                tenant_id=tenant_id,
                type="feishu",
                is_active=True,
                deleted_at__isnull=True,
            )
            .order_by("-updated_at")
            .first()
        )


async def get_feishu_credentials(tenant_id: int) -> Optional[FeishuCredentials]:
    integration = await get_active_feishu_integration(tenant_id)
    if not integration:
        return None
    config: dict[str, Any] = integration.get_config()
    app_id = str(config.get("app_id") or "").strip()
    app_secret = str(config.get("app_secret") or "").strip()
    if not app_id or not app_secret:
        return None
    return FeishuCredentials(app_id=app_id, app_secret=app_secret)
