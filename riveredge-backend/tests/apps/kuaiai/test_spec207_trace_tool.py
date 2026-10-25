"""KU-AI spec 207 单测：trace_lineage + X2=b permissions_any 基础设施。

全部 mock / 假数据，不需要真实数据库。覆盖：
- trace_lineage：闭集参数（direction）非法回固定文案；code 必填；
  NotFoundError → 真实「未找到追溯记录」；底层异常固定错误文案；
  profile 节点按层级（edges BFS）摘要、超上限截断提示去追溯页；
  tenant_id 与 direction 透传。
- X2=b：RegisteredTool.permissions_any；register_from_manifest 对
  permission / permissions_any 二选一互斥（同给/同缺/非法即跳过）；
  tool_bridge 判权：多码任一命中放行、皆无 403 审计、单值回归不变。
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import ToolMessage

from apps.kuaiai.services.tools import traceability as tr
from core.ai.runtime import tool_bridge
from core.ai.runtime.context import (
    AiRuntimeContext,
    reset_ai_context,
    set_ai_context,
)
from core.ai.tool_registry import ToolRegistry
from infra.exceptions.exceptions import NotFoundError

TENANT = 7
USER_ID = 5

PERM_QM = "kuaizhizao:quality-management-traceability:read"
PERM_ML = "kuaizhizao:material-lifecycle-trace:read"


def _ctx(**flags):
    return AiRuntimeContext(
        tenant_id=TENANT, user=SimpleNamespace(id=USER_ID), **flags
    )


def _node(nid, label, ntype, data=None):
    return SimpleNamespace(id=nid, label=label, type=ntype, data=data or {})


def _edge(source, target, label="关联"):
    return SimpleNamespace(source=source, target=target, label=label)


def _event(doc_type, doc_code, quantity=None):
    return SimpleNamespace(
        document_type=doc_type,
        document_code=doc_code,
        quantity=quantity,
        event_time=None,
    )


def _profile(nodes=None, edges=None, events=None, anchor=None):
    nodes = nodes or [
        _node(
            "batch:B2410-07",
            "B2410-07",
            "batch",
            {"material_code": "FG-01", "material_name": "成品甲"},
        ),
        _node(
            "work_order:WO-1",
            "工单: WO-1",
            "work_order",
            {
                "document_type": "work_order",
                "document_code": "WO-1",
                "material_code": "FG-01",
                "material_name": "成品甲",
            },
        ),
        _node(
            "sales_delivery:SD-9",
            "销售出库: SD-9",
            "outbound",
            {"document_type": "sales_delivery", "document_code": "SD-9"},
        ),
    ]
    edges = (
        edges
        if edges is not None
        else [
            _edge("batch:B2410-07", "work_order:WO-1", "投料"),
            _edge("work_order:WO-1", "sales_delivery:SD-9", "成品入库"),
        ]
    )
    events = events if events is not None else [
        _event("work_order", "WO-1", Decimal("10"))
    ]
    return SimpleNamespace(
        anchor=anchor
        or SimpleNamespace(
            identifier_type="batch",
            code="B2410-07",
            material_code="FG-01",
            material_name="成品甲",
        ),
        summary=SimpleNamespace(
            event_count=len(events),
            node_count=len(nodes),
            edge_count=len(edges),
        ),
        events=events,
        nodes=nodes,
        edges=edges,
    )


def _trace_service(profile=None, side_effect=None):
    return SimpleNamespace(
        build_profile=AsyncMock(
            return_value=profile, side_effect=side_effect
        )
    )


def _patch_service(service):
    return patch(
        "apps.kuaizhizao.services.traceability.TraceabilityService",
        return_value=service,
    )


class TestTraceLineageParams:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await tr.trace_lineage(code="B1", ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_code_required(self):
        out = await tr.trace_lineage(code="  ", ctx=_ctx())
        assert "必填" in out

    @pytest.mark.asyncio
    async def test_invalid_direction(self):
        out = await tr.trace_lineage(code="B1", direction="sideways", ctx=_ctx())
        assert "forward" in out and "backward" in out and "both" in out


class TestTraceLineage:
    @pytest.mark.asyncio
    async def test_nodes_layered_with_material_and_quantity(self):
        service = _trace_service(profile=_profile())
        with _patch_service(service):
            out = await tr.trace_lineage(code="B2410-07", ctx=_ctx())
        args = service.build_profile.await_args.args
        assert args[0] == TENANT
        assert args[1] == "B2410-07"
        assert args[2] == "both"
        assert "批号" in out and "B2410-07" in out
        assert "3 个节点" in out
        assert "[第0层]" in out and "[第1层]" in out and "[第2层]" in out
        assert "工单: WO-1" in out
        assert "FG-01" in out and "成品甲" in out
        assert "数量 10" in out
        # 通讯敏感字段不出现
        assert "电话" not in out and "地址" not in out

    @pytest.mark.asyncio
    async def test_direction_passed_through(self):
        service = _trace_service(profile=_profile())
        with _patch_service(service):
            await tr.trace_lineage(code="B1", direction="forward", ctx=_ctx())
        assert service.build_profile.await_args.args[2] == "forward"

    @pytest.mark.asyncio
    async def test_not_found_real_text(self):
        service = _trace_service(side_effect=NotFoundError("未找到追溯码"))
        with _patch_service(service):
            out = await tr.trace_lineage(code="GHOST", ctx=_ctx())
        assert out == "未找到追溯记录：GHOST"

    @pytest.mark.asyncio
    async def test_no_events(self):
        profile = _profile(nodes=[_node("batch:B1", "B1", "batch")], edges=[], events=[])
        service = _trace_service(profile=profile)
        with _patch_service(service):
            out = await tr.trace_lineage(code="B1", ctx=_ctx())
        assert "暂无追溯事件记录" in out

    @pytest.mark.asyncio
    async def test_truncation_note(self):
        nodes = [_node("batch:B0", "B0", "batch")]
        edges = []
        for i in range(1, 30):
            nodes.append(_node(f"work_order:WO-{i}", f"工单: WO-{i}", "work_order"))
            edges.append(_edge(f"work_order:WO-{i - 1}" if i > 1 else "batch:B0",
                               f"work_order:WO-{i}"))
        service = _trace_service(
            profile=_profile(
                nodes=nodes,
                edges=edges,
                events=[_event("batch", "B0")],
                anchor=SimpleNamespace(
                    identifier_type="batch",
                    code="B0",
                    material_code=None,
                    material_name=None,
                ),
            )
        )
        with _patch_service(service):
            out = await tr.trace_lineage(code="B0", ctx=_ctx())
        assert "已截断" in out and "追溯页" in out
        assert "WO-25" not in out  # 超出上限的节点不列出

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        service = _trace_service(side_effect=RuntimeError("db down"))
        with _patch_service(service):
            out = await tr.trace_lineage(code="B1", ctx=_ctx())
        assert out == "查询追溯链路失败，请稍后重试"
        assert "db down" not in out


# ---------------------------------------------------------------- X2=b


def _register(name, **kw):
    ToolRegistry.register(
        name,
        {
            "type": "function",
            "function": {
                "name": name,
                "description": f"desc {name}",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        **kw,
    )


def _request(name, call_id="call_1"):
    return SimpleNamespace(
        tool_call={"name": name, "id": call_id},
        tool=None,
        state={},
        runtime=None,
    )


def _manifest_item(**over):
    item = {
        "name": "ut_spec207_tool",
        "handler": "apps.kuaiai.services.tools.traceability:trace_lineage",
    }
    item.update(over)
    return {"ai_tools": [item]}


class TestRegisterFromManifestPermissionsAny:
    def teardown_method(self):
        ToolRegistry._tools.pop("ut_spec207_tool", None)

    def test_permissions_any_registers(self):
        ToolRegistry.register_from_manifest(
            "kuaiai", _manifest_item(permissions_any=[PERM_QM, PERM_ML])
        )
        tool = ToolRegistry._tools.get("ut_spec207_tool")
        assert tool is not None
        assert tool.permission is None
        assert tool.permissions_any == [PERM_QM, PERM_ML]
        assert callable(tool.handler)

    def test_single_permission_registers(self):
        ToolRegistry.register_from_manifest(
            "kuaiai", _manifest_item(permission=PERM_QM)
        )
        tool = ToolRegistry._tools.get("ut_spec207_tool")
        assert tool is not None
        assert tool.permission == PERM_QM
        assert tool.permissions_any is None

    @pytest.mark.parametrize(
        "item_over",
        [
            {"permission": PERM_QM, "permissions_any": [PERM_ML]},  # 同给
            {"permission": PERM_QM, "permissions_any": []},  # 同给但 any 非法
            {"permission": PERM_QM, "permissions_any": "x"},  # 同给但 any 非列表
            {},  # 同缺
            {"permissions_any": []},  # 空列表
            {"permissions_any": "kuaizhizao:x:read"},  # 非列表
        ],
    )
    def test_mutual_exclusion_skips(self, item_over):
        ToolRegistry.register_from_manifest("kuaiai", _manifest_item(**item_over))
        assert "ut_spec207_tool" not in ToolRegistry._tools


class TestToolGuardPermissionsAny:
    def teardown_method(self):
        ToolRegistry._tools.pop("ut_spec207_guard", None)

    @pytest.mark.asyncio
    async def test_any_hit_allows(self):
        """持有任一权限码即放行（material-lifecycle-trace 命中第二个码）。"""
        _register("ut_spec207_guard", permissions_any=[PERM_QM, PERM_ML])
        token = set_ai_context(_ctx())
        try:
            handler = AsyncMock(return_value="ok")
            has_perm = AsyncMock(
                side_effect=lambda uid, tid, code, **kw: code == PERM_ML
            )
            with (
                patch.object(
                    tool_bridge.UserPermissionService, "has_permission", has_perm
                ),
                patch.object(tool_bridge, "_audit_tool_call", AsyncMock()),
            ):
                result = await tool_bridge.build_tool_guard_middleware().awrap_tool_call(
                    _request("ut_spec207_guard"), handler
                )
        finally:
            reset_ai_context(token)
        handler.assert_awaited_once()
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_none_hit_denies_with_403_audit(self):
        """两码皆无 → 403 审计 + error ToolMessage，handler 不执行。"""
        _register("ut_spec207_guard", permissions_any=[PERM_QM, PERM_ML])
        token = set_ai_context(_ctx())
        try:
            handler = AsyncMock()
            with (
                patch.object(
                    tool_bridge.UserPermissionService,
                    "has_permission",
                    AsyncMock(return_value=False),
                ),
                patch.object(tool_bridge, "_audit_tool_call", AsyncMock()) as audit,
            ):
                result = await tool_bridge.build_tool_guard_middleware().awrap_tool_call(
                    _request("ut_spec207_guard"), handler
                )
        finally:
            reset_ai_context(token)
        assert isinstance(result, ToolMessage)
        assert result.status == "error"
        handler.assert_not_called()
        assert audit.await_args.kwargs["status_code"] == 403
        assert audit.await_args.kwargs["error"] == "permission_denied"

    @pytest.mark.asyncio
    async def test_single_permission_regression(self):
        """单值 permission 行为不变：命中放行，未命中拒绝。"""
        _register("ut_spec207_guard", permission=PERM_QM)
        token = set_ai_context(_ctx())
        try:
            handler = AsyncMock(return_value="ok")
            with (
                patch.object(
                    tool_bridge.UserPermissionService,
                    "has_permission",
                    AsyncMock(return_value=True),
                ),
                patch.object(tool_bridge, "_audit_tool_call", AsyncMock()),
            ):
                result = await tool_bridge.build_tool_guard_middleware().awrap_tool_call(
                    _request("ut_spec207_guard"), handler
                )
        finally:
            reset_ai_context(token)
        handler.assert_awaited_once()
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_tenant_admin_bypasses(self):
        """租户管理员对 permissions_any Tool 同样直通（不查码）。"""
        _register("ut_spec207_guard", permissions_any=[PERM_QM, PERM_ML])
        token = set_ai_context(_ctx(is_tenant_admin=True))
        try:
            handler = AsyncMock(return_value="ok")
            has_perm = AsyncMock(return_value=False)
            with (
                patch.object(
                    tool_bridge.UserPermissionService, "has_permission", has_perm
                ),
                patch.object(tool_bridge, "_audit_tool_call", AsyncMock()),
            ):
                result = await tool_bridge.build_tool_guard_middleware().awrap_tool_call(
                    _request("ut_spec207_guard"), handler
                )
        finally:
            reset_ai_context(token)
        has_perm.assert_not_called()
        handler.assert_awaited_once()
        assert result == "ok"
