"""操作日志中间件在请求返回后更新在线活动：无 ambient 上下文时须进入已解析组织。"""

import pytest
import pytest_asyncio
from tortoise import Tortoise

from core.middleware.operation_log_middleware import OperationLogMiddleware
from core.models.user_activity import UserActivity
from core.services.logging.online_user_service import OnlineUserService
from infra.domain.tenant_context import (
    TenantContextError,
    clear_tenant_context,
    get_current_tenant_id,
    resolve_tenant_for_query,
    set_current_tenant_id,
    with_tenant,
)


@pytest_asyncio.fixture
async def activity_db():
    clear_tenant_context()
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["core.models.user_activity"]},
        use_tz=True,
        timezone="UTC",
    )
    await Tortoise.generate_schemas()
    yield
    clear_tenant_context()
    await Tortoise.close_connections()


async def _row(tenant_id: int, user_id: int):
    async with with_tenant(tenant_id):
        return await UserActivity.filter(tenant_id=tenant_id, user_id=user_id).first()


@pytest.mark.asyncio
async def test_activity_update_uses_resolved_tenant_without_ambient_context(activity_db):
    clear_tenant_context()
    assert get_current_tenant_id() is None

    await OperationLogMiddleware._persist_activity(
        tenant_id=7,
        user_id=11,
        ip_address="10.0.0.8",
        force=True,
    )

    assert get_current_tenant_id() is None
    assert resolve_tenant_for_query() is None
    row = await _row(7, 11)
    assert row is not None
    assert row.tenant_id == 7
    assert row.login_ip == "10.0.0.8"
    assert await _row(8, 11) is None

    with pytest.raises(TenantContextError):
        await UserActivity.filter(user_id=11).first()


@pytest.mark.asyncio
async def test_activity_update_does_not_keep_or_clobber_ambient_context(activity_db):
    set_current_tenant_id(3)
    await OperationLogMiddleware._persist_activity(
        tenant_id=7,
        user_id=12,
        ip_address=None,
        force=True,
    )
    assert get_current_tenant_id() == 3
    assert resolve_tenant_for_query() == 3
    assert (await _row(7, 12)) is not None
    assert await _row(3, 12) is None
    clear_tenant_context()


@pytest.mark.asyncio
async def test_superadmin_sentinel_stays_in_tenant_zero(activity_db):
    clear_tenant_context()
    await OperationLogMiddleware._persist_activity(
        tenant_id=0,
        user_id=1,
        ip_address="127.0.0.1",
        force=True,
    )
    assert get_current_tenant_id() is None
    row = await _row(0, 1)
    assert row is not None
    assert row.tenant_id == 0
    assert await _row(7, 1) is None


@pytest.mark.asyncio
async def test_direct_update_without_scope_still_fails_closed(activity_db):
    clear_tenant_context()
    await OnlineUserService.update_user_activity(tenant_id=9, user_id=21, login_ip="1.1.1.1")
    assert await _row(9, 21) is None
    assert get_current_tenant_id() is None
    with pytest.raises(TenantContextError):
        await UserActivity.filter(tenant_id=9, user_id=21).first()
