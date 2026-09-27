"""kuaiai 路由权限依赖。

kuaiai 权限码动作（list|query|add|edit|remove）不在 STANDARD_ACTIONS 内，
require_permission_codes 装配期 validate 会拒绝；上游已废止 require_access。
此处保留旧 require_access 语义：required_permissions 走 RBAC 精确匹配，
resource/action 仅供 ABAC 策略（存在匹配策略时才叠加判定）。
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, Request, status

from core.api.deps.access import (
    AuthContext,
    _make_error,
    get_auth_context,
)
from core.api.deps.deps import get_current_tenant
from core.services.authorization.access_control_service import AccessControlService


def require_kuaiai(permission_code: str):
    """等价旧 require_access("kuaiai.<domain>", "<verb>", required_permissions=[code])。"""
    parts = [p.strip() for p in (permission_code or "").split(":") if p.strip()]
    if len(parts) != 3 or parts[0] != "kuaiai":
        raise ValueError(f"无效 kuaiai 权限码：{permission_code!r}")
    resource = f"{parts[0]}.{parts[1]}"
    action = parts[2]
    required_permissions = [permission_code]

    async def dependency(
        request: Request,
        auth: AuthContext = Depends(get_auth_context),
        tenant_id: Optional[int] = Depends(get_current_tenant),
    ) -> AuthContext:
        if tenant_id is None:
            _make_error(
                http_status=status.HTTP_400_BAD_REQUEST,
                code="TENANT_CONTEXT_REQUIRED",
                message="组织上下文未设置",
                request_id=auth.request_id,
                reason="missing_tenant",
            )
        env = {
            "method": request.method,
            "path": request.url.path,
            "client_ip": request.client.host if request.client else None,
        }
        decision = await AccessControlService.check_access(
            user_id=auth.user_id,
            tenant_id=tenant_id,
            resource=resource,
            action=action,
            is_infra_admin=auth.is_infra_admin,
            is_tenant_admin=auth.is_tenant_admin,
            check_abac=True,
            required_permissions=required_permissions,
            env=env,
        )
        if not decision.allowed:
            _make_error(
                http_status=status.HTTP_403_FORBIDDEN,
                code="ACCESS_DENIED",
                message="权限不足",
                request_id=auth.request_id,
                reason=decision.reason,
                required=decision.required,
            )
        auth.tenant_id = tenant_id
        return auth

    return dependency
