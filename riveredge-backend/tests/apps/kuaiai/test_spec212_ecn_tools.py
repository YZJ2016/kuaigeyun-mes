"""spec 212（S23 ECN 影响分析）Tool 单元测试。

覆盖 ``query_ecn`` / ``analyze_ecn_impact`` / ``query_material_where_used``
/ ``query_drawing_where_used``：无上下文、闭集校验、limit 夹取、
tenant_id 透传、行级数据范围、kuaiplm 未启用固定文案、空集与异常固定
文案、敏感字段（before/after 全文、单价/成本）不外泄、分区按读权限降级。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaiai.services.tools import ecn_impact, engineering_bom
from apps.kuaiplm.models.engineering_change import (
    EngineeringChange,
    EngineeringChangeMaterialLine,
)
from apps.kuaiplm.services.engineering_change_service import (
    EngineeringChangeService,
)
from apps.master_data.models.material import Material
from apps.master_data.services.material_service import MaterialService
from apps.master_data.services.drawing_where_used_service import (
    DrawingWhereUsedService,
)
from core.ai.runtime.context import AiRuntimeContext
from infra.exceptions.exceptions import NotFoundError

TENANT = 7
USER_ID = 5

_SCOPE_IDS = "apps.kuaiai.services.scene_tools._scoped_row_ids"
_APP_BY_CODE = (
    "core.services.application.application_service."
    "ApplicationService.get_application_by_code"
)
_PERM_VIEW = "apps.kuaiai.services.tools.document_chain._perm_view"
_RESOLVE_ROUTE = (
    "apps.kuaiai.services.tools.process_routes._resolve_material_route_id"
)

_PLM_ON = {"is_installed": True, "is_active": True}
_PLM_NOT_INSTALLED = {"is_installed": False, "is_active": False}
_PLM_DISABLED = {"is_installed": True, "is_active": False}


def _ctx(admin: bool = True):
    return AiRuntimeContext(
        tenant_id=TENANT,
        user=SimpleNamespace(id=USER_ID, full_name="测试", username="t"),
        is_tenant_admin=admin,
    )


def _qs(rows=(), first=None):
    q = MagicMock()
    for m in ("filter", "order_by", "offset", "limit"):
        setattr(q, m, MagicMock(return_value=q))
    q.all = AsyncMock(return_value=list(rows))
    q.first = AsyncMock(
        return_value=first if first is not None else (rows[0] if rows else None)
    )
    q.count = AsyncMock(return_value=len(rows))
    q.exists = AsyncMock(return_value=bool(rows))
    q.values = AsyncMock(return_value=list(rows))
    q.values_list = AsyncMock(return_value=list(rows))
    return q


def _scope_visible(*ids):
    """_scoped_row_ids 桩：全部可见（或指定可见子集）。"""
    allow = set(ids)
    return AsyncMock(
        side_effect=lambda model, ctx, resource, ids: set(ids) & allow
        if ids
        else set(ids)
    )


def _scope_all():
    return AsyncMock(side_effect=lambda model, ctx, resource, ids: set(ids))


def _ecn_row(**kw):
    base = dict(
        id=1,
        ecn_code="ECN-2024-058",
        title="外壳尺寸变更",
        status="approved",
        created_at="2024-11-01 09:00:00",
        updated_at="2024-11-02 09:00:00",
        approved_at="2024-11-02 10:00:00",
        closed_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _ecn_resp(materials=None, **kw):
    base = dict(
        id=1,
        ecn_code="ECN-2024-058",
        title="外壳尺寸变更",
        status="approved",
        change_kind="ecn",
        materials=list(materials or []),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _mat_line(**kw):
    base = dict(
        id=11,
        material_id=101,
        material_code="M-101",
        material_name="外壳",
        disposition="rework",
        before_desc="SECRET_BEFORE_TEXT",
        after_desc="SECRET_AFTER_TEXT",
        unit_price="9.99",
        cost_amount="99.9",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _ecn_service(resp=None, side_effect=None):
    svc = MagicMock()
    svc.get = AsyncMock(return_value=resp, side_effect=side_effect)
    cls = MagicMock(return_value=svc)
    return cls, svc


class TestQueryEcn:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await ecn_impact.query_ecn(ctx=None)
        assert "缺少租户/用户上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_status(self):
        out = await ecn_impact.query_ecn(status="bogus", ctx=_ctx())
        assert "status 仅支持" in out

    @pytest.mark.asyncio
    async def test_invalid_date(self):
        out = await ecn_impact.query_ecn(date_start="2024/01/01", ctx=_ctx())
        assert "date_start 须为" in out
        out = await ecn_impact.query_ecn(date_end="bad", ctx=_ctx())
        assert "date_end 须为" in out

    @pytest.mark.asyncio
    async def test_plm_not_installed(self):
        for row in (None, _PLM_NOT_INSTALLED, _PLM_DISABLED):
            with patch(_APP_BY_CODE, AsyncMock(return_value=row)):
                out = await ecn_impact.query_ecn(ctx=_ctx())
                assert out == "PLM 应用未启用，无法执行该查询"

    @pytest.mark.asyncio
    async def test_list_output_and_tenant(self):
        rows = [_ecn_row(id=1), _ecn_row(id=2, ecn_code="ECN-2024-060")]
        mat_q = _qs()
        mat_q.values_list = AsyncMock(return_value=[1, 1, 2])
        with (
            patch(_APP_BY_CODE, AsyncMock(return_value=_PLM_ON)),
            patch.object(
                EngineeringChange, "filter", MagicMock(return_value=_qs(rows))
            ) as m_filter,
            patch.object(
                EngineeringChangeMaterialLine,
                "filter",
                MagicMock(return_value=mat_q),
            ),
            patch(_SCOPE_IDS, _scope_all()),
        ):
            out = await ecn_impact.query_ecn(status="approved", ctx=_ctx())
        m_filter.assert_called_once()
        assert m_filter.call_args.kwargs.get("tenant_id") == TENANT
        assert "ECN-2024-058" in out and "ECN-2024-060" in out
        assert "涉及物料 2 项" in out and "涉及物料 1 项" in out
        assert "生效" in out

    @pytest.mark.asyncio
    async def test_limit_clamped_to_20(self):
        rows = [_ecn_row(id=i, ecn_code=f"ECN-{i:03d}") for i in range(1, 26)]
        with (
            patch(_APP_BY_CODE, AsyncMock(return_value=_PLM_ON)),
            patch.object(
                EngineeringChange, "filter", MagicMock(return_value=_qs(rows))
            ),
            patch.object(
                EngineeringChangeMaterialLine,
                "filter",
                MagicMock(return_value=_qs()),
            ),
            patch(_SCOPE_IDS, _scope_all()),
        ):
            out = await ecn_impact.query_ecn(limit=99, ctx=_ctx())
        assert "共 25 张" in out and "返回前 20 张" in out
        assert "ECN-021" not in out

    @pytest.mark.asyncio
    async def test_scope_prunes_rows(self):
        rows = [_ecn_row(id=1), _ecn_row(id=2, ecn_code="ECN-2024-060")]
        with (
            patch(_APP_BY_CODE, AsyncMock(return_value=_PLM_ON)),
            patch.object(
                EngineeringChange, "filter", MagicMock(return_value=_qs(rows))
            ),
            patch.object(
                EngineeringChangeMaterialLine,
                "filter",
                MagicMock(return_value=_qs()),
            ),
            patch(_SCOPE_IDS, _scope_visible(1)),
        ):
            out = await ecn_impact.query_ecn(ctx=_ctx())
        assert "ECN-2024-058" in out
        assert "ECN-2024-060" not in out
        assert "共 1 张" in out

    @pytest.mark.asyncio
    async def test_empty_result(self):
        with (
            patch(_APP_BY_CODE, AsyncMock(return_value=_PLM_ON)),
            patch.object(
                EngineeringChange, "filter", MagicMock(return_value=_qs())
            ),
            patch(_SCOPE_IDS, _scope_all()),
        ):
            out = await ecn_impact.query_ecn(keyword="nothing", ctx=_ctx())
        assert "未查询到符合条件的工程变更单" in out

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        with patch(
            _APP_BY_CODE, AsyncMock(side_effect=RuntimeError("db down"))
        ):
            out = await ecn_impact.query_ecn(ctx=_ctx())
        assert out == "查询工程变更单失败，请稍后重试"


def _impact_patches(resp, perms=None, visible_ecn=True):
    """analyze_ecn_impact 常规补丁栈（各分区默认有数据）。"""
    cls, svc = _ecn_service(resp=resp)
    scope = _scope_all() if visible_ecn else _scope_visible()
    work_order = SimpleNamespace(
        id=201,
        code="WO-100",
        product_code="M-101",
        status="in_progress",
        quantity=50,
        planned_end_date="2024-12-01",
    )
    batch = SimpleNamespace(
        id=301,
        material_id=101,
        batch_no="B-001",
        warehouse_name="原料仓",
        quantity=30,
    )
    route = SimpleNamespace(id=401, code="R-01", name="外壳工艺", version="1.0")
    patches = [
        patch(_APP_BY_CODE, AsyncMock(return_value=_PLM_ON)),
        patch(
            "apps.kuaiplm.services.engineering_change_service."
            "EngineeringChangeService",
            cls,
        ),
        patch(_SCOPE_IDS, scope),
        patch(_PERM_VIEW, AsyncMock(return_value=(False, frozenset(perms or ())))),
    ]
    return patches, dict(
        work_order=work_order, batch=batch, route=route, svc=svc
    )


class TestAnalyzeEcnImpact:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await ecn_impact.analyze_ecn_impact(ecn_id=1, ctx=None)
        assert "缺少租户/用户上下文" in out

    @pytest.mark.asyncio
    async def test_bad_ecn_id(self):
        out = await ecn_impact.analyze_ecn_impact(ecn_id="abc", ctx=_ctx())
        assert "ecn_id 须为工程变更单 ID 整数" in out

    @pytest.mark.asyncio
    async def test_plm_disabled(self):
        with patch(_APP_BY_CODE, AsyncMock(return_value=_PLM_DISABLED)):
            out = await ecn_impact.analyze_ecn_impact(ecn_id=1, ctx=_ctx())
        assert out == "PLM 应用未启用，无法执行该查询"

    @pytest.mark.asyncio
    async def test_ecn_not_found(self):
        cls, _svc = _ecn_service(
            side_effect=NotFoundError("工程变更单", "1")
        )
        with (
            patch(_APP_BY_CODE, AsyncMock(return_value=_PLM_ON)),
            patch(
                "apps.kuaiplm.services.engineering_change_service."
                "EngineeringChangeService",
                cls,
            ),
        ):
            out = await ecn_impact.analyze_ecn_impact(ecn_id=9, ctx=_ctx())
        assert out == "工程变更单不存在"

    @pytest.mark.asyncio
    async def test_source_out_of_scope(self):
        patches, _ = _impact_patches(
            _ecn_resp(materials=[_mat_line()]), visible_ecn=False
        )
        with patches[0], patches[1], patches[2], patches[3]:
            out = await ecn_impact.analyze_ecn_impact(ecn_id=1, ctx=_ctx())
        assert out == "当前用户数据范围内无该工程变更单"

    @pytest.mark.asyncio
    async def test_full_sections_no_sensitive_fields(self):
        resp = _ecn_resp(
            materials=[
                _mat_line(),
                _mat_line(id=12, material_id=102, material_code="M-102"),
            ]
        )
        patches, fx = _impact_patches(
            resp,
            perms={
                "kuaizhizao:work-order:read",
                "kuaizhizao:inventory:read",
                "master-data:process:engineering-bom:read",
                "master-data:process:route:read",
            },
        )
        from apps.kuaizhizao.models.work_order import WorkOrder
        from apps.master_data.models.material_batch import MaterialBatch
        from apps.master_data.models.process import ProcessRoute

        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patch.object(
                WorkOrder, "filter", MagicMock(return_value=_qs([fx["work_order"]]))
            ),
            patch.object(
                MaterialBatch, "filter", MagicMock(return_value=_qs([fx["batch"]]))
            ),
            patch.object(
                MaterialService,
                "list_bom_where_used",
                AsyncMock(
                    return_value={
                        "items": [
                            {
                                "bom_id": 501,
                                "material_id": 88,
                                "material_code": "P-88",
                                "material_name": "总成",
                                "bom_code": "BOM-88",
                                "version": "1.0",
                                "quantity": 2,
                                "unit": "个",
                                "approval_status": "approved",
                            }
                        ],
                        "total": 1,
                    }
                ),
            ),
            patch(_RESOLVE_ROUTE, AsyncMock(return_value=401)),
            patch.object(
                ProcessRoute, "filter", MagicMock(return_value=_qs([fx["route"]]))
            ),
        ):
            out = await ecn_impact.analyze_ecn_impact(ecn_id=1, ctx=_ctx())
        assert "ECN-2024-058" in out and "涉及物料 2 项" in out
        assert "M-101" in out and "返工" in out
        assert "受影响在制工单" in out and "WO-100" in out
        assert "受影响库存批次" in out and "B-001" in out
        assert "受影响 BOM 引用" in out and "P-88" in out
        assert "受影响工艺路线" in out and "R-01" in out
        # 敏感字段不外泄
        assert "SECRET_BEFORE_TEXT" not in out
        assert "SECRET_AFTER_TEXT" not in out
        assert "9.99" not in out and "99.9" not in out

    @pytest.mark.asyncio
    async def test_sections_count_only_without_permission(self):
        resp = _ecn_resp(materials=[_mat_line()])
        patches, fx = _impact_patches(resp, perms=set())
        from apps.kuaizhizao.models.work_order import WorkOrder
        from apps.master_data.models.material_batch import MaterialBatch
        from apps.master_data.models.process import ProcessRoute

        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patch.object(
                WorkOrder, "filter", MagicMock(return_value=_qs([fx["work_order"]]))
            ),
            patch.object(
                MaterialBatch, "filter", MagicMock(return_value=_qs([fx["batch"]]))
            ),
            patch.object(
                MaterialService,
                "list_bom_where_used",
                AsyncMock(
                    return_value={
                        "items": [{"bom_id": 1, "material_id": 88}],
                        "total": 1,
                    }
                ),
            ),
            patch(_RESOLVE_ROUTE, AsyncMock(return_value=401)),
            patch.object(
                ProcessRoute, "filter", MagicMock(return_value=_qs([fx["route"]]))
            ),
        ):
            out = await ecn_impact.analyze_ecn_impact(ecn_id=1, ctx=_ctx())
        assert "无工单读权限" in out
        assert "无库存读权限" in out
        assert "无工程 BOM 读权限" in out
        assert "无工艺路线读权限" in out
        assert "WO-100" not in out and "B-001" not in out

    @pytest.mark.asyncio
    async def test_no_materials(self):
        resp = _ecn_resp(materials=[])
        patches, _ = _impact_patches(resp)
        with patches[0], patches[1], patches[2], patches[3]:
            out = await ecn_impact.analyze_ecn_impact(ecn_id=1, ctx=_ctx())
        assert "变更物料行：无" in out
        assert "无物料行，无下游影响面可查" in out

    @pytest.mark.asyncio
    async def test_section_failure_degrades(self):
        resp = _ecn_resp(materials=[_mat_line()])
        patches, _ = _impact_patches(
            resp,
            perms={
                "kuaizhizao:work-order:read",
                "kuaizhizao:inventory:read",
                "master-data:process:engineering-bom:read",
                "master-data:process:route:read",
            },
        )
        from apps.kuaizhizao.models.work_order import WorkOrder
        from apps.master_data.models.material_batch import MaterialBatch

        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patch.object(
                WorkOrder,
                "filter",
                MagicMock(side_effect=RuntimeError("wo table missing")),
            ),
            patch.object(
                MaterialBatch, "filter", MagicMock(return_value=_qs())
            ),
            patch.object(
                MaterialService,
                "list_bom_where_used",
                AsyncMock(return_value={"items": [], "total": 0}),
            ),
            patch(_RESOLVE_ROUTE, AsyncMock(return_value=None)),
        ):
            out = await ecn_impact.analyze_ecn_impact(ecn_id=1, ctx=_ctx())
        assert "受影响在制工单：查询失败" in out
        assert "受影响库存批次：无" in out
        assert "受影响 BOM 引用：无" in out
        assert "受影响工艺路线：无" in out

    @pytest.mark.asyncio
    async def test_top_level_error_fixed_text(self):
        with patch(
            _APP_BY_CODE, AsyncMock(return_value=_PLM_ON)
        ), patch(
            "apps.kuaiplm.services.engineering_change_service."
            "EngineeringChangeService",
            MagicMock(side_effect=RuntimeError("x")),
        ):
            out = await ecn_impact.analyze_ecn_impact(ecn_id=1, ctx=_ctx())
        assert out == "分析工程变更影响失败，请稍后重试"


def _material_row(**kw):
    base = dict(id=101, uuid="m-uuid-1", main_code="M-101", name="外壳")
    base.update(kw)
    return SimpleNamespace(**base)


def _where_used_item(**kw):
    base = dict(
        bom_id=501,
        material_id=88,
        material_code="P-88",
        material_name="总成",
        bom_code="BOM-88",
        version="1.0",
        quantity=2,
        unit="个",
        approval_status="approved",
        level=1,
        path=None,
    )
    base.update(kw)
    return base


class TestQueryMaterialWhereUsed:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await engineering_bom.query_material_where_used(
            material_id=1, ctx=None
        )
        assert "缺少租户/用户上下文" in out

    @pytest.mark.asyncio
    async def test_bad_material_id(self):
        out = await engineering_bom.query_material_where_used(
            material_id="x", ctx=_ctx()
        )
        assert "material_id 须为物料 ID 整数" in out

    @pytest.mark.asyncio
    async def test_material_not_found(self):
        with patch.object(
            Material, "filter", MagicMock(return_value=_qs())
        ):
            out = await engineering_bom.query_material_where_used(
                material_id=999, ctx=_ctx()
            )
        assert out == "物料不存在"

    @pytest.mark.asyncio
    async def test_material_out_of_scope(self):
        with (
            patch.object(
                Material,
                "filter",
                MagicMock(return_value=_qs([_material_row()])),
            ),
            patch(_SCOPE_IDS, _scope_visible()),
        ):
            out = await engineering_bom.query_material_where_used(
                material_id=101, ctx=_ctx()
            )
        assert out == "当前用户数据范围内无该物料"

    @pytest.mark.asyncio
    async def test_items_output_and_recursive_flag(self):
        items = [_where_used_item(), _where_used_item(bom_id=502)]
        with (
            patch.object(
                Material,
                "filter",
                MagicMock(return_value=_qs([_material_row()])),
            ),
            patch(_SCOPE_IDS, _scope_all()),
            patch.object(
                MaterialService,
                "list_bom_where_used",
                AsyncMock(return_value={"items": items, "total": 2}),
            ) as m_wu,
        ):
            out = await engineering_bom.query_material_where_used(
                material_id=101, recursive=True, ctx=_ctx()
            )
        m_wu.assert_awaited_once_with(TENANT, 101, recursive=True)
        assert "M-101" in out and "P-88" in out and "BOM-88" in out
        assert "多阶" in out

    @pytest.mark.asyncio
    async def test_empty_result(self):
        with (
            patch.object(
                Material,
                "filter",
                MagicMock(return_value=_qs([_material_row()])),
            ),
            patch(_SCOPE_IDS, _scope_all()),
            patch.object(
                MaterialService,
                "list_bom_where_used",
                AsyncMock(return_value={"items": [], "total": 0}),
            ),
        ):
            out = await engineering_bom.query_material_where_used(
                material_id=101, ctx=_ctx()
            )
        assert "未被任何 BOM 引用" in out

    @pytest.mark.asyncio
    async def test_error_fixed_text(self):
        with (
            patch.object(
                Material,
                "filter",
                MagicMock(return_value=_qs([_material_row()])),
            ),
            patch(_SCOPE_IDS, _scope_all()),
            patch.object(
                MaterialService,
                "list_bom_where_used",
                AsyncMock(side_effect=RuntimeError("x")),
            ),
        ):
            out = await engineering_bom.query_material_where_used(
                material_id=101, ctx=_ctx()
            )
        assert out == "查询物料 BOM 反查失败，请稍后重试"


class TestQueryDrawingWhereUsed:
    @pytest.mark.asyncio
    async def test_param_xor(self):
        out = await engineering_bom.query_drawing_where_used(ctx=_ctx())
        assert "须且只须传一个" in out
        out = await engineering_bom.query_drawing_where_used(
            material_id=1, drawing_uuid="d-uuid", ctx=_ctx()
        )
        assert "须且只须传一个" in out

    @pytest.mark.asyncio
    async def test_material_not_found(self):
        with patch.object(Material, "filter", MagicMock(return_value=_qs())):
            out = await engineering_bom.query_drawing_where_used(
                material_id=9, ctx=_ctx()
            )
        assert out == "物料不存在"

    @pytest.mark.asyncio
    async def test_forward_drawings(self):
        resp = SimpleNamespace(
            direction="forward",
            drawings=[
                SimpleNamespace(
                    code="DWG-01",
                    name="外壳图",
                    revision="A",
                    security_level="internal",
                    status="released",
                )
            ],
            usages=[],
        )
        with (
            patch.object(
                Material,
                "filter",
                MagicMock(return_value=_qs([_material_row()])),
            ),
            patch(_SCOPE_IDS, _scope_all()),
            patch.object(
                DrawingWhereUsedService, "query", AsyncMock(return_value=resp)
            ) as m_q,
        ):
            out = await engineering_bom.query_drawing_where_used(
                material_id=101, ctx=_ctx()
            )
        m_q.assert_awaited_once()
        assert m_q.call_args.kwargs.get("material_uuid") == "m-uuid-1"
        assert m_q.call_args.args[0] == TENANT
        assert "DWG-01" in out and "密级 internal" in out

    @pytest.mark.asyncio
    async def test_forward_empty(self):
        resp = SimpleNamespace(direction="forward", drawings=[], usages=[])
        with (
            patch.object(
                Material,
                "filter",
                MagicMock(return_value=_qs([_material_row()])),
            ),
            patch(_SCOPE_IDS, _scope_all()),
            patch.object(
                DrawingWhereUsedService, "query", AsyncMock(return_value=resp)
            ),
        ):
            out = await engineering_bom.query_drawing_where_used(
                material_id=101, ctx=_ctx()
            )
        assert "未被任何图纸引用" in out

    @pytest.mark.asyncio
    async def test_reverse_usages(self):
        resp = SimpleNamespace(
            direction="reverse",
            drawings=[
                SimpleNamespace(code="DWG-01", name="外壳图", revision="A")
            ],
            usages=[
                SimpleNamespace(
                    kind="material", uuid="u", code="M-101", name="外壳",
                    extra=None,
                ),
                SimpleNamespace(
                    kind="work_order", uuid="u2", code="WO-9", name=None,
                    extra="数量10",
                ),
            ],
        )
        with patch.object(
            DrawingWhereUsedService, "query", AsyncMock(return_value=resp)
        ) as m_q:
            out = await engineering_bom.query_drawing_where_used(
                drawing_uuid="d-uuid", ctx=_ctx()
            )
        assert m_q.call_args.kwargs.get("drawing_uuid") == "d-uuid"
        assert "DWG-01" in out and "物料 M-101" in out and "工单 WO-9" in out

    @pytest.mark.asyncio
    async def test_not_found_passthrough(self):
        with patch.object(
            Material,
            "filter",
            MagicMock(return_value=_qs([_material_row()])),
        ), patch(_SCOPE_IDS, _scope_all()), patch.object(
            DrawingWhereUsedService,
            "query",
            AsyncMock(side_effect=NotFoundError("物料", "u")),
        ):
            out = await engineering_bom.query_drawing_where_used(
                material_id=101, ctx=_ctx()
            )
        assert "不存在" in out

    @pytest.mark.asyncio
    async def test_error_fixed_text(self):
        with patch.object(
            DrawingWhereUsedService,
            "query",
            AsyncMock(side_effect=RuntimeError("x")),
        ):
            out = await engineering_bom.query_drawing_where_used(
                drawing_uuid="d-uuid", ctx=_ctx()
            )
        assert out == "查询图纸反查失败，请稍后重试"
