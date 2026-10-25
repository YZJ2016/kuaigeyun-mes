"""KU-AI spec 216 单测：query_molds / query_tooling。

全部 mock / 假数据，不需要真实数据库。覆盖：
- 闭集参数（status 经 normalize_*_status 归一 + 闭集校验、
  life_warning_only 布尔归一）非法回固定文案；
- 底层 service 不接收 current_user：适配层用
  ``scene_tools._scoped_row_ids`` 套页面资源键行级收敛；
- 寿命字段确定性计算（design_lifetime/total_usage_count）；
  life_warning_only 只列剩余寿命 <20% 的行，无寿命数据行不进预警名单；
- location 对 storage_location 适配层后过滤；领用/归还快照字段输出；
- 不输出供应商/制造商/采购日期等商务信息；
- 空结果、底层异常、limit 截断与既有 Tool 口径一致。
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaiai.services.tools import mold_tooling as mt
from core.ai.runtime.context import AiRuntimeContext

TENANT = 7
USER_ID = 5


def _ctx():
    return AiRuntimeContext(
        tenant_id=TENANT,
        user=SimpleNamespace(id=USER_ID, full_name="测试", username="t"),
    )


def _scope_patch(visible):
    return patch(
        "apps.kuaiai.services.scene_tools._scoped_row_ids",
        new=AsyncMock(return_value=visible),
    )


def _mold(**kw):
    base = dict(
        id=1,
        uuid="mold-uuid-1",
        code="M-078",
        name="汽车门板注塑模",
        type="注塑模具",
        status="在用",
        is_active=True,
        total_usage_count=80000,
        design_lifetime=100000,
        last_maintenance_date=date(2026, 1, 10),
        supplier="某模具供应商",
        manufacturer="某制造商",
        purchase_date=date(2024, 3, 1),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _mold_service(rows=None):
    svc = SimpleNamespace()
    svc.list_molds = AsyncMock(
        return_value=(rows if rows is not None else [], len(rows or []))
    )
    return svc


def _tool(**kw):
    base = dict(
        id=1,
        uuid="tool-uuid-1",
        code="T-110",
        name="面板装配治具",
        type="治具",
        status="在用",
        is_active=True,
        storage_location="工装库 A-03",
        custodian_name="王五",
        current_borrower_name="李四",
        current_borrow_at=datetime(2026, 1, 20, 9, 30),
        last_return_at=datetime(2026, 1, 5, 17, 0),
        last_return_by_name="赵六",
        supplier="某工装供应商",
        manufacturer="某制造商",
        purchase_date=date(2024, 6, 1),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _tool_service(rows=None):
    svc = SimpleNamespace()
    svc.list_tools = AsyncMock(
        return_value=(rows if rows is not None else [], len(rows or []))
    )
    return svc


class TestQueryMolds:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await mt.query_molds(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_status_and_bool(self):
        out = await mt.query_molds(status="bogus", ctx=_ctx())
        assert "status" in out and "待用" in out
        out = await mt.query_molds(life_warning_only="maybe", ctx=_ctx())
        assert "life_warning_only" in out

    @pytest.mark.asyncio
    async def test_status_normalized(self):
        """历史状态值经 normalize_mold_status 归一后下传 service。"""
        svc = _mold_service(rows=[_mold()])
        with patch(
            "apps.kuaizhizao.services.mold_service.MoldService", svc
        ), _scope_patch({1}):
            out = await mt.query_molds(status="正常", ctx=_ctx())
        kw = svc.list_molds.await_args.kwargs
        assert kw["status"] == "待用"
        assert "M-078" in out

    @pytest.mark.asyncio
    async def test_list_scoped_and_formatted(self):
        svc = _mold_service(
            rows=[
                _mold(),
                _mold(id=2, uuid="m2", code="M-081", name="冲压模"),
            ]
        )
        with patch(
            "apps.kuaizhizao.services.mold_service.MoldService", svc
        ), _scope_patch({1}) as m_scope:
            out = await mt.query_molds(keyword="注塑", ctx=_ctx())
        args = m_scope.await_args.args
        assert args[2] == "kuaizhizao:equipment-management-molds"
        assert args[3] == {1, 2}
        kw = svc.list_molds.await_args.kwargs
        assert kw["keyword"] == "注塑"
        # 寿命口径：80000/100000 → 剩余 20.0%
        assert "M-078" in out and "汽车门板注塑模" in out
        assert "累计模次 80,000" in out or "累计模次 80000" in out
        assert "寿命上限" in out and "剩余寿命 20.0%" in out
        assert "最近保养" in out and "在用" in out
        assert "M-081" not in out  # 范围外被剔除
        # 商务信息不输出
        assert "某模具供应商" not in out and "某制造商" not in out
        assert "2024-03-01" not in out

    @pytest.mark.asyncio
    async def test_no_lifetime_data(self):
        svc = _mold_service(rows=[_mold(design_lifetime=None)])
        with patch(
            "apps.kuaizhizao.services.mold_service.MoldService", svc
        ), _scope_patch({1}):
            out = await mt.query_molds(ctx=_ctx())
        assert "无寿命数据" in out and "寿命上限 未设置" in out

    @pytest.mark.asyncio
    async def test_life_warning_only_filters(self):
        """低于 20% 阈值的列出；无寿命数据行不进预警名单。"""
        svc = _mold_service(
            rows=[
                _mold(id=1, code="M-078"),  # 剩余 20% → 不预警（<20 才计）
                _mold(
                    id=2,
                    uuid="m2",
                    code="M-090",
                    total_usage_count=95000,
                    design_lifetime=100000,
                ),  # 剩余 5% → 预警
                _mold(
                    id=3,
                    uuid="m3",
                    code="M-099",
                    design_lifetime=None,
                ),  # 无寿命数据 → 排除
            ]
        )
        with patch(
            "apps.kuaizhizao.services.mold_service.MoldService", svc
        ), _scope_patch({1, 2, 3}):
            out = await mt.query_molds(life_warning_only=True, ctx=_ctx())
        assert "M-090" in out and "剩余寿命 5.0%" in out
        assert "M-078" not in out
        assert "M-099" not in out

    @pytest.mark.asyncio
    async def test_life_warning_over_limit_clamps_zero(self):
        svc = _mold_service(
            rows=[
                _mold(
                    total_usage_count=120000,
                    design_lifetime=100000,
                )
            ]
        )
        with patch(
            "apps.kuaizhizao.services.mold_service.MoldService", svc
        ), _scope_patch({1}):
            out = await mt.query_molds(life_warning_only=True, ctx=_ctx())
        assert "剩余寿命 0.0%" in out

    @pytest.mark.asyncio
    async def test_life_warning_uses_unrounded_ratio(self):
        """预警判定按未舍入真实比值：真实 19.96%（展示舍入 20.0%）命中，
        真实 20.04%（展示舍入 20.0%）不命中。"""
        svc = _mold_service(
            rows=[
                _mold(
                    id=1,
                    code="M-196",
                    total_usage_count=4002,
                    design_lifetime=5000,
                ),  # 剩余 998/5000 = 19.96% → 展示 20.0%，命中预警
                _mold(
                    id=2,
                    uuid="m2",
                    code="M-204",
                    total_usage_count=3998,
                    design_lifetime=5000,
                ),  # 剩余 1002/5000 = 20.04% → 展示 20.0%，不命中
            ]
        )
        with patch(
            "apps.kuaizhizao.services.mold_service.MoldService", svc
        ), _scope_patch({1, 2}):
            out = await mt.query_molds(life_warning_only=True, ctx=_ctx())
        assert "共 1 副模具剩余寿命低于 20%" in out
        assert "M-196" in out and "剩余寿命 20.0%" in out
        assert "M-204" not in out

    @pytest.mark.asyncio
    async def test_limit_clamped(self):
        """limit 钳位：>20 钳到 20，≤0 钳到 1（与 _clamp_limit 同口径）。"""
        svc = _mold_service(
            rows=[
                _mold(id=i, uuid=f"m{i}", code=f"M-{i:03d}")
                for i in range(1, 26)
            ]
        )
        with patch(
            "apps.kuaizhizao.services.mold_service.MoldService", svc
        ), _scope_patch(set(range(1, 26))):
            out = await mt.query_molds(limit=999, ctx=_ctx())
        assert "共 25 副模具" in out and "返回前 20 副" in out
        with patch(
            "apps.kuaizhizao.services.mold_service.MoldService", svc
        ), _scope_patch(set(range(1, 26))):
            out = await mt.query_molds(limit=0, ctx=_ctx())
        assert "返回前 1 副" in out

    @pytest.mark.asyncio
    async def test_empty_and_error(self):
        svc = _mold_service(rows=[])
        with patch(
            "apps.kuaizhizao.services.mold_service.MoldService", svc
        ), _scope_patch(set()):
            out = await mt.query_molds(ctx=_ctx())
        assert "未查询到" in out
        with patch(
            "apps.kuaizhizao.services.mold_service.MoldService", svc
        ), _scope_patch(set()):
            out = await mt.query_molds(life_warning_only=True, ctx=_ctx())
        assert "寿命预警" in out and "未查询到" in out
        svc.list_molds = AsyncMock(side_effect=RuntimeError("db down"))
        with patch(
            "apps.kuaizhizao.services.mold_service.MoldService", svc
        ):
            out = await mt.query_molds(ctx=_ctx())
        assert out == "查询模具台账失败，请稍后重试"
        assert "db down" not in out


class TestQueryTooling:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await mt.query_tooling(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_status(self):
        out = await mt.query_tooling(status="bogus", ctx=_ctx())
        assert "status" in out and "待用" in out

    @pytest.mark.asyncio
    async def test_status_normalized(self):
        svc = _tool_service(rows=[_tool()])
        with patch(
            "apps.kuaizhizao.services.tool_service.ToolService", svc
        ), _scope_patch({1}):
            out = await mt.query_tooling(status="领用中", ctx=_ctx())
        kw = svc.list_tools.await_args.kwargs
        assert kw["status"] == "在用"
        assert "T-110" in out

    @pytest.mark.asyncio
    async def test_list_scoped_and_formatted(self):
        svc = _tool_service(
            rows=[
                _tool(),
                _tool(id=2, uuid="t2", code="T-111", name="检具"),
            ]
        )
        with patch(
            "apps.kuaizhizao.services.tool_service.ToolService", svc
        ), _scope_patch({1}) as m_scope:
            out = await mt.query_tooling(keyword="治具", ctx=_ctx())
        args = m_scope.await_args.args
        assert args[2] == "kuaizhizao:equipment-management-tool-ledger"
        assert args[3] == {1, 2}
        kw = svc.list_tools.await_args.kwargs
        assert kw["keyword"] == "治具"
        assert "T-110" in out and "面板装配治具" in out
        assert "工装库 A-03" in out and "在用" in out
        assert "李四" in out and "赵六" in out  # 领用/归还快照
        assert "T-111" not in out  # 范围外被剔除
        # 商务信息不输出
        assert "某工装供应商" not in out and "某制造商" not in out
        assert "2024-06-01" not in out

    @pytest.mark.asyncio
    async def test_location_post_filter(self):
        svc = _tool_service(
            rows=[
                _tool(),
                _tool(
                    id=2,
                    uuid="t2",
                    code="T-120",
                    storage_location="工装库 B-01",
                ),
            ]
        )
        with patch(
            "apps.kuaizhizao.services.tool_service.ToolService", svc
        ), _scope_patch({1, 2}):
            out = await mt.query_tooling(location="a-03", ctx=_ctx())
        assert "T-110" in out and "T-120" not in out
        # location 不下传 service（无形参）
        kw = svc.list_tools.await_args.kwargs
        assert "location" not in kw

    @pytest.mark.asyncio
    async def test_unborrowed_row(self):
        svc = _tool_service(
            rows=[
                _tool(
                    current_borrower_name=None,
                    current_borrow_at=None,
                    last_return_at=None,
                    last_return_by_name=None,
                )
            ]
        )
        with patch(
            "apps.kuaizhizao.services.tool_service.ToolService", svc
        ), _scope_patch({1}):
            out = await mt.query_tooling(ctx=_ctx())
        assert "当前未领用" in out and "最近归还" not in out

    @pytest.mark.asyncio
    async def test_limit_clamped(self):
        """limit 钳位：>20 钳到 20（与 _clamp_limit 同口径）。"""
        svc = _tool_service(
            rows=[
                _tool(id=i, uuid=f"t{i}", code=f"T-{i:03d}")
                for i in range(1, 26)
            ]
        )
        with patch(
            "apps.kuaizhizao.services.tool_service.ToolService", svc
        ), _scope_patch(set(range(1, 26))):
            out = await mt.query_tooling(limit=999, ctx=_ctx())
        assert "共 25 件工装" in out and "返回前 20 件" in out

    @pytest.mark.asyncio
    async def test_empty_and_error(self):
        svc = _tool_service(rows=[])
        with patch(
            "apps.kuaizhizao.services.tool_service.ToolService", svc
        ), _scope_patch(set()):
            out = await mt.query_tooling(ctx=_ctx())
        assert "未查询到" in out
        svc.list_tools = AsyncMock(side_effect=RuntimeError("db down"))
        with patch(
            "apps.kuaizhizao.services.tool_service.ToolService", svc
        ):
            out = await mt.query_tooling(ctx=_ctx())
        assert out == "查询工装台账失败，请稍后重试"
        assert "db down" not in out
