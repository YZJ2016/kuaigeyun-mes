"""工位写操作必须归属于服务端确认的实际操作员。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from apps.kuaizhizao.api.deps.station_operator_session import (
    STATION_OPERATOR_SESSION_DENIED_MESSAGE,
    StationBusinessOperator,
)
from apps.kuaizhizao.api.productions import work_orders as work_orders_api
from apps.kuaizhizao.api.station import station as station_api
from apps.kuaizhizao.schemas.station import FaceEnrollRequest, OperatorSkillCreate


def _terminal_user():
    return SimpleNamespace(
        id=7, tenant_id=1, username="terminal", full_name="共享终端"
    )


def _operator():
    return StationBusinessOperator(user_id=99, user_name="操作员甲", user=None)


@pytest.mark.asyncio
async def test_work_order_start_is_attributed_to_confirmed_operator(monkeypatch):
    """开工记录不得继续写入共享终端账号 ID。"""
    start = AsyncMock(return_value=SimpleNamespace(id=1))
    monkeypatch.setattr(
        work_orders_api,
        "WorkOrderService",
        lambda: SimpleNamespace(start_work_order_operation=start),
    )

    await work_orders_api.start_work_order_operation(
        work_order_id=10,
        operation_id=20,
        business_operator=_operator(),
        current_user=_terminal_user(),
        tenant_id=1,
    )

    assert start.await_args.kwargs["started_by"] == 99


@pytest.mark.asyncio
async def test_face_enrollment_rejects_user_other_than_confirmed_operator(monkeypatch):
    """有效会话也不能为其他用户登记人脸模板。"""
    enroll = AsyncMock()
    monkeypatch.setattr(station_api.FaceTemplateService, "enroll", enroll)

    with pytest.raises(HTTPException) as raised:
        await station_api.enroll_face_template(
            data=FaceEnrollRequest(user_id=88, descriptor=[0.1, 0.2]),
            business_operator=_operator(),
            current_user=_terminal_user(),
            tenant_id=1,
        )

    assert raised.value.status_code == 403
    assert raised.value.detail == STATION_OPERATOR_SESSION_DENIED_MESSAGE
    enroll.assert_not_awaited()


@pytest.mark.asyncio
async def test_operator_skill_rejects_user_other_than_confirmed_operator(monkeypatch):
    """工位端创建资质记录时，目标用户必须是已确认操作员。"""
    create = AsyncMock()
    monkeypatch.setattr(station_api.station_service, "create_operator_skill", create)

    with pytest.raises(HTTPException) as raised:
        await station_api.create_operator_skill(
            data=OperatorSkillCreate(user_id=88, operation_id=3),
            business_operator=_operator(),
            current_user=_terminal_user(),
            tenant_id=1,
        )

    assert raised.value.status_code == 403
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_face_template_list_uses_confirmed_operator(monkeypatch):
    """“我的模板”中的“我”是已确认操作员，不是共享终端账号。"""
    list_for_user = AsyncMock(return_value=[])
    monkeypatch.setattr(
        station_api.FaceTemplateService, "list_for_user", list_for_user
    )

    result = await station_api.list_my_face_templates(
        business_operator=_operator(),
        current_user=_terminal_user(),
        tenant_id=1,
    )

    assert result == []
    list_for_user.assert_awaited_once_with(1, 99)


@pytest.mark.asyncio
async def test_face_template_delete_uses_confirmed_operator(monkeypatch):
    """删除模板的所有权校验必须使用已确认操作员。"""
    delete = AsyncMock()
    monkeypatch.setattr(
        station_api.FaceTemplateService, "delete_template", delete
    )

    await station_api.delete_face_template(
        template_id=12,
        business_operator=_operator(),
        current_user=_terminal_user(),
        tenant_id=1,
    )

    delete.assert_awaited_once_with(1, 12, user_id=99)
