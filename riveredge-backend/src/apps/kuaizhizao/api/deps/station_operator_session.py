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
      显式携带但无法解析为正整数同样拒绝；
      请求取不到工位字段时以会话绑定为准。
- 拒绝统一返回 403 通用文案，不区分「缺头/坏凭据/错绑定」，不泄露会话与人员细节。
- 只挂写接口（产生业务记录的 POST/DELETE 等）；GET/读取路径不挂此依赖。
- 门禁只验会话与权限，不另行提交业务数据；业务事务仍归原 service。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
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


@dataclass(frozen=True)
class StationBusinessOperator:
    """写入业务记录的可信操作员；登录账号仍只负责认证与权限。"""

    user_id: int
    user_name: str
    user: Optional[User]


# ---------------------------------------------------------------------------
# 工位写闭包：纯工位账号 + 有效操作员会话才允许执行的写 URL（路由内注册形态，
# 不含 /api/v1/apps/kuaizhizao 前缀）。
# 唯一真源——tests/apps/kuaizhizao/api/test_station_operator_write_gate.py 的
# 断言清单由本表推导，路由鉴权归一（_kuaizhizao_route_access）同样引用本表，
# 禁止在别处复制第二份清单。
# ---------------------------------------------------------------------------
GATED_WRITE_URL_MANIFEST: tuple[tuple[str, str], ...] = (
    # execution/api.ts —— 开工 / 撤回开工 / 暂停 / 恢复 / 完工 / 设备上下机
    ("POST", "/work-orders/{work_order_id}/operations/{operation_id}/start"),
    ("POST", "/work-orders/{work_order_id}/operations/{operation_id}/withdraw-start"),
    ("POST", "/work-orders/{work_order_id}/operations/{operation_id}/pause"),
    ("POST", "/work-orders/{work_order_id}/operations/{operation_id}/resume"),
    ("POST", "/work-orders/{work_order_id}/operations/{operation_id}/complete"),
    ("POST", "/work-orders/{work_order_id}/operations/{operation_id}/machine-session"),
    # reporting/StationReportingPage.tsx —— 快速报工 / 投料 / 下料 / 报废 / 不良
    ("POST", "/reporting/quick"),
    ("POST", "/reporting/{record_id}/material-binding/feeding"),
    ("POST", "/reporting/{record_id}/material-binding/discharging"),
    ("POST", "/reporting/{record_id}/scrap"),
    ("POST", "/reporting/{record_id}/defect"),
    # andon/api.ts —— 安灯发起 / 响应 / 关闭 / 取消
    ("POST", "/station/andon"),
    ("POST", "/station/andon/{andon_id}/acknowledge"),
    ("POST", "/station/andon/{andon_id}/close"),
    ("POST", "/station/andon/{andon_id}/cancel"),
    # execution/api.ts acknowledgeSop —— SOP 确认
    ("POST", "/station/sop-acknowledgments"),
    # face/api.ts —— 交接确认 / 刷脸登记 / 刷脸删除
    ("POST", "/station/shift-handover"),
    ("POST", "/station/face-templates"),
    ("DELETE", "/station/face-templates/{template_id}"),
    # 产生资质记录的写（当前前端未调用，防御性收口）
    ("POST", "/station/operator-skills"),
)

# 确认流前置调用：刷脸比对 / 上岗资质检查 / 会话签发与关闭。
# 不挂会话门禁（会话生命周期本身），但纯工位账号必须可达——
# 路由鉴权同样归一到 production-execution-terminal:execute。
STATION_EXECUTE_PRECHECK_URLS: tuple[tuple[str, str], ...] = (
    ("POST", "/station/face-identify"),
    ("POST", "/station/skill-check"),
    ("POST", "/station/operator-session/confirm"),
    ("POST", "/station/operator-session/close"),
)


def _compile_url_template(template: str) -> "re.Pattern[str]":
    """把 ``/a/{id}/b`` 模板编译成尾缀匹配正则（``{param}`` → ``[^/]+``）。"""
    segments = re.split(r"\{[^}/]+\}", template)
    pattern = "[^/]+".join(re.escape(seg) for seg in segments)
    return re.compile(pattern + r"/?$", re.IGNORECASE)


_STATION_TERMINAL_EXECUTE_URLS: tuple[tuple[str, "re.Pattern[str]"], ...] = tuple(
    (method, _compile_url_template(template))
    for method, template in (
        *GATED_WRITE_URL_MANIFEST,
        *STATION_EXECUTE_PRECHECK_URLS,
    )
)


def is_station_terminal_execute_path(method: str, path: str) -> bool:
    """请求是否属于工位写闭包或确认流前置端点。

    尾缀匹配（模板本身以 ``/`` 开头，避免 ``/rework-orders`` 误命中
    ``/work-orders``），兼容 ``/api/v1/apps/kuaizhizao`` 前缀路径。
    """
    m = (method or "").upper()
    p = path or ""
    if not m or not p:
        return False
    return any(
        m == allowed_method and pattern.search(p) is not None
        for allowed_method, pattern in _STATION_TERMINAL_EXECUTE_URLS
    )


async def is_pure_station_terminal_user(*, user_id: int, tenant_id: int) -> bool:
    """判定当前登录用户是否纯工位账号：绑定角色全部 role_type=station（至少一个）。

    参照 ``role_type_policy.assert_roles_assignment_pure`` 的查法：
    UserRole 按 user_id 取角色集合，Role 按租户 + 未删除 + 启用过滤后取
    role_type——已停用角色不计入纯度（与权限判定口径一致）。
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
        is_active=True,
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
            coerced = int(text)
            return coerced if coerced > 0 else None
    return None


def _require_valid_workstation_id(raw: Any) -> int:
    """显式携带的工位字段必须解析为正整数；非法值按工位不匹配统一拒绝。"""
    workstation_id = _coerce_workstation_id(raw)
    if workstation_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=STATION_OPERATOR_SESSION_DENIED_MESSAGE,
        )
    return workstation_id


async def _extract_request_workstation_id(request: Request) -> Optional[int]:
    """按端点实际形态取请求工位字段：query.workstation_id → body.workstation_id
    → body.device_info.workstation_id；取不到返回 None（以会话绑定为准）。

    区分「字段缺失」与「字段存在但非法」：显式携带 workstation_id 却不能解析
    为正整数（0、负数、非数字、布尔等）时按工位不匹配拒绝，不再回落会话绑定。

    body 只在 content-type 为 JSON 且解析成功时读取；读取走 Starlette 缓存，
    不影响下游 FastAPI 的 body 解析。
    """
    raw = request.query_params.get("workstation_id")
    if raw is not None:
        return _require_valid_workstation_id(raw)
    try:
        body = await request.json()
    except Exception:
        return None
    if not isinstance(body, dict):
        return None
    raw = body.get("workstation_id")
    if raw is not None:
        return _require_valid_workstation_id(raw)
    device_info = body.get("device_info")
    if isinstance(device_info, dict) and device_info.get("workstation_id") is not None:
        return _require_valid_workstation_id(device_info.get("workstation_id"))
    return None


async def require_station_operator_session(
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    x_station_operator_session: Optional[str] = Header(
        None, alias=STATION_OPERATOR_SESSION_HEADER
    ),
) -> Optional[Any]:
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
    # 供下游处理器（如快捷报工本人/小组边界）复用已解析会话，避免二次解析
    request.state.station_operator_session = session
    return session


async def get_station_business_operator(
    current_user: User = Depends(get_current_user),
    station_session: Optional[Any] = Depends(require_station_operator_session),
) -> StationBusinessOperator:
    """统一解析业务操作员：工位取确认会话，PC 保持当前登录用户。"""
    if station_session is not None:
        return StationBusinessOperator(
            user_id=int(station_session.operator_user_id),
            user_name=str(station_session.operator_name),
            user=None,
        )
    return StationBusinessOperator(
        user_id=int(current_user.id),
        user_name=current_user.full_name or current_user.username,
        user=current_user,
    )


async def get_optional_station_business_operator(
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    x_station_operator_session: Optional[str] = Header(
        None, alias=STATION_OPERATOR_SESSION_HEADER
    ),
) -> StationBusinessOperator:
    """只读接口可借有效凭据识别操作员，缺失或无效时保持原 PC 行为。

    仅纯工位账号按会话解析操作员；非纯工位账号即使带了有效凭据头也直接
    回落 current_user——归属不随凭据切换。
    """
    session = None
    if x_station_operator_session and await is_pure_station_terminal_user(
        user_id=current_user.id, tenant_id=tenant_id
    ):
        session = await operator_session_service.get_current_session(
            tenant_id=tenant_id,
            terminal_user_id=current_user.id,
            credential=x_station_operator_session,
            workstation_id=None,
        )
    if session is not None:
        return StationBusinessOperator(
            user_id=int(session.operator_user_id),
            user_name=str(session.operator_name),
            user=None,
        )
    return StationBusinessOperator(
        user_id=int(current_user.id),
        user_name=current_user.full_name or current_user.username,
        user=current_user,
    )


def ensure_station_operator_matches(
    operator: StationBusinessOperator, *, submitted_user_id: Optional[int]
) -> None:
    """工位请求不得把业务人员字段指向当前确认操作员之外的用户。"""
    if (
        operator.user is None
        and submitted_user_id is not None
        and int(submitted_user_id) != operator.user_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=STATION_OPERATOR_SESSION_DENIED_MESSAGE,
        )
