"""星报表 spec 149 分发余项。存储用内存替身，不连数据库。"""

from __future__ import annotations

import copy
import inspect
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from apps.kuaireport.schemas.execute import ExecuteReportResult
from apps.kuaireport.services.subscription_service import (
    TASK_TYPE,
    SubscriptionService,
)
from apps.kuaireport.slices import s149_distribution as dist
from apps.kuaireport.slices.s149_distribution import (
    RESOURCE_REPORT,
    DistributionError,
    DistributionNotFoundError,
    TortoiseDistributionStore,
    backfill_dashboard_versions,
    can_view_by_grant,
    create_subscription,
    grant_share,
    restore_dashboard_version,
    restore_report_version,
    router,
    save_dashboard,
)
from core.schemas.message_template import SendMessageResponse
from core.schemas.scheduled_task import ScheduledTaskCreate
from infra.exceptions.exceptions import (
    AuthorizationError,
    NotFoundError,
    ValidationError,
)


class MemoryStore:
    def __init__(self) -> None:
        self.reports: dict[tuple[int, int], dict] = {}
        self.dashboards: dict[tuple[int, int], dict] = {}
        self.roles: set[tuple[int, int]] = set()
        self.users: set[tuple[int, int]] = set()
        self.user_roles: dict[tuple[int, int], list[int]] = {}
        self.grants: list[dict] = []
        self.subs: dict[int, dict] = {}
        self.report_versions: list[dict] = []
        self.dash_versions: list[dict] = []
        self.source_uuids: set[tuple[int, str]] = set()
        self._sub_seq = 1

    @asynccontextmanager
    async def transaction(self):
        snap = copy.deepcopy(
            {
                "reports": self.reports,
                "dashboards": self.dashboards,
                "grants": self.grants,
                "subs": self.subs,
                "report_versions": self.report_versions,
                "dash_versions": self.dash_versions,
                "_sub_seq": self._sub_seq,
            }
        )
        try:
            yield self
        except Exception:
            self.reports = snap["reports"]
            self.dashboards = snap["dashboards"]
            self.grants = snap["grants"]
            self.subs = snap["subs"]
            self.report_versions = snap["report_versions"]
            self.dash_versions = snap["dash_versions"]
            self._sub_seq = snap["_sub_seq"]
            raise

    async def get_report(self, tenant_id: int, report_id: int):
        row = self.reports.get((tenant_id, report_id))
        return copy.deepcopy(row) if row else None

    async def registered_data_source(self, tenant_id: int, source_uuid: str) -> bool:
        return (int(tenant_id), str(source_uuid)) in self.source_uuids

    async def get_dashboard(self, tenant_id: int, dashboard_id: int):
        row = self.dashboards.get((tenant_id, dashboard_id))
        return copy.deepcopy(row) if row else None

    async def role_in_tenant(self, tenant_id: int, role_id: int) -> bool:
        return (tenant_id, role_id) in self.roles

    async def insert_grant(
        self, tenant_id, resource_type, resource_id, role_id, permission, created_by
    ):
        for row in self.grants:
            if (
                row["tenant_id"] == tenant_id
                and row["resource_type"] == resource_type
                and row["resource_id"] == resource_id
                and row["role_id"] == role_id
                and row["permission"] == permission
            ):
                raise DistributionError("授权已存在")
        saved = {
            "id": len(self.grants) + 1,
            "tenant_id": tenant_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "role_id": role_id,
            "permission": permission,
            "created_by": created_by,
        }
        self.grants.append(saved)
        return saved

    async def list_grants(self, tenant_id, resource_type, resource_id):
        return [
            row
            for row in self.grants
            if row["tenant_id"] == tenant_id
            and row["resource_type"] == resource_type
            and row["resource_id"] == resource_id
        ]

    async def user_role_ids(self, tenant_id, user_id):
        if (tenant_id, user_id) not in self.users:
            return []
        return list(self.user_roles.get((tenant_id, user_id), []))

    async def has_grant(self, tenant_id, resource_type, resource_id, role_ids, permission):
        allowed = set(role_ids)
        return any(
            row["tenant_id"] == tenant_id
            and row["resource_type"] == resource_type
            and row["resource_id"] == resource_id
            and row["permission"] == permission
            and row["role_id"] in allowed
            for row in self.grants
        )

    async def users_in_tenant(self, tenant_id, user_ids):
        return {int(user_id) for user_id in user_ids if (tenant_id, int(user_id)) in self.users}

    async def insert_subscription(self, row):
        sub_id = self._sub_seq
        self._sub_seq += 1
        saved = {
            "id": sub_id,
            "tenant_id": row["tenant_id"],
            "report_id": row["report_id"],
            "name": row["name"],
            "cron": row["cron"],
            "channel": row["channel"],
            "recipient_user_ids": list(row["recipient_user_ids"]),
            "filters": copy.deepcopy(row.get("filters")),
            "attach_excel": bool(row["attach_excel"]),
            "is_active": bool(row["is_active"]),
            "scheduled_task_uuid": None,
            "last_run_at": None,
            "last_run_status": None,
            "last_run_error": None,
        }
        self.subs[sub_id] = saved
        return saved

    async def set_subscription_task_uuid(self, tenant_id, subscription_id, task_uuid):
        self.subs[subscription_id]["scheduled_task_uuid"] = task_uuid

    async def get_subscription(self, tenant_id, subscription_id):
        row = self.subs.get(subscription_id)
        if row is None or row["tenant_id"] != tenant_id:
            return None
        return copy.deepcopy(row)

    async def mark_run(self, tenant_id, subscription_id, status, error):
        row = self.subs[subscription_id]
        row["last_run_status"] = status
        row["last_run_error"] = error
        row["last_run_at"] = "now"

    async def list_report_versions(self, tenant_id, report_id):
        rows = [
            row
            for row in self.report_versions
            if row["tenant_id"] == tenant_id and row["report_id"] == report_id
        ]
        return sorted(copy.deepcopy(rows), key=lambda item: item["version_no"], reverse=True)

    async def get_report_version(self, tenant_id, report_id, version_no):
        for row in self.report_versions:
            if (
                row["tenant_id"] == tenant_id
                and row["report_id"] == report_id
                and row["version_no"] == version_no
            ):
                return copy.deepcopy(row)
        return None

    async def update_report_restored(self, tenant_id, report_id, report_config, current_version):
        row = self.reports[(tenant_id, report_id)]
        row["report_config"] = copy.deepcopy(report_config)
        row["current_version"] = current_version

    async def insert_report_version(
        self, tenant_id, report_id, version_no, snapshot, note, user_id
    ):
        saved = {
            "tenant_id": tenant_id,
            "report_id": report_id,
            "version_no": version_no,
            "snapshot": copy.deepcopy(snapshot),
            "note": note,
            "created_by_user_id": user_id,
        }
        self.report_versions.append(saved)
        return copy.deepcopy(saved)

    async def list_dashboards_without_versions(self, tenant_id):
        rows = []
        for (owner, dashboard_id), row in self.dashboards.items():
            if owner != tenant_id:
                continue
            if any(
                item["tenant_id"] == tenant_id and item["dashboard_id"] == dashboard_id
                for item in self.dash_versions
            ):
                continue
            rows.append(copy.deepcopy(row))
        return rows

    async def dashboard_version_count(self, tenant_id, dashboard_id):
        return sum(
            1
            for item in self.dash_versions
            if item["tenant_id"] == tenant_id and item["dashboard_id"] == dashboard_id
        )

    async def update_dashboard_saved(self, tenant_id, dashboard_id, configs, current_version):
        row = self.dashboards[(tenant_id, dashboard_id)]
        for key in ("layout_config", "widgets_config", "theme_config", "tv_config"):
            row[key] = copy.deepcopy(configs.get(key))
        row["current_version"] = current_version

    async def insert_dashboard_version(
        self, tenant_id, dashboard_id, version_no, snapshot, note, user_id
    ):
        saved = {
            "tenant_id": tenant_id,
            "dashboard_id": dashboard_id,
            "version_no": version_no,
            "snapshot": copy.deepcopy(snapshot),
            "note": note,
        }
        self.dash_versions.append(saved)
        return copy.deepcopy(saved)

    async def list_dashboard_versions(self, tenant_id, dashboard_id):
        rows = [
            row
            for row in self.dash_versions
            if row["tenant_id"] == tenant_id and row["dashboard_id"] == dashboard_id
        ]
        return sorted(copy.deepcopy(rows), key=lambda item: item["version_no"], reverse=True)

    async def get_dashboard_version(self, tenant_id, dashboard_id, version_no):
        for row in self.dash_versions:
            if (
                row["tenant_id"] == tenant_id
                and row["dashboard_id"] == dashboard_id
                and row["version_no"] == version_no
            ):
                return copy.deepcopy(row)
        return None


def _seed_report(store: MemoryStore, tenant_id=1, report_id=10, config=None, version=1):
    store.reports[(tenant_id, report_id)] = {
        "id": report_id,
        "tenant_id": tenant_id,
        "report_config": config if config is not None else {"fields": ["qty"]},
        "current_version": version,
        "is_shared": True,
        "share_token": "share-token",
        "share_password_hash": "hashed-secret",
    }


@pytest.mark.asyncio
async def test_grant_allows_role_and_blocks_other():
    store = MemoryStore()
    _seed_report(store)
    store.roles.update({(1, 3), (1, 4)})
    store.users.update({(1, 8), (1, 9)})
    store.user_roles[(1, 8)] = [3]
    store.user_roles[(1, 9)] = [4]

    saved = await grant_share(1, RESOURCE_REPORT, 10, 3, store=store)
    assert saved["resource_type"] == RESOURCE_REPORT
    assert saved["resource_id"] == 10
    assert saved["role_id"] == 3
    assert saved["permission"] == "view"
    assert await can_view_by_grant(1, 8, RESOURCE_REPORT, 10, store=store) is True
    assert await can_view_by_grant(1, 9, RESOURCE_REPORT, 10, store=store) is False
    assert "share_password" not in inspect.getsource(can_view_by_grant)
    assert "share_token" not in inspect.getsource(can_view_by_grant)


@pytest.mark.asyncio
async def test_grant_rejects_missing_resource_and_other_tenant_role():
    store = MemoryStore()
    _seed_report(store, tenant_id=2, report_id=10)
    store.roles.add((2, 3))
    with pytest.raises(DistributionError, match="资源不存在"):
        await grant_share(1, RESOURCE_REPORT, 10, 3, store=store)


@pytest.mark.asyncio
async def test_shared_flag_without_grant_does_not_allow_view():
    store = MemoryStore()
    _seed_report(store)
    store.users.add((1, 8))
    store.user_roles[(1, 8)] = []
    assert await can_view_by_grant(1, 8, RESOURCE_REPORT, 10, store=store) is False


def test_routes_do_not_expose_shared_report_data():
    paths = [getattr(route, "path", "") for route in router.routes]
    assert paths
    assert all("shared" not in path for path in paths)
    source = inspect.getsource(TortoiseDistributionStore)
    assert "apps_kuaireport_share_access_logs" not in source
    assert "share_password" not in source
    assert "UPDATE apps_kuaireport_report_versions" not in source
    assert "UPDATE apps_kuaireport_dashboard_versions" not in source
    assert "INSERT INTO apps_kuaireport_report_versions" in source
    assert "INSERT INTO apps_kuaireport_dashboard_versions" in source
    assert "INSERT INTO apps_kuaireport_report_subscriptions" in source
    assert "name" in source
    assert "range(5, 5 + len(role_ids))" in inspect.getsource(TortoiseDistributionStore.has_grant)


def test_task_type_fits_scheduled_task_column():
    assert len(TASK_TYPE) > 20
    assert len(TASK_TYPE) <= 64
    created = ScheduledTaskCreate(
        name="早报",
        code="krps1",
        type=TASK_TYPE,
        trigger_type="cron",
        trigger_config={"cron": "0 8 * * 1-5"},
        task_config={"subscription_id": 1},
    )
    assert created.type == TASK_TYPE


@pytest.mark.asyncio
async def test_create_subscription_stores_name_and_task_binding():
    store = MemoryStore()
    _seed_report(store)
    store.users.add((1, 5))
    captured = {}

    async def fake_task(tenant_id, fields):
        captured["tenant_id"] = tenant_id
        captured["fields"] = fields
        return SimpleNamespace(uuid="task-uuid-1")

    saved = await create_subscription(
        1,
        10,
        "早报",
        [5],
        store=store,
        create_task=fake_task,
        attach_excel=True,
    )
    assert saved["name"] == "早报"
    assert saved["scheduled_task_uuid"] == "task-uuid-1"
    assert saved["channel"] == "inbox"
    assert captured["fields"]["type"] == TASK_TYPE
    assert captured["fields"]["task_config"] == {"subscription_id": saved["id"]}
    assert captured["fields"]["trigger_config"] == {"cron": "0 8 * * 1-5"}
    assert store.subs[saved["id"]]["attach_excel"] is True


@pytest.mark.asyncio
async def test_execute_runs_report_then_sends_inbox():
    store = MemoryStore()
    store.users.add((1, 5))
    store.subs[3] = {
        "id": 3,
        "tenant_id": 1,
        "report_id": 10,
        "name": "早报",
        "channel": "inbox",
        "recipient_user_ids": [5],
        "is_active": True,
        "attach_excel": True,
        "filters": {"warehouse": "A"},
    }
    order: list[str] = []
    workbook = b"workbook-bytes"

    async def fake_execute(tenant_id, report_id, filters):
        order.append("execute")
        assert tenant_id == 1
        assert report_id == 10
        assert filters == {"warehouse": "A"}
        return ExecuteReportResult(data=[{"qty": 1}], total=4, summary={"qty": 1})

    async def fake_export(report_id, filters):
        order.append("export")
        assert report_id == 10
        assert filters == {"warehouse": "A"}
        return workbook, "inv_ledger.xlsx"

    send = AsyncMock(return_value=SendMessageResponse(success=True))

    async def _send(*args, **kwargs):
        order.append("send")
        return await send(*args, **kwargs)

    with (
        patch(
            "apps.kuaireport.services.execute_service.execute_report",
            fake_execute,
        ),
        patch(
            "apps.kuaireport.slices.s146_center.export_full_excel",
            fake_export,
        ),
        patch(
            "apps.kuaireport.services.subscription_service.MessageService.send_message",
            _send,
        ),
    ):
        result = await SubscriptionService(store).execute_subscription(1, 3)
    assert order == ["execute", "export", "send"]
    assert result["success"] is True
    assert result["excel_attached"] is True
    assert "attachment_note" not in result
    request = send.await_args.kwargs["request"]
    assert request.type == "internal"
    assert request.recipient == "5"
    assert "已执行" in request.content
    assert "共 4 行" in request.content
    assert request.content != "报表订阅已生成"
    assert request.attachment.filename == "inv_ledger.xlsx"
    assert request.attachment.content == workbook
    assert store.subs[3]["last_run_status"] == "success"
    assert store.subs[3]["last_run_error"] is None
    assert "openpyxl" not in inspect.getsource(
        __import__(
            "apps.kuaireport.services.subscription_service",
            fromlist=["SubscriptionService"],
        )
    )


@pytest.mark.asyncio
async def test_execute_omits_attachment_when_excel_disabled():
    store = MemoryStore()
    store.users.add((1, 5))
    store.subs[3] = {
        "id": 3,
        "tenant_id": 1,
        "report_id": 10,
        "name": "早报",
        "channel": "inbox",
        "recipient_user_ids": [5],
        "is_active": True,
        "attach_excel": False,
        "filters": {},
    }

    async def fake_execute(tenant_id, report_id, filters):
        return ExecuteReportResult(data=[], total=1, summary={})

    export = AsyncMock(return_value=(b"workbook-bytes", "inv_ledger.xlsx"))
    send = AsyncMock(return_value=SendMessageResponse(success=True))
    with (
        patch(
            "apps.kuaireport.services.execute_service.execute_report",
            fake_execute,
        ),
        patch(
            "apps.kuaireport.slices.s146_center.export_full_excel",
            export,
        ),
        patch(
            "apps.kuaireport.services.subscription_service.MessageService.send_message",
            send,
        ),
    ):
        result = await SubscriptionService(store).execute_subscription(1, 3)
    export.assert_not_awaited()
    request = send.await_args.kwargs["request"]
    assert request.attachment is None
    assert result["success"] is True
    assert result["excel_attached"] is False
    assert "attachment_note" not in result


@pytest.mark.asyncio
async def test_execute_rejects_other_tenant_recipient_before_send():
    store = MemoryStore()
    store.users.add((2, 5))
    store.subs[3] = {
        "id": 3,
        "tenant_id": 1,
        "report_id": 10,
        "name": "早报",
        "channel": "inbox",
        "recipient_user_ids": [5],
        "is_active": True,
        "attach_excel": True,
    }
    send = AsyncMock(return_value=SendMessageResponse(success=True))
    execute = AsyncMock()
    with (
        patch(
            "apps.kuaireport.services.execute_service.execute_report",
            execute,
        ),
        patch(
            "apps.kuaireport.services.subscription_service.MessageService.send_message",
            send,
        ),
    ):
        result = await SubscriptionService(store).execute_subscription(1, 3)
    execute.assert_not_awaited()
    send.assert_not_awaited()
    assert result["success"] is False
    assert store.subs[3]["last_run_status"] == "failed"


@pytest.mark.asyncio
async def test_execute_failure_hides_password_and_path():
    store = MemoryStore()
    store.users.add((1, 5))
    store.subs[3] = {
        "id": 3,
        "tenant_id": 1,
        "report_id": 10,
        "name": "早报",
        "channel": "inbox",
        "recipient_user_ids": [5],
        "is_active": True,
        "attach_excel": True,
    }
    send = AsyncMock(
        return_value=SendMessageResponse(
            success=False,
            error=r"C:\apps\secret\password=hidden",
        )
    )
    execute = AsyncMock(
        return_value=ExecuteReportResult(data=[], total=0, summary={})
    )
    export = AsyncMock(return_value=(b"workbook-bytes", "inv_ledger.xlsx"))
    with (
        patch(
            "apps.kuaireport.services.execute_service.execute_report",
            execute,
        ),
        patch(
            "apps.kuaireport.slices.s146_center.export_full_excel",
            export,
        ),
        patch(
            "apps.kuaireport.services.subscription_service.MessageService.send_message",
            send,
        ),
    ):
        result = await SubscriptionService(store).execute_subscription(1, 3)
    assert result["success"] is False
    assert result["excel_attached"] is True
    assert store.subs[3]["last_run_status"] == "failed"
    last_error = store.subs[3]["last_run_error"]
    assert "订阅执行失败" in last_error
    assert "password" not in last_error
    assert "C:\\" not in last_error
    assert "password" not in store.subs[3]["last_run_error"]
    assert "C:" not in store.subs[3]["last_run_error"]


@pytest.mark.asyncio
async def test_restore_report_keeps_old_version_and_rolls_back():
    store = MemoryStore()
    old = {"fields": ["old"]}
    new = {"fields": ["new"]}
    _seed_report(store, config=new, version=2)
    store.report_versions.append(
        {
            "tenant_id": 1,
            "report_id": 10,
            "version_no": 1,
            "snapshot": old,
            "note": "save",
        }
    )
    store.report_versions.append(
        {
            "tenant_id": 1,
            "report_id": 10,
            "version_no": 2,
            "snapshot": new,
            "note": "save",
        }
    )
    restored = await restore_report_version(1, 10, 1, store=store)
    assert restored["report_config"] == old
    assert restored["current_version"] == 3
    assert store.reports[(1, 10)]["report_config"] == old
    versions = {row["version_no"]: row["snapshot"] for row in store.report_versions}
    assert versions[1] == old
    assert versions[2] == new
    assert versions[3] == old

    async def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    store.insert_report_version = boom
    before = copy.deepcopy(store.reports[(1, 10)])
    version_count = len(store.report_versions)
    with pytest.raises(RuntimeError, match="boom"):
        await restore_report_version(1, 10, 1, store=store)
    assert store.reports[(1, 10)]["report_config"] == before["report_config"]
    assert store.reports[(1, 10)]["current_version"] == before["current_version"]
    assert len(store.report_versions) == version_count


@pytest.mark.asyncio
async def test_restore_report_reads_bare_snapshot_and_source_uuid():
    store = MemoryStore()
    source_uuid = "11111111-1111-4111-8111-111111111111"
    store.source_uuids.add((1, source_uuid))
    _seed_report(store, config={"fields": ["live"]}, version=1)
    store.report_versions.append(
        {
            "tenant_id": 1,
            "report_id": 10,
            "version_no": 1,
            "snapshot": {
                "fields": ["raw"],
                "data_source_id": 9,
                "extra": {"data_source_uuid": source_uuid},
            },
            "note": "save",
        }
    )
    restored = await restore_report_version(1, 10, 1, store=store)
    assert restored["report_config"]["fields"] == ["raw"]
    assert "data_source_id" not in restored["report_config"]
    assert restored["report_config"]["extra"]["data_source_uuid"] == source_uuid
    versions = {row["version_no"]: row["snapshot"] for row in store.report_versions}
    assert "report_config" not in versions[2]
    assert versions[2]["extra"]["data_source_uuid"] == source_uuid


@pytest.mark.asyncio
async def test_dashboard_backfill_save_and_restore_keep_history():
    store = MemoryStore()
    store.dashboards[(1, 1)] = {
        "id": 1,
        "tenant_id": 1,
        "layout_config": {"cols": 1},
        "widgets_config": [],
        "theme_config": {"bg": "navy"},
        "tv_config": None,
        "current_version": 0,
    }
    store.dashboards[(1, 2)] = {
        "id": 2,
        "tenant_id": 1,
        "layout_config": {"cols": 2},
        "widgets_config": [],
        "theme_config": {},
        "tv_config": {},
        "current_version": 2,
    }
    store.dash_versions.append(
        {
            "tenant_id": 1,
            "dashboard_id": 2,
            "version_no": 2,
            "snapshot": {
                "layout_config": {"cols": 2},
                "widgets_config": [],
                "theme_config": {},
                "tv_config": {},
            },
            "note": "save",
        }
    )
    first = await backfill_dashboard_versions(1, store=store)
    second = await backfill_dashboard_versions(1, store=store)
    assert first["dashboard_ids"] == [1]
    assert second["dashboard_ids"] == []
    assert store.dashboards[(1, 1)]["current_version"] == 1
    assert sum(1 for row in store.dash_versions if row["dashboard_id"] == 1) == 1
    assert sum(1 for row in store.dash_versions if row["dashboard_id"] == 2) == 1

    await save_dashboard(
        1,
        1,
        {
            "layout_config": {"cols": 9},
            "widgets_config": [{"id": "w"}],
            "theme_config": {"bg": "white"},
            "tv_config": {"mode": "tv"},
        },
        store=store,
    )
    versions = await dist.list_dashboard_versions(1, 1, store=store)
    by_no = {row["version_no"]: row["snapshot"] for row in versions}
    assert by_no[1]["layout_config"] == {"cols": 1}
    assert by_no[2]["layout_config"] == {"cols": 9}
    assert store.dashboards[(1, 1)]["current_version"] == 2

    await restore_dashboard_version(1, 1, 1, store=store)
    assert store.dashboards[(1, 1)]["layout_config"] == {"cols": 1}
    assert store.dashboards[(1, 1)]["widgets_config"] == []
    assert store.dashboards[(1, 1)]["theme_config"] == {"bg": "navy"}
    assert store.dashboards[(1, 1)]["tv_config"] is None
    assert store.dashboards[(1, 1)]["current_version"] == 3
    kept = next(row for row in store.dash_versions if row["dashboard_id"] == 1 and row["version_no"] == 1)
    assert kept["snapshot"]["layout_config"] == {"cols": 1}
    assert any(row["version_no"] == 2 and row["dashboard_id"] == 1 for row in store.dash_versions)


@pytest.mark.asyncio
async def test_executor_calls_execute_subscription():
    from core.workflows.functions.scheduled_task_executor import (
        _execute_kuaireport_subscription_task,
    )

    seen = {}

    class FakeService:
        async def execute_subscription(self, tenant_id, subscription_id):
            seen["args"] = (tenant_id, subscription_id)
            return {"success": True, "excel_attached": False}

    task = SimpleNamespace(task_config={"subscription_id": "12"})
    with patch(
        "apps.kuaireport.services.subscription_service.SubscriptionService",
        FakeService,
    ):
        result = await _execute_kuaireport_subscription_task(3, task)
    assert result["success"] is True
    assert seen["args"] == (3, 12)

    missing = await _execute_kuaireport_subscription_task(
        3, SimpleNamespace(task_config={})
    )
    assert missing["success"] is False


@pytest.mark.asyncio
async def test_grant_rejects_non_view_permission():
    """permission 白名单只允许 view；can_view_by_grant 也只查 view。"""
    store = MemoryStore()
    _seed_report(store)
    store.roles.add((1, 3))
    with pytest.raises(DistributionError, match="view"):
        await grant_share(1, RESOURCE_REPORT, 10, 3, permission="edit", store=store)
    assert store.grants == []

    saved = await grant_share(1, RESOURCE_REPORT, 10, 3, permission="view", store=store)
    assert saved["permission"] == "view"

    rows = await dist.list_grants(1, RESOURCE_REPORT, 10, store=store)
    assert rows[0]["resource_type"] == RESOURCE_REPORT
    assert rows[0]["resource_id"] == 10
    assert rows[0]["role_id"] == 3
    assert rows[0]["permission"] == "view"


def test_raise_http_maps_exception_statuses():
    with pytest.raises(HTTPException) as not_found:
        dist._raise_http(DistributionNotFoundError("报表不存在"))
    assert not_found.value.status_code == 404

    with pytest.raises(HTTPException) as infra_not_found:
        dist._raise_http(NotFoundError("报表", "1"))
    assert infra_not_found.value.status_code == 404

    with pytest.raises(HTTPException) as forbidden:
        dist._raise_http(AuthorizationError("权限不足"))
    assert forbidden.value.status_code == 403

    with pytest.raises(HTTPException) as invalid:
        dist._raise_http(ValidationError("bad"))
    assert invalid.value.status_code == 422

    with pytest.raises(HTTPException) as dist_err:
        dist._raise_http(DistributionError("授权已存在"))
    assert dist_err.value.status_code == 422

    with pytest.raises(HTTPException) as unknown:
        dist._raise_http(RuntimeError("boom"))
    assert unknown.value.status_code == 500


@pytest.mark.asyncio
async def test_subscription_rolls_back_when_task_creation_fails():
    """定时任务创建抛错时，订阅行随事务回滚。"""
    store = MemoryStore()
    _seed_report(store)
    store.users.add((1, 5))

    async def boom(tenant_id, fields):
        raise RuntimeError("task save failed")

    with pytest.raises(RuntimeError, match="task save failed"):
        await create_subscription(1, 10, "早报", [5], store=store, create_task=boom)
    assert store.subs == {}


@pytest.mark.asyncio
async def test_subscription_rolls_back_when_uuid_writeback_fails(monkeypatch):
    """回写失败时订阅行回滚；默认任务工厂收到的是事务连接（任务同事务，无孤儿）。"""
    store = MemoryStore()
    _seed_report(store)
    store.users.add((1, 5))
    store.conn = "TX-CONN"
    captured = {}

    async def fake_default(tenant_id, fields, using_db=None):
        captured["using_db"] = using_db
        return SimpleNamespace(uuid="task-uuid-9")

    async def fail_writeback(*_args, **_kwargs):
        raise RuntimeError("writeback failed")

    monkeypatch.setattr(dist, "_default_create_task", fake_default)
    store.set_subscription_task_uuid = fail_writeback
    with pytest.raises(RuntimeError, match="writeback failed"):
        await create_subscription(1, 10, "早报", [5], store=store)
    assert store.subs == {}
    assert captured["using_db"] == "TX-CONN"


@pytest.mark.asyncio
async def test_create_subscription_passes_tx_connection_to_default_task(monkeypatch):
    """默认路径把事务连接传给 ScheduledTaskService（同事务，无孤儿任务）。"""
    store = MemoryStore()
    _seed_report(store)
    store.users.add((1, 5))
    store.conn = "TX-CONN"
    captured = {}

    async def fake_default(tenant_id, fields, using_db=None):
        captured["using_db"] = using_db
        captured["fields"] = fields
        return SimpleNamespace(uuid="task-uuid-tx")

    monkeypatch.setattr(dist, "_default_create_task", fake_default)
    saved = await create_subscription(1, 10, "早报", [5], store=store)
    assert captured["using_db"] == "TX-CONN"
    assert saved["scheduled_task_uuid"] == "task-uuid-tx"


@pytest.mark.asyncio
async def test_default_create_task_forwards_using_db(monkeypatch):
    captured = {}

    class FakeService:
        @staticmethod
        async def create_scheduled_task(tenant_id, data, using_db=None):
            captured["using_db"] = using_db
            captured["type"] = data.type
            return SimpleNamespace(uuid="u-1")

    monkeypatch.setattr(dist, "ScheduledTaskService", FakeService)
    fields = {
        "name": "早报",
        "code": "krps1",
        "type": TASK_TYPE,
        "trigger_type": "cron",
        "trigger_config": {"cron": "0 8 * * 1-5"},
        "task_config": {"subscription_id": 1},
        "is_active": True,
    }
    task = await dist._default_create_task(1, fields, using_db="CONN")
    assert captured["using_db"] == "CONN"
    assert captured["type"] == TASK_TYPE
    assert task.uuid == "u-1"


@pytest.mark.asyncio
async def test_execute_partial_recipient_failure_aggregates():
    """单收件人失败不中断整批；聚合后 last_run_status=failed 且错误脱敏。"""
    store = MemoryStore()
    store.users.update({(1, 5), (1, 6)})
    store.subs[3] = {
        "id": 3,
        "tenant_id": 1,
        "report_id": 10,
        "name": "早报",
        "channel": "inbox",
        "recipient_user_ids": [5, 6],
        "is_active": True,
        "attach_excel": False,
        "filters": {},
    }
    calls: list[str] = []

    async def fake_send(*args, **kwargs):
        request = kwargs["request"]
        calls.append(request.recipient)
        if request.recipient == "5":
            return SendMessageResponse(success=False, error="smtp password=abc /tmp/x")
        return SendMessageResponse(success=True)

    async def fake_execute(tenant_id, report_id, filters):
        return ExecuteReportResult(data=[{"qty": 1}], total=1, summary={})

    with (
        patch(
            "apps.kuaireport.services.execute_service.execute_report",
            fake_execute,
        ),
        patch(
            "apps.kuaireport.services.subscription_service.MessageService.send_message",
            fake_send,
        ),
    ):
        result = await SubscriptionService(store).execute_subscription(1, 3)

    assert calls == ["5", "6"]
    assert result["success"] is False
    assert store.subs[3]["last_run_status"] == "failed"
    err = store.subs[3]["last_run_error"]
    assert "接收人 5" in err
    assert "password" not in err
    assert "/tmp" not in err


class _CenterStore:
    """报表行与授权行放在同一个替身上，列表和详情才能按授权过滤。"""

    def __init__(self, grants: MemoryStore) -> None:
        self.grants = grants
        self.rows: dict[tuple[int, int], dict] = {}

    async def list_rows(self, tenant_id, status, category, classify):
        found = []
        for (owner, _report_id), row in self.rows.items():
            if owner != tenant_id:
                continue
            if status is not None and row["status"] != status:
                continue
            if category is not None and row["category"] != category:
                continue
            if classify is not None and row["classify"] != classify:
                continue
            found.append(dict(row))
        return found

    async def get_row(self, tenant_id, report_id):
        row = self.rows.get((tenant_id, report_id))
        return dict(row) if row else None

    async def list_grants(self, tenant_id, resource_type, resource_id):
        return await self.grants.list_grants(tenant_id, resource_type, resource_id)

    async def has_grant(self, tenant_id, resource_type, resource_id, role_ids, permission):
        return await self.grants.has_grant(
            tenant_id, resource_type, resource_id, role_ids, permission
        )

    async def user_role_ids(self, tenant_id, user_id):
        return await self.grants.user_role_ids(tenant_id, user_id)


def _report_row(report_id: int, code: str) -> dict:
    return {
        "id": report_id,
        "tenant_id": 1,
        "code": code,
        "name": code,
        "category": "custom",
        "classify": "未分类",
        "is_system": False,
        "status": "DRAFT",
        "is_shared": False,
        "report_config": {},
    }


def _arm_roles(store: MemoryStore) -> None:
    store.users.update({(1, 8), (1, 9)})
    store.user_roles[(1, 8)] = [3]
    store.user_roles[(1, 9)] = [4]


def _add_view_grant(store: MemoryStore, resource_type: str, resource_id: int, role_id: int) -> None:
    store.grants.append(
        {
            "id": len(store.grants) + 1,
            "tenant_id": 1,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "role_id": role_id,
            "permission": "view",
        }
    )


@pytest.mark.asyncio
async def test_entries_stay_open_when_resource_has_no_grants(monkeypatch):
    """没有任何授权记录时，列表、详情、预览、执行、导出仍按原调用通过。"""
    from apps.kuaireport.api import execute as execute_api
    from apps.kuaireport.slices import s146_center as center
    from apps.kuaireport.slices import s147_designer as designer
    from apps.kuaireport.slices import s148_share as share
    from infra.domain.tenant_context import clear_tenant_context, set_current_tenant_id

    grants = MemoryStore()
    _arm_roles(grants)
    center_store = _CenterStore(grants)
    center_store.rows[(1, 10)] = _report_row(10, "open")

    @asynccontextmanager
    async def _tx():
        yield center_store

    monkeypatch.setattr(center, "report_center_transaction", _tx)
    set_current_tenant_id(1)

    async def fake_execute(tenant_id, report_id, filters):
        return ExecuteReportResult(data=[{"qty": 1}], total=1, summary={"qty": 1})

    async def fake_load(report_id, tenant_id=None):
        return {"report_id": report_id, "code": "open"}

    monkeypatch.setattr(execute_api, "execute_report", fake_execute)
    monkeypatch.setattr(center, "resolve_execute_report", lambda: fake_execute)
    monkeypatch.setattr(designer, "load_report_for_view", fake_load)

    board = share.MemoryShareStore()
    board.dashboards[20] = share.DashboardRecord(
        id=20, uuid="d-20", tenant_id=1, code="board", name="大屏"
    )
    board.list_grants = grants.list_grants
    board.has_grant = grants.has_grant
    board.user_role_ids = grants.user_role_ids
    service = share.ShareService(board)

    try:
        listed = await center.list_reports(user_id=9)
        assert [row["id"] for row in listed] == [10]
        detail = await center.get_report(10, user_id=9)
        assert detail["code"] == "open"
        content, filename = await center.export_full_excel(
            10, {}, viewer_id=9, apply_grant=True
        )
        assert filename == "open.xlsx"
        assert content[:2] == b"PK"
        executed = await execute_api.execute_report_for_viewer(
            1, 9, 10, {}, grant_store=grants
        )
        assert executed.total == 1
        viewed = await designer.open_designer_report(
            10, tenant_id=1, user_id=9, grant_store=grants
        )
        assert viewed["code"] == "open"
        dashboards = await service.list_dashboards(1, user_id=9)
        assert [row["id"] for row in dashboards] == [20]
        preview = await service.preview_dashboard(tenant_id=1, dashboard_id=20, user_id=9)
        assert preview["name"] == "大屏"
    finally:
        clear_tenant_context()


@pytest.mark.asyncio
async def test_grant_hides_list_and_rejects_other_role(monkeypatch):
    from apps.kuaireport.api import execute as execute_api
    from apps.kuaireport.slices import s146_center as center
    from apps.kuaireport.slices import s147_designer as designer
    from apps.kuaireport.slices import s148_share as share
    from infra.domain.tenant_context import clear_tenant_context, set_current_tenant_id

    grants = MemoryStore()
    _arm_roles(grants)
    _add_view_grant(grants, "report", 10, 3)
    _add_view_grant(grants, "dashboard", 20, 3)
    center_store = _CenterStore(grants)
    center_store.rows[(1, 10)] = _report_row(10, "locked")
    center_store.rows[(1, 11)] = _report_row(11, "free")

    @asynccontextmanager
    async def _tx():
        yield center_store

    monkeypatch.setattr(center, "report_center_transaction", _tx)
    set_current_tenant_id(1)
    executed = {"called": False}

    async def fake_execute(tenant_id, report_id, filters):
        executed["called"] = True
        return ExecuteReportResult(data=[], total=0, summary={})

    async def fake_load(report_id, tenant_id=None):
        executed["called"] = True
        return {"report_id": report_id}

    monkeypatch.setattr(execute_api, "execute_report", fake_execute)
    monkeypatch.setattr(designer, "load_report_for_view", fake_load)

    board = share.MemoryShareStore()
    board.dashboards[20] = share.DashboardRecord(
        id=20, uuid="d-20", tenant_id=1, code="board", name="大屏"
    )
    board.dashboards[21] = share.DashboardRecord(
        id=21, uuid="d-21", tenant_id=1, code="free", name="开放"
    )
    board.list_grants = grants.list_grants
    board.has_grant = grants.has_grant
    board.user_role_ids = grants.user_role_ids
    service = share.ShareService(board)

    try:
        listed = await center.list_reports(user_id=9)
        assert [row["id"] for row in listed] == [11]
        with pytest.raises(AuthorizationError):
            await center.get_report(10, user_id=9)
        with pytest.raises(AuthorizationError):
            await center.export_full_excel(10, {}, viewer_id=9, apply_grant=True)
        with pytest.raises(AuthorizationError):
            await execute_api.execute_report_for_viewer(1, 9, 10, {}, grant_store=grants)
        with pytest.raises(AuthorizationError):
            await designer.open_designer_report(
                10, tenant_id=1, user_id=9, grant_store=grants
            )
        dashboards = await service.list_dashboards(1, user_id=9)
        assert [row["id"] for row in dashboards] == [21]
        with pytest.raises(AuthorizationError):
            await service.preview_dashboard(tenant_id=1, dashboard_id=20, user_id=9)
        assert executed["called"] is False
    finally:
        clear_tenant_context()


@pytest.mark.asyncio
async def test_grant_allows_matching_role(monkeypatch):
    from apps.kuaireport.api import execute as execute_api
    from apps.kuaireport.slices import s146_center as center
    from apps.kuaireport.slices import s147_designer as designer
    from apps.kuaireport.slices import s148_share as share
    from infra.domain.tenant_context import clear_tenant_context, set_current_tenant_id

    grants = MemoryStore()
    _arm_roles(grants)
    _add_view_grant(grants, "report", 10, 3)
    _add_view_grant(grants, "dashboard", 20, 3)
    center_store = _CenterStore(grants)
    center_store.rows[(1, 10)] = _report_row(10, "locked")

    @asynccontextmanager
    async def _tx():
        yield center_store

    monkeypatch.setattr(center, "report_center_transaction", _tx)
    set_current_tenant_id(1)

    async def fake_execute(tenant_id, report_id, filters):
        return ExecuteReportResult(data=[{"qty": 2}], total=1, summary={"qty": 2})

    async def fake_load(report_id, tenant_id=None):
        return {"report_id": report_id, "code": "locked"}

    monkeypatch.setattr(execute_api, "execute_report", fake_execute)
    monkeypatch.setattr(center, "resolve_execute_report", lambda: fake_execute)
    monkeypatch.setattr(designer, "load_report_for_view", fake_load)

    board = share.MemoryShareStore()
    board.dashboards[20] = share.DashboardRecord(
        id=20, uuid="d-20", tenant_id=1, code="board", name="大屏"
    )
    board.list_grants = grants.list_grants
    board.has_grant = grants.has_grant
    board.user_role_ids = grants.user_role_ids
    service = share.ShareService(board)

    try:
        listed = await center.list_reports(user_id=8)
        assert [row["id"] for row in listed] == [10]
        detail = await center.get_report(10, user_id=8)
        assert detail["code"] == "locked"
        _content, filename = await center.export_full_excel(
            10, {}, viewer_id=8, apply_grant=True
        )
        assert filename == "locked.xlsx"
        executed = await execute_api.execute_report_for_viewer(
            1, 8, 10, {}, grant_store=grants
        )
        assert executed.data == [{"qty": 2}]
        viewed = await designer.open_designer_report(
            10, tenant_id=1, user_id=8, grant_store=grants
        )
        assert viewed["code"] == "locked"
        dashboards = await service.list_dashboards(1, user_id=8)
        assert [row["id"] for row in dashboards] == [20]
        preview = await service.preview_dashboard(tenant_id=1, dashboard_id=20, user_id=8)
        assert preview["code"] == "board"
    finally:
        clear_tenant_context()
