"""数据备份列表在无组织上下文时仍只读指定组织，超管缺头按既有契约 400。"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from tortoise.exceptions import DoesNotExist

from core.api.data_backups import data_backups as api
from core.api.deps.deps import get_current_user
from core.services.system import data_backup_service as service
from infra.domain.tenant_context import (
    TenantContextError,
    clear_request_actor,
    clear_tenant_context,
    get_current_tenant_id,
    set_current_tenant_id,
)

ROWS = (
    SimpleNamespace(uuid="a", tenant_id=7, name="org-7"),
    SimpleNamespace(uuid="b", tenant_id=8, name="org-8"),
)


class _ScopedQuery:
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id

    def filter(self, **_kwargs):
        return self

    def _visible(self):
        ctx = get_current_tenant_id()
        if ctx is None:
            raise TenantContextError("无组织上下文访问租户模型 DataBackup")
        if ctx != self.tenant_id:
            return []
        return [row for row in ROWS if row.tenant_id == ctx]

    async def count(self):
        return len(self._visible())

    def order_by(self, *_args):
        return self

    def offset(self, _n):
        return self

    def limit(self, _n):
        return self

    async def all(self):
        return list(self._visible())


@pytest.fixture(autouse=True)
def _reset_tenant_context():
    clear_tenant_context()
    clear_request_actor()
    yield
    clear_tenant_context()
    clear_request_actor()


@pytest.mark.asyncio
async def test_list_without_ambient_context_stays_in_requested_org(monkeypatch):
    monkeypatch.setattr(service.DataBackup, "filter", lambda **kwargs: _ScopedQuery(kwargs["tenant_id"]))

    set_current_tenant_id(8)
    items, total = await service.DataBackupService.get_backups(7)
    assert total == 1
    assert [item.name for item in items] == ["org-7"]
    assert get_current_tenant_id() == 8

    clear_tenant_context()
    items, total = await service.DataBackupService.get_backups(8)
    assert total == 1
    assert [item.name for item in items] == ["org-8"]
    assert get_current_tenant_id() is None


@pytest.mark.asyncio
async def test_get_by_uuid_without_ambient_context_restores_caller(monkeypatch):
    async def fake_get(**kwargs):
        ctx = get_current_tenant_id()
        if ctx is None:
            raise TenantContextError("无组织上下文访问租户模型 DataBackup")
        match = next(
            (row for row in ROWS if row.tenant_id == ctx and row.uuid == kwargs["uuid"]),
            None,
        )
        if match is None or kwargs["tenant_id"] != ctx:
            raise DoesNotExist(service.DataBackup)
        return match

    monkeypatch.setattr(service.DataBackup, "get", fake_get)
    set_current_tenant_id(3)
    backup = await service.DataBackupService.get_backup_by_uuid(7, "a")
    assert backup.name == "org-7"
    assert get_current_tenant_id() == 3

    with pytest.raises(ValueError, match="备份不存在"):
        await service.DataBackupService.get_backup_by_uuid(8, "a")
    assert get_current_tenant_id() == 3


@pytest.mark.asyncio
async def test_superadmin_backup_routes_require_tenant_header(monkeypatch):
    user = SimpleNamespace(
        id=1,
        tenant_id=None,
        _is_infra_superadmin=True,
        is_infra_admin_user=lambda: True,
        is_organization_admin=lambda: False,
    )

    async def fake_list(tenant_id, *_args, **_kwargs):
        assert get_current_tenant_id() == tenant_id
        return [], 0

    monkeypatch.setattr(api.DataBackupService, "get_backups", fake_list)

    class _HealthQuery:
        def filter(self, **_kwargs):
            return self

        async def count(self):
            assert get_current_tenant_id() == 21
            return 0

    monkeypatch.setattr(api.DataBackup, "filter", lambda **_kwargs: _HealthQuery())

    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_current_user] = lambda: user
    headers = {"Authorization": "Bearer admin"}
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        missing = await client.get("/data-backups", headers=headers)
        health_missing = await client.get("/data-backups/worker-health", headers=headers)
        listed = await client.get("/data-backups", headers={**headers, "X-Tenant-ID": "21"})
        health = await client.get("/data-backups/worker-health", headers={**headers, "X-Tenant-ID": "21"})

    assert missing.status_code == 400
    assert missing.json()["detail"] == "平台超级管理员访问租户资源时，必须通过 X-Tenant-ID 指定租户ID"
    assert health_missing.status_code == 400
    assert health_missing.json()["detail"] == missing.json()["detail"]
    assert listed.status_code == 200
    assert listed.json()["total"] == 0
    assert health.status_code == 200
    assert health.json()["pending_total"] == 0
