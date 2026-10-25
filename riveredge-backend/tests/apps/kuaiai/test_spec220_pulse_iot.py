"""KU-AI spec 220 单测：Pulse 设备领域接入 kuaiiot 告警（全部 mock，不触真库）。

代码事实表（写死在本测试固定边界的真实代码依据）：
- IotAlert.status 闭集 open|acknowledged（models/iot.py:410；代码另写
  recovered/closed 终态）；「未处理」口径 = status='open'（与 kuaiiot
  dashboard listAlerts({status:'open'}) 同一口径）；
- IotAlert.severity 闭集 info|warning|critical（models/iot.py:407）；
- AlertService.list_alerts(tenant_id, page, page_size, status, device_id)
  → (items, total)，按 -triggered_at 排序（alert_service.py:18-32）；
- kuaiiot 可用性 = ApplicationService.get_application_by_code(tenant_id,
  'kuaiiot') 的 is_installed+is_active（沿用 spec 212 _plm_enabled 模式，
  ecn_impact.py:94-99）；
- 读权限锚点 kuaiiot:alert:read（kuaiiot manifest permissions）；
- 告警路由 /apps/kuaiiot/alerts（kuaiiot manifest menu_config）；
- X8=a 来源级权限：sources[].status 闭集 ok|no_permission|unavailable；
  无权来源 signals 恒空（不查数不泄露）；两来源均无权限仍整领域
  permission_denied（spec 203 语义不变）。

覆盖：未安装跳过、双源并存不合并、逐设备聚合（数/最新级别/最新时间）、
单权限占位不泄露、无权限领域级拒绝、超时/异常→unavailable 隔离、
registry 来源状态透传与空信号占位分组、detect() 展平向后兼容。
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

import core.utils.timezone_utils as tz_utils
from apps.kuaiai.schemas.pulse import PulseOut
from apps.kuaiai.services.pulse import equipment as equipment_module
from apps.kuaiai.services.pulse import registry as pulse_registry
from apps.kuaiai.services.pulse.base import (
    PulseContext,
    PulsePermissionDenied,
)
from apps.kuaiai.services.pulse.equipment import (
    EquipmentFaultDetector,
    IOT_PERMISSION,
    IOT_RULE_CODE,
    REQUIRED_PERMISSION,
    RULE_CODE,
)

TENANT = 7
USER_ID = 5
SH = ZoneInfo("Asia/Shanghai")
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
    """模拟 Tortoise QuerySet 链（与 spec203 同型）。"""
    q = MagicMock()
    for m in ("filter", "exclude", "order_by", "limit", "offset"):
        setattr(q, m, MagicMock(return_value=q))
    q.all = AsyncMock(return_value=list(rows))
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


def _alert(**kw):
    base = dict(
        id=9001,
        uuid="alert-uuid-1",
        device_id=88,
        equipment_uuid="eq-uuid-1",
        rule_id=3,
        tag_key="temperature",
        severity="warning",
        message="温度超限",
        actual_value="96.5",
        status="open",
        triggered_at=datetime(2026, 1, 9, 12, 0, tzinfo=timezone.utc),
        deleted_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _device(**kw):
    base = dict(id=88, code="IOT-88", name="注塑机一号")
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch):
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
def scope_passthrough(monkeypatch):
    mock = AsyncMock(side_effect=lambda qs, **kw: qs)
    monkeypatch.setattr(
        "core.services.authorization.data_scope_service."
        "DataScopeService.apply",
        mock,
    )
    return mock


def _patch_permissions(monkeypatch, allowed=()):
    """按权限码集合放行；返回 mock 供调用断言。"""
    mock = AsyncMock(side_effect=lambda uid, tid, code: code in allowed)
    monkeypatch.setattr(
        "core.services.authorization.user_permission_service."
        "UserPermissionService.has_permission",
        mock,
    )
    return mock


def _patch_app_installed(monkeypatch, installed: bool):
    """kuaiiot 应用可用性：installed=True → is_installed+is_active。"""
    row = (
        {"is_installed": True, "is_active": True} if installed else None
    )
    mock = AsyncMock(return_value=row)
    monkeypatch.setattr(
        "core.services.application.application_service."
        "ApplicationService.get_application_by_code",
        mock,
    )
    return mock


def _patch_fault_source(monkeypatch, rows):
    qs = _qs(rows)
    mock_filter = MagicMock(return_value=qs)
    monkeypatch.setattr(
        "apps.kuaizhizao.models.equipment_fault.EquipmentFault.filter",
        mock_filter,
    )
    return qs, mock_filter


def _patch_iot_source(monkeypatch, alerts, devices=()):
    """mock AlertService.list_alerts（单页即可满足测试）与 IotDevice.filter。"""
    list_mock = AsyncMock(return_value=(list(alerts), len(alerts)))
    monkeypatch.setattr(
        "apps.kuaiiot.services.alert_service.AlertService.list_alerts",
        list_mock,
    )
    device_mock = AsyncMock(return_value=list(devices))
    monkeypatch.setattr(
        "apps.kuaiiot.models.iot.IotDevice.filter",
        device_mock,
    )
    return list_mock, device_mock


# ============================================================ 来源级权限与可用性


class TestSourceSemantics:
    @pytest.mark.asyncio
    async def test_kuaiiot_not_installed_skips_source(
        self, scope_passthrough, monkeypatch
    ):
        """kuaiiot 未安装：sources 仅含 MES 故障单来源，无 IoT 占位。"""
        _patch_permissions(monkeypatch, allowed={REQUIRED_PERMISSION})
        _patch_app_installed(monkeypatch, installed=False)
        _patch_fault_source(monkeypatch, [_fault()])
        iot_mock, _ = _patch_iot_source(monkeypatch, [], [])

        result = await EquipmentFaultDetector().detect_sources(_ctx())
        assert [s.key for s in result.sources] == [RULE_CODE]
        assert result.sources[0].status == "ok"
        assert len(result.sources[0].signals) == 1
        iot_mock.assert_not_awaited()  # 未安装整体跳过，不查数

    @pytest.mark.asyncio
    async def test_no_iot_permission_placeholder_leaks_nothing(
        self, scope_passthrough, monkeypatch
    ):
        """有故障权限无 IoT 权限：iot_alert 来源 no_permission、signals 恒空、
        不调用 kuaiiot 取数（不泄露数量/明细）。"""
        _patch_permissions(monkeypatch, allowed={REQUIRED_PERMISSION})
        _patch_app_installed(monkeypatch, installed=True)
        _patch_fault_source(monkeypatch, [_fault()])
        iot_mock, device_mock = _patch_iot_source(monkeypatch, [_alert()], [])

        result = await EquipmentFaultDetector().detect_sources(_ctx())
        by_key = {s.key: s for s in result.sources}
        assert by_key[RULE_CODE].status == "ok"
        assert len(by_key[RULE_CODE].signals) == 1
        assert by_key[IOT_RULE_CODE].status == "no_permission"
        assert by_key[IOT_RULE_CODE].signals == []
        iot_mock.assert_not_awaited()
        device_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_fault_permission_iot_only(
        self, scope_passthrough, monkeypatch
    ):
        """仅 IoT 权限：故障单来源占位，IoT 来源正常出信号。"""
        _patch_permissions(monkeypatch, allowed={IOT_PERMISSION})
        _patch_app_installed(monkeypatch, installed=True)
        _, fault_filter = _patch_fault_source(monkeypatch, [_fault()])
        _patch_iot_source(
            monkeypatch, [_alert()], [_device()]
        )

        result = await EquipmentFaultDetector().detect_sources(_ctx())
        by_key = {s.key: s for s in result.sources}
        assert by_key[RULE_CODE].status == "no_permission"
        assert by_key[RULE_CODE].signals == []
        assert by_key[IOT_RULE_CODE].status == "ok"
        assert len(by_key[IOT_RULE_CODE].signals) == 1
        fault_filter.assert_not_called()  # 无权来源不查数

    @pytest.mark.asyncio
    async def test_neither_permission_denies_domain(
        self, scope_passthrough, monkeypatch
    ):
        """两来源均无权限：沿用整领域拒绝（spec 203 语义不变）。"""
        _patch_permissions(monkeypatch, allowed=set())
        _patch_app_installed(monkeypatch, installed=True)
        _, fault_filter = _patch_fault_source(monkeypatch, [_fault()])
        iot_mock, _ = _patch_iot_source(monkeypatch, [_alert()], [])

        with pytest.raises(PulsePermissionDenied):
            await EquipmentFaultDetector().detect_sources(_ctx())
        fault_filter.assert_not_called()
        iot_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_iot_timeout_marks_unavailable_keeps_fault(
        self, scope_passthrough, monkeypatch
    ):
        """IoT 来源独立短超时：超时 → unavailable，MES 故障单不受影响。"""
        _patch_permissions(
            monkeypatch, allowed={REQUIRED_PERMISSION, IOT_PERMISSION}
        )
        _patch_app_installed(monkeypatch, installed=True)
        _patch_fault_source(monkeypatch, [_fault()])
        monkeypatch.setattr(equipment_module, "IOT_SOURCE_TIMEOUT", 0.05)

        async def _slow(*args, **kwargs):
            await asyncio.sleep(1)
            return ([], 0)

        monkeypatch.setattr(
            "apps.kuaiiot.services.alert_service.AlertService.list_alerts",
            _slow,
        )

        result = await EquipmentFaultDetector().detect_sources(_ctx())
        by_key = {s.key: s for s in result.sources}
        assert by_key[RULE_CODE].status == "ok"
        assert len(by_key[RULE_CODE].signals) == 1
        assert by_key[IOT_RULE_CODE].status == "unavailable"
        assert by_key[IOT_RULE_CODE].signals == []

    @pytest.mark.asyncio
    async def test_iot_error_marks_unavailable(
        self, scope_passthrough, monkeypatch
    ):
        _patch_permissions(
            monkeypatch, allowed={REQUIRED_PERMISSION, IOT_PERMISSION}
        )
        _patch_app_installed(monkeypatch, installed=True)
        _patch_fault_source(monkeypatch, [])
        monkeypatch.setattr(
            "apps.kuaiiot.services.alert_service.AlertService.list_alerts",
            AsyncMock(side_effect=RuntimeError("iot db down")),
        )

        result = await EquipmentFaultDetector().detect_sources(_ctx())
        by_key = {s.key: s for s in result.sources}
        assert by_key[RULE_CODE].status == "ok"
        assert by_key[IOT_RULE_CODE].status == "unavailable"


# ============================================================ IoT 聚合与信号内容


class TestIotAlertSignals:
    @pytest.mark.asyncio
    async def test_per_device_aggregation(
        self, scope_passthrough, monkeypatch
    ):
        """按设备聚合：告警数、最新级别、最新时间各自准确。"""
        _patch_permissions(monkeypatch, allowed={IOT_PERMISSION})
        _patch_app_installed(monkeypatch, installed=True)
        _patch_fault_source(monkeypatch, [])
        alerts = [
            _alert(
                id=1,
                device_id=88,
                severity="warning",
                triggered_at=datetime(2026, 1, 9, 10, 0, tzinfo=timezone.utc),
            ),
            _alert(
                id=2,
                device_id=88,
                severity="critical",
                triggered_at=datetime(2026, 1, 9, 12, 0, tzinfo=timezone.utc),
            ),
            _alert(
                id=3,
                device_id=99,
                severity="info",
                triggered_at=datetime(2026, 1, 9, 8, 0, tzinfo=timezone.utc),
            ),
        ]
        devices = [
            _device(id=88, code="IOT-88", name="注塑机一号"),
            _device(id=99, code="IOT-99", name="空压机"),
        ]
        list_mock, _ = _patch_iot_source(monkeypatch, alerts, devices)

        result = await EquipmentFaultDetector().detect_sources(_ctx())
        iot_source = next(
            s for s in result.sources if s.key == IOT_RULE_CODE
        )
        signals = iot_source.signals
        assert len(signals) == 2

        dev88 = next(s for s in signals if s.resource_id == "88")
        assert dev88.id == "equipment:iot_alert:88"
        assert dev88.domain == "equipment"
        assert dev88.rule_code == "iot_alert"
        assert dev88.resource_type == "iot_device"
        assert dev88.severity == "critical" and dev88.priority == "high"
        assert dev88.route == "/apps/kuaiiot/alerts"
        assert "2 条未处理" in dev88.fact
        assert "IOT-88" in dev88.fact and "注塑机一号" in dev88.fact
        assert "紧急" in dev88.fact
        # UTC 12:00 → 上海 20:00
        assert "2026-01-09 20:00" in dev88.fact
        assert dev88.detected_at == FIXED_NOW

        dev99 = next(s for s in signals if s.resource_id == "99")
        assert dev99.severity == "info" and dev99.priority == "low"
        assert "1 条未处理" in dev99.fact
        # list_alerts 只传 tenant_id + 已判权参数（status），不传 user
        call_kwargs = list_mock.call_args
        assert call_kwargs.args[0] == TENANT
        assert call_kwargs.kwargs["status"] == "open"

    @pytest.mark.asyncio
    async def test_iot_severity_matrix(
        self, scope_passthrough, monkeypatch
    ):
        """IoT 最新级别映射：critical→critical/high、warning→warning/medium、
        info→info/low、未知兜底 warning/medium。"""
        _patch_permissions(monkeypatch, allowed={IOT_PERMISSION})
        _patch_app_installed(monkeypatch, installed=True)
        _patch_fault_source(monkeypatch, [])
        alerts = [
            _alert(id=1, device_id=1, severity="critical"),
            _alert(id=2, device_id=2, severity="warning"),
            _alert(id=3, device_id=3, severity="info"),
            _alert(id=4, device_id=4, severity="mystery"),
        ]
        _patch_iot_source(monkeypatch, alerts, [])

        result = await EquipmentFaultDetector().detect_sources(_ctx())
        iot_source = next(
            s for s in result.sources if s.key == IOT_RULE_CODE
        )
        signals = {
            s.resource_id: (s.severity, s.priority)
            for s in iot_source.signals
        }
        assert signals["1"] == ("critical", "high")
        assert signals["2"] == ("warning", "medium")
        assert signals["3"] == ("info", "low")
        assert signals["4"] == ("warning", "medium")

    @pytest.mark.asyncio
    async def test_both_sources_same_equipment_no_merge(
        self, scope_passthrough, monkeypatch
    ):
        """同设备两源并存：故障单与告警各出一条信号，不合并去重。"""
        _patch_permissions(
            monkeypatch, allowed={REQUIRED_PERMISSION, IOT_PERMISSION}
        )
        _patch_app_installed(monkeypatch, installed=True)
        _patch_fault_source(monkeypatch, [_fault(equipment_uuid="eq-uuid-1")])
        _patch_iot_source(
            monkeypatch,
            [_alert(equipment_uuid="eq-uuid-1")],
            [_device()],
        )

        items = await EquipmentFaultDetector().detect(_ctx())
        assert len(items) == 2
        rule_codes = {i.rule_code for i in items}
        assert rule_codes == {RULE_CODE, IOT_RULE_CODE}
        fault_item = next(i for i in items if i.rule_code == RULE_CODE)
        iot_item = next(i for i in items if i.rule_code == IOT_RULE_CODE)
        assert fault_item.resource_id == "501"
        assert iot_item.resource_id == "88"
        # 各自准确：故障单含故障描述，告警含未处理计数
        assert "主轴异响" in fault_item.fact
        assert "未处理" in iot_item.fact

    @pytest.mark.asyncio
    async def test_empty_iot_alerts_ok_source(
        self, scope_passthrough, monkeypatch
    ):
        """IoT 有权限但零未处理告警：来源 ok 且 signals 为空。"""
        _patch_permissions(monkeypatch, allowed={IOT_PERMISSION})
        _patch_app_installed(monkeypatch, installed=True)
        _patch_fault_source(monkeypatch, [])
        _patch_iot_source(monkeypatch, [], [])

        result = await EquipmentFaultDetector().detect_sources(_ctx())
        by_key = {s.key: s for s in result.sources}
        assert by_key[IOT_RULE_CODE].status == "ok"
        assert by_key[IOT_RULE_CODE].signals == []

    @pytest.mark.asyncio
    async def test_iot_pagination_bounded_by_max_pages(
        self, scope_passthrough, monkeypatch
    ):
        """审计 minor：total 持续前移（并发新增）时翻页仍有界——
        达 IOT_ALERT_MAX_PAGES 上限后按已拉取部分聚合，不再翻页。"""
        _patch_permissions(monkeypatch, allowed={IOT_PERMISSION})
        _patch_app_installed(monkeypatch, installed=True)
        _patch_fault_source(monkeypatch, [])
        monkeypatch.setattr(equipment_module, "IOT_ALERT_PAGE_SIZE", 2)
        monkeypatch.setattr(equipment_module, "IOT_ALERT_MAX_PAGES", 3)

        # 每页满 2 条且 total 始终大于已收集数 → 无上限时会无限翻页
        async def _always_full(tenant_id, page=1, page_size=20, status=None,
                               device_id=None):
            return (
                [
                    _alert(id=page * 10 + i, device_id=88)
                    for i in range(page_size)
                ],
                1000,
            )

        list_mock = AsyncMock(side_effect=_always_full)
        monkeypatch.setattr(
            "apps.kuaiiot.services.alert_service.AlertService.list_alerts",
            list_mock,
        )
        monkeypatch.setattr(
            "apps.kuaiiot.models.iot.IotDevice.filter",
            AsyncMock(return_value=[_device(id=88)]),
        )

        result = await EquipmentFaultDetector().detect_sources(_ctx())
        iot_source = next(
            s for s in result.sources if s.key == IOT_RULE_CODE
        )
        assert list_mock.await_count == 3
        assert [
            c.kwargs["page"] for c in list_mock.await_args_list
        ] == [1, 2, 3]
        # 已拉取的 6 条照常聚合出信号
        assert len(iot_source.signals) == 1
        assert "6 条未处理" in iot_source.signals[0].fact


# ============================================================ registry 透传与兼容


class TestRegistrySources:
    @pytest.mark.asyncio
    async def test_sources_reach_group_and_placeholder(
        self, scope_passthrough, monkeypatch
    ):
        """registry：来源状态进 group.sources；无权来源不泄露且
        领域有信号时分组携带占位语义。"""
        _patch_permissions(monkeypatch, allowed={REQUIRED_PERMISSION})
        _patch_app_installed(monkeypatch, installed=True)
        _patch_fault_source(monkeypatch, [_fault()])
        iot_mock, _ = _patch_iot_source(monkeypatch, [_alert()], [])

        out = await pulse_registry.run_pulse(
            TENANT, _user(), domains=["equipment"]
        )
        assert isinstance(out, PulseOut)
        assert out.complete is True
        assert out.errors == []
        assert len(out.groups) == 1
        group = out.groups[0]
        assert group.domain == "equipment"
        assert len(group.items) == 1
        assert group.items[0].rule_code == RULE_CODE
        sources = {s.key: s for s in group.sources}
        assert sources[RULE_CODE].status == "ok"
        assert sources[RULE_CODE].count == 1
        assert sources[IOT_RULE_CODE].status == "no_permission"
        assert sources[IOT_RULE_CODE].count == 0
        # 占位不泄露：分组信号中无 iot 条目
        assert all(i.rule_code != IOT_RULE_CODE for i in group.items)
        iot_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_group_emitted_with_placeholder_only(
        self, scope_passthrough, monkeypatch
    ):
        """有权来源 0 信号 + 无权来源：仍出设备分组供前端渲染占位。"""
        _patch_permissions(monkeypatch, allowed={REQUIRED_PERMISSION})
        _patch_app_installed(monkeypatch, installed=True)
        _patch_fault_source(monkeypatch, [])
        _patch_iot_source(monkeypatch, [_alert()], [])

        out = await pulse_registry.run_pulse(
            TENANT, _user(), domains=["equipment"]
        )
        assert len(out.groups) == 1
        group = out.groups[0]
        assert group.items == []
        assert group.count == 0
        assert {s.key: s.status for s in group.sources} == {
            RULE_CODE: "ok",
            IOT_RULE_CODE: "no_permission",
        }

    @pytest.mark.asyncio
    async def test_iot_only_user_sees_signals_and_placeholder(
        self, scope_passthrough, monkeypatch
    ):
        _patch_permissions(monkeypatch, allowed={IOT_PERMISSION})
        _patch_app_installed(monkeypatch, installed=True)
        _patch_fault_source(monkeypatch, [_fault()])
        _patch_iot_source(monkeypatch, [_alert()], [_device()])

        out = await pulse_registry.run_pulse(
            TENANT, _user(), domains=["equipment"]
        )
        group = out.groups[0]
        assert [i.rule_code for i in group.items] == [IOT_RULE_CODE]
        sources = {s.key: s.status for s in group.sources}
        assert sources[RULE_CODE] == "no_permission"
        assert sources[IOT_RULE_CODE] == "ok"

    @pytest.mark.asyncio
    async def test_source_count_reflects_severity_filter(
        self, scope_passthrough, monkeypatch
    ):
        """审计 minor：来源 count 与该来源 severity 过滤后实际条数一致
        （过滤前计数会让来源计数与分组可见条数口径不符）；占位来源恒 0。"""
        _patch_permissions(monkeypatch, allowed={IOT_PERMISSION})
        _patch_app_installed(monkeypatch, installed=True)
        _patch_fault_source(monkeypatch, [_fault()])
        _patch_iot_source(
            monkeypatch,
            [
                _alert(id=1, device_id=88, severity="critical"),
                _alert(id=2, device_id=99, severity="info"),
            ],
            [
                _device(id=88),
                _device(id=99, code="IOT-99", name="空压机"),
            ],
        )

        out = await pulse_registry.run_pulse(
            TENANT, _user(), domains=["equipment"], severity="critical"
        )
        group = out.groups[0]
        assert len(group.items) == 1
        assert group.items[0].severity == "critical"
        sources = {s.key: s for s in group.sources}
        # 该来源过滤前有 2 条信号，severity=critical 后实际贡献 1 条
        assert sources[IOT_RULE_CODE].count == 1
        assert sources[RULE_CODE].status == "no_permission"
        assert sources[RULE_CODE].count == 0

    @pytest.mark.asyncio
    async def test_neither_permission_still_domain_error(
        self, scope_passthrough, monkeypatch
    ):
        """两来源均无权限：领域级 permission_denied（向后兼容 spec 203）。"""
        _patch_permissions(monkeypatch, allowed=set())
        _patch_app_installed(monkeypatch, installed=True)
        _patch_fault_source(monkeypatch, [_fault()])
        _patch_iot_source(monkeypatch, [_alert()], [])

        out = await pulse_registry.run_pulse(
            TENANT, _user(), domains=["equipment"]
        )
        assert out.complete is False
        assert out.groups == []
        assert [e.code for e in out.errors] == ["permission_denied"]

    @pytest.mark.asyncio
    async def test_other_domains_have_empty_sources(
        self, scope_passthrough, monkeypatch
    ):
        """向后兼容：单来源 detector 分组 sources 为空数组（旧前端忽略新字段）。"""
        _patch_permissions(
            monkeypatch,
            allowed={
                REQUIRED_PERMISSION,
                "kuaizhizao:warehouse-management-inventory-alert:read",
            },
        )
        _patch_app_installed(monkeypatch, installed=False)
        _patch_fault_source(monkeypatch, [_fault()])
        monkeypatch.setattr(
            "apps.kuaizhizao.models.inventory_alert.InventoryAlert.filter",
            MagicMock(return_value=_qs([])),
        )

        out = await pulse_registry.run_pulse(
            TENANT, _user(), domains=["equipment", "inventory"]
        )
        equipment_group = next(
            g for g in out.groups if g.domain == "equipment"
        )
        assert {s.key: s.status for s in equipment_group.sources} == {
            RULE_CODE: "ok"
        }
        # 未安装 kuaiiot：iot 来源不出现
        assert all(
            s.key != IOT_RULE_CODE for s in equipment_group.sources
        )
