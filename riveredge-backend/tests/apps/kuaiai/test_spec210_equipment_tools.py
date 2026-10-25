"""KU-AI spec 210 单测：query_equipment / query_equipment_faults /
query_maintenance_plans / query_maintenance_reminders / query_calibration_alerts。

全部 mock / 假数据，不需要真实数据库。覆盖：
- 闭集参数（view / status / fault_level / plan_type / execution_result /
  reminder_type / due_type / 布尔 / 日期）非法回固定文案；
- 五个底层 service 均不接收 current_user：适配层用
  ``scene_tools._scoped_row_ids`` 套页面资源键行级收敛；
- equipment_code 经 get_equipment_by_code 解析为 equipment_uuid 过滤；
- 摘要字段口径（编码/名称/状态/时间），不输出维修费用等金额字段；
- 空结果、底层异常、limit 截断与既有 Tool 口径一致。
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaiai.services.tools import equipment_maintenance as em
from core.ai.runtime.context import AiRuntimeContext

TENANT = 7
USER_ID = 5
EQ_UUID = "eq-uuid-0001"


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


def _equipment(**kw):
    base = dict(
        id=1,
        uuid=EQ_UUID,
        code="EQ-001",
        name="3号注塑机",
        type="加工设备",
        category="注塑机",
        equipment_nature="通用设备",
        status="正常",
        is_active=True,
        workshop_name="注塑车间",
        production_line_name="一线",
        workstation_name=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _equipment_service(rows=None, by_code=None):
    svc = SimpleNamespace()
    svc.list_equipment = AsyncMock(
        return_value=(rows if rows is not None else [], len(rows or []))
    )
    svc.get_equipment_by_code = AsyncMock(return_value=by_code)
    svc.list_calibration_alerts = AsyncMock(return_value=([], 0))
    return svc


def _fault(**kw):
    base = dict(
        id=11,
        uuid="f-uuid-1",
        fault_no="GZ-2026-001",
        equipment_id=1,
        equipment_uuid=EQ_UUID,
        equipment_code="EQ-001",
        equipment_name="3号注塑机",
        fault_date=datetime(2026, 1, 10, 8, 30),
        fault_type="机械故障",
        fault_level="严重",
        fault_description="射胶压力异常波动，疑似液压阀故障",
        status="处理中",
        repair_required=True,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _repair(**kw):
    base = dict(
        id=21,
        uuid="r-uuid-1",
        repair_no="WX-2026-001",
        equipment_id=1,
        equipment_uuid=EQ_UUID,
        equipment_name="3号注塑机",
        repair_date=datetime(2026, 1, 11, 14, 0),
        repair_type="现场维修",
        repair_description="更换液压阀并复测",
        repair_cost=1200.0,
        repairer_name="张三",
        repair_duration=3.5,
        status="已完成",
        repair_result="成功",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _plan(**kw):
    base = dict(
        id=31,
        uuid="p-uuid-1",
        plan_no="MP-2026-001",
        plan_name="注塑机月度保养",
        equipment_items=[{"id": 1, "uuid": EQ_UUID, "code": "EQ-001", "name": "3号注塑机"}],
        scheme_name="注塑机保养方案",
        plan_type="定期维护",
        status="已发布",
        planned_start_date=datetime(2026, 2, 1, 9, 0),
        planned_end_date=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _execution(**kw):
    base = dict(
        id=41,
        uuid="e-uuid-1",
        execution_no="EX-2026-001",
        equipment_id=1,
        equipment_uuid=EQ_UUID,
        equipment_name="3号注塑机",
        execution_date=datetime(2026, 1, 15, 10, 0),
        executor_name="李四",
        execution_result="正常",
        status="已确认",
        maintenance_cost=500.0,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _reminder(**kw):
    base = dict(
        id=51,
        uuid="m-uuid-1",
        equipment_id=1,
        equipment_uuid=EQ_UUID,
        equipment_code="EQ-001",
        equipment_name="3号注塑机",
        reminder_type="due_soon",
        reminder_date=datetime(2026, 1, 20, 9, 0),
        planned_maintenance_date=datetime(2026, 1, 25, 9, 0),
        days_until_due=5,
        is_read=False,
        is_handled=False,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _alert_row(**kw):
    base = dict(
        equipment_uuid=EQ_UUID,
        equipment_code="EQ-001",
        equipment_name="3号注塑机",
        reminder_type="calibration",
        due_type="overdue",
        due_date=date(2026, 1, 5),
        days_until_due=-15,
        calibration_period=180,
        last_calibration_date=date(2025, 7, 9),
    )
    base.update(kw)
    return base


class TestQueryEquipment:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await em.query_equipment(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_status_and_bool(self):
        out = await em.query_equipment(status="bogus", ctx=_ctx())
        assert "status" in out and "正常" in out
        out = await em.query_equipment(is_active="maybe", ctx=_ctx())
        assert "is_active" in out

    @pytest.mark.asyncio
    async def test_list_scoped_and_formatted(self):
        svc = _equipment_service(rows=[_equipment(), _equipment(id=2, uuid="u2", code="EQ-002")])
        with patch(
            "apps.kuaizhizao.services.equipment_service.EquipmentService", svc
        ), _scope_patch({1}) as m_scope:
            out = await em.query_equipment(keyword="注塑", ctx=_ctx())
        args = m_scope.await_args.args
        assert args[2] == "kuaizhizao:equipment-management-equipment"
        assert args[3] == {1, 2}
        kw = svc.list_equipment.await_args.kwargs
        assert kw["keyword"] == "注塑"
        assert "EQ-001" in out and "3号注塑机" in out
        assert "EQ-002" not in out  # 范围外被剔除
        assert "uuid=" in out

    @pytest.mark.asyncio
    async def test_equipment_code_exact_lookup(self):
        svc = _equipment_service(by_code=_equipment())
        with patch(
            "apps.kuaizhizao.services.equipment_service.EquipmentService", svc
        ), _scope_patch({1}):
            out = await em.query_equipment(equipment_code="EQ-001", ctx=_ctx())
        svc.get_equipment_by_code.assert_awaited_once()
        svc.list_equipment.assert_not_awaited()
        assert "EQ-001" in out

    @pytest.mark.asyncio
    async def test_code_not_found_and_empty(self):
        svc = _equipment_service(by_code=None)
        with patch(
            "apps.kuaizhizao.services.equipment_service.EquipmentService", svc
        ), _scope_patch(set()):
            out = await em.query_equipment(equipment_code="NOPE", ctx=_ctx())
        assert "未查询到" in out

    @pytest.mark.asyncio
    async def test_service_error_fixed_text(self):
        svc = SimpleNamespace(
            list_equipment=AsyncMock(side_effect=RuntimeError("db down")),
            get_equipment_by_code=AsyncMock(return_value=None),
        )
        with patch(
            "apps.kuaizhizao.services.equipment_service.EquipmentService", svc
        ):
            out = await em.query_equipment(ctx=_ctx())
        assert out == "查询设备台账失败，请稍后重试"
        assert "db down" not in out


class TestQueryEquipmentFaults:
    @pytest.mark.asyncio
    async def test_no_context(self):
        out = await em.query_equipment_faults(ctx=None)
        assert "上下文" in out

    @pytest.mark.asyncio
    async def test_invalid_enums(self):
        out = await em.query_equipment_faults(view="evil", ctx=_ctx())
        assert "view" in out and "faults" in out
        out = await em.query_equipment_faults(status="bogus", ctx=_ctx())
        assert "待处理" in out
        out = await em.query_equipment_faults(
            view="repairs", status="待处理", ctx=_ctx()
        )
        assert "进行中" in out
        out = await em.query_equipment_faults(fault_level="bogus", ctx=_ctx())
        assert "fault_level" in out
        out = await em.query_equipment_faults(date_start="bad", ctx=_ctx())
        assert "date_start" in out
        out = await em.query_equipment_faults(date_end="bad", ctx=_ctx())
        assert "date_end" in out

    @pytest.mark.asyncio
    async def test_faults_scoped_and_formatted(self):
        fault_svc = SimpleNamespace(
            list_equipment_faults=AsyncMock(
                return_value=([_fault(), _fault(id=12, fault_no="GZ-002")], 2)
            )
        )
        with patch(
            "apps.kuaizhizao.services.equipment_fault_service"
            ".EquipmentFaultService",
            fault_svc,
        ), _scope_patch({11}) as m_scope:
            out = await em.query_equipment_faults(
                status="处理中",
                date_start="2026-01-01",
                date_end="2026-01-31",
                ctx=_ctx(),
            )
        assert m_scope.await_args.args[2] == "kuaizhizao:equipment-fault"
        kw = fault_svc.list_equipment_faults.await_args.kwargs
        assert kw["status"] == "处理中"
        assert kw["fault_start_date"] == date(2026, 1, 1)
        assert kw["fault_end_date"] == date(2026, 1, 31)
        assert "GZ-2026-001" in out and "严重" in out and "射胶压力异常" in out
        assert "GZ-002" not in out

    @pytest.mark.asyncio
    async def test_equipment_code_resolved_to_uuid(self):
        eq_svc = _equipment_service(by_code=_equipment())
        fault_svc = SimpleNamespace(
            list_equipment_faults=AsyncMock(return_value=([_fault()], 1))
        )
        with patch(
            "apps.kuaizhizao.services.equipment_service.EquipmentService", eq_svc
        ), patch(
            "apps.kuaizhizao.services.equipment_fault_service"
            ".EquipmentFaultService",
            fault_svc,
        ), _scope_patch({11}):
            out = await em.query_equipment_faults(
                equipment_code="EQ-001", ctx=_ctx()
            )
        kw = fault_svc.list_equipment_faults.await_args.kwargs
        assert kw["equipment_uuid"] == EQ_UUID
        assert "GZ-2026-001" in out

    @pytest.mark.asyncio
    async def test_equipment_code_not_found(self):
        eq_svc = _equipment_service(by_code=None)
        with patch(
            "apps.kuaizhizao.services.equipment_service.EquipmentService", eq_svc
        ):
            out = await em.query_equipment_faults(
                equipment_code="NOPE", ctx=_ctx()
            )
        assert "NOPE" in out and "未查询到" in out

    @pytest.mark.asyncio
    async def test_repairs_view_no_cost_fields(self):
        repair_svc = SimpleNamespace(
            list_equipment_repairs=AsyncMock(return_value=([_repair()], 1))
        )
        with patch(
            "apps.kuaizhizao.services.equipment_fault_service"
            ".EquipmentRepairService",
            repair_svc,
        ), _scope_patch({21}), patch.object(
            em,
            "_equipment_code_map",
            new=AsyncMock(return_value={EQ_UUID: "EQ-001"}),
        ):
            out = await em.query_equipment_faults(view="repairs", ctx=_ctx())
        assert "WX-2026-001" in out and "EQ-001（3号注塑机）" in out
        assert "已完成" in out and "更换液压阀" in out
        # 费用金额不输出
        assert "1200" not in out and "费用" not in out

    @pytest.mark.asyncio
    async def test_empty_and_error(self):
        fault_svc = SimpleNamespace(
            list_equipment_faults=AsyncMock(return_value=([], 0))
        )
        with patch(
            "apps.kuaizhizao.services.equipment_fault_service"
            ".EquipmentFaultService",
            fault_svc,
        ), _scope_patch(set()):
            out = await em.query_equipment_faults(ctx=_ctx())
        assert "未查询到" in out
        fault_svc.list_equipment_faults = AsyncMock(
            side_effect=RuntimeError("x")
        )
        with patch(
            "apps.kuaizhizao.services.equipment_fault_service"
            ".EquipmentFaultService",
            fault_svc,
        ):
            out = await em.query_equipment_faults(ctx=_ctx())
        assert out == "查询设备故障/维修记录失败，请稍后重试"


class TestQueryMaintenancePlans:
    @pytest.mark.asyncio
    async def test_invalid_enums(self):
        out = await em.query_maintenance_plans(view="x", ctx=_ctx())
        assert "plans" in out
        out = await em.query_maintenance_plans(status="bogus", ctx=_ctx())
        assert "已发布" in out
        out = await em.query_maintenance_plans(
            view="executions", status="已发布", ctx=_ctx()
        )
        assert "已确认" in out
        out = await em.query_maintenance_plans(plan_type="bogus", ctx=_ctx())
        assert "plan_type" in out
        out = await em.query_maintenance_plans(
            execution_result="bogus", ctx=_ctx()
        )
        assert "execution_result" in out

    @pytest.mark.asyncio
    async def test_plans_scoped_and_formatted(self):
        plan_svc = SimpleNamespace(
            list_maintenance_plans=AsyncMock(return_value=([_plan()], 1))
        )
        with patch(
            "apps.kuaizhizao.services.maintenance_plan_service"
            ".MaintenancePlanService",
            plan_svc,
        ), _scope_patch({31}) as m_scope:
            out = await em.query_maintenance_plans(ctx=_ctx())
        assert m_scope.await_args.args[2] == "kuaizhizao:maintenance-plan"
        assert "MP-2026-001" in out and "注塑机月度保养" in out
        assert "EQ-001（3号注塑机）" in out and "已发布" in out

    @pytest.mark.asyncio
    async def test_executions_view_no_cost(self):
        exec_svc = SimpleNamespace(
            list_maintenance_executions=AsyncMock(
                return_value=([_execution()], 1)
            )
        )
        with patch(
            "apps.kuaizhizao.services.maintenance_plan_service"
            ".MaintenanceExecutionService",
            exec_svc,
        ), _scope_patch({41}), patch.object(
            em,
            "_equipment_code_map",
            new=AsyncMock(return_value={EQ_UUID: "EQ-001"}),
        ):
            out = await em.query_maintenance_plans(
                view="executions", execution_result="正常", ctx=_ctx()
            )
        kw = exec_svc.list_maintenance_executions.await_args.kwargs
        assert kw["execution_result"] == "正常"
        assert "EX-2026-001" in out and "正常" in out and "李四" in out
        assert "500" not in out and "成本" not in out

    @pytest.mark.asyncio
    async def test_empty(self):
        plan_svc = SimpleNamespace(
            list_maintenance_plans=AsyncMock(return_value=([], 0))
        )
        with patch(
            "apps.kuaizhizao.services.maintenance_plan_service"
            ".MaintenancePlanService",
            plan_svc,
        ), _scope_patch(set()):
            out = await em.query_maintenance_plans(ctx=_ctx())
        assert "未查询到" in out

    @pytest.mark.asyncio
    async def test_error_fixed_text(self):
        plan_svc = SimpleNamespace(
            list_maintenance_plans=AsyncMock(side_effect=RuntimeError("x"))
        )
        with patch(
            "apps.kuaizhizao.services.maintenance_plan_service"
            ".MaintenancePlanService",
            plan_svc,
        ):
            out = await em.query_maintenance_plans(ctx=_ctx())
        assert out == "查询保养计划/执行记录失败，请稍后重试"


class TestQueryMaintenanceReminders:
    @pytest.mark.asyncio
    async def test_invalid_enums(self):
        out = await em.query_maintenance_reminders(
            reminder_type="bogus", ctx=_ctx()
        )
        assert "reminder_type" in out
        out = await em.query_maintenance_reminders(
            is_handled="bogus", ctx=_ctx()
        )
        assert "is_handled" in out
        out = await em.query_maintenance_reminders(is_read="x", ctx=_ctx())
        assert "is_read" in out

    @pytest.mark.asyncio
    async def test_scoped_and_formatted(self):
        reminder_svc = SimpleNamespace(
            list_reminders=AsyncMock(
                return_value=([_reminder(), _reminder(id=52, days_until_due=-3)], 2)
            )
        )
        with patch(
            "apps.kuaizhizao.services.maintenance_reminder_service"
            ".MaintenanceReminderService",
            return_value=reminder_svc,
        ), _scope_patch({51, 52}) as m_scope:
            out = await em.query_maintenance_reminders(
                is_handled=False, ctx=_ctx()
            )
        assert m_scope.await_args.args[2] == "kuaizhizao:maintenance-reminder"
        kw = reminder_svc.list_reminders.await_args.kwargs
        assert kw["is_handled"] is False
        assert "EQ-001（3号注塑机）" in out
        assert "即将到期" in out and "5 天后到期" in out
        assert "已逾期 3 天" in out

    @pytest.mark.asyncio
    async def test_empty_and_error(self):
        reminder_svc = SimpleNamespace(
            list_reminders=AsyncMock(return_value=([], 0))
        )
        with patch(
            "apps.kuaizhizao.services.maintenance_reminder_service"
            ".MaintenanceReminderService",
            return_value=reminder_svc,
        ), _scope_patch(set()):
            out = await em.query_maintenance_reminders(ctx=_ctx())
        assert "未查询到" in out
        reminder_svc.list_reminders = AsyncMock(side_effect=RuntimeError("x"))
        with patch(
            "apps.kuaizhizao.services.maintenance_reminder_service"
            ".MaintenanceReminderService",
            return_value=reminder_svc,
        ):
            out = await em.query_maintenance_reminders(ctx=_ctx())
        assert out == "查询维护提醒失败，请稍后重试"


class TestQueryCalibrationAlerts:
    @pytest.mark.asyncio
    async def test_invalid_due_type(self):
        out = await em.query_calibration_alerts(due_type="bogus", ctx=_ctx())
        assert "due_type" in out

    @pytest.mark.asyncio
    async def test_scoped_and_formatted(self):
        svc = _equipment_service()
        svc.list_calibration_alerts = AsyncMock(
            return_value=([_alert_row(), _alert_row(equipment_uuid="u2")], 2)
        )
        with patch(
            "apps.kuaizhizao.services.equipment_service.EquipmentService", svc
        ), _scope_patch({1}) as m_scope, patch.object(
            em,
            "_equipment_id_map",
            new=AsyncMock(return_value={EQ_UUID: 1, "u2": 2}),
        ):
            out = await em.query_calibration_alerts(ctx=_ctx())
        # 范围资源键 = 校准提醒页权限码
        assert m_scope.await_args.args[2] == "kuaizhizao:maintenance-reminder"
        kw = svc.list_calibration_alerts.await_args.kwargs
        assert kw["due_type"] is None
        assert "EQ-001（3号注塑机）" in out and "已逾期 15 天" in out
        assert "u2" not in out  # 范围外行剔除

    @pytest.mark.asyncio
    async def test_keyword_post_filter(self):
        svc = _equipment_service()
        svc.list_calibration_alerts = AsyncMock(
            return_value=(
                [_alert_row(), _alert_row(equipment_code="EQ-009", equipment_name="投影仪")],
                2,
            )
        )
        with patch(
            "apps.kuaizhizao.services.equipment_service.EquipmentService", svc
        ), _scope_patch({1, 9}), patch.object(
            em,
            "_equipment_id_map",
            new=AsyncMock(return_value={EQ_UUID: 1, "u9": 9}),
        ):
            out = await em.query_calibration_alerts(
                equipment_keyword="注塑", ctx=_ctx()
            )
        assert "EQ-001" in out and "EQ-009" not in out

    @pytest.mark.asyncio
    async def test_empty_and_error(self):
        svc = _equipment_service()
        with patch(
            "apps.kuaizhizao.services.equipment_service.EquipmentService", svc
        ), _scope_patch(set()):
            out = await em.query_calibration_alerts(ctx=_ctx())
        assert "未查询到" in out
        svc.list_calibration_alerts = AsyncMock(side_effect=RuntimeError("x"))
        with patch(
            "apps.kuaizhizao.services.equipment_service.EquipmentService", svc
        ):
            out = await em.query_calibration_alerts(ctx=_ctx())
        assert out == "查询设备校准到期提醒失败，请稍后重试"
