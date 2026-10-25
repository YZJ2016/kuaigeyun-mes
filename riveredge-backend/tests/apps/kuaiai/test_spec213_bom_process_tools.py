"""spec 213（S24 BOM/工艺问答）Tool 单元测试。

覆盖 ``query_engineering_bom``（tree/flat/substitutes、level≤5、截断与
总节点数、替代料组如实空态）与 ``query_process_routes(view=parameters)``
（T1 结论=复用既有 Tool，仅补参数视图；计件单价不输出）。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaiai.services.tools import engineering_bom, process_routes
from apps.master_data.models.material import BOM, Material
from apps.master_data.services.material_product_process_service import (
    MaterialProductProcessService,
)
from apps.master_data.services.material_service import MaterialService
from core.ai.runtime.context import AiRuntimeContext
from infra.exceptions.exceptions import NotFoundError

TENANT = 7
USER_ID = 5

_SCOPE_IDS = "apps.kuaiai.services.scene_tools._scoped_row_ids"


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


def _scope_all():
    return AsyncMock(side_effect=lambda model, ctx, resource, ids: set(ids))


def _scope_visible(*allowed):
    allow = set(allowed)
    return AsyncMock(
        side_effect=lambda model, ctx, resource, ids: set(ids) & allow
    )


def _material_row(**kw):
    base = dict(id=101, uuid="m-uuid-1", main_code="M-101", name="外壳")
    base.update(kw)
    return SimpleNamespace(**base)


def _bom_node(component_id=201, children=None, **kw):
    base = dict(
        component_id=component_id,
        component_code="C-201",
        component_name="内衬",
        quantity=2.0,
        unit="个",
        waste_rate=0.5,
        level=0,
        is_alternative=False,
        alternative_group_id=None,
        priority=0,
        is_configurable=False,
        children=list(children or []),
    )
    base.update(kw)
    return base


def _hierarchy(items=None, **kw):
    base = dict(
        material_id=101,
        material_code="M-101",
        material_name="外壳",
        version="2.0",
        items=list(items or []),
    )
    base.update(kw)
    return base


def _material_ok():
    return patch.object(
        Material,
        "filter",
        MagicMock(return_value=_qs([_material_row()])),
    )


class TestQueryEngineeringBom:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await engineering_bom.query_engineering_bom(
            material_id=1, ctx=None
        )
        assert "缺少租户/用户上下文" in out

    @pytest.mark.asyncio
    async def test_param_xor(self):
        out = await engineering_bom.query_engineering_bom(ctx=_ctx())
        assert "须且只须传一个" in out
        out = await engineering_bom.query_engineering_bom(
            material_id=1, bom_id=2, ctx=_ctx()
        )
        assert "须且只须传一个" in out

    @pytest.mark.asyncio
    async def test_view_closed_set(self):
        out = await engineering_bom.query_engineering_bom(
            material_id=1, view="bogus", ctx=_ctx()
        )
        assert "view 仅支持 tree|flat|substitutes" in out

    @pytest.mark.asyncio
    async def test_level_bounds(self):
        for bad in (0, 6, "x"):
            out = await engineering_bom.query_engineering_bom(
                material_id=1, level=bad, ctx=_ctx()
            )
            assert "level 须为 1-5 的整数" in out

    @pytest.mark.asyncio
    async def test_bom_id_resolves_material_and_version(self):
        bom_row = SimpleNamespace(
            id=501, material_id=101, version="2.0"
        )
        with (
            patch.object(
                BOM, "filter", MagicMock(return_value=_qs([bom_row]))
            ),
            _material_ok(),
            patch(_SCOPE_IDS, _scope_all()),
            patch.object(
                MaterialService,
                "generate_bom_hierarchy",
                AsyncMock(
                    return_value=_hierarchy(items=[_bom_node()])
                ),
            ) as m_h,
        ):
            out = await engineering_bom.query_engineering_bom(
                bom_id=501, ctx=_ctx()
            )
        m_h.assert_awaited_once_with(TENANT, 101, version="2.0")
        assert "BOM 版本 2.0" in out and "C-201" in out

    @pytest.mark.asyncio
    async def test_bom_id_not_found(self):
        with patch.object(BOM, "filter", MagicMock(return_value=_qs())):
            out = await engineering_bom.query_engineering_bom(
                bom_id=999, ctx=_ctx()
            )
        assert out == "BOM 不存在"

    @pytest.mark.asyncio
    async def test_material_not_found(self):
        with patch.object(Material, "filter", MagicMock(return_value=_qs())):
            out = await engineering_bom.query_engineering_bom(
                material_id=999, ctx=_ctx()
            )
        assert out == "物料不存在"

    @pytest.mark.asyncio
    async def test_material_out_of_scope(self):
        with (
            _material_ok(),
            patch(_SCOPE_IDS, _scope_visible()),
        ):
            out = await engineering_bom.query_engineering_bom(
                material_id=101, ctx=_ctx()
            )
        assert out == "当前用户数据范围内无该物料"

    @pytest.mark.asyncio
    async def test_tree_view_indents_levels(self):
        child = _bom_node(component_id=202, component_code="C-202", level=1)
        tree = _bom_node(children=[child])
        with (
            _material_ok(),
            patch(_SCOPE_IDS, _scope_all()),
            patch.object(
                MaterialService,
                "generate_bom_hierarchy",
                AsyncMock(return_value=_hierarchy(items=[tree])),
            ),
        ):
            out = await engineering_bom.query_engineering_bom(
                material_id=101, view="tree", ctx=_ctx()
            )
        assert "共 2 节点" in out
        lines = out.splitlines()
        # 根节点缩进 1 级、子件缩进 2 级
        assert lines[1].startswith("  C-201")
        assert lines[2].startswith("    C-202")
        assert "损耗" in out and "用量" in out

    @pytest.mark.asyncio
    async def test_tree_level_cap(self):
        child = _bom_node(component_id=202, component_code="C-202", level=1)
        tree = _bom_node(children=[child])
        with (
            _material_ok(),
            patch(_SCOPE_IDS, _scope_all()),
            patch.object(
                MaterialService,
                "generate_bom_hierarchy",
                AsyncMock(return_value=_hierarchy(items=[tree])),
            ),
        ):
            out = await engineering_bom.query_engineering_bom(
                material_id=101, view="tree", level=1, ctx=_ctx()
            )
        assert "C-201" in out and "C-202" not in out
        assert "共 1 节点" in out

    @pytest.mark.asyncio
    async def test_flat_view_numbered(self):
        items = [_bom_node(), _bom_node(component_id=202, component_code="C-202")]
        with (
            _material_ok(),
            patch(_SCOPE_IDS, _scope_all()),
            patch.object(
                MaterialService,
                "generate_bom_hierarchy",
                AsyncMock(return_value=_hierarchy(items=items)),
            ),
        ):
            out = await engineering_bom.query_engineering_bom(
                material_id=101, view="flat", ctx=_ctx()
            )
        assert "1. L1" in out and "2. L1" in out

    @pytest.mark.asyncio
    async def test_substitutes_groups(self):
        alt1 = _bom_node(
            component_id=211,
            component_code="C-211",
            is_alternative=True,
            alternative_group_id=5,
            priority=2,
        )
        alt2 = _bom_node(
            component_id=212,
            component_code="C-212",
            is_alternative=True,
            alternative_group_id=5,
            priority=1,
        )
        with (
            _material_ok(),
            patch(_SCOPE_IDS, _scope_all()),
            patch.object(
                MaterialService,
                "generate_bom_hierarchy",
                AsyncMock(return_value=_hierarchy(items=[alt1, alt2])),
            ),
        ):
            out = await engineering_bom.query_engineering_bom(
                material_id=101, view="substitutes", ctx=_ctx()
            )
        assert "1 个替代料组" in out and "替代组 5" in out
        # 按优先级升序：C-212(priority=1) 在前
        assert out.index("C-212") < out.index("C-211")

    @pytest.mark.asyncio
    async def test_substitutes_empty_truthful(self):
        with (
            _material_ok(),
            patch(_SCOPE_IDS, _scope_all()),
            patch.object(
                MaterialService,
                "generate_bom_hierarchy",
                AsyncMock(return_value=_hierarchy(items=[_bom_node()])),
            ),
        ):
            out = await engineering_bom.query_engineering_bom(
                material_id=101, view="substitutes", ctx=_ctx()
            )
        assert "无替代料组配置" in out

    @pytest.mark.asyncio
    async def test_empty_bom(self):
        with (
            _material_ok(),
            patch(_SCOPE_IDS, _scope_all()),
            patch.object(
                MaterialService,
                "generate_bom_hierarchy",
                AsyncMock(return_value=_hierarchy(items=[])),
            ),
        ):
            out = await engineering_bom.query_engineering_bom(
                material_id=101, ctx=_ctx()
            )
        assert "无 BOM 明细" in out

    @pytest.mark.asyncio
    async def test_node_truncation_states_total(self):
        items = [
            _bom_node(component_id=300 + i, component_code=f"C-{300 + i}")
            for i in range(55)
        ]
        with (
            _material_ok(),
            patch(_SCOPE_IDS, _scope_all()),
            patch.object(
                MaterialService,
                "generate_bom_hierarchy",
                AsyncMock(return_value=_hierarchy(items=items)),
            ),
        ):
            out = await engineering_bom.query_engineering_bom(
                material_id=101, view="flat", ctx=_ctx()
            )
        assert "共 55 节点" in out
        assert "已截断" in out and "前 50" in out
        assert "C-351" not in out

    @pytest.mark.asyncio
    async def test_out_of_scope_subtree_hidden(self):
        hidden_child = _bom_node(
            component_id=203, component_code="C-203", level=1
        )
        hidden = _bom_node(
            component_id=202, component_code="C-202", children=[hidden_child]
        )
        with (
            _material_ok(),
            # 物料本体 + C-201 可见；C-202 及其子树不可见
            patch(_SCOPE_IDS, _scope_visible(101, 201)),
            patch.object(
                MaterialService,
                "generate_bom_hierarchy",
                AsyncMock(
                    return_value=_hierarchy(items=[_bom_node(), hidden])
                ),
            ),
        ):
            out = await engineering_bom.query_engineering_bom(
                material_id=101, view="flat", ctx=_ctx()
            )
        assert "C-201" in out
        assert "C-202" not in out and "C-203" not in out
        assert "2 个节点超出当前用户数据范围" in out

    @pytest.mark.asyncio
    async def test_error_fixed_text(self):
        with (
            _material_ok(),
            patch(_SCOPE_IDS, _scope_all()),
            patch.object(
                MaterialService,
                "generate_bom_hierarchy",
                AsyncMock(side_effect=RuntimeError("x")),
            ),
        ):
            out = await engineering_bom.query_engineering_bom(
                material_id=101, ctx=_ctx()
            )
        assert out == "查询工程 BOM 失败，请稍后重试"


def _line(**kw):
    base = dict(
        code="OP10",
        name="下料",
        standard_time=3600.0,
        standard_time_qty=1.0,
        setup_time=300.0,
        reporting_type="quantity",
        is_node_operation=False,
        is_outsourced=False,
        outsource_lead_time_days=None,
        outsource_supplier_name=None,
        over_report_mode="none",
        over_report_value=0,
        piece_rate="12.34",
    )
    base.update(kw)
    return SimpleNamespace(**base)


class TestQueryProcessRoutesParameters:
    """T3：复用 query_process_routes，仅补 view=parameters（T1 结论）。"""

    @pytest.mark.asyncio
    async def test_view_closed_set(self):
        out = await process_routes.query_process_routes(
            view="bogus", ctx=_ctx()
        )
        assert "view 仅支持 nodes|parameters" in out

    @pytest.mark.asyncio
    async def test_parameters_requires_material_id(self):
        out = await process_routes.query_process_routes(
            view="parameters", ctx=_ctx()
        )
        assert "view=parameters 须传 material_id" in out

    @pytest.mark.asyncio
    async def test_material_not_found(self):
        with patch.object(Material, "filter", MagicMock(return_value=_qs())):
            out = await process_routes.query_process_routes(
                material_id=9, view="parameters", ctx=_ctx()
            )
        assert out == "物料不存在"

    @pytest.mark.asyncio
    async def test_material_out_of_scope(self):
        with (
            _material_ok(),
            patch(_SCOPE_IDS, _scope_visible()),
        ):
            out = await process_routes.query_process_routes(
                material_id=101, view="parameters", ctx=_ctx()
            )
        assert out == "当前用户数据范围内无该物料"

    @pytest.mark.asyncio
    async def test_parameters_output_no_piece_rate(self):
        resp = SimpleNamespace(
            lines=[
                _line(),
                _line(
                    code="OP20",
                    name="焊接",
                    reporting_type="status",
                    is_node_operation=True,
                    is_outsourced=True,
                    outsource_lead_time_days=3,
                    outsource_supplier_name="供应商甲",
                    over_report_mode="fixed",
                    over_report_value=2,
                ),
            ]
        )
        with (
            _material_ok(),
            patch(_SCOPE_IDS, _scope_all()),
            patch.object(
                MaterialProductProcessService,
                "get_for_material",
                AsyncMock(return_value=resp),
            ) as m_g,
        ):
            out = await process_routes.query_process_routes(
                material_id=101, view="parameters", ctx=_ctx()
            )
        m_g.assert_awaited_once_with(TENANT, "m-uuid-1")
        assert "共 2 道" in out
        assert "OP10" in out and "3600 秒" in out and "准备 300 秒" in out
        assert "OP20" in out and "节点工序" in out and "委外" in out
        assert "超报 fixed 2" in out
        # 计件单价（工资敏感）不输出
        assert "12.34" not in out

    @pytest.mark.asyncio
    async def test_parameters_limit_clamped(self):
        resp = SimpleNamespace(
            lines=[_line(code=f"OP{i:02d}") for i in range(1, 26)]
        )
        with (
            _material_ok(),
            patch(_SCOPE_IDS, _scope_all()),
            patch.object(
                MaterialProductProcessService,
                "get_for_material",
                AsyncMock(return_value=resp),
            ),
        ):
            out = await process_routes.query_process_routes(
                material_id=101, view="parameters", limit=99, ctx=_ctx()
            )
        assert "共 25 道，返回前 20 道" in out
        assert "另有 5 道未展开" in out

    @pytest.mark.asyncio
    async def test_parameters_empty(self):
        with (
            _material_ok(),
            patch(_SCOPE_IDS, _scope_all()),
            patch.object(
                MaterialProductProcessService,
                "get_for_material",
                AsyncMock(return_value=SimpleNamespace(lines=[])),
            ),
        ):
            out = await process_routes.query_process_routes(
                material_id=101, view="parameters", ctx=_ctx()
            )
        assert "暂无配置工序参数" in out

    @pytest.mark.asyncio
    async def test_parameters_not_found_error(self):
        with (
            _material_ok(),
            patch(_SCOPE_IDS, _scope_all()),
            patch.object(
                MaterialProductProcessService,
                "get_for_material",
                AsyncMock(side_effect=NotFoundError("物料", "u")),
            ),
        ):
            out = await process_routes.query_process_routes(
                material_id=101, view="parameters", ctx=_ctx()
            )
        assert out == "物料不存在"

    @pytest.mark.asyncio
    async def test_parameters_error_fixed_text(self):
        with (
            _material_ok(),
            patch(_SCOPE_IDS, _scope_all()),
            patch.object(
                MaterialProductProcessService,
                "get_for_material",
                AsyncMock(side_effect=RuntimeError("x")),
            ),
        ):
            out = await process_routes.query_process_routes(
                material_id=101, view="parameters", ctx=_ctx()
            )
        assert out == "查询工艺路线失败，请稍后重试"
