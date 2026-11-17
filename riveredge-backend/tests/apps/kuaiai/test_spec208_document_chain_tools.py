"""KU-AI spec 208 单测：单据关联链追溯与变更影响 Tools。

全部 mock / 假数据，不需要真实数据库。覆盖：
- document_type/direction/id 闭集与非法参数固定文案；
- X3=a：源单类型无读权限不返回；链上无权节点只计数不显示编号
  （含子树整块计数、映射缺项失败关闭、reporting_timeline 合成节点）；
- 源单行级数据范围复核（scene_tools._scoped_row_ids 同资源键），范围外
  按不存在回复；
- 三个变更影响 Tool 与 DocumentRelationNewService 同参数一致、受影响条目
  按类型读权限过滤、建议操作透传、NotFoundError 按不存在回复；
- 单据类型 → 读权限码映射覆盖 DOCUMENT_TYPES 全部类型，且权限码均存在
  于 kuaizhizao / kuaicaiwu manifest。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaiai.services.tools import document_chain as dc
from apps.kuaizhizao.schemas.document_relation import (
    DocumentTraceNode,
    DocumentTraceResponse,
)
from apps.kuaizhizao.services.document_relation_service import (
    DocumentRelationService,
)
from core.ai.runtime.context import AiRuntimeContext
from infra.exceptions.exceptions import NotFoundError

TENANT = 7
USER_ID = 5

_TRACE_SVC = (
    "apps.kuaizhizao.services.document_relation_new_service"
    ".DocumentRelationNewService"
)
_SCOPE_IDS = "apps.kuaiai.services.scene_tools._scoped_row_ids"
_USER_PERMS = (
    "core.services.authorization.user_permission_service"
    ".UserPermissionService.get_user_permissions"
)


def _ctx(admin: bool = False):
    return AiRuntimeContext(
        tenant_id=TENANT,
        user=SimpleNamespace(id=USER_ID, full_name="测试", username="t"),
        is_tenant_admin=admin,
    )


def _node(doc_type, doc_id=1, code=None, name=None, children=None, deleted=False):
    return DocumentTraceNode(
        document_type=doc_type,
        document_id=doc_id,
        document_code=code,
        document_name=name,
        level=1,
        is_deleted=deleted,
        children=list(children or []),
    )


def _trace(code="SO-2026-001", upstream=None, downstream=None):
    return DocumentTraceResponse(
        document_type="sales_order",
        document_id=101,
        document_code=code,
        document_name=None,
        upstream_chain=list(upstream or []),
        downstream_chain=list(downstream or []),
    )


def _service(method_name, return_value=None, side_effect=None):
    service = SimpleNamespace()
    mock = AsyncMock(return_value=return_value, side_effect=side_effect)
    setattr(service, method_name, mock)
    return service, mock


def _sales_impact(**kw):
    base = {
        "upstream_change": {
            "type": "sales_order",
            "id": 101,
            "code": "SO-2026-001",
            "name": "SO-2026-001",
            "changed_at": "2026-10-20T10:00:00+08:00",
        },
        "affected_demands": [
            {"id": 11, "code": "XR-001", "name": "需求一", "status": "AUDITED"}
        ],
        "affected_computations": [
            {"id": 12, "code": "JS-009", "name": None, "status": "done"}
        ],
        "affected_plans": [],
        "affected_work_orders": [
            {"id": 13, "code": "WO-100", "name": "工单一", "status": "released"}
        ],
        "recommended_actions": ["重算需求计算", "重新排程"],
    }
    base.update(kw)
    return base


def _purchase_impact(**kw):
    base = {
        "upstream_change": {
            "type": "purchase_order",
            "id": 201,
            "code": "PO-2026-001",
            "changed_at": None,
        },
        "affected_receipt_notices": [
            {"id": 21, "code": "SH-001", "name": None, "status": "pending"}
        ],
        "affected_inbounds": [
            {"id": 22, "code": "RK-009", "name": None, "status": "draft"}
        ],
        "recommended_actions": ["核对收货通知数量"],
    }
    base.update(kw)
    return base


def _demand_impact(**kw):
    base = {
        "upstream_change": {
            "type": "demand",
            "id": 301,
            "code": "XR-301",
            "name": "需求三",
            "changed_at": "2026-10-21T09:00:00+08:00",
        },
        "affected_demands": [
            {"id": 301, "code": "XR-301", "name": "需求三", "status": "released"}
        ],
        "affected_computations": [],
        "affected_plans": [],
        "affected_work_orders": [
            {"id": 31, "code": "WO-300", "name": None, "status": "in_progress"}
        ],
        "recommended_actions": ["重新排程"],
    }
    base.update(kw)
    return base


def _scope_visible(*ids):
    """_scoped_row_ids 桩：返回调用方传入的 id 集合（全部可见）。"""
    return AsyncMock(side_effect=lambda model, ctx, resource, ids: set(ids))


class TestMappingCompleteness:
    """映射表覆盖 service 支持的全部单据类型（spec §2 验证策略）。"""

    def test_closed_set_matches_service_document_types(self):
        assert dc._TRACE_DOCUMENT_TYPES == frozenset(
            DocumentRelationService.DOCUMENT_TYPES.keys()
        )

    def test_every_document_type_has_read_permission(self):
        missing = [
            t for t in dc._TRACE_DOCUMENT_TYPES
            if not dc._DOC_TYPE_READ_PERMISSION.get(t)
        ]
        assert missing == []
        # 合成节点 reporting_timeline 也必须有映射（随报工权限）
        assert dc._DOC_TYPE_READ_PERMISSION.get("reporting_timeline")

    def test_mapping_codes_exist_in_app_manifests(self):
        src = Path(__file__).resolve().parents[3] / "src"
        codes = set()
        for app in ("kuaizhizao", "kuaicaiwu"):
            manifest = json.loads(
                (src / "apps" / app / "manifest.json").read_text(encoding="utf-8")
            )
            for p in manifest.get("permissions") or []:
                codes.add(p if isinstance(p, str) else p.get("code"))
        unknown = {
            t: code
            for t, code in dc._DOC_TYPE_READ_PERMISSION.items()
            if code not in codes
        }
        assert unknown == {}


class TestTraceParams:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await dc.trace_document_chain(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_document_type(self):
        out = await dc.trace_document_chain(
            document_type="evil", document_id=1, ctx=_ctx(admin=True)
        )
        assert "document_type" in out and "闭集" in out

    @pytest.mark.asyncio
    async def test_invalid_direction(self):
        out = await dc.trace_document_chain(
            document_type="sales_order",
            document_id=1,
            direction="sideways",
            ctx=_ctx(admin=True),
        )
        assert "direction" in out and "upstream" in out

    @pytest.mark.asyncio
    async def test_invalid_document_id(self):
        out = await dc.trace_document_chain(
            document_type="sales_order", document_id="abc", ctx=_ctx(admin=True)
        )
        assert "document_id" in out and "正整数" in out
        out = await dc.trace_document_chain(
            document_type="sales_order", document_id=0, ctx=_ctx(admin=True)
        )
        assert "document_id" in out and "正整数" in out


class TestTracePermissionAndScope:
    @pytest.mark.asyncio
    async def test_source_type_no_read_permission(self):
        # 用户仅有工单读权限，无 sales-order:read → 不返回
        with patch(_USER_PERMS, new=AsyncMock(
            return_value={"kuaizhizao:work-order:read"}
        )):
            out = await dc.trace_document_chain(
                document_type="sales_order", document_id=101, ctx=_ctx()
            )
        assert "无权" in out
        assert "SO-2026-001" not in out

    @pytest.mark.asyncio
    async def test_source_out_of_scope_reply_not_found(self):
        with patch(_USER_PERMS, new=AsyncMock(
            return_value={"kuaizhizao:sales-order:read"}
        )), patch(_SCOPE_IDS, new=AsyncMock(return_value=set())):
            out = await dc.trace_document_chain(
                document_type="sales_order", document_id=101, ctx=_ctx()
            )
        assert "未找到" in out or "不在当前用户数据范围内" in out

    @pytest.mark.asyncio
    async def test_scope_recheck_uses_sales_order_resource(self):
        scoped = _scope_visible()
        service, _ = _service("trace_document_chain", _trace())
        with patch(_USER_PERMS, new=AsyncMock(
            return_value={"kuaizhizao:sales-order:read"}
        )), patch(_SCOPE_IDS, new=scoped), patch(
            _TRACE_SVC, return_value=service
        ):
            await dc.trace_document_chain(
                document_type="sales_order", document_id=101, ctx=_ctx()
            )
        kw = scoped.await_args.args
        assert kw[2] == "kuaizhizao:sales-order"
        assert kw[3] == {101}


class TestTraceNodeFiltering:
    @pytest.mark.asyncio
    async def test_hidden_node_counts_only_no_code(self):
        # 上游：可见需求节点 + 无权应收单（带子树，整块计数 2）
        upstream = [
            _node("demand", 11, "XR-001", "需求一"),
            _node(
                "receivable", 21, "AR-SECRET-1",
                children=[_node("sales_invoice", 22, "INV-SECRET-2")],
            ),
        ]
        downstream = [_node("work_order", 13, "WO-100", "工单一")]
        service, _ = _service(
            "trace_document_chain",
            _trace(upstream=upstream, downstream=downstream),
        )
        codes = {
            "kuaizhizao:sales-order:read",
            "kuaizhizao:plan-management-demand-management:read",
            "kuaizhizao:work-order:read",
        }
        with patch(_USER_PERMS, new=AsyncMock(return_value=codes)), patch(
            _SCOPE_IDS, new=_scope_visible()
        ), patch(_TRACE_SVC, return_value=service):
            out = await dc.trace_document_chain(
                document_type="sales_order", document_id=101, ctx=_ctx()
            )
        assert "XR-001" in out and "WO-100" in out
        # 无权节点只计数：编号与其子节点编号均不出现
        assert "AR-SECRET-1" not in out
        assert "INV-SECRET-2" not in out
        assert "2 个无权查看的关联单据" in out

    @pytest.mark.asyncio
    async def test_unmapped_document_type_fails_closed(self):
        upstream = [_node("mystery_doc", 31, "XXX-1")]
        service, _ = _service(
            "trace_document_chain", _trace(upstream=upstream)
        )
        with patch(_USER_PERMS, new=AsyncMock(
            return_value={"kuaizhizao:sales-order:read"}
        )), patch(_SCOPE_IDS, new=_scope_visible()), patch(
            _TRACE_SVC, return_value=service
        ):
            out = await dc.trace_document_chain(
                document_type="sales_order", document_id=101, ctx=_ctx()
            )
        assert "XXX-1" not in out
        assert "1 个无权查看的关联单据" in out

    @pytest.mark.asyncio
    async def test_reporting_timeline_follows_reporting_permission(self):
        timeline = _node("reporting_timeline", -13, "3条报工")
        downstream = [
            _node("work_order", 13, "WO-100", children=[timeline])
        ]
        service, _ = _service(
            "trace_document_chain", _trace(downstream=downstream)
        )
        codes = {
            "kuaizhizao:sales-order:read",
            "kuaizhizao:work-order:read",
        }
        with patch(_USER_PERMS, new=AsyncMock(return_value=codes)), patch(
            _SCOPE_IDS, new=_scope_visible()
        ), patch(_TRACE_SVC, return_value=service):
            out = await dc.trace_document_chain(
                document_type="sales_order",
                document_id=101,
                direction="downstream",
                ctx=_ctx(),
            )
        assert "WO-100" in out
        assert "3条报工" not in out
        assert "1 个无权查看的关联单据" in out

    @pytest.mark.asyncio
    async def test_admin_sees_all_nodes(self):
        upstream = [_node("receivable", 21, "AR-1")]
        service, _ = _service(
            "trace_document_chain", _trace(upstream=upstream)
        )
        with patch(_SCOPE_IDS, new=_scope_visible()), patch(
            _TRACE_SVC, return_value=service
        ):
            out = await dc.trace_document_chain(
                document_type="sales_order",
                document_id=101,
                ctx=_ctx(admin=True),
            )
        assert "AR-1" in out
        assert "无权查看" not in out


class TestTraceBehavior:
    @pytest.mark.asyncio
    async def test_root_not_found(self):
        service, _ = _service("trace_document_chain", _trace(code=None))
        with patch(_SCOPE_IDS, new=_scope_visible()), patch(
            _TRACE_SVC, return_value=service
        ):
            out = await dc.trace_document_chain(
                document_type="sales_order", document_id=101,
                ctx=_ctx(admin=True),
            )
        assert "未找到" in out

    @pytest.mark.asyncio
    async def test_empty_chains(self):
        service, _ = _service("trace_document_chain", _trace())
        with patch(_SCOPE_IDS, new=_scope_visible()), patch(
            _TRACE_SVC, return_value=service
        ):
            out = await dc.trace_document_chain(
                document_type="sales_order", document_id=101,
                ctx=_ctx(admin=True),
            )
        assert "没有可展示的关联单据" in out

    @pytest.mark.asyncio
    async def test_direction_upstream_only(self):
        service, _ = _service(
            "trace_document_chain",
            _trace(
                upstream=[_node("demand", 11, "XR-001")],
                downstream=[_node("work_order", 13, "WO-100")],
            ),
        )
        with patch(_SCOPE_IDS, new=_scope_visible()), patch(
            _TRACE_SVC, return_value=service
        ):
            out = await dc.trace_document_chain(
                document_type="sales_order",
                document_id=101,
                direction="upstream",
                ctx=_ctx(admin=True),
            )
        assert "上游关联" in out and "XR-001" in out
        assert "下游关联" not in out and "WO-100" not in out

    @pytest.mark.asyncio
    async def test_max_depth_clamped_to_10(self):
        service, mock = _service("trace_document_chain", _trace())
        with patch(_SCOPE_IDS, new=_scope_visible()), patch(
            _TRACE_SVC, return_value=service
        ):
            await dc.trace_document_chain(
                document_type="sales_order",
                document_id=101,
                max_depth=99,
                ctx=_ctx(admin=True),
            )
        assert mock.await_args.kwargs["max_depth"] == 10
        assert mock.await_args.kwargs["direction"] == "both"
        assert mock.await_args.kwargs["tenant_id"] == TENANT

    @pytest.mark.asyncio
    async def test_deleted_node_flagged(self):
        upstream = [_node("demand", 11, "XR-001", deleted=True)]
        service, _ = _service(
            "trace_document_chain", _trace(upstream=upstream)
        )
        with patch(_SCOPE_IDS, new=_scope_visible()), patch(
            _TRACE_SVC, return_value=service
        ):
            out = await dc.trace_document_chain(
                document_type="sales_order", document_id=101,
                ctx=_ctx(admin=True),
            )
        assert "已删除" in out

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        service, _ = _service(
            "trace_document_chain", side_effect=RuntimeError("db down")
        )
        with patch(_SCOPE_IDS, new=_scope_visible()), patch(
            _TRACE_SVC, return_value=service
        ):
            out = await dc.trace_document_chain(
                document_type="sales_order", document_id=101,
                ctx=_ctx(admin=True),
            )
        assert out == "追溯单据关联链失败，请稍后重试"
        assert "db down" not in out


class TestSalesOrderImpact:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await dc.analyze_sales_order_change_impact(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_id(self):
        out = await dc.analyze_sales_order_change_impact(
            sales_order_id="x", ctx=_ctx(admin=True)
        )
        assert "sales_order_id" in out and "正整数" in out

    @pytest.mark.asyncio
    async def test_out_of_scope_reply_not_found(self):
        with patch(_SCOPE_IDS, new=AsyncMock(return_value=set())):
            out = await dc.analyze_sales_order_change_impact(
                sales_order_id=101, ctx=_ctx(admin=True)
            )
        assert "未查询到该销售订单" in out

    @pytest.mark.asyncio
    async def test_not_found_error_reply_not_found(self):
        service, _ = _service(
            "get_change_impact_sales_order",
            side_effect=NotFoundError("销售订单不存在: 101"),
        )
        with patch(_SCOPE_IDS, new=_scope_visible()), patch(
            _TRACE_SVC, return_value=service
        ):
            out = await dc.analyze_sales_order_change_impact(
                sales_order_id=101, ctx=_ctx(admin=True)
            )
        assert "未查询到该销售订单" in out
        assert "101" not in out

    @pytest.mark.asyncio
    async def test_happy_path_same_params_as_service(self):
        service, mock = _service(
            "get_change_impact_sales_order", _sales_impact()
        )
        with patch(_SCOPE_IDS, new=_scope_visible()), patch(
            _TRACE_SVC, return_value=service
        ):
            out = await dc.analyze_sales_order_change_impact(
                sales_order_id=101, ctx=_ctx(admin=True)
            )
        assert mock.await_args.kwargs == {
            "tenant_id": TENANT,
            "order_id": 101,
        }
        assert "SO-2026-001" in out
        assert "受影响需求（1）" in out and "XR-001" in out
        assert "受影响需求计算（1）" in out and "JS-009" in out
        assert "受影响工单（1）" in out and "WO-100" in out
        assert "重算需求计算" in out and "重新排程" in out
        # 敏感字段不出现
        assert "金额" not in out and "单价" not in out

    @pytest.mark.asyncio
    async def test_affected_items_filtered_by_permission(self):
        service, _ = _service(
            "get_change_impact_sales_order", _sales_impact()
        )
        # 无 demand_computation / work-order 读权限
        codes = {
            "kuaizhizao:sales-order-change:read",
            "kuaizhizao:sales-order:read",
            "kuaizhizao:plan-management-demand-management:read",
        }
        with patch(_SCOPE_IDS, new=_scope_visible()), patch(
            _USER_PERMS, new=AsyncMock(return_value=codes)
        ), patch(_TRACE_SVC, return_value=service):
            out = await dc.analyze_sales_order_change_impact(
                sales_order_id=101, ctx=_ctx()
            )
        assert "XR-001" in out
        assert "JS-009" not in out and "WO-100" not in out
        assert "无权查看" in out

    @pytest.mark.asyncio
    async def test_empty_impact(self):
        service, _ = _service(
            "get_change_impact_sales_order",
            _sales_impact(
                affected_demands=[],
                affected_computations=[],
                affected_work_orders=[],
                recommended_actions=[],
            ),
        )
        with patch(_SCOPE_IDS, new=_scope_visible()), patch(
            _TRACE_SVC, return_value=service
        ):
            out = await dc.analyze_sales_order_change_impact(
                sales_order_id=101, ctx=_ctx(admin=True)
            )
        assert "未影响任何下游单据" in out

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        service, _ = _service(
            "get_change_impact_sales_order",
            side_effect=RuntimeError("boom"),
        )
        with patch(_SCOPE_IDS, new=_scope_visible()), patch(
            _TRACE_SVC, return_value=service
        ):
            out = await dc.analyze_sales_order_change_impact(
                sales_order_id=101, ctx=_ctx(admin=True)
            )
        assert out == "分析销售订单变更影响失败，请稍后重试"


class TestPurchaseOrderImpact:
    @pytest.mark.asyncio
    async def test_happy_path(self):
        service, mock = _service(
            "get_change_impact_purchase_order", _purchase_impact()
        )
        with patch(_SCOPE_IDS, new=_scope_visible()), patch(
            _TRACE_SVC, return_value=service
        ):
            out = await dc.analyze_purchase_order_change_impact(
                purchase_order_id=201, ctx=_ctx(admin=True)
            )
        assert mock.await_args.kwargs == {
            "tenant_id": TENANT,
            "order_id": 201,
        }
        assert "PO-2026-001" in out
        assert "受影响收货通知单（1）" in out and "SH-001" in out
        assert "受影响入库单（1）" in out and "RK-009" in out
        assert "核对收货通知数量" in out

    @pytest.mark.asyncio
    async def test_inbound_items_filtered(self):
        service, _ = _service(
            "get_change_impact_purchase_order", _purchase_impact()
        )
        codes = {
            "kuaizhizao:purchase-order-change:read",
            "kuaizhizao:purchase-order:read",
            "kuaizhizao:receipt-notice:read",
        }
        with patch(_SCOPE_IDS, new=_scope_visible()), patch(
            _USER_PERMS, new=AsyncMock(return_value=codes)
        ), patch(_TRACE_SVC, return_value=service):
            out = await dc.analyze_purchase_order_change_impact(
                purchase_order_id=201, ctx=_ctx()
            )
        assert "SH-001" in out
        assert "RK-009" not in out
        assert "无权查看" in out

    @pytest.mark.asyncio
    async def test_out_of_scope_and_error_text(self):
        with patch(_SCOPE_IDS, new=AsyncMock(return_value=set())):
            out = await dc.analyze_purchase_order_change_impact(
                purchase_order_id=201, ctx=_ctx(admin=True)
            )
        assert "未查询到该采购订单" in out

        service, _ = _service(
            "get_change_impact_purchase_order",
            side_effect=RuntimeError("x"),
        )
        with patch(_SCOPE_IDS, new=_scope_visible()), patch(
            _TRACE_SVC, return_value=service
        ):
            out = await dc.analyze_purchase_order_change_impact(
                purchase_order_id=201, ctx=_ctx(admin=True)
            )
        assert out == "分析采购订单变更影响失败，请稍后重试"


class TestDemandImpact:
    @pytest.mark.asyncio
    async def test_happy_path(self):
        service, mock = _service(
            "get_change_impact_demand", _demand_impact()
        )
        scoped = _scope_visible()
        with patch(_SCOPE_IDS, new=scoped), patch(
            _TRACE_SVC, return_value=service
        ):
            out = await dc.analyze_demand_change_impact(
                demand_id=301, ctx=_ctx(admin=True)
            )
        assert mock.await_args.kwargs == {
            "tenant_id": TENANT,
            "demand_id": 301,
        }
        # 需求源单按 plan-management-demand-management 资源键复核（T1 定）
        assert scoped.await_args.args[2] == (
            "kuaizhizao:plan-management-demand-management"
        )
        assert "XR-301" in out
        assert "受影响工单（1）" in out and "WO-300" in out
        assert "重新排程" in out

    @pytest.mark.asyncio
    async def test_out_of_scope_and_error_text(self):
        with patch(_SCOPE_IDS, new=AsyncMock(return_value=set())):
            out = await dc.analyze_demand_change_impact(
                demand_id=301, ctx=_ctx(admin=True)
            )
        assert "未查询到该需求" in out

        service, _ = _service(
            "get_change_impact_demand", side_effect=RuntimeError("x")
        )
        with patch(_SCOPE_IDS, new=_scope_visible()), patch(
            _TRACE_SVC, return_value=service
        ):
            out = await dc.analyze_demand_change_impact(
                demand_id=301, ctx=_ctx(admin=True)
            )
        assert out == "分析需求变更影响失败，请稍后重试"
