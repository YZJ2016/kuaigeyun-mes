"""纯工位账号工位写操作服务端操作员会话门禁（spec 180 T6）。

覆盖：
- 写 URL 清单完整性：工位前端实际调用的全部写 URL 都挂了组合门禁依赖；
- 门禁行为：无头/坏头/错绑定（跨租户、跨终端账号、工位不匹配）拒绝，
  有效头放行，PC（非纯 station）账号不受影响；
- 只读 GET 路径不挂门禁、无头仍可访问；
- 路由级鉴权归一：纯工位账号命中闭包/前置端点时所需权限为 terminal:execute；
  纯工位账号对清单外的写方法（非 GET/HEAD/OPTIONS）一律默认拒写 403；
  非纯工位账号与所有 GET 路径完全走原 URL→action 映射。
"""

import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from apps.kuaizhizao.api import _kuaizhizao_route_access as route_access_mod
from apps.kuaizhizao.api.deps import station_operator_session as gate_mod
from apps.kuaizhizao.api.productions import reporting as reporting_api
from apps.kuaizhizao.api.productions import work_orders as work_orders_api
from apps.kuaizhizao.api.station import station as station_api

# ---------------------------------------------------------------------------
# 写 URL 清单：唯一真源在 deps/station_operator_session.py 的
# GATED_WRITE_URL_MANIFEST（路由鉴权归一同样引用），这里只补路由归属。
# path 为路由文件内注册形态（对外前缀 /api/v1/apps/kuaizhizao）。
# ---------------------------------------------------------------------------


def _router_for_gated_path(path: str):
    if path.startswith("/work-orders/"):
        return work_orders_api.router
    if path.startswith("/reporting/"):
        return reporting_api.router
    if path.startswith("/station/"):
        return station_api.router
    raise AssertionError(f"工位写 URL 未映射到路由：{path}")


GATED_WRITE_URL_MANIFEST = [
    (method, path, _router_for_gated_path(path), path)
    for method, path in gate_mod.GATED_WRITE_URL_MANIFEST
]

# 明确不挂门禁的接口：会话生命周期本身、刷脸比对（确认流程前置）与只读检查
UNGATED_URL_MANIFEST = [
    ("POST", "/station/face-identify", station_api.router, "刷脸比对（确认前置）"),
    ("POST", "/station/skill-check", station_api.router, "上岗资质检查（只读）"),
    ("POST", "/station/operator-session/confirm", station_api.router, "会话签发"),
    ("POST", "/station/operator-session/close", station_api.router, "会话关闭"),
    ("GET", "/station/operator-session/current", station_api.router, "会话状态"),
    ("GET", "/station/andon", station_api.router, "安灯列表"),
    ("GET", "/station/andon/open", station_api.router, "未结安灯"),
    ("GET", "/station/sop-acknowledgments/check", station_api.router, "SOP 确认查询"),
    ("GET", "/station/face-templates/me", station_api.router, "我的人脸模板"),
    ("GET", "/station/operator-skills", station_api.router, "资质列表"),
    ("GET", "/station/shift-summary", station_api.router, "交接汇总"),
]


def _walk_dependants(dep):
    """递归遍历 FastAPI dependant 树。"""
    yield dep
    for sub in dep.dependencies:
        yield from _walk_dependants(sub)


def _route_has_gate(route) -> bool:
    return any(
        dep.call is gate_mod.require_station_operator_session
        for dep in _walk_dependants(route.dependant)
    )


def _find_route(router, method: str, path: str):
    for route in router.routes:
        if route.path == path and method in (route.methods or set()):
            return route
    return None


@pytest.mark.parametrize(
    "method,path,router,label",
    GATED_WRITE_URL_MANIFEST,
    ids=[f"{m} {p}" for m, p, _r, _l in GATED_WRITE_URL_MANIFEST],
)
def test_manifest_write_url_has_session_gate(method, path, router, label):
    """清单内每个工位写 URL 必须存在且挂了操作员会话门禁依赖。"""
    route = _find_route(router, method, path)
    assert route is not None, f"路由不存在：{method} {path}（{label}）"
    assert _route_has_gate(route), f"{method} {path}（{label}）未挂会话门禁"


@pytest.mark.parametrize(
    "method,path,router,label",
    UNGATED_URL_MANIFEST,
    ids=[f"{m} {p}" for m, p, _r, _l in UNGATED_URL_MANIFEST],
)
def test_read_and_session_routes_have_no_gate(method, path, router, label):
    """GET/读取路径与会话生命周期接口不挂门禁——无头仍可访问。"""
    route = _find_route(router, method, path)
    assert route is not None, f"路由不存在：{method} {path}（{label}）"
    assert not _route_has_gate(route), f"{method} {path}（{label}）不应挂会话门禁"


def test_all_station_get_routes_ungated():
    """station 路由下所有 GET 一律不挂门禁（未确认也可查看任务资料）。"""
    for route in station_api.router.routes:
        if "GET" in (route.methods or set()):
            assert not _route_has_gate(route), f"GET {route.path} 不应挂会话门禁"


# ---------------------------------------------------------------------------
# 门禁行为测试：直接调用依赖函数（与既有测试风格一致，不经过 HTTP 层）
# ---------------------------------------------------------------------------

_NO_BODY = object()


def _request(*, method="POST", path="/apps/kuaizhizao/station/andon", query=None, json_body=_NO_BODY):
    request = MagicMock()
    request.method = method
    request.url = SimpleNamespace(path=path)
    request.query_params = query or {}
    request.headers = {}
    request.client = None
    if json_body is _NO_BODY:
        request.json = AsyncMock(side_effect=Exception("no json body"))
    else:
        request.json = AsyncMock(return_value=json_body)
    return request


def _station_user(user_id: int = 7):
    return SimpleNamespace(
        id=user_id, tenant_id=1, username="terminal", full_name="终端账号"
    )


def _auth():
    return SimpleNamespace(
        user_id=7, tenant_id=1, is_infra_admin=False, is_tenant_admin=False, request_id="r-1"
    )


def _session(**kw):
    base = {"id": 1, "workstation_id": 5, "status": "active"}
    base.update(kw)
    return SimpleNamespace(**base)


def _patch_pure_station(monkeypatch, is_pure: bool):
    monkeypatch.setattr(
        gate_mod,
        "is_pure_station_terminal_user",
        AsyncMock(return_value=is_pure),
    )


def _patch_permission(monkeypatch, allow: bool = True):
    mock = AsyncMock(
        side_effect=None if allow else HTTPException(status_code=403, detail="权限不足")
    )
    monkeypatch.setattr(gate_mod, "ensure_permission_codes", mock)
    return mock


def _patch_session(monkeypatch, session):
    mock = AsyncMock(return_value=session)
    monkeypatch.setattr(
        gate_mod.operator_session_service, "get_current_session", mock
    )
    return mock


async def _run_gate(request, *, credential="cred", user=None, auth=None, tenant_id=1):
    return await gate_mod.require_station_operator_session(
        request=request,
        auth=auth or _auth(),
        current_user=user or _station_user(),
        tenant_id=tenant_id,
        x_station_operator_session=credential,
    )


@pytest.mark.asyncio
async def test_pc_user_bypasses_gate(monkeypatch):
    """非纯工位账号：不查权限、不查会话，直接放行（PC 兼容分支行为不变）。"""
    _patch_pure_station(monkeypatch, False)
    perm = _patch_permission(monkeypatch, allow=False)
    session = _patch_session(monkeypatch, None)

    result = await _run_gate(_request(), credential=None)

    assert result is None
    perm.assert_not_awaited()
    session.assert_not_awaited()


@pytest.mark.asyncio
async def test_station_user_valid_session_passes(monkeypatch):
    """纯工位账号 + execute 权限 + 有效会话 → 放行。"""
    _patch_pure_station(monkeypatch, True)
    perm = _patch_permission(monkeypatch)
    session = _patch_session(monkeypatch, _session())

    result = await _run_gate(
        _request(json_body={"call_type": "quality", "workstation_id": 5}),
        credential="cred",
    )

    assert result is session.return_value
    perm.assert_awaited_once()
    assert perm.await_args.args[3] == [gate_mod.STATION_TERMINAL_EXECUTE_PERMISSION]
    assert session.await_args.kwargs["credential"] == "cred"
    assert session.await_args.kwargs["tenant_id"] == 1
    assert session.await_args.kwargs["terminal_user_id"] == 7
    assert session.await_args.kwargs["workstation_id"] == 5


@pytest.mark.asyncio
async def test_business_operator_uses_confirmed_operator_for_station_session():
    """工位写入的业务归属必须来自已确认会话，不能继续使用共享终端账号。"""
    actor = await gate_mod.get_station_business_operator(
        current_user=_station_user(),
        station_session=_session(operator_user_id=99, operator_name="操作员甲"),
    )

    assert actor.user_id == 99
    assert actor.user_name == "操作员甲"
    assert actor.user is None


@pytest.mark.asyncio
async def test_business_operator_keeps_current_user_for_pc_request():
    """PC 兼容分支没有工位会话时，业务归属保持当前登录用户。"""
    current_user = _station_user()

    actor = await gate_mod.get_station_business_operator(
        current_user=current_user,
        station_session=None,
    )

    assert actor.user_id == 7
    assert actor.user_name == "终端账号"
    assert actor.user is current_user


def test_station_payload_operator_mismatch_is_rejected():
    """工位请求体中的人员 ID 不得冒用已确认操作员之外的用户。"""
    actor = gate_mod.StationBusinessOperator(
        user_id=99, user_name="操作员甲", user=None
    )

    with pytest.raises(HTTPException) as raised:
        gate_mod.ensure_station_operator_matches(actor, submitted_user_id=88)

    assert raised.value.status_code == 403
    assert raised.value.detail == gate_mod.STATION_OPERATOR_SESSION_DENIED_MESSAGE


def test_pc_payload_operator_is_not_restricted_by_station_session_rule():
    """PC 用户原有代维护能力不受工位操作员匹配规则影响。"""
    current_user = _station_user()
    actor = gate_mod.StationBusinessOperator(
        user_id=7, user_name="终端账号", user=current_user
    )

    gate_mod.ensure_station_operator_matches(actor, submitted_user_id=88)


@pytest.mark.asyncio
async def test_optional_business_operator_uses_valid_header_without_gating_get(
    monkeypatch,
):
    """只读接口携带有效凭据时识别实际操作员，但缺头仍保持原有可读行为。"""
    _patch_pure_station(monkeypatch, True)
    get_current = _patch_session(
        monkeypatch,
        _session(operator_user_id=99, operator_name="操作员甲"),
    )

    actor = await gate_mod.get_optional_station_business_operator(
        current_user=_station_user(),
        tenant_id=1,
        x_station_operator_session="cred",
    )

    assert actor.user_id == 99
    assert actor.user_name == "操作员甲"
    get_current.assert_awaited_once_with(
        tenant_id=1,
        terminal_user_id=7,
        credential="cred",
        workstation_id=None,
    )


@pytest.mark.asyncio
async def test_optional_business_operator_ignores_header_for_non_station_user(
    monkeypatch,
):
    """非纯工位账号（PC）带有效凭据头也不切换归属：仍读到自己（face-templates/me
    的唯一消费场景）。"""
    _patch_pure_station(monkeypatch, False)
    get_current = _patch_session(
        monkeypatch,
        _session(operator_user_id=99, operator_name="操作员甲"),
    )
    current_user = _station_user()

    actor = await gate_mod.get_optional_station_business_operator(
        current_user=current_user,
        tenant_id=1,
        x_station_operator_session="cred",
    )

    assert actor.user_id == 7
    assert actor.user_name == "终端账号"
    assert actor.user is current_user
    get_current.assert_not_awaited()


@pytest.mark.asyncio
async def test_station_user_missing_header_rejected(monkeypatch):
    """纯工位账号无 X-Station-Operator-Session 头 → 403。"""
    _patch_pure_station(monkeypatch, True)
    _patch_permission(monkeypatch)
    _patch_session(monkeypatch, None)

    with pytest.raises(HTTPException) as raised:
        await _run_gate(_request(json_body={"workstation_id": 5}), credential=None)
    assert raised.value.status_code == 403


@pytest.mark.asyncio
async def test_station_user_bad_credential_rejected(monkeypatch):
    """坏凭据（含跨租户/跨终端账号命中不了会话）→ 403 通用文案。"""
    _patch_pure_station(monkeypatch, True)
    _patch_permission(monkeypatch)
    _patch_session(monkeypatch, None)

    with pytest.raises(HTTPException) as raised:
        await _run_gate(_request(json_body={"workstation_id": 5}), credential="stolen")
    assert raised.value.status_code == 403
    assert raised.value.detail == gate_mod.STATION_OPERATOR_SESSION_DENIED_MESSAGE


@pytest.mark.asyncio
async def test_station_user_workstation_mismatch_rejected(monkeypatch):
    """请求工位与会话绑定工位不一致 → 服务返回 None → 403。

    这里模拟服务行为：workstation_id 传入且与绑定不一致时命中失败。
    """
    _patch_pure_station(monkeypatch, True)
    _patch_permission(monkeypatch)

    async def fake_resolve(*, tenant_id, terminal_user_id, credential, workstation_id):
        bound = _session(workstation_id=5)
        if credential != "cred" or workstation_id is not None and workstation_id != bound.workstation_id:
            return None
        return bound

    monkeypatch.setattr(
        gate_mod.operator_session_service, "get_current_session", fake_resolve
    )

    with pytest.raises(HTTPException) as raised:
        await _run_gate(
            _request(json_body={"workstation_id": 9}), credential="cred"
        )
    assert raised.value.status_code == 403


@pytest.mark.asyncio
async def test_gate_passes_tenant_and_terminal_binding(monkeypatch):
    """跨租户/跨终端账号：门禁把 tenant_id 与 current_user.id 原样传给会话解析。"""
    _patch_pure_station(monkeypatch, True)
    _patch_permission(monkeypatch)
    session = _patch_session(monkeypatch, None)

    with pytest.raises(HTTPException):
        await _run_gate(
            _request(json_body={"workstation_id": 5}),
            credential="cred",
            user=_station_user(user_id=7),
            tenant_id=1,
        )
    kwargs = session.await_args.kwargs
    assert kwargs["tenant_id"] == 1
    assert kwargs["terminal_user_id"] == 7


@pytest.mark.asyncio
async def test_station_user_without_execute_permission_denied(monkeypatch):
    """纯工位账号但无 execute 权限 → 权限层拒绝，且不查会话。"""
    _patch_pure_station(monkeypatch, True)
    _patch_permission(monkeypatch, allow=False)
    session = _patch_session(monkeypatch, _session())

    with pytest.raises(HTTPException) as raised:
        await _run_gate(
            _request(json_body={"workstation_id": 5}), credential="cred"
        )
    assert raised.value.status_code == 403
    session.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "request_kwargs,expected_ws",
    [
        ({"query": {"workstation_id": "5"}}, 5),  # query 参数
        ({"json_body": {"workstation_id": 5}}, 5),  # body.workstation_id
        ({"json_body": {"device_info": {"workstation_id": 5}}}, 5),  # device_info 嵌套
        ({"json_body": {"device_info": "station-pc-01"}}, None),  # 字符串 device_info 不取
        ({"json_body": {"reason_code": "break"}}, None),  # 无工位字段 → 会话绑定为准
        ({}, None),  # 无 body（如 DELETE）→ 会话绑定为准
        ({"json_body": "not-a-dict"}, None),  # 非 dict body
    ],
)
async def test_workstation_id_extraction(monkeypatch, request_kwargs, expected_ws):
    """工位一致性取数口径：query > body.workstation_id > body.device_info.workstation_id。"""
    _patch_pure_station(monkeypatch, True)
    _patch_permission(monkeypatch)
    session = _patch_session(monkeypatch, _session())

    await _run_gate(_request(**request_kwargs), credential="cred")
    assert session.await_args.kwargs["workstation_id"] == expected_ws


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "request_kwargs",
    [
        {"query": {"workstation_id": "abc"}},  # query 非数字
        {"query": {"workstation_id": "0"}},  # query 零
        {"json_body": {"workstation_id": 0}},  # body 零
        {"json_body": {"workstation_id": -3}},  # body 负数
        {"json_body": {"workstation_id": "x5"}},  # body 非数字
        {"json_body": {"workstation_id": True}},  # body 布尔
        {"json_body": {"device_info": {"workstation_id": "oops"}}},  # device_info 非法
        {"json_body": {"device_info": {"workstation_id": -1}}},  # device_info 负数
    ],
    ids=[
        "query-non-numeric",
        "query-zero",
        "body-zero",
        "body-negative",
        "body-non-numeric",
        "body-bool",
        "device-info-non-numeric",
        "device-info-negative",
    ],
)
async def test_invalid_explicit_workstation_id_rejected(monkeypatch, request_kwargs):
    """显式携带 workstation_id 但无法解析为正整数 → 按工位不匹配统一 403，
    不再回落「未携带以会话绑定为准」。"""
    _patch_pure_station(monkeypatch, True)
    _patch_permission(monkeypatch)
    session = _patch_session(monkeypatch, _session())

    with pytest.raises(HTTPException) as raised:
        await _run_gate(_request(**request_kwargs), credential="cred")

    assert raised.value.status_code == 403
    assert raised.value.detail == gate_mod.STATION_OPERATOR_SESSION_DENIED_MESSAGE
    session.assert_not_awaited()


# ---------------------------------------------------------------------------
# is_pure_station_terminal_user 纯度判定
# ---------------------------------------------------------------------------


def _qs_mock(values):
    qs = MagicMock()
    qs.values_list = AsyncMock(return_value=values)
    return qs


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role_ids,role_types,expected",
    [
        ([11], ["station"], True),  # 纯 station
        ([11, 12], ["station", "station"], True),  # 多个纯 station
        ([11, 12], ["station", "internal"], False),  # 混挂（数据层已禁止，防御）
        ([11], ["internal"], False),  # PC 内部角色
        ([11], ["external"], False),  # 外部角色
        ([], [], False),  # 无角色绑定
        ([11], [], False),  # 角色已删除/非本租户 → 查询为空
    ],
)
async def test_pure_station_detection(monkeypatch, role_ids, role_types, expected):
    from core.models.role import Role
    from core.models.user_role import UserRole

    monkeypatch.setattr(UserRole, "filter", MagicMock(return_value=_qs_mock(role_ids)))
    monkeypatch.setattr(Role, "filter", MagicMock(return_value=_qs_mock(role_types)))

    result = await gate_mod.is_pure_station_terminal_user(user_id=7, tenant_id=1)
    assert result is expected


@pytest.mark.asyncio
async def test_pure_station_detection_filters_inactive_roles(monkeypatch):
    """角色查询带 is_active=True：只绑定已停用 station 角色的用户判为非纯工位，
    与权限判定口径一致。"""
    from core.models.role import Role
    from core.models.user_role import UserRole

    role_filter = MagicMock(return_value=_qs_mock([]))
    monkeypatch.setattr(UserRole, "filter", MagicMock(return_value=_qs_mock([11])))
    monkeypatch.setattr(Role, "filter", role_filter)

    result = await gate_mod.is_pure_station_terminal_user(user_id=7, tenant_id=1)

    assert result is False
    assert role_filter.call_args.kwargs["is_active"] is True


# ---------------------------------------------------------------------------
# 路由级鉴权归一：纯工位账号命中工位写闭包/确认流前置端点时，
# 所需权限归一为 kuaizhizao:production-execution-terminal:execute（真实注册码，
# 不 mock 注册表）；其他用户与其他路径完全走原 URL→action 映射。
# ---------------------------------------------------------------------------

_STATION_EXECUTE_ALL_URLS = [
    *gate_mod.GATED_WRITE_URL_MANIFEST,
    *gate_mod.STATION_EXECUTE_PRECHECK_URLS,
]


def _concrete_path(template: str) -> str:
    return re.sub(r"\{[^}/]+\}", "1", template)


def _route_access_dep(path: str):
    """按闭包 URL 归属返回对应的路由级鉴权依赖。"""
    if path.startswith("/work-orders/"):
        return route_access_mod.require_kuaizhizao_work_order_access()
    if path.startswith("/reporting/"):
        return route_access_mod.require_kuaizhizao_productions_access()
    if path.startswith("/station/"):
        return route_access_mod.require_kuaizhizao_module_access(
            "production-execution-terminal"
        )
    raise AssertionError(f"未映射鉴权依赖的 URL：{path}")


def _access_request(method: str, template: str) -> MagicMock:
    request = MagicMock()
    request.method = method
    request.url = SimpleNamespace(
        path=f"/api/v1/apps/kuaizhizao{_concrete_path(template)}"
    )
    return request


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,template",
    _STATION_EXECUTE_ALL_URLS,
    ids=[f"{m} {p}" for m, p in _STATION_EXECUTE_ALL_URLS],
)
async def test_pure_station_route_access_normalized_to_execute(
    monkeypatch, method, template
):
    """纯工位账号：闭包/前置 URL 的路由级鉴权所需码归一为 terminal:execute。"""
    captured = AsyncMock()
    monkeypatch.setattr(route_access_mod, "ensure_permission_codes", captured)
    _patch_pure_station(monkeypatch, True)

    dep = _route_access_dep(template)
    await dep(
        request=_access_request(method, template),
        auth=_auth(),
        tenant_id=1,
    )

    captured.assert_awaited_once()
    assert captured.await_args.args[3] == [
        gate_mod.STATION_TERMINAL_EXECUTE_PERMISSION
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,template,expected_code",
    [
        (
            "POST",
            "/reporting/quick",
            "kuaizhizao:production-execution-reporting:create",
        ),
        ("POST", "/station/andon", "kuaizhizao:production-execution-terminal:create"),
        (
            "DELETE",
            "/station/face-templates/{template_id}",
            "kuaizhizao:production-execution-terminal:delete",
        ),
        (
            "POST",
            "/work-orders/{work_order_id}/operations/{operation_id}/start",
            "kuaizhizao:work-order:create",
        ),
        (
            "POST",
            "/station/skill-check",
            "kuaizhizao:production-execution-terminal:create",
        ),
    ],
)
async def test_non_station_user_keeps_original_mapping(
    monkeypatch, method, template, expected_code
):
    """非纯工位账号：同样 URL 仍按原 URL→action 映射取权限码，不归一。"""
    captured = AsyncMock()
    monkeypatch.setattr(route_access_mod, "ensure_permission_codes", captured)
    _patch_pure_station(monkeypatch, False)

    dep = _route_access_dep(template)
    await dep(
        request=_access_request(method, template),
        auth=_auth(),
        tenant_id=1,
    )

    captured.assert_awaited_once()
    assert captured.await_args.args[3] == [expected_code]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,expected_code,dep_factory",
    [
        (
            "GET",
            "/work-orders",
            "kuaizhizao:work-order:read",
            route_access_mod.require_kuaizhizao_work_order_access,
        ),
        (
            "GET",
            "/station/andon",
            "kuaizhizao:production-execution-terminal:read",
            lambda: route_access_mod.require_kuaizhizao_module_access(
                "production-execution-terminal"
            ),
        ),
    ],
)
async def test_pure_station_outside_closure_get_keeps_original_mapping(
    monkeypatch, method, path, expected_code, dep_factory
):
    """纯工位账号：闭包外 GET 不归一也不拒读——未确认操作员仍可查看资料。"""
    captured = AsyncMock()
    monkeypatch.setattr(route_access_mod, "ensure_permission_codes", captured)
    _patch_pure_station(monkeypatch, True)

    request = MagicMock()
    request.method = method
    request.url = SimpleNamespace(
        path=f"/api/v1/apps/kuaizhizao{_concrete_path(path)}"
    )
    dep = dep_factory()
    await dep(request=request, auth=_auth(), tenant_id=1)

    captured.assert_awaited_once()
    assert captured.await_args.args[3] == [expected_code]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,dep_factory",
    [
        (
            "POST",
            "/work-orders",
            route_access_mod.require_kuaizhizao_work_order_access,
        ),
        (
            "DELETE",
            "/work-orders/{work_order_id:int}",
            route_access_mod.require_kuaizhizao_work_order_access,
        ),
        (
            "POST",
            "/reporting",
            route_access_mod.require_kuaizhizao_productions_access,
        ),
        (
            "DELETE",
            "/material-binding/{binding_id}",
            route_access_mod.require_kuaizhizao_productions_access,
        ),
        (
            "POST",
            "/station/work-orders/1/operations/2/documents",
            lambda: route_access_mod.require_kuaizhizao_module_access(
                "production-execution-terminal"
            ),
        ),
        (
            "POST",
            "/sales-orders",
            route_access_mod.require_kuaizhizao_sales_order_access,
        ),
        (
            "POST",
            "/process-inspections/1/conduct",
            route_access_mod.require_kuaizhizao_quality_execution_access,
        ),
        (
            "POST",
            "/other-inbounds",
            route_access_mod.require_kuaizhizao_warehouse_execution_access,
        ),
    ],
    ids=lambda v: v if isinstance(v, str) else None,
)
async def test_pure_station_outside_closure_write_denied(
    monkeypatch, method, path, dep_factory
):
    """纯工位账号 + 清单外写方法 → 默认拒写 403 通用文案，不再进入原权限判定。"""
    captured = AsyncMock()
    monkeypatch.setattr(route_access_mod, "ensure_permission_codes", captured)
    _patch_pure_station(monkeypatch, True)

    request = MagicMock()
    request.method = method
    request.url = SimpleNamespace(
        path=f"/api/v1/apps/kuaizhizao{_concrete_path(path)}"
    )
    dep = dep_factory()
    with pytest.raises(HTTPException) as raised:
        await dep(request=request, auth=_auth(), tenant_id=1)

    assert raised.value.status_code == 403
    assert raised.value.detail == gate_mod.STATION_OPERATOR_SESSION_DENIED_MESSAGE
    captured.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_station_outside_closure_write_keeps_original_mapping(
    monkeypatch,
):
    """非纯工位账号：清单外写路径仍按原 URL→action 映射取权限码，不受默认拒写影响。"""
    captured = AsyncMock()
    monkeypatch.setattr(route_access_mod, "ensure_permission_codes", captured)
    _patch_pure_station(monkeypatch, False)

    dep = route_access_mod.require_kuaizhizao_productions_access()
    await dep(
        request=_access_request("POST", "/reporting"),
        auth=_auth(),
        tenant_id=1,
    )

    captured.assert_awaited_once()
    assert captured.await_args.args[3] == [
        "kuaizhizao:production-execution-reporting:create"
    ]


# ---------------------------------------------------------------------------
# M-2 漂移测试：三个工位相关 router 的全部非 GET/HEAD/OPTIONS 路由必须被显式
# 归类——工位写闭包 / 确认流前置 / PC 专用写。新增写路由不进任一类则测试红。
# ---------------------------------------------------------------------------

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# PC 专用写路由：存在于工位相关 router，但对纯工位账号默认拒写（不代表工位可达）。
PC_ONLY_WRITE_ROUTES: frozenset[tuple[str, str]] = frozenset({
    # productions/work_orders.py
    ("POST", "/work-orders"),
    ("POST", "/work-orders/create-peer-group"),
    ("POST", "/work-orders/dissolve-group"),
    ("POST", "/work-orders/merge"),
    ("POST", "/work-orders/merge-into-group"),
    ("POST", "/work-orders/resolve-by-scan"),
    ("POST", "/work-orders/scheduling-quick-action"),
    ("POST", "/work-orders/scores/batch-refresh"),
    ("POST", "/work-orders/sync-from-source"),
    ("POST", "/work-orders/tracking/preview"),
    ("POST", "/work-orders/{work_order_id}/complete"),
    ("POST", "/work-orders/{work_order_id}/confirm-tracking"),
    ("POST", "/work-orders/{work_order_id}/freeze"),
    ("POST", "/work-orders/{work_order_id}/operations/{operation_id}/dispatch"),
    ("POST", "/work-orders/{work_order_id}/outsource"),
    ("POST", "/work-orders/{work_order_id}/push-purchase-requisition"),
    ("POST", "/work-orders/{work_order_id}/release"),
    ("POST", "/work-orders/{work_order_id}/remind-batching"),
    ("POST", "/work-orders/{work_order_id}/revoke"),
    ("POST", "/work-orders/{work_order_id}/rework"),
    ("POST", "/work-orders/{work_order_id}/scores/refresh"),
    ("POST", "/work-orders/{work_order_id}/split"),
    ("POST", "/work-orders/{work_order_id}/unfreeze"),
    ("POST", "/work-orders/{work_order_id}/unsplit"),
    ("POST", "/work-orders/{work_order_id}/withdraw-manual-complete"),
    ("POST", "/rework-orders"),
    ("POST", "/rework-orders/{rework_order_id}/advance-next"),
    ("POST", "/rework-orders/{rework_order_id}/approve"),
    ("POST", "/rework-orders/{rework_order_id}/cancel"),
    ("POST", "/rework-orders/{rework_order_id}/close"),
    ("POST", "/rework-orders/{rework_order_id}/finance-sign"),
    ("POST", "/rework-orders/{rework_order_id}/hold"),
    ("POST", "/rework-orders/{rework_order_id}/oqc-notify"),
    ("POST", "/rework-orders/{rework_order_id}/pqc-check"),
    ("POST", "/rework-orders/{rework_order_id}/quality-release"),
    ("POST", "/rework-orders/{rework_order_id}/reject"),
    ("POST", "/rework-orders/{rework_order_id}/release"),
    ("POST", "/rework-orders/{rework_order_id}/report"),
    ("POST", "/rework-orders/{rework_order_id}/request-complete"),
    ("POST", "/rework-orders/{rework_order_id}/resume"),
    ("POST", "/rework-orders/{rework_order_id}/submit"),
    ("POST", "/outsource-orders"),
    ("POST", "/outsource-orders/{outsource_order_id}/link-purchase-receipt"),
    ("PUT", "/work-orders/batch-priority"),
    ("PUT", "/work-orders/batch-update-dates"),
    ("PUT", "/work-orders/batch-update-operation-assignments"),
    ("PUT", "/work-orders/batch-update-operation-dates"),
    ("PUT", "/work-orders/batch-update-operation-stations"),
    ("PUT", "/work-orders/push-binding"),
    ("PUT", "/work-orders/sync-binding"),
    ("PUT", "/work-orders/{work_order_id:int}"),
    ("PUT", "/work-orders/{work_order_id}/operations"),
    ("PUT", "/work-orders/{work_order_id}/priority"),
    ("PUT", "/rework-orders/{rework_order_id}"),
    ("PUT", "/outsource-orders/{outsource_order_id}"),
    ("DELETE", "/work-orders/{work_order_id:int}"),
    ("DELETE", "/rework-orders/{rework_order_id}"),
    ("DELETE", "/outsource-orders/{outsource_order_id}"),
    # api/station/station.py（require_station_settings，PC 侧人脸模板管理）
    ("DELETE", "/station/face-templates/by-user/{user_id}"),
    # productions/reporting.py
    ("POST", "/reporting"),
    ("POST", "/reporting/batch-revoke"),
    ("POST", "/reporting/sync-from-source"),
    ("POST", "/reporting/{record_id}/approve"),
    ("POST", "/reporting/{record_id}/retry"),
    ("POST", "/reporting/{record_id}/revoke"),
    ("POST", "/scrap/{scrap_id}/approve"),
    ("POST", "/defect/{defect_id}/approve-acceptance"),
    ("PUT", "/reporting/sync-binding"),
    ("PUT", "/reporting/{record_id}/correct"),
    ("DELETE", "/reporting/{record_id}"),
    ("DELETE", "/material-binding/{binding_id}"),
})


def test_all_write_routes_classified_for_station_terminal():
    """station / work_orders / reporting 三个 router 的全部写路由必须 ∈
    gated ∪ precheck ∪ PC_ONLY_WRITE_ROUTES——新增写路由不归类即红。"""
    station_urls = (
        set(gate_mod.GATED_WRITE_URL_MANIFEST)
        | set(gate_mod.STATION_EXECUTE_PRECHECK_URLS)
    )
    assert not (PC_ONLY_WRITE_ROUTES & station_urls)
    classified = station_urls | PC_ONLY_WRITE_ROUTES

    unclassified = []
    for router in (
        station_api.router,
        work_orders_api.router,
        reporting_api.router,
    ):
        for route in router.routes:
            for method in (route.methods or set()) - _SAFE_METHODS:
                if (method, route.path) not in classified:
                    unclassified.append(f"{method} {route.path}")
    assert not unclassified, (
        f"未归类的写路由（须加入工位写闭包、确认流前置或 PC_ONLY_WRITE_ROUTES）："
        f"{unclassified}"
    )
