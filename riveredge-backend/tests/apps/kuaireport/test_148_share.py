"""spec 148：大屏保存与受控分享。"""

from __future__ import annotations

import inspect
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.kuaireport.slices import s148_share as share
from infra.api.deps.deps import get_current_user

PLAIN = "share-plain-9f3a"
NOW = datetime(2026, 9, 28, 8, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(days=2)
PAST = NOW - timedelta(hours=1)
TENANT = 7


def _widgets():
    rows = []
    for index, widget_type in enumerate(share.WIDGET_TYPES, start=1):
        rows.append(
            {
                "id": f"w{index}",
                "type": widget_type,
                "data_source_id": index,
                "refresh_seconds": 15 + index,
                "title": widget_type,
                "options": {"label": widget_type},
            }
        )
    return rows


def _service(store, *, execute_source=None, execute_report=None, preview_url=None):
    async def source(tenant_id, data_source_id):
        if execute_source:
            return await execute_source(tenant_id, data_source_id)
        return {"data": [{"n": data_source_id}], "total": 1, "summary": {"n": data_source_id}}

    async def report_exec(tenant_id, report_id, report_config):
        if execute_report:
            return await execute_report(tenant_id, report_id, report_config)
        return {"data": [{"id": report_id}], "total": 1, "summary": {"rows": 1}}

    async def preview(file_uuid, tenant_id, size):
        if preview_url:
            return await preview_url(file_uuid, tenant_id, size)
        return f"/api/v1/core/files/{file_uuid}/download?token=preview&tenant={tenant_id}"

    return share.ShareService(
        store,
        secret="test-share-secret",
        execute_source=source,
        execute_report=report_exec,
        preview_url=preview,
        clock=lambda: NOW,
    )


def _client(service) -> TestClient:
    app = FastAPI()
    app.include_router(share.create_router(service), prefix="/api/v1/apps/kuaireport")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, tenant_id=TENANT, username="designer"
    )
    return TestClient(app)


def _blob(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _assert_no_secret(value, *hashes: str) -> None:
    text = _blob(value)
    assert PLAIN not in text
    for hashed in hashes:
        assert hashed not in text
        assert "pbkdf2" not in text


def _assert_logs_clean(store, *hashes: str) -> None:
    assert store.logs
    for record in store.logs:
        assert record.action == "view"
        assert record.detail in share.ALLOWED_DETAILS
        _assert_no_secret(record.__dict__, *hashes)


async def _save_dashboard(service, store):
    saved = await service.save_dashboard(
        tenant_id=TENANT,
        dashboard_id=None,
        code="board-1",
        name="车间大屏",
        layout_config={"cols": 12},
        widgets_config=_widgets(),
        theme_config={"bg": "#001"},
        tv_config={"interval": 30},
    )
    return saved


@pytest.mark.asyncio
async def test_save_dashboard_widgets_and_logged_in_preview_skips_share_path():
    store = share.MemoryShareStore()
    seen = []

    async def source(tenant_id, data_source_id):
        seen.append((tenant_id, data_source_id))
        return {"data": [{"v": data_source_id}], "total": 1, "summary": {"v": data_source_id}}

    service = _service(store, execute_source=source)
    saved = await _save_dashboard(service, store)
    assert saved["layout_config"] == {"cols": 12}
    assert saved["theme_config"] == {"bg": "#001"}
    assert saved["tv_config"] == {"interval": 30}
    assert [item["type"] for item in saved["widgets_config"]] == list(share.WIDGET_TYPES)
    assert all("data_source_id" in item for item in saved["widgets_config"])
    assert "share_password_hash" not in saved

    with pytest.raises(ValueError):
        await service.save_dashboard(
            tenant_id=TENANT,
            dashboard_id=None,
            code="board-2",
            name="坏组件",
            layout_config={},
            widgets_config=[
                {
                    "type": "metric",
                    "data_source_id": 1,
                    "data_source_ids": [1, 2],
                    "refresh_seconds": 10,
                }
            ],
            theme_config={},
            tv_config={},
        )

    client = _client(service)
    preview = client.get(
        f"/api/v1/apps/kuaireport/dashboards/{saved['id']}/preview",
        headers={"X-Tenant-ID": "999"},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert "shared" not in preview.request.url.path
    assert set(seen) == {(TENANT, index) for index in range(1, 4)}
    metric = next(item for item in body["widgets_config"] if item["type"] == "metric")
    assert metric["result"]["data"] == [{"v": 1}]
    assert metric["result"]["total"] == 1
    assert metric["result"]["summary"] == {"v": 1}
    assert any(item["type"] == "clock" for item in body["widgets_config"])
    _assert_no_secret(body)
    paths = [getattr(route, "path", "") for route in client.app.routes]
    assert "/api/v1/apps/kuaireport/dashboards/{dashboard_id}/preview" in paths
    assert not any(path.endswith("/shared/preview") for path in paths)


@pytest.mark.asyncio
async def test_share_gate_logs_and_does_not_leak_password():
    store = share.MemoryShareStore()
    calls = []

    async def source(tenant_id, data_source_id):
        calls.append(tenant_id)
        return {"data": [{"ok": True}], "total": 1, "summary": {"ok": 1}}

    service = _service(store, execute_source=source)
    saved = await _save_dashboard(service, store)
    client = _client(service)
    issued = client.post(
        f"/api/v1/apps/kuaireport/dashboards/{saved['id']}/share",
        json={"expires_at": LATER.isoformat(), "password": PLAIN, "allow_ip_cidrs": ["10.0.0.0/8"]},
    )
    assert issued.status_code == 200
    issued_body = issued.json()
    _assert_no_secret(issued_body)
    assert issued_body["share_path"].startswith("/apps/kuaireport/dashboards/shared?token=")
    token = issued_body["share_path"].split("token=", 1)[1]
    row = store.dashboards[saved["id"]]
    assert row.share_password_hash != PLAIN
    assert row.share_password_hash.startswith("$pbkdf2-sha256$")
    assert len(row.share_password_hash) <= 128
    hashed = row.share_password_hash

    def open_with(password=PLAIN, ip="10.1.2.3", share_token=token):
        return client.get(
            "/api/v1/apps/kuaireport/dashboards/shared",
            params={"token": share_token},
            headers={"X-Share-Password": password, "X-Forwarded-For": ip, "X-Tenant-ID": "999"},
        )

    ok = open_with()
    assert ok.status_code == 200
    assert calls == [TENANT, TENANT, TENANT]
    assert ok.json()["widgets_config"]
    _assert_no_secret(ok.json(), hashed)

    before = len(store.logs)
    cases = [
        ("nope", "8.8.8.8", "password_mismatch"),
        (PLAIN, "8.8.8.8", "ip_denied"),
    ]
    for password, ip, reason in cases:
        denied = open_with(password=password, ip=ip)
        assert denied.status_code == 403
        assert denied.json()["detail"]["reason"] == reason
        _assert_no_secret(denied.json(), hashed)
        assert "widgets_config" not in denied.json()
    assert len(store.logs) == before + 2

    row.share_expires_at = PAST
    expired = open_with()
    assert expired.status_code == 403
    assert expired.json()["detail"]["reason"] == "expired"

    row.share_expires_at = LATER
    row.share_password_hash = None
    missing_hash = open_with()
    assert missing_hash.status_code == 403
    assert missing_hash.json()["detail"]["reason"] == "missing_password_hash"

    row.share_password_hash = hashed
    row.share_expires_at = None
    missing_expiry = open_with()
    assert missing_expiry.status_code == 403
    assert missing_expiry.json()["detail"]["reason"] == "missing_expiry"

    row.share_expires_at = LATER
    row.share_allow_ip_cidrs = []
    empty_list = open_with(ip="8.8.8.8")
    assert empty_list.status_code == 200

    row.share_allow_ip_cidrs = None
    empty_null = open_with(ip="1.1.1.1")
    assert empty_null.status_code == 200

    row.is_shared = False
    not_shared = open_with()
    assert not_shared.status_code == 403
    assert not_shared.json()["detail"]["reason"] == "not_shared"

    _assert_logs_clean(store, hashed)
    assert all(record.success for record in store.logs if record.detail == "ok")
    assert any(record.success is False and record.detail == "ip_denied" for record in store.logs)


@pytest.mark.asyncio
async def test_report_share_uses_same_gate_and_system_rows_stay_unshared():
    store = share.MemoryShareStore()
    calls = []

    async def report_exec(tenant_id, report_id, report_config):
        calls.append((tenant_id, report_id))
        return {"data": [{"code": "row"}], "total": 4, "summary": {"qty": 4}}

    service = _service(store, execute_report=report_exec)
    for index, code in enumerate(sorted(share.SYSTEM_REPORT_CODES), start=1):
        await store.add_report(
            share.ReportRecord(
                id=index,
                uuid=f"rep-{index}",
                tenant_id=TENANT,
                code=code,
                name=code,
                report_config={"data_source_id": 3},
                is_system=True,
                is_shared=False,
            )
        )
    flags = await service.system_share_flags(TENANT)
    assert flags == {code: False for code in share.SYSTEM_REPORT_CODES}
    assert "UPDATE" not in share.SYSTEM_SHARE_FLAG_SQL.upper()

    client = _client(service)
    blocked = client.get(
        "/api/v1/apps/kuaireport/reports/shared",
        params={"token": "not-issued"},
    )
    assert blocked.status_code == 404
    assert calls == []
    inv = next(row for row in store.reports.values() if row.code == "inv_ledger")

    issued = client.post(
        f"/api/v1/apps/kuaireport/reports/{inv.id}/share",
        json={"expires_at": LATER.isoformat(), "password": PLAIN},
    )
    assert issued.status_code == 200
    _assert_no_secret(issued.json())
    token = issued.json()["share_path"].split("token=", 1)[1]
    flags = await service.system_share_flags(TENANT)
    assert flags["inv_ledger"] is True
    assert sum(1 for value in flags.values() if value) == 1

    denied = client.get(
        "/api/v1/apps/kuaireport/reports/shared",
        params={"token": token},
        headers={"X-Forwarded-For": "10.0.0.8"},
    )
    assert denied.status_code == 403
    assert calls == []
    assert "data" not in denied.json()

    opened = client.get(
        "/api/v1/apps/kuaireport/reports/shared",
        params={"token": token},
        headers={"X-Share-Password": PLAIN, "X-Forwarded-For": "8.8.8.8", "X-Tenant-ID": "1"},
    )
    assert opened.status_code == 200
    body = opened.json()
    assert body["data"] == [{"code": "row"}]
    assert body["total"] == 4
    assert body["summary"] == {"qty": 4}
    assert calls == [(TENANT, inv.id)]
    _assert_no_secret(body, inv.share_password_hash or "")
    report_logs = [record for record in store.logs if record.resource_type == "report"]
    assert {record.detail for record in report_logs} >= {"password_mismatch", "ok"}
    _assert_logs_clean(store, inv.share_password_hash or "")


@pytest.mark.asyncio
async def test_file_preview_contract_and_log_failure_hides_payload():
    store = share.MemoryShareStore()
    seen = {}

    async def preview(file_uuid, tenant_id, size):
        seen["args"] = (file_uuid, tenant_id, size)
        if size == 0:
            return ""
        return f"/api/v1/core/files/{file_uuid}/download?token=preview"

    service = _service(store, preview_url=preview)
    saved = await _save_dashboard(service, store)
    client = _client(service)
    issued = client.post(
        f"/api/v1/apps/kuaireport/dashboards/{saved['id']}/share",
        json={"expires_at": LATER.isoformat(), "password": PLAIN},
    )
    token = issued.json()["share_path"].split("token=", 1)[1]
    opened = client.get(
        "/api/v1/apps/kuaireport/dashboards/shared",
        params={"token": token},
        headers={"X-Share-Password": PLAIN},
    )
    assert opened.status_code == 200
    cookie = opened.headers.get("set-cookie") or ""
    assert PLAIN not in cookie
    assert share.UNLOCK_COOKIE in cookie

    preview_res = client.get(
        "/api/v1/apps/kuaireport/dashboards/shared/file-preview",
        params={"token": token, "uuid": "file-1", "size": 64},
    )
    assert preview_res.status_code == 200
    body = preview_res.json()
    assert body["success"] is True
    assert body["preview_url"].startswith("/api/v1/core/files/file-1/")
    assert seen["args"] == ("file-1", TENANT, 64)
    _assert_no_secret(body, store.dashboards[saved["id"]].share_password_hash)

    failed = client.get(
        "/api/v1/apps/kuaireport/dashboards/shared/file-preview",
        params={"token": token, "uuid": "file-2"},
        headers={"X-Share-Password": "wrong-pass"},
    )
    assert failed.status_code == 200
    assert failed.json()["success"] is False
    assert "preview_url" not in failed.json()

    store.fail_logs = True
    hidden = client.get(
        "/api/v1/apps/kuaireport/dashboards/shared",
        params={"token": token},
        headers={"X-Share-Password": PLAIN},
    )
    assert hidden.status_code == 503
    assert "widgets_config" not in hidden.json()
    assert "preview_url" not in hidden.json()
    preview_hidden = client.get(
        "/api/v1/apps/kuaireport/dashboards/shared/file-preview",
        params={"token": token, "uuid": "file-1"},
    )
    assert preview_hidden.status_code == 503
    assert "preview_url" not in preview_hidden.json()


@pytest.mark.asyncio
async def test_save_appends_dashboard_version_in_the_save_transaction(monkeypatch):
    store = share.MemoryShareStore()
    inserted: list[tuple] = []

    async def run_in_transaction(work):
        return await work(object())

    store.run_in_transaction = run_in_transaction
    original = store.create_dashboard

    async def create_dashboard(**kwargs):
        row = await original(**kwargs)
        row.current_version = 1
        return row

    store.create_dashboard = create_dashboard

    async def fake_append(dist_store, tenant_id, dashboard_id, configs, version_no, user_id=None, note="save"):
        inserted.append((tenant_id, dashboard_id, version_no, note))
        return {"version_no": version_no}

    monkeypatch.setattr(
        "apps.kuaireport.slices.s149_distribution.append_dashboard_version",
        fake_append,
    )
    service = _service(store)
    saved = await _save_dashboard(service, store)
    assert inserted == [(TENANT, saved["id"], 1, "save")]


def test_slice_calls_version_insert_without_writing_sql():
    source = inspect.getsource(share)
    assert "append_dashboard_version" in source
    assert "INSERT INTO apps_kuaireport_dashboard_versions" not in source
    assert "apps_kuaireport_share_grants" not in source
    assert "apps_kuaireport_report_subscriptions" not in source
    route_paths = [getattr(route, "path", "") for route in share.router.routes]
    assert any(path.endswith("/dashboards/shared/file-preview") for path in route_paths)
    assert not any("rollback" in path or "subscription" in path or "grant" in path for path in route_paths)
