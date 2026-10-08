"""纯工位账号的工位写操作服务端操作员会话门禁（spec 180 T6）。

语义：

- 只有「纯工位账号」（绑定角色全部 role_type=station 且至少一个）才走门禁；
  其他账号直接放行，继续走原有 RBAC 流程——PC 调用行为不变（PC 兼容分支）。
- 纯工位账号必须同时满足：
  (a) 持有 ``kuaizhizao:production-execution-terminal:execute`` 权限
      （走现有 ``ensure_permission_codes`` 判定入口，不自造）；
  (b) 请求头 ``X-Station-Operator-Session`` 能解析出同租户 + 同终端账号的
      active 操作员会话；
  (c) 请求里带 ``workstation_id``（query 或 JSON body 的 ``workstation_id`` /
      ``device_info.workstation_id``）时与会话工位一致，不一致拒绝；
      请求取不到工位字段时以会话绑定为准。
- 拒绝统一返回 403 通用文案，不区分「缺头/坏凭据/错绑定」，不泄露会话与人员细节。
- 只挂写接口（产生业务记录的 POST/DELETE 等）；GET/读取路径不挂此依赖。
- 门禁只验会话与权限，不另行提交业务数据；业务事务仍归原 service。
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import Depends, Header, HTTPException, Request, status

from core.api.deps.access import AuthContext, ensure_permission_codes, get_auth_context
from core.api.deps.deps import get_current_tenant, get_current_user
from core.services.authorization.role_type_policy import is_station_role_type
from infra.models.user import User

from apps.kuaizhizao.services.station_operator_session_service import (
    StationOperatorSessionService,
)

STATION_OPERATOR_SESSION_HEADER = "X-Station-Operator-Session"
STATION_TERMINAL_EXECUTE_PERMISSION = (
    "kuaizhizao:production-execution-terminal:execute"
)
# 拒绝文案保持通用：不区分缺头/坏凭据/跨租户/跨终端/工位不匹配，不泄露会话细节
STATION_OPERATOR_SESSION_DENIED_MESSAGE = "工位写操作需要先确认有效的当前操作员"

operator_session_service = StationOperatorSessionService()


async def is_pure_station_terminal_user(*, user_id: int, tenant_id: int) -> bool:
    """判定当前登录用户是否纯工位账号：绑定角色全部 role_type=station（至少一个）。

    参照 ``role_type_policy.assert_roles_assignment_pure`` 的查法：
    UserRole 按 user_id 取角色集合，Role 按租户 + 未删除过滤后取 role_type。
    """
    from core.models.role import Role
    from core.models.user_role import UserRole

    role_ids = await UserRole.filter(user_id=user_id).values_list("role_id", flat=True)
    if not role_ids:
        return False
    role_types = await Role.filter(
        id__in=list(role_ids),
        tenant_id=tenant_id,
        deleted_at__isnull=True,
    ).values_list("role_type", flat=True)
    return bool(role_types) and all(
        is_station_role_type(role_type) for role_type in role_types
    )


def _coerce_workstation_id(value: Any) -> Optional[int]:
    """宽松取正整数工位 ID；非数字形态一律返回 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
    return None


async def _extract_request_workstation_id(request: Request) -> Optional[int]:
    """按端点实际形态取请求工位字段：query.workstation_id → body.workstation_id
    → body.device_info.workstation_id；取不到返回 None（以会话绑定为准）。

    body 只在 content-type 为 JSON 且解析成功时读取；读取走 Starlette 缓存，
    不影响下游 FastAPI 的 body 解析。
    """
    workstation_id = _coerce_workstation_id(request.query_params.get("workstation_id"))
    if workstation_id is not None:
        return workstation_id
    try:
        body = await request.json()
    except Exception:
        return None
    if not isinstance(body, dict):
        return None
    workstation_id = _coerce_workstation_id(body.get("workstation_id"))
    if workstation_id is not None:
        return workstation_id
    device_info = body.get("device_info")
    if isinstance(device_info, dict):
        return _coerce_workstation_id(device_info.get("workstation_id"))
    return None


async def require_station_operator_session(
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    x_station_operator_session: Optional[str] = Header(
        None, alias=STATION_OPERATOR_SESSION_HEADER
    ),
) -> None:
    """纯工位账号的工位写操作门禁依赖。

    非纯工位账号直接返回（原有 RBAC 不变）；纯工位账号须持 execute 权限 +
    有效操作员会话（工位一致）。门禁不写业务数据。
    """
    if not await is_pure_station_terminal_user(
        user_id=current_user.id, tenant_id=tenant_id
    ):
        # PC 兼容分支：非纯工位账号一律放行原有 RBAC 流程，行为不变
        return

    await ensure_permission_codes(
        auth,
        tenant_id,
        request,
        [STATION_TERMINAL_EXECUTE_PERMISSION],
    )

    workstation_id = await _extract_request_workstation_id(request)
    session = await operator_session_service.get_current_session(
        tenant_id=tenant_id,
        terminal_user_id=current_user.id,
        credential=x_station_operator_session,
        workstation_id=workstation_id,
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=STATION_OPERATOR_SESSION_DENIED_MESSAGE,
        )
