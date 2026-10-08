"""工位操作员会话服务：凭据哈希落库、替换/关闭、租户与绑定隔离（spec 180 T4）。"""

import hashlib
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.kuaizhizao.models.station_operator_session import StationOperatorSession
from apps.kuaizhizao.services import station_operator_session_service as svc_mod
from apps.kuaizhizao.services.station_operator_session_service import (
    CLOSE_REASON_EXPLICIT_CLOSE,
    CLOSE_REASON_REPLACED,
    CONFIRM_FAILED_MESSAGE,
    STATUS_ACTIVE,
    STATUS_CLOSED,
    StationOperatorSessionService,
    hash_credential,
)
from infra.exceptions.exceptions import BusinessLogicError
from infra.models.user import User
from apps.kuaioa.models.employee import KuaioaEmployeeProfile


@asynccontextmanager
async def _noop_tx():
    yield


@pytest.fixture(autouse=True)
def _patch_transaction(monkeypatch):
    monkeypatch.setattr(svc_mod, "in_transaction", _noop_tx)


def _terminal_user(user_id: int = 7) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, tenant_id=1)


def _query_stub(first=None, all_rows=None):
    query = MagicMock()
    query.first = AsyncMock(return_value=first)
    query.all = AsyncMock(return_value=all_rows or [])
    query.update = AsyncMock(return_value=1)
    query.filter = MagicMock(return_value=query)
    return query


def _profile(**kw) -> SimpleNamespace:
    base = {"id": 21, "user_id": 99, "full_name": "操作员甲", "tenant_id": 1}
    base.update(kw)
    return SimpleNamespace(**base)


def _workstation() -> SimpleNamespace:
    return SimpleNamespace(id=5, name="工位A", tenant_id=1)


def _session_row(**kw) -> SimpleNamespace:
    base = {
        "id": 1,
        "uuid": "u-1",
        "tenant_id": 1,
        "terminal_user_id": 7,
        "workstation_id": 5,
        "workstation_name": "工位A",
        "operator_employee_id": 21,
        "operator_user_id": 99,
        "operator_name": "操作员甲",
        "confirm_method": "employee_code",
        "status": STATUS_ACTIVE,
        "close_reason": None,
        "closed_at": None,
        "save": AsyncMock(),
    }
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_confirm_hashes_credential_and_never_stores_plaintext(monkeypatch):
    """签发：库中只有 SHA-256 hex，原始凭据只出现在返回值。"""
    created_kwargs = {}

    async def _create(**kwargs):
        created_kwargs.update(kwargs)
        return _session_row(**{k: v for k, v in kwargs.items() if k != "save"})

    close_query = _query_stub()
    monkeypatch.setattr(StationOperatorSession, "create", _create)
    monkeypatch.setattr(StationOperatorSession, "filter", lambda **kw: close_query)
    monkeypatch.setattr(
        svc_mod.Workstation, "get_or_none", AsyncMock(return_value=_workstation())
    )
    monkeypatch.setattr(
        KuaioaEmployeeProfile, "filter", lambda **kw: _query_stub(first=_profile())
    )
    monkeypatch.setattr(
        User, "get_or_none", AsyncMock(return_value=SimpleNamespace(id=99, tenant_id=1))
    )

    session, credential = await StationOperatorSessionService().confirm(
        tenant_id=1,
        terminal_user=_terminal_user(),
        workstation_id=5,
        candidate_user_id=99,
        confirm_method="employee_code",
        employee_code="E-1",
    )

    assert credential
    assert created_kwargs["credential_hash"] == hashlib.sha256(
        credential.encode("utf-8")
    ).hexdigest()
    assert created_kwargs["credential_hash"] != credential
    assert credential not in str(created_kwargs)
    assert created_kwargs["status"] == STATUS_ACTIVE
    assert created_kwargs["operator_employee_id"] == 21
    assert session.credential_hash == created_kwargs["credential_hash"]


@pytest.mark.asyncio
async def test_confirm_closes_legacy_active_sessions_in_transaction(monkeypatch):
    """同一事务：确认前关闭同租户+终端账号的遗留 active 会话（replaced）。"""
    close_query = _query_stub()
    monkeypatch.setattr(
        StationOperatorSession, "create", AsyncMock(return_value=_session_row())
    )
    filter_calls = []

    def _filter(**kw):
        filter_calls.append(kw)
        return close_query

    monkeypatch.setattr(StationOperatorSession, "filter", _filter)
    monkeypatch.setattr(
        svc_mod.Workstation, "get_or_none", AsyncMock(return_value=_workstation())
    )
    monkeypatch.setattr(
        KuaioaEmployeeProfile, "filter", lambda **kw: _query_stub(first=_profile())
    )
    monkeypatch.setattr(
        User, "get_or_none", AsyncMock(return_value=SimpleNamespace(id=99))
    )

    await StationOperatorSessionService().confirm(
        tenant_id=1,
        terminal_user=_terminal_user(),
        workstation_id=5,
        candidate_user_id=99,
        confirm_method="employee_code",
        employee_code="E-1",
    )

    assert filter_calls == [
        {"tenant_id": 1, "terminal_user_id": 7, "status": STATUS_ACTIVE}
    ]
    close_query.update.assert_awaited_once()
    update_kwargs = close_query.update.await_args.kwargs
    assert update_kwargs["status"] == STATUS_CLOSED
    assert update_kwargs["close_reason"] == CLOSE_REASON_REPLACED


@pytest.mark.asyncio
async def test_resolve_rejects_credential_across_tenant_terminal_workstation(monkeypatch):
    """凭据不可跨租户/跨终端账号/跨工位复用：任何绑定不一致均返回 None。"""
    credential = "opaque-credential"
    row = _session_row(credential_hash=hash_credential(credential))
    seen_filters = []

    def _filter(**kw):
        seen_filters.append(kw)
        match = (
            kw.get("tenant_id") == row.tenant_id
            and kw.get("terminal_user_id") == row.terminal_user_id
            and kw.get("credential_hash") == row.credential_hash
            and kw.get("status") == STATUS_ACTIVE
        )
        return _query_stub(first=row if match else None)

    monkeypatch.setattr(StationOperatorSession, "filter", _filter)
    service = StationOperatorSessionService()

    assert (
        await service.resolve_active_session(
            tenant_id=1, terminal_user_id=7, credential=credential
        )
        is row
    )
    # 跨租户
    assert (
        await service.resolve_active_session(
            tenant_id=2, terminal_user_id=7, credential=credential
        )
        is None
    )
    # 跨终端账号
    assert (
        await service.resolve_active_session(
            tenant_id=1, terminal_user_id=8, credential=credential
        )
        is None
    )
    # 跨工位
    assert (
        await service.resolve_active_session(
            tenant_id=1, terminal_user_id=7, credential=credential, workstation_id=6
        )
        is None
    )
    # 未知凭据
    assert (
        await service.resolve_active_session(
            tenant_id=1, terminal_user_id=7, credential="other-credential"
        )
        is None
    )
    # 空凭据
    assert (
        await service.resolve_active_session(
            tenant_id=1, terminal_user_id=7, credential=None
        )
        is None
    )


@pytest.mark.asyncio
async def test_no_automatic_timeout(monkeypatch):
    """无固定 TTL/闲置超时：久未活动的 active 会话仍有效。"""
    credential = "opaque-credential"
    row = _session_row(credential_hash=hash_credential(credential))
    monkeypatch.setattr(
        StationOperatorSession, "filter", lambda **kw: _query_stub(first=row)
    )

    session = await StationOperatorSessionService().resolve_active_session(
        tenant_id=1, terminal_user_id=7, credential=credential
    )
    assert session is row


@pytest.mark.asyncio
async def test_get_current_touches_last_seen(monkeypatch):
    credential = "opaque-credential"
    row = _session_row(credential_hash=hash_credential(credential))
    monkeypatch.setattr(
        StationOperatorSession, "filter", lambda **kw: _query_stub(first=row)
    )

    session = await StationOperatorSessionService().get_current_session(
        tenant_id=1, terminal_user_id=7, credential=credential
    )
    assert session is row
    row.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_is_idempotent(monkeypatch):
    """重复关闭不报错：第二次返回 False。"""
    credential = "opaque-credential"
    row = _session_row(credential_hash=hash_credential(credential))
    active = {"row": row}

    def _filter(**kw):
        if kw.get("status") == STATUS_ACTIVE and active["row"] is not None:
            return _query_stub(first=active["row"])
        return _query_stub(first=None)

    async def _save(**kwargs):
        active["row"] = None

    row.save = AsyncMock(side_effect=_save)
    monkeypatch.setattr(StationOperatorSession, "filter", _filter)
    service = StationOperatorSessionService()

    assert (
        await service.close_session(
            tenant_id=1, terminal_user_id=7, credential=credential
        )
        is True
    )
    assert row.status == STATUS_CLOSED
    assert row.close_reason == CLOSE_REASON_EXPLICIT_CLOSE
    # 幂等：再次关闭返回 False 而非抛错
    assert (
        await service.close_session(
            tenant_id=1, terminal_user_id=7, credential=credential
        )
        is False
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "profile,user,candidate",
    [
        (None, SimpleNamespace(id=99), 99),       # 未知员工码
        (_profile(), None, 99),                    # 档案关联用户停用/缺失
        (_profile(user_id=None), SimpleNamespace(id=99), 99),  # 未关联用户（被查询条件排除后仍兜底）
        (_profile(), SimpleNamespace(id=99), 100), # 候选不一致
    ],
)
async def test_confirm_failures_are_generic(monkeypatch, profile, user, candidate):
    """未知/未关联/停用/候选不一致 → 统一通用失败，不区分原因。"""
    monkeypatch.setattr(
        svc_mod.Workstation, "get_or_none", AsyncMock(return_value=_workstation())
    )
    # profile=None 时模拟员工码未命中；未关联场景模拟 filter 仍返回 profile 再由 user 校验拦截
    monkeypatch.setattr(
        KuaioaEmployeeProfile, "filter", lambda **kw: _query_stub(first=profile)
    )
    monkeypatch.setattr(User, "get_or_none", AsyncMock(return_value=user))
    create = AsyncMock()
    monkeypatch.setattr(StationOperatorSession, "create", create)

    with pytest.raises(BusinessLogicError) as raised:
        await StationOperatorSessionService().confirm(
            tenant_id=1,
            terminal_user=_terminal_user(),
            workstation_id=5,
            candidate_user_id=candidate,
            confirm_method="employee_code",
            employee_code="E-any",
        )
    assert str(raised.value) == CONFIRM_FAILED_MESSAGE
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_face_confirm_mismatch_raises_generic(monkeypatch):
    """刷脸识别出的用户与候选不一致 → 通用失败。"""
    monkeypatch.setattr(
        svc_mod.Workstation, "get_or_none", AsyncMock(return_value=_workstation())
    )
    monkeypatch.setattr(
        svc_mod.FaceTemplateService,
        "identify",
        AsyncMock(
            return_value={
                "matched": True,
                "score": 0.9,
                "user_id": 55,
                "username": "x",
                "full_name": "y",
                "template_id": 1,
            }
        ),
    )
    monkeypatch.setattr(
        KuaioaEmployeeProfile,
        "filter",
        lambda **kw: _query_stub(first=_profile(user_id=55)),
    )
    monkeypatch.setattr(
        User, "get_or_none", AsyncMock(return_value=SimpleNamespace(id=55))
    )
    create = AsyncMock()
    monkeypatch.setattr(StationOperatorSession, "create", create)

    with pytest.raises(BusinessLogicError, match=CONFIRM_FAILED_MESSAGE):
        await StationOperatorSessionService().confirm(
            tenant_id=1,
            terminal_user=_terminal_user(),
            workstation_id=5,
            candidate_user_id=99,
            confirm_method="face",
            face_descriptor=[0.1] * 128,
        )
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_face_confirm_success_issues_session(monkeypatch):
    """刷脸识别用户与候选一致 → 正常签发。"""
    monkeypatch.setattr(
        svc_mod.Workstation, "get_or_none", AsyncMock(return_value=_workstation())
    )
    monkeypatch.setattr(
        svc_mod.FaceTemplateService,
        "identify",
        AsyncMock(
            return_value={
                "matched": True,
                "score": 0.9,
                "user_id": 99,
                "username": "x",
                "full_name": "y",
                "template_id": 1,
            }
        ),
    )
    monkeypatch.setattr(
        KuaioaEmployeeProfile, "filter", lambda **kw: _query_stub(first=_profile())
    )
    monkeypatch.setattr(
        User, "get_or_none", AsyncMock(return_value=SimpleNamespace(id=99))
    )
    create = AsyncMock(return_value=_session_row(confirm_method="face"))
    monkeypatch.setattr(StationOperatorSession, "create", create)
    monkeypatch.setattr(
        StationOperatorSession, "filter", lambda **kw: _query_stub()
    )

    session, credential = await StationOperatorSessionService().confirm(
        tenant_id=1,
        terminal_user=_terminal_user(),
        workstation_id=5,
        candidate_user_id=99,
        confirm_method="face",
        face_descriptor=[0.1] * 128,
    )
    assert credential
    assert create.await_args.kwargs["confirm_method"] == "face"
    assert create.await_args.kwargs["operator_user_id"] == 99
