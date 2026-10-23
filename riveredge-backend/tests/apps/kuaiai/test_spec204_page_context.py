"""spec 204 单测：页上下文扩展到 P1 单据页 + 行级数据范围收口。

全部 mock Tortoise / 业务 service，不需要真实数据库。覆盖：
- 新白名单 screen（销售订单/采购订单/质量异常/缺料异常/库存预警）
- 每个新增 reader：范围内出摘要、范围外 record_id → 返回 None（不泄露存在性）、
  无功能读权限 → None、底层异常 → None
- 既有工单 reader 补行级范围：越界 record_id → None 且不触达 service
- 销售订单沿 service current_user 行级校验（service 抛 403 → None）
- 异常单附加关联工单范围求交；库存预警附加 (material, warehouse) 可见对求交
- 摘要不含联系人/电话等敏感字段
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import apps.kuaiai.services.page_context as page_context

TENANT = 7
USER_ID = 5


def _user(uid: int = USER_ID):
    return SimpleNamespace(
        id=uid,
        full_name="测试用户",
        username="tester",
        is_infra_admin=False,
        is_tenant_admin=False,
    )


def _patch_perm(granted=True):
    return patch.object(
        page_context.UserPermissionService,
        "has_permission",
        new=AsyncMock(return_value=granted),
    )


def _patch_row_scope(visible=True):
    """行级数据范围替身：默认放行，越界用例显式传 False。"""
    return patch.object(
        page_context, "_row_in_scope", AsyncMock(return_value=visible)
    )


def _wo(**kw):
    base = dict(
        id=11,
        code="WO-2026-001",
        name="测试工单",
        product_name="产品A",
        status="in_progress",
        quantity=Decimal("100"),
        completed_quantity=Decimal("40"),
    )
    base.update(kw)
    return SimpleNamespace(**base)


class TestRowInScopeHelper:
    """_row_in_scope 统一走 scene_tools._scoped_row_ids（DataScopeService 收口）。"""

    @pytest.mark.asyncio
    async def test_delegates_to_scoped_row_ids(self):
        ctx = SimpleNamespace(tenant_id=TENANT, user=_user())
        scoped = AsyncMock(return_value={11})
        with patch(
            "apps.kuaiai.services.scene_tools._scoped_row_ids", scoped
        ):
            assert (
                await page_context._row_in_scope(
                    ctx, MagicMock(), "kuaizhizao:work-order", 11
                )
                is True
            )
        assert scoped.await_args.args[2] == "kuaizhizao:work-order"
        assert scoped.await_args.args[3] == {11}

        with patch(
            "apps.kuaiai.services.scene_tools._scoped_row_ids",
            AsyncMock(return_value=set()),
        ):
            assert (
                await page_context._row_in_scope(
                    ctx, MagicMock(), "kuaizhizao:work-order", 11
                )
                is False
            )

    @pytest.mark.asyncio
    async def test_scope_resolution_failure_closes(self):
        ctx = SimpleNamespace(tenant_id=TENANT, user=_user())
        with patch(
            "apps.kuaiai.services.scene_tools._scoped_row_ids",
            AsyncMock(side_effect=RuntimeError("rbac down")),
        ):
            assert (
                await page_context._row_in_scope(
                    ctx, MagicMock(), "kuaizhizao:work-order", 11
                )
                is False
            )

    @pytest.mark.asyncio
    async def test_invalid_id_closes(self):
        ctx = SimpleNamespace(tenant_id=TENANT, user=_user())
        assert (
            await page_context._row_in_scope(
                ctx, MagicMock(), "kuaizhizao:work-order", "abc"
            )
            is False
        )
        assert (
            await page_context._row_in_scope(
                ctx, MagicMock(), "kuaizhizao:work-order", -1
            )
            is False
        )


class TestWorkOrderScope:
    """既有工单 reader 补行级数据范围：范围外 record_id 不再产出摘要。"""

    @pytest.mark.asyncio
    async def test_in_scope_returns_summary(self):
        service = MagicMock()
        service.get_work_order_by_id = AsyncMock(return_value=_wo())
        context = {
            "screen": "/apps/kuaizhizao/production-execution/work-orders",
            "resource_key": "kuaizhizao:work_order",
            "record_id": 11,
        }
        with (
            patch(
                "apps.kuaizhizao.services.work_order_service.WorkOrderService",
                return_value=service,
            ),
            _patch_perm(),
            _patch_row_scope(True),
        ):
            result = await page_context.build_page_context_summary(
                context, tenant_id=TENANT, user=_user()
            )
        assert result is not None
        assert "工单管理" in result
        assert "WO-2026-001" in result
        service.get_work_order_by_id.assert_awaited_once_with(TENANT, 11)

    @pytest.mark.asyncio
    async def test_out_of_scope_record_returns_none(self):
        """越界 record_id：整个摘要省略（不回落到仅页名），且不触达 service。"""
        service = MagicMock()
        service.get_work_order_by_id = AsyncMock()
        context = {
            "screen": "/apps/kuaizhizao/production-execution/work-orders",
            "resource_key": "kuaizhizao:work_order",
            "record_id": 999,
        }
        with (
            patch(
                "apps.kuaizhizao.services.work_order_service.WorkOrderService",
                return_value=service,
            ),
            _patch_perm(),
            _patch_row_scope(False),
        ):
            result = await page_context.build_page_context_summary(
                context, tenant_id=TENANT, user=_user()
            )
        assert result is None
        service.get_work_order_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_permission_returns_none(self):
        with (
            _patch_perm(False),
            patch.object(
                page_context, "_row_in_scope", AsyncMock()
            ) as scope,
        ):
            result = await page_context.build_page_context_summary(
                {
                    "screen": "/apps/kuaizhizao/production-execution/work-orders",
                    "resource_key": "kuaizhizao:work_order",
                    "record_id": 11,
                },
                tenant_id=TENANT,
                user=_user(),
            )
        assert result is None
        scope.assert_not_called()

    @pytest.mark.asyncio
    async def test_summary_matches_tool_row_format(self):
        """AC4：工单摘要与 query_workorder Tool 行格式化共用函数，输出一致。"""
        import apps.kuaiai.services.chat_tools as chat_tools

        wo = _wo()
        service = MagicMock()
        service.get_work_order_by_id = AsyncMock(return_value=wo)
        with (
            patch(
                "apps.kuaizhizao.services.work_order_service.WorkOrderService",
                return_value=service,
            ),
            _patch_perm(),
            _patch_row_scope(True),
        ):
            result = await page_context.build_page_context_summary(
                {"resource_key": "kuaizhizao:work_order", "record_id": 11},
                tenant_id=TENANT,
                user=_user(),
            )
        assert result == chat_tools._fmt_work_order_row(wo)


class TestSalesOrderReader:
    def _order(self, **kw):
        base = dict(
            id=21,
            order_code="SO-2026-001",
            customer_name="客户甲",
            customer_contact="张三",
            customer_phone="13800000000",
            status="AUDITED",
            review_status="APPROVED",
            delivery_date="2026-02-01",
            delivery_progress=30.0,
            total_amount=Decimal("9999"),
        )
        base.update(kw)
        return SimpleNamespace(**base)

    @pytest.mark.asyncio
    async def test_in_scope_summary_without_sensitive_fields(self):
        service = MagicMock()
        service.get_sales_order_by_id = AsyncMock(
            return_value=self._order()
        )
        with (
            patch(
                "apps.kuaizhizao.services.sales_order_service.SalesOrderService",
                return_value=service,
            ),
            _patch_perm(),
        ):
            result = await page_context.build_page_context_summary(
                {
                    "screen": "/apps/kuaizhizao/sales-management/sales-orders",
                    "resource_key": "kuaizhizao:sales_order",
                    "record_id": 21,
                },
                tenant_id=TENANT,
                user=_user(),
            )
        assert result is not None
        assert "销售订单" in result
        assert "SO-2026-001" in result
        assert "客户甲" in result
        # AC4：与 query_sales_orders 行格式化同一函数同一输出
        from apps.kuaiai.services.tools.sales_purchase import (
            _fmt_sales_order_row,
        )

        assert _fmt_sales_order_row(self._order()) in result
        # 敏感字段不进摘要
        assert "13800000000" not in result
        assert "张三" not in result
        assert "9999" not in result
        # service current_user 路径是行级校验真源
        kwargs = service.get_sales_order_by_id.await_args.kwargs
        assert kwargs.get("current_user").id == USER_ID

    @pytest.mark.asyncio
    async def test_out_of_scope_via_service_assert_returns_none(self):
        """service 对 current_user 的行级校验抛 403 → 按不存在省略摘要。"""
        service = MagicMock()
        service.get_sales_order_by_id = AsyncMock(
            side_effect=HTTPException(status_code=403, detail="denied")
        )
        with (
            patch(
                "apps.kuaizhizao.services.sales_order_service.SalesOrderService",
                return_value=service,
            ),
            _patch_perm(),
        ):
            result = await page_context.build_page_context_summary(
                {
                    "screen": "/apps/kuaizhizao/sales-management/sales-orders",
                    "resource_key": "kuaizhizao:sales_order",
                    "record_id": 21,
                },
                tenant_id=TENANT,
                user=_user(),
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_no_permission_returns_none(self):
        service = MagicMock()
        service.get_sales_order_by_id = AsyncMock()
        with (
            patch(
                "apps.kuaizhizao.services.sales_order_service.SalesOrderService",
                return_value=service,
            ),
            _patch_perm(False),
        ):
            result = await page_context.build_page_context_summary(
                {
                    "screen": "/apps/kuaizhizao/sales-management/sales-orders",
                    "resource_key": "kuaizhizao:sales_order",
                    "record_id": 21,
                },
                tenant_id=TENANT,
                user=_user(),
            )
        assert result is None
        service.get_sales_order_by_id.assert_not_called()


class TestPurchaseOrderReader:
    def _list_row(self, **kw):
        base = dict(
            id=31,
            order_code="PO-2026-001",
            supplier_name="供应商乙",
            supplier_contact="李四",
            supplier_phone="13900000000",
            status="released",
            review_status="approved",
            delivery_date="2026-03-01",
            outstanding_total=Decimal("5"),
            has_arrival_overdue=False,
        )
        base.update(kw)
        return SimpleNamespace(**base)

    def _model_row(self, **kw):
        base = dict(id=31, order_code="PO-2026-001")
        base.update(kw)
        return SimpleNamespace(**base)

    @pytest.mark.asyncio
    async def test_in_scope_summary_reuses_tool_formatter(self):
        import apps.kuaiai.services.scene_tools as scene_tools

        row = self._list_row()
        service = MagicMock()
        service.list_purchase_orders = AsyncMock(
            return_value={"data": [row], "total": 1}
        )
        with (
            patch(
                "apps.kuaizhizao.services.purchase_service.PurchaseService",
                return_value=service,
            ),
            patch(
                "apps.kuaizhizao.models.purchase_order.PurchaseOrder.get_or_none",
                new=AsyncMock(return_value=self._model_row()),
            ),
            _patch_perm(),
            _patch_row_scope(True),
        ):
            result = await page_context.build_page_context_summary(
                {
                    "screen": "/apps/kuaizhizao/purchase-management/purchase-orders",
                    "resource_key": "kuaizhizao:purchase_order",
                    "record_id": 31,
                },
                tenant_id=TENANT,
                user=_user(),
            )
        assert result is not None
        assert "采购订单" in result
        # AC4：与 query_purchase_followup 行格式化同一函数同一输出
        assert scene_tools._fmt_purchase_order_row(row) in result
        assert "13900000000" not in result
        kwargs = service.list_purchase_orders.await_args.kwargs
        assert kwargs.get("current_user").id == USER_ID

    @pytest.mark.asyncio
    async def test_out_of_scope_record_returns_none(self):
        service = MagicMock()
        service.list_purchase_orders = AsyncMock()
        with (
            patch(
                "apps.kuaizhizao.services.purchase_service.PurchaseService",
                return_value=service,
            ),
            _patch_perm(),
            _patch_row_scope(False),
        ):
            result = await page_context.build_page_context_summary(
                {
                    "screen": "/apps/kuaizhizao/purchase-management/purchase-orders",
                    "resource_key": "kuaizhizao:purchase_order",
                    "record_id": 999,
                },
                tenant_id=TENANT,
                user=_user(),
            )
        assert result is None
        service.list_purchase_orders.assert_not_called()

    @pytest.mark.asyncio
    async def test_row_missing_from_scoped_list_returns_none(self):
        service = MagicMock()
        service.list_purchase_orders = AsyncMock(
            return_value={"data": [self._list_row(id=32)], "total": 1}
        )
        with (
            patch(
                "apps.kuaizhizao.services.purchase_service.PurchaseService",
                return_value=service,
            ),
            patch(
                "apps.kuaizhizao.models.purchase_order.PurchaseOrder.get_or_none",
                new=AsyncMock(return_value=self._model_row()),
            ),
            _patch_perm(),
            _patch_row_scope(True),
        ):
            result = await page_context.build_page_context_summary(
                {
                    "screen": "/apps/kuaizhizao/purchase-management/purchase-orders",
                    "resource_key": "kuaizhizao:purchase_order",
                    "record_id": 31,
                },
                tenant_id=TENANT,
                user=_user(),
            )
        assert result is None


class TestQualityExceptionReader:
    def _exc(self, **kw):
        base = dict(
            id=41,
            work_order_id=11,
            work_order_code="WO-2026-001",
            exception_type="inspection_failure",
            severity="major",
            status="pending",
            problem_description="尺寸超差 0.2mm",
            responsible_person_name="王五",
        )
        base.update(kw)
        return SimpleNamespace(**base)

    @pytest.mark.asyncio
    async def test_in_scope_summary(self):
        from apps.kuaiai.services.tools.kitting_exceptions import (
            _fmt_quality_exception_row,
        )

        exc = self._exc()
        service = MagicMock()
        service.get_quality_exception = AsyncMock(return_value=exc)
        with (
            patch(
                "apps.kuaizhizao.services.exception_service.ExceptionService",
                return_value=service,
            ),
            _patch_perm(),
            _patch_row_scope(True),
        ):
            result = await page_context.build_page_context_summary(
                {
                    "screen": "/apps/kuaizhizao/production-execution/quality-exceptions",
                    "resource_key": "kuaizhizao:quality_exception",
                    "record_id": 41,
                },
                tenant_id=TENANT,
                user=_user(),
            )
        assert result is not None
        assert "质量异常" in result
        assert "WO-2026-001" in result
        # AC4：与 query_quality_exceptions Tool 行格式化同一函数同一输出
        assert _fmt_quality_exception_row(exc) in result

    @pytest.mark.asyncio
    async def test_out_of_scope_record_returns_none(self):
        service = MagicMock()
        service.get_quality_exception = AsyncMock()
        with (
            patch(
                "apps.kuaizhizao.services.exception_service.ExceptionService",
                return_value=service,
            ),
            _patch_perm(),
            _patch_row_scope(False),
        ):
            result = await page_context.build_page_context_summary(
                {
                    "screen": "/apps/kuaizhizao/production-execution/quality-exceptions",
                    "resource_key": "kuaizhizao:quality_exception",
                    "record_id": 999,
                },
                tenant_id=TENANT,
                user=_user(),
            )
        assert result is None
        service.get_quality_exception.assert_not_called()

    @pytest.mark.asyncio
    async def test_linked_work_order_out_of_scope_returns_none(self):
        """异常自身在范围内、但关联工单越界（spec 197：按工单资源求交）→ 不存在。"""
        service = MagicMock()
        service.get_quality_exception = AsyncMock(return_value=self._exc())

        async def _scope(ctx, model, resource, record_id):
            return resource != "kuaizhizao:work-order"

        with (
            patch(
                "apps.kuaizhizao.services.exception_service.ExceptionService",
                return_value=service,
            ),
            _patch_perm(),
            patch.object(
                page_context, "_row_in_scope", AsyncMock(side_effect=_scope)
            ),
        ):
            result = await page_context.build_page_context_summary(
                {
                    "screen": "/apps/kuaizhizao/production-execution/quality-exceptions",
                    "resource_key": "kuaizhizao:quality_exception",
                    "record_id": 41,
                },
                tenant_id=TENANT,
                user=_user(),
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_no_permission_returns_none(self):
        service = MagicMock()
        service.get_quality_exception = AsyncMock()
        with (
            patch(
                "apps.kuaizhizao.services.exception_service.ExceptionService",
                return_value=service,
            ),
            _patch_perm(False),
        ):
            result = await page_context.build_page_context_summary(
                {
                    "screen": "/apps/kuaizhizao/production-execution/quality-exceptions",
                    "resource_key": "kuaizhizao:quality_exception",
                    "record_id": 41,
                },
                tenant_id=TENANT,
                user=_user(),
            )
        assert result is None
        service.get_quality_exception.assert_not_called()


class TestMaterialShortageReader:
    def _exc(self, **kw):
        base = dict(
            id=51,
            work_order_id=11,
            work_order_code="WO-2026-001",
            material_code="M-100",
            material_name="钢板",
            shortage_quantity=Decimal("8"),
            required_quantity=Decimal("20"),
            available_quantity=Decimal("12"),
            alert_level="high",
            status="pending",
            handled_by_name="赵六",
        )
        base.update(kw)
        return SimpleNamespace(**base)

    @pytest.mark.asyncio
    async def test_in_scope_summary(self):
        service = MagicMock()
        service.get_material_shortage_exception = AsyncMock(
            return_value=self._exc()
        )
        with (
            patch(
                "apps.kuaizhizao.services.exception_service.ExceptionService",
                return_value=service,
            ),
            _patch_perm(),
            _patch_row_scope(True),
        ):
            result = await page_context.build_page_context_summary(
                {
                    "screen": "/apps/kuaizhizao/production-execution/material-shortage-exceptions",
                    "resource_key": "kuaizhizao:material_shortage",
                    "record_id": 51,
                },
                tenant_id=TENANT,
                user=_user(),
            )
        assert result is not None
        assert "缺料异常" in result
        assert "M-100" in result
        assert "WO-2026-001" in result
        # AC4：与 query_material_shortages 行格式化同一函数同一输出
        from apps.kuaiai.services.tools.kitting_exceptions import (
            _fmt_material_shortage_row,
        )

        assert _fmt_material_shortage_row(self._exc()) in result
        assert "赵六" not in result

    @pytest.mark.asyncio
    async def test_out_of_scope_record_returns_none(self):
        service = MagicMock()
        service.get_material_shortage_exception = AsyncMock()
        with (
            patch(
                "apps.kuaizhizao.services.exception_service.ExceptionService",
                return_value=service,
            ),
            _patch_perm(),
            _patch_row_scope(False),
        ):
            result = await page_context.build_page_context_summary(
                {
                    "screen": "/apps/kuaizhizao/production-execution/material-shortage-exceptions",
                    "resource_key": "kuaizhizao:material_shortage",
                    "record_id": 999,
                },
                tenant_id=TENANT,
                user=_user(),
            )
        assert result is None
        service.get_material_shortage_exception.assert_not_called()

    @pytest.mark.asyncio
    async def test_linked_work_order_out_of_scope_returns_none(self):
        service = MagicMock()
        service.get_material_shortage_exception = AsyncMock(
            return_value=self._exc()
        )

        async def _scope(ctx, model, resource, record_id):
            return resource != "kuaizhizao:work-order"

        with (
            patch(
                "apps.kuaizhizao.services.exception_service.ExceptionService",
                return_value=service,
            ),
            _patch_perm(),
            patch.object(
                page_context, "_row_in_scope", AsyncMock(side_effect=_scope)
            ),
        ):
            result = await page_context.build_page_context_summary(
                {
                    "screen": "/apps/kuaizhizao/production-execution/material-shortage-exceptions",
                    "resource_key": "kuaizhizao:material_shortage",
                    "record_id": 51,
                },
                tenant_id=TENANT,
                user=_user(),
            )
        assert result is None


class TestInventoryAlertReader:
    def _alert(self, **kw):
        base = dict(
            id=61,
            material_id=101,
            warehouse_id=202,
            material_code="M-200",
            material_name="纸箱",
            warehouse_name="主仓",
            alert_type="low_stock",
            alert_level="critical",
            alert_message="低于安全库存",
            current_quantity=Decimal("5"),
            threshold_value=Decimal("10"),
            status="pending",
            handled_by_name="孙七",
        )
        base.update(kw)
        return SimpleNamespace(**base)

    @pytest.mark.asyncio
    async def test_in_scope_summary(self):
        service = MagicMock()
        service.get_alert_by_id = AsyncMock(return_value=self._alert())
        with (
            patch(
                "apps.kuaizhizao.services.inventory_alert_service.InventoryAlertService",
                return_value=service,
            ),
            patch(
                "apps.kuaiai.services.scene_tools._inventory_visible_pairs",
                AsyncMock(return_value={(101, 202)}),
            ),
            _patch_perm(),
            _patch_row_scope(True),
        ):
            result = await page_context.build_page_context_summary(
                {
                    "screen": "/apps/kuaizhizao/warehouse-management/inventory-alert",
                    "resource_key": "kuaizhizao:inventory_alert",
                    "record_id": 61,
                },
                tenant_id=TENANT,
                user=_user(),
            )
        assert result is not None
        assert "库存预警" in result
        assert "M-200" in result
        assert "主仓" in result
        # AC4：与 query_inventory_alerts 行格式化同一函数同一输出
        from apps.kuaiai.services.tools.inventory_alerts import (
            _fmt_inventory_alert_row,
        )

        assert _fmt_inventory_alert_row(self._alert()) in result
        assert "孙七" not in result

    @pytest.mark.asyncio
    async def test_out_of_scope_record_returns_none(self):
        service = MagicMock()
        service.get_alert_by_id = AsyncMock()
        with (
            patch(
                "apps.kuaizhizao.services.inventory_alert_service.InventoryAlertService",
                return_value=service,
            ),
            _patch_perm(),
            _patch_row_scope(False),
        ):
            result = await page_context.build_page_context_summary(
                {
                    "screen": "/apps/kuaizhizao/warehouse-management/inventory-alert",
                    "resource_key": "kuaizhizao:inventory_alert",
                    "record_id": 999,
                },
                tenant_id=TENANT,
                user=_user(),
            )
        assert result is None
        service.get_alert_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_material_warehouse_pair_out_of_scope_returns_none(self):
        """预警行 (material, warehouse) 不在库存资源可见对 → 按不存在处理。"""
        service = MagicMock()
        service.get_alert_by_id = AsyncMock(return_value=self._alert())
        with (
            patch(
                "apps.kuaizhizao.services.inventory_alert_service.InventoryAlertService",
                return_value=service,
            ),
            patch(
                "apps.kuaiai.services.scene_tools._inventory_visible_pairs",
                AsyncMock(return_value={(999, 888)}),
            ),
            _patch_perm(),
            _patch_row_scope(True),
        ):
            result = await page_context.build_page_context_summary(
                {
                    "screen": "/apps/kuaizhizao/warehouse-management/inventory-alert",
                    "resource_key": "kuaizhizao:inventory_alert",
                    "record_id": 61,
                },
                tenant_id=TENANT,
                user=_user(),
            )
        assert result is None


class TestNewScreenWhitelist:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "screen,page_name",
        [
            ("/apps/kuaizhizao/sales-management/sales-orders", "销售订单"),
            ("/apps/kuaizhizao/purchase-management/purchase-orders", "采购订单"),
            (
                "/apps/kuaizhizao/production-execution/quality-exceptions",
                "质量异常",
            ),
            (
                "/apps/kuaizhizao/production-execution/material-shortage-exceptions",
                "缺料异常",
            ),
            ("/apps/kuaizhizao/warehouse-management/inventory-alert", "库存预警"),
        ],
    )
    async def test_screen_only_pages(self, screen, page_name):
        result = await page_context.build_page_context_summary(
            {"screen": screen}, tenant_id=TENANT, user=_user()
        )
        assert result == f"用户当前位于「{page_name}」页面。"

    @pytest.mark.asyncio
    async def test_unknown_new_resource_returns_none(self):
        result = await page_context.build_page_context_summary(
            {
                "screen": "/apps/kuaizhizao/sales-management/sales-orders",
                "resource_key": "kuaizhizao:secret_table",
                "record_id": 1,
            },
            tenant_id=TENANT,
            user=_user(),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_record_id_returns_none(self):
        with _patch_perm():
            for bad in ("abc", None, -1, 0):
                result = await page_context.build_page_context_summary(
                    {
                        "screen": "/apps/kuaizhizao/sales-management/sales-orders",
                        "resource_key": "kuaizhizao:sales_order",
                        "record_id": bad,
                    },
                    tenant_id=TENANT,
                    user=_user(),
                )
                assert result is None, bad
