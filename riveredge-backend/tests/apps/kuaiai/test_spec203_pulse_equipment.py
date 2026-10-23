"""KU-AI spec 203 单测：Pulse 设备故障 detector（全部 mock，不触真库）。

代码事实表（写死在本测试固定边界的真实代码依据）：
- EquipmentFault.status 闭集 待处理/处理中/已修复/已关闭
  （models/equipment_fault.py:88）；未闭环闭集 =
  equipment_fault_service._OPEN_FAULT_STATUSES（待处理/处理中，
  驱动设备「故障」主数据状态同一口径）；
- EquipmentFault.fault_level 闭集 轻微/一般/严重/紧急（:81）；
- 读权限 kuaizhizao:equipment-fault:read / 数据范围
  kuaizhizao:equipment-fault / 路由
  /apps/kuaizhizao/equipment-management/equipment-faults
  （manifest code_rule_pages.page_path + SCENE_ROUTE_PERMISSIONS 白名单）；
- E1=a：本单元只接 MES 设备故障单；kuaiiot 设备告警另立单元
  （传感器已告警但未报修的设备在接入前不出现在 Pulse）。

覆盖：严重度/优先级逐值矩阵、状态闭集钉死、权限失败关闭零泄露、租户隔离、
数据范围资源键、200 条批次扫描、空候选、持续天数事实、registry 注册与
逐域权限失败隔离、白名单路由。
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call
from zoneinfo import ZoneInfo

import pytest

import core.utils.timezone_utils as tz_utils
from apps.kuaiai.services.pulse import registry as pulse_registry
from apps.kuaiai.services.pulse.base import (
    PulseContext,
    PulsePermissionDenied,
)
from apps.kuaiai.services.pulse.equipment import (
    OPEN_FAULT_STATUSES,
    EquipmentFaultDetector,
)

TENANT = 7
USER_ID = 5
SH = ZoneInfo("Asia/Shanghai")
# 固定业务时刻：UTC 2026-01-09 16:30 → 上海 2026-01-10 00:30
FIXED_NOW = datetime(2026, 1, 9, 16, 30, tzinfo=timezone.utc)
TODAY = date(2026, 1, 10)


def _user(uid: int = USER_ID):
    return SimpleNamespace(id=uid, full_name="测试用户", username="tester")


def _ctx(tenant_id: int = TENANT, user=None):
    return PulseContext(
        tenant_id=tenant_id,
        user=user if user is not None else _user(),
        now=FIXED_NOW,
        today=TODAY,
    )


def _qs(rows=()):
    """模拟 Tortoise QuerySet 链（filter/exclude/order_by/limit → all）。"""
    q = MagicMock()
    for m in ("filter", "exclude", "order_by", "limit", "offset"):
        setattr(q, m, MagicMock(return_value=q))
    q.all = AsyncMock(return_value=list(rows))
    return q


def _paged_qs(rows):
    """模拟 offset/limit 分批读取，保留调用记录供批次边界断言。"""
    q = _qs([])

    async def _all():
        offset = q.offset.call_args.args[0] if q.offset.call_args else 0
        limit = q.limit.call_args.args[0] if q.limit.call_args else len(rows)
        return list(rows[offset : offset + limit])

    q.all = AsyncMock(side_effect=_all)
    return q


def _fault(**kw):
    base = dict(
        id=501,
        uuid="fault-uuid-1",
        fault_no="FLT-001",
        equipment_id=61,
        equipment_uuid="eq-uuid-1",
        equipment_code="EQ-001",
        equipment_name="注塑机一号",
        fault_date=datetime(2026, 1, 8, 10, 0),
        fault_type="机械故障",
        fault_description="主轴异响 需停机检查",
        fault_level="严重",
        status="待处理",
        deleted_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch):
    """固定站点时区与业务时刻（所有脉冲测试共享同一业务日）。"""
    monkeypatch.setattr(
        tz_utils,
        "resolve_business_datetime",
        lambda value=None: FIXED_NOW
        if value is None
        else tz_utils.coerce_business_datetime_to_utc(value),
    )
    monkeypatch.setattr(tz_utils, "site_timezone_name", lambda: "Asia/Shanghai")

    def _to_site(dt):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(SH)

    monkeypatch.setattr(tz_utils, "to_site_timezone", _to_site)


@pytest.fixture
def perm_ok(monkeypatch):
    mock = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "core.services.authorization.user_permission_service."
        "UserPermissionService.has_permission",
        mock,
    )
    return mock


@pytest.fixture
def scope_passthrough(monkeypatch):
    mock = AsyncMock(side_effect=lambda qs, **kw: qs)
    monkeypatch.setattr(
        "core.services.authorization.data_scope_service."
        "DataScopeService.apply",
        mock,
    )
    return mock


# ============================================================ 设备故障 detector


class TestEquipmentFaultDetector:
    def _patch(self, monkeypatch, rows):
        qs = _qs(rows)
        mock_filter = MagicMock(return_value=qs)
        monkeypatch.setattr(
            "apps.kuaizhizao.models.equipment_fault.EquipmentFault.filter",
            mock_filter,
        )
        return qs, mock_filter

    @pytest.mark.asyncio
    async def test_open_fault_produces_item(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        self._patch(monkeypatch, [_fault()])
        items = await EquipmentFaultDetector().detect(_ctx())
        assert len(items) == 1
        it = items[0]
        assert it.domain == "equipment"
        assert it.rule_code == "equipment_fault"
        assert it.id == "equipment:equipment_fault:501"
        assert it.severity == "error" and it.priority == "high"
        assert it.resource_type == "equipment_fault"
        assert it.resource_id == "501"
        assert it.resource_uuid == "fault-uuid-1"
        assert it.route == "/apps/kuaizhizao/equipment-management/equipment-faults"
        assert "EQ-001" in it.fact and "注塑机一号" in it.fact
        assert "待处理" in it.fact
        assert "持续 2 天" in it.fact  # 1-08 → 1-10，时长只进事实描述
        assert it.detected_at == FIXED_NOW

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("fault_level", "severity", "priority"),
        (
            ("紧急", "critical", "high"),
            ("严重", "error", "high"),
            ("一般", "warning", "medium"),
            ("轻微", "info", "low"),
            ("未知级别", "warning", "medium"),  # 未知值兜底，不臆造级别
        ),
    )
    async def test_severity_matrix(
        self,
        fault_level,
        severity,
        priority,
        perm_ok,
        scope_passthrough,
        monkeypatch,
    ):
        self._patch(monkeypatch, [_fault(fault_level=fault_level)])
        items = await EquipmentFaultDetector().detect(_ctx())
        assert items[0].severity == severity
        assert items[0].priority == priority

    @pytest.mark.asyncio
    async def test_open_status_closed_set_pinned(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        """未闭环闭集须与 equipment_fault_service._OPEN_FAULT_STATUSES 一致。"""
        qs, mock_filter = self._patch(monkeypatch, [])
        await EquipmentFaultDetector().detect(_ctx())
        from apps.kuaizhizao.services.equipment_fault_service import (
            _OPEN_FAULT_STATUSES,
        )

        assert tuple(OPEN_FAULT_STATUSES) == tuple(_OPEN_FAULT_STATUSES)
        kwargs = mock_filter.call_args.kwargs
        assert kwargs["tenant_id"] == TENANT
        assert kwargs["deleted_at__isnull"] is True
        assert kwargs["status__in"] == ["待处理", "处理中"]
        assert "已修复" not in kwargs["status__in"]
        assert "已关闭" not in kwargs["status__in"]
        qs.all.assert_awaited_once()  # 单查询，无逐卡 N+1

    @pytest.mark.asyncio
    async def test_scans_in_bounded_batches(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        rows = [
            _fault(id=i + 1, uuid=f"f-{i + 1}") for i in range(250)
        ]
        qs = _paged_qs(rows)
        monkeypatch.setattr(
            "apps.kuaizhizao.models.equipment_fault.EquipmentFault.filter",
            MagicMock(return_value=qs),
        )
        items = await EquipmentFaultDetector().detect(_ctx())
        assert len(items) == 250
        assert qs.limit.call_args_list == [call(200), call(200)]
        assert qs.offset.call_args_list == [call(0), call(200)]

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        self._patch(monkeypatch, [])
        assert await EquipmentFaultDetector().detect(_ctx()) == []

    @pytest.mark.asyncio
    async def test_no_permission_denies_and_leaks_nothing(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        perm_ok.return_value = False
        mock_filter = MagicMock()
        monkeypatch.setattr(
            "apps.kuaizhizao.models.equipment_fault.EquipmentFault.filter",
            mock_filter,
        )
        with pytest.raises(PulsePermissionDenied):
            await EquipmentFaultDetector().detect(_ctx())
        mock_filter.assert_not_called()
        scope_passthrough.assert_not_called()

    @pytest.mark.asyncio
    async def test_permission_anchor_pinned(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        self._patch(monkeypatch, [])
        await EquipmentFaultDetector().detect(_ctx())
        perm_ok.assert_awaited_once_with(
            USER_ID, TENANT, "kuaizhizao:equipment-fault:read"
        )
        assert (
            scope_passthrough.call_args.kwargs["resource"]
            == "kuaizhizao:equipment-fault"
        )

    @pytest.mark.asyncio
    async def test_tenant_id_carried(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        _qs_obj, mock_filter = self._patch(monkeypatch, [])
        await EquipmentFaultDetector().detect(_ctx(tenant_id=42))
        assert mock_filter.call_args.kwargs["tenant_id"] == 42


# ============================================================ registry 注册与白名单


class TestSpec203Registry:
    def test_detector_registered(self):
        assert isinstance(
            pulse_registry.DETECTORS["equipment"], EquipmentFaultDetector
        )
        assert set(pulse_registry.PULSE_DOMAINS) == set(
            pulse_registry.DETECTORS.keys()
        )
        assert pulse_registry.IMPLEMENTED_DOMAINS == frozenset(
            pulse_registry.PULSE_DOMAINS
        )

    def test_fault_route_in_scene_route_whitelist(self):
        """spec 203：故障页路由须进 SCENE_ROUTE_PERMISSIONS 白名单。"""
        from apps.kuaiai.services.agent_scene_service import (
            SCENE_ROUTE_PERMISSIONS,
        )

        assert (
            SCENE_ROUTE_PERMISSIONS[
                "/apps/kuaizhizao/equipment-management/equipment-faults"
            ]
            == "kuaizhizao:equipment-fault:read"
        )
        assert (
            SCENE_ROUTE_PERMISSIONS[
                "/apps/kuaizhizao/warehouse-management/inventory-alert"
            ]
            == "kuaizhizao:warehouse-management-inventory-alert:read"
        )

    @pytest.mark.asyncio
    async def test_domain_permission_denied_isolated(
        self, monkeypatch, scope_passthrough
    ):
        """仅 equipment 无权限：该域 permission_denied、complete=false，
        inventory 正常产出且 summary 不含失败域。"""
        denied_code = "kuaizhizao:equipment-fault:read"

        async def _perm(uid, tenant_id, code):
            return code != denied_code

        monkeypatch.setattr(
            "core.services.authorization.user_permission_service."
            "UserPermissionService.has_permission",
            AsyncMock(side_effect=_perm),
        )
        monkeypatch.setattr(
            "apps.kuaizhizao.models.equipment_fault.EquipmentFault.filter",
            MagicMock(return_value=_qs([_fault()])),
        )
        monkeypatch.setattr(
            "apps.kuaizhizao.models.inventory_alert.InventoryAlert.filter",
            MagicMock(return_value=_qs([])),
        )

        out = await pulse_registry.run_pulse(
            TENANT, _user(), domains=["equipment", "inventory"]
        )
        assert out.complete is False
        assert out.summary.total == 0
        codes = {e.domain: e.code for e in out.errors}
        assert codes["equipment"] == "permission_denied"
        assert "inventory" not in codes

    @pytest.mark.asyncio
    async def test_detector_error_isolated(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        """equipment detector 内部异常只影响本领域，complete=false。"""
        qs = _qs([])
        qs.all = AsyncMock(side_effect=RuntimeError("db down"))
        monkeypatch.setattr(
            "apps.kuaizhizao.models.equipment_fault.EquipmentFault.filter",
            MagicMock(return_value=qs),
        )
        monkeypatch.setattr(
            "apps.kuaizhizao.models.inventory_alert.InventoryAlert.filter",
            MagicMock(return_value=_qs([])),
        )
        out = await pulse_registry.run_pulse(
            TENANT, _user(), domains=["equipment", "inventory"]
        )
        assert out.complete is False
        codes = {e.domain: e.code for e in out.errors}
        assert codes["equipment"] == "detector_error"
        assert "inventory" not in codes

    @pytest.mark.asyncio
    async def test_full_scan_all_five_domains_no_not_connected(
        self, perm_ok, scope_passthrough, monkeypatch
    ):
        """五领域全部注册后，默认请求不再出现 not_connected。"""
        monkeypatch.setattr(
            "apps.kuaizhizao.models.work_order.WorkOrder.filter",
            MagicMock(return_value=_qs([])),
        )
        monkeypatch.setattr(
            "apps.kuaizhizao.models.sales_order.SalesOrder.filter",
            MagicMock(return_value=_qs([])),
        )
        monkeypatch.setattr(
            "infra.services.tenant_service.TenantService.get_tenant_config",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            "apps.kuaizhizao.models.inventory_alert.InventoryAlert.filter",
            MagicMock(return_value=_qs([])),
        )
        monkeypatch.setattr(
            "apps.kuaizhizao.models.quality_exception.QualityException.filter",
            MagicMock(return_value=_qs([])),
        )
        monkeypatch.setattr(
            "apps.kuaizhizao.models.equipment_fault.EquipmentFault.filter",
            MagicMock(return_value=_qs([])),
        )
        out = await pulse_registry.run_pulse(TENANT, _user())
        assert out.complete is True
        assert out.errors == []
