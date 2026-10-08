"""工位操作员确认/状态/关闭 API：候选人一致才签发，失败不泄露差异（spec 180 T5）。"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from apps.kuaizhizao.api.station import station as station_api
from apps.kuaizhizao.schemas.station import StationOperatorSessionConfirmRequest
from infra.exceptions.exceptions import BusinessLogicError


def _user(user_id: int = 7) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, tenant_id=1, username="terminal", full_name="终端")


def _confirm_request(**kw) -> StationOperatorSessionConfirmRequest:
    payload = {
        "workstation_id": 5,
        "candidate_user_id": 99,
        "confirm_method": "employee_code",
        "employee_code": "E-1",
    }
    payload.update(kw)
    return StationOperatorSessionConfirmRequest.model_validate(payload)


def _session(**kw) -> SimpleNamespace:
    base = {
        "id": 1,
        "uuid": "u-1",
        "workstation_id": 5,
        "workstation_name": "工位A",
        "operator_employee_id": 21,
        "operator_user_id": 99,
        "operator_name": "操作员甲",
        "confirm_method": "employee_code",
        "status": "active",
        "issued_at": datetime(2026, 10, 8, 9, 0, 0, tzinfo=timezone.utc),
        "last_seen_at": datetime(2026, 10, 8, 9, 0, 0, tzinfo=timezone.utc),
        "closed_at": None,
        "close_reason": None,
    }
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_confirm_returns_plaintext_credential_once(monkeypatch):
    """确认成功：响应返回凭据原文 + 会话概要，且不包含哈希字段。"""
    confirm = AsyncMock(return_value=(_session(), "the-raw-credential"))
    monkeypatch.setattr(station_api.operator_session_service, "confirm", confirm)

    result = await station_api.confirm_operator_session(
        data=_confirm_request(), current_user=_user(), tenant_id=1
    )

    assert result.credential == "the-raw-credential"
    assert result.session.operator_user_id == 99
    assert not hasattr(result.session, "credential_hash")
    assert confirm.await_args.kwargs["candidate_user_id"] == 99
    assert confirm.await_args.kwargs["confirm_method"] == "employee_code"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "detail",
    ["操作员身份确认失败，请重新选择人员后重试"],
)
async def test_confirm_failure_is_generic_and_hides_reason(monkeypatch, detail):
    """确认失败统一 400 + 通用文案，不区分不存在/离职/未关联/停用/候选不一致。"""
    confirm = AsyncMock(side_effect=BusinessLogicError(detail))
    monkeypatch.setattr(station_api.operator_session_service, "confirm", confirm)

    with pytest.raises(HTTPException) as raised:
        await station_api.confirm_operator_session(
            data=_confirm_request(employee_code="E-any"),
            current_user=_user(),
            tenant_id=1,
        )
    assert raised.value.status_code == 400
    assert raised.value.detail == detail
    assert "E-any" not in str(raised.value.detail)


@pytest.mark.asyncio
async def test_current_returns_valid_session(monkeypatch):
    get_current = AsyncMock(return_value=_session())
    monkeypatch.setattr(
        station_api.operator_session_service, "get_current_session", get_current
    )

    result = await station_api.get_current_operator_session(
        workstation_id=5,
        x_station_operator_session="cred",
        current_user=_user(),
        tenant_id=1,
    )

    assert result.valid is True
    assert result.session.operator_user_id == 99
    assert result.session.workstation_id == 5
    assert get_current.await_args.kwargs["credential"] == "cred"
    assert get_current.await_args.kwargs["terminal_user_id"] == 7


@pytest.mark.asyncio
@pytest.mark.parametrize("credential", [None, "wrong-credential"])
async def test_current_invalid_or_missing_credential(monkeypatch, credential):
    """缺失/无效凭据 → valid=False，不返回他人会话信息。"""
    get_current = AsyncMock(return_value=None)
    monkeypatch.setattr(
        station_api.operator_session_service, "get_current_session", get_current
    )

    result = await station_api.get_current_operator_session(
        workstation_id=None,
        x_station_operator_session=credential,
        current_user=_user(),
        tenant_id=1,
    )

    assert result.valid is False
    assert result.session is None


@pytest.mark.asyncio
async def test_close_is_idempotent(monkeypatch):
    """关闭幂等：服务返回 False（会话已关闭/凭据无效）时接口仍返回 closed=True。"""
    close = AsyncMock(return_value=False)
    monkeypatch.setattr(
        station_api.operator_session_service, "close_session", close
    )

    result = await station_api.close_operator_session(
        x_station_operator_session="cred",
        current_user=_user(),
        tenant_id=1,
    )

    assert result.closed is True
    assert close.await_args.kwargs["credential"] == "cred"
    assert close.await_args.kwargs["terminal_user_id"] == 7
