"""轻办公 P0：员工入职介绍人 + 最低工资 end_date / is_current 单元测试。"""

from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.kuaioa.schemas.employee import EmployeeProfileCreate, EmployeeProfileUpdate
from apps.kuaioa.schemas.minimum_wage import MinimumWageCreate, MinimumWageUpdate
from apps.kuaioa.services import employee_service as emp_mod
from apps.kuaioa.services import minimum_wage_service as mw_mod
from apps.kuaioa.services import payroll_service as pay_mod
from apps.kuaioa.services.employee_service import EmployeeProfileService
from apps.kuaioa.services.minimum_wage_service import MinimumWageService
from apps.kuaioa.services.payroll_service import PayrollSettlementService
from infra.exceptions.exceptions import BusinessLogicError


@asynccontextmanager
async def _noop_tx():
    yield


def _query_stub(*, first=None, exists=False):
    q = MagicMock()
    q.filter.return_value = q
    q.exclude.return_value = q
    q.order_by.return_value = q
    q.first = AsyncMock(return_value=first)
    q.exists = AsyncMock(return_value=exists)
    q.update = AsyncMock(return_value=1)
    return q


@pytest.mark.asyncio
async def test_employee_create_and_update_hire_introducer(monkeypatch):
    svc = EmployeeProfileService()
    created_payload: dict = {}

    async def _fake_create(**kwargs):
        created_payload.update(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(emp_mod, "apply_create_audit_by_user_id", AsyncMock())
    monkeypatch.setattr(emp_mod, "model_to_dict", lambda r: dict(r.__dict__))
    monkeypatch.setattr(
        emp_mod.KuaioaEmployeeProfile,
        "filter",
        MagicMock(return_value=_query_stub(exists=False)),
    )
    monkeypatch.setattr(emp_mod.KuaioaEmployeeProfile, "create", _fake_create)

    res = await svc.create_profile(
        1,
        EmployeeProfileCreate(
            employee_code="EMP-01",
            full_name="王五",
            hire_introducer="  李四  ",
        ),
        user_id=10,
    )
    assert created_payload["hire_introducer"] == "李四"
    assert res["hire_introducer"] == "李四"

    row = SimpleNamespace(
        id=1,
        leave_date=None,
        status="active",
        hire_introducer="李四",
        save=AsyncMock(),
    )
    monkeypatch.setattr(
        emp_mod.KuaioaEmployeeProfile, "get_or_none", AsyncMock(return_value=row)
    )
    monkeypatch.setattr(emp_mod, "touch_updated", AsyncMock())

    updated = await svc.update_profile(
        1, 1, EmployeeProfileUpdate(hire_introducer="   "), user_id=10
    )
    assert row.hire_introducer is None
    assert updated["hire_introducer"] is None


@pytest.mark.asyncio
async def test_minimum_wage_create_validates_end_date_and_clears_old_current(monkeypatch):
    svc = MinimumWageService()
    monkeypatch.setattr(mw_mod, "in_transaction", _noop_tx)
    monkeypatch.setattr(mw_mod, "apply_create_audit_by_user_id", AsyncMock())
    monkeypatch.setattr(mw_mod, "model_to_dict", lambda r: dict(r.__dict__))

    with pytest.raises(BusinessLogicError, match="执行结束时间不能早于执行开始时间"):
        await svc.create_config(
            1,
            MinimumWageCreate(
                amount=Decimal("2660"),
                effective_date="2026-08-01",
                end_date="2026-07-31",
                is_current=True,
            ),
            user_id=5,
        )

    clear_q = _query_stub()
    monkeypatch.setattr(
        mw_mod.KuaioaMinimumWageConfig, "filter", MagicMock(return_value=clear_q)
    )
    captured: dict = {}

    async def _fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id=2, **kwargs)

    monkeypatch.setattr(mw_mod.KuaioaMinimumWageConfig, "create", _fake_create)

    res = await svc.create_config(
        1,
        MinimumWageCreate(
            amount=Decimal("2660"),
            effective_date="2026-08-01",
            end_date="2027-07-31",
            is_current=True,
        ),
        user_id=5,
    )
    clear_q.update.assert_awaited_once_with(is_current=False)
    assert captured["effective_date"] == date(2026, 8, 1)
    assert captured["end_date"] == date(2027, 7, 31)
    assert captured["is_current"] is True
    assert res["is_current"] is True


@pytest.mark.asyncio
async def test_minimum_wage_update_clears_other_current(monkeypatch):
    svc = MinimumWageService()
    row = SimpleNamespace(
        id=9,
        effective_date=date(2026, 1, 1),
        end_date=None,
        is_current=False,
        amount=Decimal("2490"),
        save=AsyncMock(),
    )
    clear_q = _query_stub()
    monkeypatch.setattr(mw_mod, "in_transaction", _noop_tx)
    monkeypatch.setattr(mw_mod, "touch_updated", AsyncMock())
    monkeypatch.setattr(mw_mod, "model_to_dict", lambda r: dict(r.__dict__))
    monkeypatch.setattr(
        mw_mod.KuaioaMinimumWageConfig, "get_or_none", AsyncMock(return_value=row)
    )
    monkeypatch.setattr(
        mw_mod.KuaioaMinimumWageConfig, "filter", MagicMock(return_value=clear_q)
    )

    res = await svc.update_config(
        1,
        9,
        MinimumWageUpdate(end_date="2026-12-31", is_current=True),
        user_id=5,
    )
    clear_q.exclude.assert_called_once_with(id=9)
    clear_q.update.assert_awaited_once_with(is_current=False)
    assert row.end_date == date(2026, 12, 31)
    assert row.is_current is True
    assert res["is_current"] is True


@pytest.mark.asyncio
async def test_payroll_resolve_minimum_wage_period_and_current_fallback(monkeypatch):
    svc = PayrollSettlementService()

    # 1) Period match returns covering config
    period_q = _query_stub(first=SimpleNamespace(amount=Decimal("2490")))
    monkeypatch.setattr(
        pay_mod.KuaioaMinimumWageConfig, "filter", MagicMock(return_value=period_q)
    )
    amount = await svc._resolve_minimum_wage(1, "2026-06")
    assert amount == Decimal("2490")
    period_q.order_by.assert_called_with("-is_current", "-effective_date", "-id")

    # 2) When no dated period covers the month, falls back to is_current=True
    miss_q = _query_stub(first=None)
    current_q = _query_stub(first=SimpleNamespace(amount=Decimal("2660")))
    monkeypatch.setattr(
        pay_mod.KuaioaMinimumWageConfig,
        "filter",
        MagicMock(side_effect=[miss_q, current_q]),
    )
    fallback_amount = await svc._resolve_minimum_wage(1, "2024-01")
    assert fallback_amount == Decimal("2660")
