"""快捷报工的工位边界（spec 180 STN-D15/Q4 修复语义）。

- X-Client-Channel 只是来源标记，不再参与权限判定；
- 纯工位账号以服务端操作员会话为边界：小组报工（不带 worker_id）放行，
  请求显式携带的 worker_id 必须等于会话确认的操作员用户，代报/他人一律拒绝；
- 非纯工位账号保持原代报判断：伪造 station 渠道头不能跳过 assign。
"""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from apps.kuaizhizao.api.deps.station_operator_session import StationBusinessOperator
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


def _request(channel: str = "pc", session=None) -> MagicMock:
    request = MagicMock()
    request.headers = {"X-Client-Channel": channel}
    request.state = SimpleNamespace(station_operator_session=session)
    return request


def _user(user_id: int) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    return user


def _station_operator(user_id: int = 99) -> StationBusinessOperator:
    return StationBusinessOperator(
        user_id=user_id, user_name="操作员", user=None
    )


def _pc_operator(user_id: int = 7) -> StationBusinessOperator:
    user = _user(user_id)
    return StationBusinessOperator(user_id=user_id, user_name="本人", user=user)


@pytest.mark.asyncio
async def test_pure_station_worker_matches_session_operator_passes(monkeypatch):
    """纯工位账号 + 有效会话 + worker_id == 会话操作员 → 放行，不查 assign。"""
    denied = AsyncMock(side_effect=HTTPException(status_code=403, detail="assign"))
    created = MagicMock()
    create = AsyncMock(return_value=created)
    monkeypatch.setattr(reporting_api, "ensure_permission_codes", denied)
    monkeypatch.setattr(reporting_api.reporting_service, "create_reporting_record", create)

    result = await reporting_api.create_quick_reporting_record(
        reporting=_record(worker_id=99, worker_name="操作员"),
        request=_request("station"),
        business_operator=_station_operator(),
        auth=MagicMock(),
        current_user=_user(7),
        tenant_id=1,
    )

    denied.assert_not_awaited()
    assert result is created
    assert create.await_args.kwargs["reported_by"] == 99
    assert create.await_args.kwargs["entry_mode"] == "quick"
    assert create.await_args.kwargs["client_channel"] == "station"


@pytest.mark.asyncio
async def test_pure_station_team_report_passes(monkeypatch):
    """纯工位账号 + 小组报工 → 放行，不校验 worker_id、不查 assign。"""
    denied = AsyncMock(side_effect=HTTPException(status_code=403, detail="assign"))
    create = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(reporting_api, "ensure_permission_codes", denied)
    monkeypatch.setattr(reporting_api.reporting_service, "create_reporting_record", create)

    await reporting_api.create_quick_reporting_record(
        reporting=_record(worker_id=None, worker_name=None, team_id=6, team_name="甲班"),
        request=_request("station"),
        business_operator=_station_operator(),
        auth=MagicMock(),
        current_user=_user(7),
        tenant_id=1,
    )

    denied.assert_not_awaited()
    assert create.await_args.kwargs["reported_by"] == 99


@pytest.mark.asyncio
async def test_pure_station_team_report_with_own_worker_passes(monkeypatch):
    """纯工位账号 + 小组报工且 worker_id == 会话操作员 → 放行。"""
    denied = AsyncMock(side_effect=HTTPException(status_code=403, detail="assign"))
    create = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(reporting_api, "ensure_permission_codes", denied)
    monkeypatch.setattr(reporting_api.reporting_service, "create_reporting_record", create)

    await reporting_api.create_quick_reporting_record(
        reporting=_record(
            worker_id=99, worker_name="操作员", team_id=6, team_name="甲班"
        ),
        request=_request("station"),
        business_operator=_station_operator(),
        auth=MagicMock(),
        current_user=_user(7),
        tenant_id=1,
    )

    denied.assert_not_awaited()
    assert create.await_args.kwargs["reported_by"] == 99


@pytest.mark.asyncio
async def test_pure_station_team_report_with_other_worker_rejected(monkeypatch):
    """纯工位账号 + 小组报工夹带他人 worker_id → 拒绝，不落库、不查 assign。"""
    denied = AsyncMock(side_effect=HTTPException(status_code=403, detail="assign"))
    create = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(reporting_api, "ensure_permission_codes", denied)
    monkeypatch.setattr(reporting_api.reporting_service, "create_reporting_record", create)

    with pytest.raises(HTTPException) as raised:
        await reporting_api.create_quick_reporting_record(
            reporting=_record(
                worker_id=88, worker_name="他人", team_id=6, team_name="甲班"
            ),
            request=_request("station"),
            business_operator=_station_operator(),
            auth=MagicMock(),
            current_user=_user(7),
            tenant_id=1,
        )

    assert raised.value.status_code == 400
    denied.assert_not_awaited()
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_pure_station_worker_mismatch_rejected(monkeypatch):
    """纯工位账号报 worker_id 非会话操作员 → 拒绝，不落库、不查 assign。"""
    denied = AsyncMock(side_effect=HTTPException(status_code=403, detail="assign"))
    create = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(reporting_api, "ensure_permission_codes", denied)
    monkeypatch.setattr(reporting_api.reporting_service, "create_reporting_record", create)

    with pytest.raises(HTTPException) as raised:
        await reporting_api.create_quick_reporting_record(
            reporting=_record(worker_id=88, worker_name="他人"),
            request=_request("station"),
            business_operator=_station_operator(),
            auth=MagicMock(),
            current_user=_user(7),
            tenant_id=1,
        )

    assert raised.value.status_code == 400
    denied.assert_not_awaited()
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_forged_station_channel_non_pure_user_still_requires_assign(monkeypatch):
    """非纯工位账号伪造 X-Client-Channel: station 代报 → 仍被 assign 拦截。"""
    denied = AsyncMock(side_effect=HTTPException(status_code=403, detail="assign"))
    create = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(reporting_api, "ensure_permission_codes", denied)
    monkeypatch.setattr(reporting_api.reporting_service, "create_reporting_record", create)

    with pytest.raises(HTTPException) as raised:
        await reporting_api.create_quick_reporting_record(
            reporting=_record(worker_id=99, worker_name="操作员"),
            request=_request("station"),
            business_operator=_pc_operator(),
            auth=MagicMock(),
            current_user=_user(7),
            tenant_id=1,
        )

    assert raised.value.status_code == 403
    create.assert_not_awaited()
    denied.assert_awaited()
    assert denied.await_args.args[3] == ["kuaizhizao:production-execution-reporting:assign"]


@pytest.mark.asyncio
async def test_non_station_self_report_passes_without_assign(monkeypatch):
    """非纯工位账号本人报工（worker == 登录用户）→ 不查 assign，照常创建。"""
    denied = AsyncMock(side_effect=HTTPException(status_code=403, detail="assign"))
    create = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(reporting_api, "ensure_permission_codes", denied)
    monkeypatch.setattr(reporting_api.reporting_service, "create_reporting_record", create)

    await reporting_api.create_quick_reporting_record(
        reporting=_record(worker_id=7, worker_name="本人"),
        request=_request("pc"),
        business_operator=_pc_operator(),
        auth=MagicMock(),
        current_user=_user(7),
        tenant_id=1,
    )

    denied.assert_not_awaited()
    create.assert_awaited_once()
