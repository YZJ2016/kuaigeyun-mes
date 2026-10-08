"""快捷报工的工位边界（spec 180 STN-D15/Q4 修复语义）。

- X-Client-Channel 只是来源标记，不再参与权限判定；
- 纯工位账号以服务端操作员会话为边界：小组报工放行，非小组报工的
  worker_id 必须等于会话确认的操作员用户，代报/他人一律拒绝；
- 非纯工位账号保持原代报判断：伪造 station 渠道头不能跳过 assign。
"""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
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


def _request(channel: str = "pc", session=None) -> MagicMock:
    request = MagicMock()
    request.headers = {"X-Client-Channel": channel}
    request.state = SimpleNamespace(station_operator_session=session)
    return request


def _user(user_id: int) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    return user


def _patch_pure(monkeypatch, is_pure: bool):
    monkeypatch.setattr(
        reporting_api,
        "is_pure_station_terminal_user",
        AsyncMock(return_value=is_pure),
    )


def _patch_fallback_resolve(monkeypatch, session):
    mock = AsyncMock(return_value=session)
    monkeypatch.setattr(
        reporting_api.operator_session_service, "get_current_session", mock
    )
    return mock


@pytest.mark.asyncio
async def test_pure_station_worker_matches_session_operator_passes(monkeypatch):
    """纯工位账号 + 有效会话 + worker_id == 会话操作员 → 放行，不查 assign。"""
    denied = AsyncMock(side_effect=HTTPException(status_code=403, detail="assign"))
    created = MagicMock()
    create = AsyncMock(return_value=created)
    _patch_pure(monkeypatch, True)
    monkeypatch.setattr(reporting_api, "ensure_permission_codes", denied)
    monkeypatch.setattr(reporting_api.reporting_service, "create_reporting_record", create)

    session = SimpleNamespace(operator_user_id=99)
    result = await reporting_api.create_quick_reporting_record(
        reporting=_record(worker_id=99, worker_name="操作员"),
        request=_request("station", session=session),
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
async def test_pure_station_team_report_passes(monkeypatch):
    """纯工位账号 + 小组报工 → 放行，不校验 worker_id、不查 assign。"""
    denied = AsyncMock(side_effect=HTTPException(status_code=403, detail="assign"))
    create = AsyncMock(return_value=MagicMock())
    _patch_pure(monkeypatch, True)
    monkeypatch.setattr(reporting_api, "ensure_permission_codes", denied)
    monkeypatch.setattr(reporting_api.reporting_service, "create_reporting_record", create)

    session = SimpleNamespace(operator_user_id=99)
    await reporting_api.create_quick_reporting_record(
        reporting=_record(worker_id=None, worker_name=None, team_id=6, team_name="甲班"),
        request=_request("station", session=session),
        auth=MagicMock(),
        current_user=_user(7),
        tenant_id=1,
    )

    denied.assert_not_awaited()
    assert create.await_args.kwargs["reported_by"] == 7


@pytest.mark.asyncio
async def test_pure_station_worker_mismatch_rejected(monkeypatch):
    """纯工位账号报 worker_id 非会话操作员 → 拒绝，不落库、不查 assign。"""
    denied = AsyncMock(side_effect=HTTPException(status_code=403, detail="assign"))
    create = AsyncMock(return_value=MagicMock())
    _patch_pure(monkeypatch, True)
    monkeypatch.setattr(reporting_api, "ensure_permission_codes", denied)
    monkeypatch.setattr(reporting_api.reporting_service, "create_reporting_record", create)

    session = SimpleNamespace(operator_user_id=99)
    with pytest.raises(HTTPException) as raised:
        await reporting_api.create_quick_reporting_record(
            reporting=_record(worker_id=88, worker_name="他人"),
            request=_request("station", session=session),
            auth=MagicMock(),
            current_user=_user(7),
            tenant_id=1,
        )

    assert raised.value.status_code == 400
    denied.assert_not_awaited()
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_pure_station_no_session_rejected(monkeypatch):
    """纯工位账号但无已解析会话（含回退解析失败）→ 403 通用文案。"""
    create = AsyncMock(return_value=MagicMock())
    _patch_pure(monkeypatch, True)
    monkeypatch.setattr(reporting_api, "ensure_permission_codes", AsyncMock())
    monkeypatch.setattr(reporting_api.reporting_service, "create_reporting_record", create)
    resolve = _patch_fallback_resolve(monkeypatch, None)

    with pytest.raises(HTTPException) as raised:
        await reporting_api.create_quick_reporting_record(
            reporting=_record(worker_id=99, worker_name="操作员"),
            request=_request("station", session=None),
            auth=MagicMock(),
            current_user=_user(7),
            tenant_id=1,
        )

    assert raised.value.status_code == 403
    assert (
        raised.value.detail == reporting_api.STATION_OPERATOR_SESSION_DENIED_MESSAGE
    )
    resolve.assert_awaited_once()
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_forged_station_channel_non_pure_user_still_requires_assign(monkeypatch):
    """非纯工位账号伪造 X-Client-Channel: station 代报 → 仍被 assign 拦截。"""
    denied = AsyncMock(side_effect=HTTPException(status_code=403, detail="assign"))
    create = AsyncMock(return_value=MagicMock())
    _patch_pure(monkeypatch, False)
    monkeypatch.setattr(reporting_api, "ensure_permission_codes", denied)
    monkeypatch.setattr(reporting_api.reporting_service, "create_reporting_record", create)

    with pytest.raises(HTTPException) as raised:
        await reporting_api.create_quick_reporting_record(
            reporting=_record(worker_id=99, worker_name="操作员"),
            request=_request("station"),
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
    _patch_pure(monkeypatch, False)
    monkeypatch.setattr(reporting_api, "ensure_permission_codes", denied)
    monkeypatch.setattr(reporting_api.reporting_service, "create_reporting_record", create)

    await reporting_api.create_quick_reporting_record(
        reporting=_record(worker_id=7, worker_name="本人"),
        request=_request("pc"),
        auth=MagicMock(),
        current_user=_user(7),
        tenant_id=1,
    )

    denied.assert_not_awaited()
    create.assert_awaited_once()
