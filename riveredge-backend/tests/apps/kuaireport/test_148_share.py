"""spec 148：大屏保存与受控分享。"""

from __future__ import annotations

import asyncio
import inspect
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from apps.kuaireport.slices import s148_share as share
from infra.api.deps.deps import get_current_user
from infra.utils import client_ip as client_ip_mod

PLAIN = "share-plain-9f3a"
NOW = datetime(2026, 9, 28, 8, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(days=2)
PAST = NOW - timedelta(hours=1)
TENANT = 7

PERMISSION_DEPS = (
    share.DASHBOARD_DESIGN_DEP,
    share.DASHBOARD_DISPLAY_DEP,
    share.SHARE_MANAGE_DEP,
)


@pytest.fixture(autouse=True)
def _trust_testclient_proxy(monkeypatch):
    """TestClient 直连对端视为可信代理，XFF 用例才能走到转发头。"""
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "*")


def _widgets(file_uuid="file-1"):
    rows = []
    for index, widget_type in enumerate(share.WIDGET_TYPES, start=1):
        options = {"label": widget_type}
        if widget_type == "image":
            options["file_uuid"] = file_uuid
        rows.append(
            {
                "id": f"w{index}",
                "type": widget_type,
                "data_source_id": index,
                "refresh_seconds": 15 + index,
                "title": widget_type,
                "options": options,
            }
        )
    return rows


def _service(store, *, execute_source=None, execute_report=None, preview_url=None):
    async def source(tenant_id, data_source_id):
        if execute_source:
            return await execute_source(tenant_id, data_source_id)
        return {"data": [{"n": data_source_id}], "total": 1, "summary": {"n": data_source_id}}

    async def report_exec(tenant_id, report_id, report_config, page=None):
        if execute_report:
            return await execute_report(tenant_id, report_id, report_config, page)
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
    for dep in PERMISSION_DEPS:
        app.dependency_overrides[dep] = lambda: SimpleNamespace(tenant_id=TENANT)
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

    async def report_exec(tenant_id, report_id, report_config, page=None):
        calls.append((tenant_id, report_id, page))
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
    assert denied.json()["detail"]["reason"] == "password_required"
    assert denied.json()["detail"]["requires_password"] is True
    assert calls == []
    assert "data" not in denied.json()

    mismatch = client.get(
        "/api/v1/apps/kuaireport/reports/shared",
        params={"token": token},
        headers={"X-Share-Password": "not-it", "X-Forwarded-For": "10.0.0.8"},
    )
    assert mismatch.status_code == 403
    assert mismatch.json()["detail"]["reason"] == "password_mismatch"
    assert calls == []

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
    assert calls == [(TENANT, inv.id, None)]
    _assert_no_secret(body, inv.share_password_hash or "")
    report_logs = [record for record in store.logs if record.resource_type == "report"]
    assert {record.detail for record in report_logs} >= {
        "password_required",
        "password_mismatch",
        "ok",
    }
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

    # file_uuid 必须在该大屏组件引用集合内；遍历任意 uuid 不能签出预览 URL
    denied_uuid = client.get(
        "/api/v1/apps/kuaireport/dashboards/shared/file-preview",
        params={"token": token, "uuid": "file-other"},
        headers={"X-Share-Password": PLAIN},
    )
    assert denied_uuid.status_code == 200
    assert denied_uuid.json()["success"] is False
    assert denied_uuid.json()["message"] == "file_not_shared"
    assert seen["args"] == ("file-1", TENANT, 64)
    denied_logs = [
        record for record in store.logs if record.detail == "file_not_shared"
    ]
    assert denied_logs and denied_logs[-1].success is False

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
    assert "_conn_override" not in source
    route_paths = [getattr(route, "path", "") for route in share.router.routes]
    assert any(path.endswith("/dashboards/shared/file-preview") for path in route_paths)
    assert any(path == "/dashboards/{dashboard_id}/share" for path in route_paths)
    assert any(path == "/reports/{report_id}/share" for path in route_paths)
    assert not any("rollback" in path or "subscription" in path or "grant" in path for path in route_paths)


@pytest.mark.asyncio
async def test_sql_store_binds_conn_per_call_not_on_singleton(monkeypatch):
    """事务连接随每次调用传入，进程级单例不残留可变 conn 状态。"""
    store = share.SqlShareStore()
    conns = []

    class _FakeTx:
        def __init__(self, conn):
            self._conn = conn

        async def __aenter__(self):
            return self._conn

        async def __aexit__(self, *args):
            return False

    def fake_in_transaction(*args, **kwargs):
        conn = object()
        conns.append(conn)
        return _FakeTx(conn)

    monkeypatch.setattr("tortoise.transactions.in_transaction", fake_in_transaction)

    entered = asyncio.Event()
    seen = []

    async def work(conn):
        seen.append(conn)
        entered.set()
        await asyncio.wait_for(entered.wait(), 5)
        await asyncio.sleep(0)
        return conn

    first, second = await asyncio.gather(
        store.run_in_transaction(work), store.run_in_transaction(work)
    )
    assert first is not second
    assert set(seen) == {first, second}
    assert getattr(store, "_conn", None) is None
    assert not hasattr(store, "_conn_override")

    class _FakeConn:
        def __init__(self):
            self.calls = []

        async def execute_query_dict(self, sql, params):
            self.calls.append((sql, params))
            return []

        async def execute_query(self, sql, params):
            self.calls.append((sql, params))

    conn_a = _FakeConn()
    bound = store.with_conn(conn_a)
    assert bound is not store
    assert await bound.get_dashboard(TENANT, 123) is None
    assert len(conn_a.calls) == 1


@pytest.mark.asyncio
async def test_disable_share_clears_credentials_and_revokes_link():
    store = share.MemoryShareStore()
    service = _service(store)
    saved = await _save_dashboard(service, store)
    report = share.ReportRecord(
        id=88, uuid="rep-88", tenant_id=TENANT, code="rep-88", name="报表88"
    )
    await store.add_report(report)
    client = _client(service)

    issued = client.post(
        f"/api/v1/apps/kuaireport/dashboards/{saved['id']}/share",
        json={"expires_at": LATER.isoformat(), "password": PLAIN},
    )
    assert issued.status_code == 200
    token = issued.json()["share_path"].split("token=", 1)[1]

    closed = client.delete(f"/api/v1/apps/kuaireport/dashboards/{saved['id']}/share")
    assert closed.status_code == 200
    assert closed.json() == {"is_shared": False}
    row = store.dashboards[saved["id"]]
    assert row.is_shared is False
    assert row.share_token is None
    assert row.share_expires_at is None
    assert row.share_password_hash is None
    assert row.share_allow_ip_cidrs is None

    reopened = client.get(
        "/api/v1/apps/kuaireport/dashboards/shared",
        params={"token": token},
        headers={"X-Share-Password": PLAIN},
    )
    assert reopened.status_code == 404
    assert reopened.json()["detail"]["reason"] == "missing"

    issued_report = client.post(
        f"/api/v1/apps/kuaireport/reports/{report.id}/share",
        json={"expires_at": LATER.isoformat(), "password": PLAIN},
    )
    report_token = issued_report.json()["share_path"].split("token=", 1)[1]
    closed_report = client.delete(
        f"/api/v1/apps/kuaireport/reports/{report.id}/share"
    )
    assert closed_report.status_code == 200
    assert closed_report.json() == {"is_shared": False}
    reopened_report = client.get(
        "/api/v1/apps/kuaireport/reports/shared",
        params={"token": report_token},
        headers={"X-Share-Password": PLAIN},
    )
    assert reopened_report.status_code == 404
    assert reopened_report.json()["detail"]["code"] == "SHARE_ACCESS_DENIED"

    missing = client.delete("/api/v1/apps/kuaireport/reports/999999/share")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_enable_share_rejects_past_expiry_and_bad_inputs():
    store = share.MemoryShareStore()
    service = _service(store)
    saved = await _save_dashboard(service, store)
    client = _client(service)
    url = f"/api/v1/apps/kuaireport/dashboards/{saved['id']}/share"

    past = client.post(
        url, json={"expires_at": PAST.isoformat(), "password": PLAIN}
    )
    assert past.status_code == 400

    long_password = client.post(
        url, json={"expires_at": LATER.isoformat(), "password": "x" * 129}
    )
    assert long_password.status_code == 400

    bad_cidr = client.post(
        url,
        json={
            "expires_at": LATER.isoformat(),
            "password": PLAIN,
            "allow_ip_cidrs": ["not-a-cidr"],
        },
    )
    assert bad_cidr.status_code == 400

    too_many = client.post(
        url,
        json={
            "expires_at": LATER.isoformat(),
            "password": PLAIN,
            "allow_ip_cidrs": [f"10.0.{i // 256}.{i % 256}/32" for i in range(51)],
        },
    )
    assert too_many.status_code == 400

    ok = client.post(
        url,
        json={
            "expires_at": LATER.isoformat(),
            "password": PLAIN,
            "allow_ip_cidrs": ["10.0.0.0/8", "1.2.3.4"],
        },
    )
    assert ok.status_code == 200
    assert store.dashboards[saved["id"]].share_allow_ip_cidrs == [
        "10.0.0.0/8",
        "1.2.3.4",
    ]


@pytest.mark.asyncio
async def test_shared_report_forwards_limit_and_offset_with_cap():
    store = share.MemoryShareStore()
    pages = []

    async def report_exec(tenant_id, report_id, report_config, page=None):
        pages.append(page)
        return {"data": [], "total": 0, "summary": {}}

    service = _service(store, execute_report=report_exec)
    report = share.ReportRecord(
        id=91, uuid="rep-91", tenant_id=TENANT, code="rep-91", name="报表91"
    )
    await store.add_report(report)
    client = _client(service)
    issued = client.post(
        f"/api/v1/apps/kuaireport/reports/{report.id}/share",
        json={"expires_at": LATER.isoformat(), "password": PLAIN},
    )
    token = issued.json()["share_path"].split("token=", 1)[1]
    headers = {"X-Share-Password": PLAIN}

    paged = client.get(
        "/api/v1/apps/kuaireport/reports/shared",
        params={"token": token, "limit": 10, "offset": 30},
        headers=headers,
    )
    assert paged.status_code == 200
    assert pages[-1] == {"limit": 10, "offset": 30}

    capped = client.get(
        "/api/v1/apps/kuaireport/reports/shared",
        params={"token": token, "limit": 9999},
        headers=headers,
    )
    assert capped.status_code == 200
    assert pages[-1] == {"limit": 500}

    default_page = client.get(
        "/api/v1/apps/kuaireport/reports/shared",
        params={"token": token},
        headers=headers,
    )
    assert default_page.status_code == 200
    assert pages[-1] is None


@pytest.mark.asyncio
async def test_dashboard_list_endpoint_returns_tenant_summary():
    store = share.MemoryShareStore()
    service = _service(store)
    saved = await _save_dashboard(service, store)
    other = share.DashboardRecord(
        id=999, uuid="d-999", tenant_id=TENANT + 1, code="other", name="别租户"
    )
    store.dashboards[other.id] = other
    client = _client(service)

    listed = client.get("/api/v1/apps/kuaireport/dashboards")
    assert listed.status_code == 200
    rows = listed.json()
    assert [row["id"] for row in rows] == [saved["id"]]
    row = rows[0]
    assert row["code"] == "board-1"
    assert row["name"] == "车间大屏"
    assert row["status"] == "DRAFT"
    assert row["is_shared"] is False
    assert row["updated_at"]
    assert "share_token" not in row


@pytest.mark.asyncio
async def test_decorative_widgets_source_optional_but_must_be_registered():
    store = share.MemoryShareStore()
    store.data_source_ids = {1, 2, 3}
    service = _service(store)
    widgets = [
        {"type": "metric", "data_source_id": 1, "refresh_seconds": 5},
        {"type": "clock", "refresh_seconds": 5},
        {
            "type": "image",
            "options": {"file_uuid": "f-9"},
            "refresh_seconds": 5,
        },
    ]
    saved = await service.save_dashboard(
        tenant_id=TENANT,
        dashboard_id=None,
        code="board-decor",
        name="装饰",
        layout_config=None,
        widgets_config=widgets,
        theme_config=None,
        tv_config=None,
    )
    clock = next(w for w in saved["widgets_config"] if w["type"] == "clock")
    assert "data_source_id" not in clock

    base = dict(
        tenant_id=TENANT,
        dashboard_id=None,
        name="坏",
        layout_config=None,
        theme_config=None,
        tv_config=None,
    )
    with pytest.raises(ValueError):
        await service.save_dashboard(
            code="b1",
            widgets_config=[
                {"type": "clock", "data_source_id": 999, "refresh_seconds": 5}
            ],
            **base,
        )
    with pytest.raises(ValueError):
        await service.save_dashboard(
            code="b2",
            widgets_config=[{"type": "metric", "refresh_seconds": 5}],
            **base,
        )
    with pytest.raises(ValueError):
        await service.save_dashboard(
            code="b3",
            widgets_config=[
                {"type": "metric", "data_source_id": 999, "refresh_seconds": 5}
            ],
            **base,
        )


def test_create_dashboard_code_conflict_returns_4xx():
    store = share.MemoryShareStore()
    service = _service(store)
    client = _client(service)
    body = {
        "code": "dup-code",
        "name": "一",
        "widgets_config": [
            {"type": "clock", "refresh_seconds": 5}
        ],
    }
    first = client.post("/api/v1/apps/kuaireport/dashboards", json=body)
    assert first.status_code == 200
    second = client.post("/api/v1/apps/kuaireport/dashboards", json=body)
    assert second.status_code == 400
    assert "already exists" in second.json()["detail"]


def _fake_request(headers=None, client_host="9.9.9.9", scheme="http") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [
            (key.lower().encode(), value.encode())
            for key, value in (headers or {}).items()
        ],
        "client": (client_host, 50000),
        "server": ("testserver", 80),
        "scheme": scheme,
    }
    return Request(scope)


def test_forwarded_headers_only_trusted_with_configured_proxies(monkeypatch):
    for key in ("TRUSTED_PROXY_IPS", "FORWARDED_ALLOW_IPS", "TRUSTED_PROXIES"):
        monkeypatch.delenv(key, raising=False)

    req = _fake_request({"X-Forwarded-For": "1.2.3.4"}, client_host="9.9.9.9")
    assert client_ip_mod.get_client_ip(req) == "9.9.9.9"

    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.0/8")
    assert client_ip_mod.get_client_ip(req) == "9.9.9.9"

    monkeypatch.setenv("TRUSTED_PROXY_IPS", "9.9.9.0/24")
    assert client_ip_mod.get_client_ip(req) == "1.2.3.4"

    https_via_proxy = _fake_request(
        {"X-Forwarded-Proto": "https"}, client_host="9.9.9.9"
    )
    assert client_ip_mod.request_is_https(https_via_proxy) is True

    monkeypatch.delenv("TRUSTED_PROXY_IPS")
    assert client_ip_mod.request_is_https(https_via_proxy) is False
    direct_https = _fake_request({}, client_host="9.9.9.9", scheme="https")
    assert client_ip_mod.request_is_https(direct_https) is True
