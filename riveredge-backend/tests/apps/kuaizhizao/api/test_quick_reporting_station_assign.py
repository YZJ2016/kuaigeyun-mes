"""工位渠道快捷报工：操作员与登录用户不同、以及小组报工，不因办公室代报权限被拒。"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from apps.kuaizhizao.api.productions import reporting as reporting_api
from apps.kuaizhizao.schemas.reporting_record import ReportingRecordCreate


def _record(**overrides) -> ReportingRecordCreate:
    payload = {
        "work_order_id": 1,
        "work_order_code": "WO-1",
        "work_order_name": "工单",
        "operation_id": 2,
        "operation_code": "OP-1",
        "operation_name": "组装",
        "worker_id": 99,
        "worker_name": "操作员",
        "reported_quantity": Decimal("1"),
        "qualified_quantity": Decimal("1"),
        "unqualified_quantity": Decimal("0"),
        "work_hours": Decimal("1"),
        "reported_at": datetime(2026, 9, 29, 10, 0, 0),
    }
    payload.update(overrides)
    return ReportingRecordCreate.model_validate(payload)


def _request(channel: str) -> MagicMock:
    request = MagicMock()
    request.headers = {"X-Client-Channel": channel}
    return request


def _user(user_id: int) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    return user


@pytest.mark.asyncio
async def test_station_quick_report_does_not_require_assign_when_worker_differs(monkeypatch):
    """station 渠道、worker_id 不等于登录用户、无 assign 时，不被这条权限拒绝。"""
    denied = AsyncMock(side_effect=HTTPException(status_code=403, detail="assign"))
    created = MagicMock()
    create = AsyncMock(return_value=created)
    monkeypatch.setattr(reporting_api, "ensure_permission_codes", denied)
    monkeypatch.setattr(reporting_api.reporting_service, "create_reporting_record", create)

    result = await reporting_api.create_quick_reporting_record(
        reporting=_record(worker_id=99, worker_name="操作员"),
        request=_request("station"),
        auth=MagicMock(),
        current_user=_user(7),
        tenant_id=1,
    )

    denied.assert_not_awaited()
    assert result is created
    assert create.await_args.kwargs["reported_by"] == 7
    assert create.await_args.kwargs["entry_mode"] == "quick"
    assert create.await_args.kwargs["client_channel"] == "station"


@pytest.mark.asyncio
async def test_station_team_quick_report_does_not_require_assign(monkeypatch):
    denied = AsyncMock(side_effect=HTTPException(status_code=403, detail="assign"))
    create = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(reporting_api, "ensure_permission_codes", denied)
    monkeypatch.setattr(reporting_api.reporting_service, "create_reporting_record", create)

    await reporting_api.create_quick_reporting_record(
        reporting=_record(
            worker_id=None,
            worker_name=None,
            team_id=6,
            team_name="甲班",
        ),
        request=_request("station"),
        auth=MagicMock(),
        current_user=_user(7),
        tenant_id=1,
    )

    denied.assert_not_awaited()
    assert create.await_args.kwargs["reported_by"] == 7


@pytest.mark.asyncio
async def test_non_station_quick_report_still_requires_assign_when_worker_differs(monkeypatch):
    denied = AsyncMock(side_effect=HTTPException(status_code=403, detail="assign"))
    create = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(reporting_api, "ensure_permission_codes", denied)
    monkeypatch.setattr(reporting_api.reporting_service, "create_reporting_record", create)

    with pytest.raises(HTTPException) as raised:
        await reporting_api.create_quick_reporting_record(
            reporting=_record(worker_id=99, worker_name="操作员"),
            request=_request("pc"),
            auth=MagicMock(),
            current_user=_user(7),
            tenant_id=1,
        )

    assert raised.value.status_code == 403
    create.assert_not_awaited()
    denied.assert_awaited()
    assert denied.await_args.args[3] == ["kuaizhizao:production-execution-reporting:assign"]
