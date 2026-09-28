"""spec 146：报表中心列表、十张系统报表种入、后端全量 Excel。"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

from apps.kuaireport.slices import s146_center as center
from infra.domain.tenant_context import TenantContextError, clear_tenant_context, set_current_tenant_id

TENANT = 9
FRONTEND_REPORTS = (
    Path(__file__).resolve().parents[4]
    / "riveredge-frontend"
    / "src"
    / "apps"
    / "kuaireport"
    / "pages"
    / "reports"
)


class MemoryStore:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self._pending: list[dict] | None = None
        self.fail_on_insert: int | None = None
        self.inserts = 0
        self.next_id = 1
        # 模拟本租户已登记的 dataset 数据源 uuid；None 表示没有可用数据集源
        self.dataset_uuid: str | None = None
        self.binds = 0

    async def registered_dataset_uuid(self, tenant_id):
        return self.dataset_uuid

    async def bind_data_source(self, tenant_id, report_id, source_uuid):
        self.binds += 1
        for bucket in (self._pending or [], self.rows):
            for row in bucket:
                if row["tenant_id"] == tenant_id and row["id"] == report_id:
                    config = dict(row.get("report_config") or {})
                    extra = dict(config.get("extra") or {})
                    extra["data_source_uuid"] = source_uuid
                    config["extra"] = extra
                    row["report_config"] = config
                    return center._public_row(row)
        return None

    def _visible(self) -> list[dict]:
        if self._pending is None:
            return list(self.rows)
        return [*self.rows, *self._pending]

    async def list_rows(self, tenant_id, status, category, classify):
        rows = []
        for row in self._visible():
            if row["tenant_id"] != tenant_id:
                continue
            if status is not None and row["status"] != status:
                continue
            if category is not None and row["category"] != category:
                continue
            if classify is not None and row["classify"] != classify:
                continue
            rows.append(center._public_row(row))
        rows.sort(key=lambda item: (item["classify"], item["code"]))
        return rows

    async def get_row(self, tenant_id, report_id):
        for row in self._visible():
            if row["tenant_id"] == tenant_id and row["id"] == report_id:
                return center._public_row(row)
        return None

    async def existing_codes(self, tenant_id, codes):
        wanted = set(codes)
        return {
            row["code"]
            for row in self._visible()
            if row["tenant_id"] == tenant_id and row["code"] in wanted
        }

    async def set_status(self, tenant_id, report_id, status):
        for bucket in (self._pending or [], self.rows):
            for row in bucket:
                if row["tenant_id"] == tenant_id and row["id"] == report_id:
                    row["status"] = status
                    return

    async def insert_system_report(self, row):
        self.inserts += 1
        if self.fail_on_insert is not None and self.inserts == self.fail_on_insert:
            raise RuntimeError("seed failed")
        stored = dict(row)
        stored["id"] = self.next_id
        self.next_id += 1
        assert self._pending is not None
        self._pending.append(stored)


@asynccontextmanager
async def _open(store: MemoryStore):
    store._pending = []
    try:
        yield store
    except Exception:
        store._pending = None
        raise
    else:
        store.rows.extend(store._pending)
        store._pending = None


@pytest.fixture
def store(monkeypatch):
    memory = MemoryStore()

    @asynccontextmanager
    async def report_center_transaction():
        async with _open(memory) as current:
            yield current

    monkeypatch.setattr(center, "report_center_transaction", report_center_transaction)
    set_current_tenant_id(TENANT)
    try:
        yield memory
    finally:
        clear_tenant_context()


def test_system_report_codes_match_spec():
    codes = [code for code, _name, _classify in center.SYSTEM_REPORTS]
    assert codes == [
        "inv_ledger",
        "wo_tracking",
        "qc_pass_rate",
        "perf_stats",
        "node_timeliness",
        "process_efficiency",
        "sales_trace",
        "purchase_trace",
        "material_trace",
        "biz_overview",
    ]
    names = {code: name for code, name, _classify in center.SYSTEM_REPORTS}
    assert names["sales_trace"] == "销售全链路追踪"
    assert names["purchase_trace"] == "采购全链路追踪"
    assert center.FORBIDDEN_REPORT_NAMES.isdisjoint(names.values())


@pytest.mark.asyncio
async def test_no_tenant_does_not_read_reports():
    clear_tenant_context()
    with pytest.raises(TenantContextError):
        await center.list_reports()


@pytest.mark.asyncio
async def test_seed_is_idempotent_and_defaults(store: MemoryStore):
    inserted = await center.seed_system_reports()
    assert inserted == [code for code, _name, _classify in center.SYSTEM_REPORTS]
    assert await center.seed_system_reports() == []
    rows = await center.list_reports()
    assert len(rows) == 10
    by_code = {row["code"]: row for row in rows}
    assert by_code["sales_trace"]["classify"] == "销售"
    assert by_code["purchase_trace"]["classify"] == "采购"
    for code, _name, classify in center.SYSTEM_REPORTS:
        row = by_code[code]
        assert row["category"] == "system"
        assert row["is_system"] is True
        assert row["status"] == "DRAFT"
        assert row["is_shared"] is False
        assert row["name"] not in center.FORBIDDEN_REPORT_NAMES
        assert row["classify"] == classify
        blob = json.dumps(row["report_config"], ensure_ascii=False).lower()
        assert "select " not in blob
        assert "query_config" not in blob
        assert "data_source_id" not in row["report_config"]
        assert row["report_config"]["extra"]["data_source_uuid"] is None
        assert "dataset_uuid" not in row["report_config"]
        assert row["report_config"]["fields"] == []
    assert await center.list_reports(category="custom") == []


@pytest.mark.asyncio
async def test_seed_rolls_back_when_insert_fails(store: MemoryStore):
    store.fail_on_insert = 4
    with pytest.raises(RuntimeError, match="seed failed"):
        await center.seed_system_reports()
    assert store.rows == []
    store.fail_on_insert = None
    store.inserts = 0
    inserted = await center.seed_system_reports()
    assert len(inserted) == 10


@pytest.mark.asyncio
async def test_list_filters_status_category_and_classify(store: MemoryStore):
    await center.seed_system_reports()
    store.rows.append(
        {
            "id": 100,
            "uuid": "custom-1",
            "tenant_id": TENANT,
            "code": "my_sheet",
            "name": "我的报表",
            "category": "custom",
            "classify": "销售",
            "is_system": False,
            "status": "NOT_DRAFT_SAMPLE",
            "is_shared": False,
            "report_config": {"dataset_code": "my_sheet", "fields": []},
        }
    )
    drafts = await center.list_reports(status="DRAFT")
    assert len(drafts) == 10
    assert all(row["status"] == "DRAFT" for row in drafts)
    other = await center.list_reports(status="NOT_DRAFT_SAMPLE")
    assert [row["code"] for row in other] == ["my_sheet"]
    custom = await center.list_reports(category="custom")
    assert [row["code"] for row in custom] == ["my_sheet"]
    sales = await center.list_reports(classify="销售")
    assert {row["code"] for row in sales} == {"sales_trace", "my_sheet"}
    with pytest.raises(center.ValidationError):
        await center.list_reports(category="analysis")


@pytest.mark.asyncio
async def test_full_excel_pages_through_execute_report(store: MemoryStore, monkeypatch):
    await center.seed_system_reports()
    report = next(row for row in store.rows if row["code"] == "inv_ledger")
    calls: list[dict] = []

    class _ExecutePage:
        def __init__(self, data, total, summary):
            self.data = data
            self.total = total
            self.summary = summary

        def model_dump(self):
            return {"data": self.data, "total": self.total, "summary": self.summary}

    async def fake_execute(tenant_id, report_id, filters):
        assert tenant_id == TENANT
        assert report_id == report["id"]
        calls.append(dict(filters))
        all_rows = [
            {"qty": index, "note": f"n{index}", "password": "hidden", "file": r"C:\secret\a.xlsx"}
            for index in range(5)
        ]
        offset = filters["offset"]
        limit = filters["limit"]
        return _ExecutePage(
            all_rows[offset : offset + limit],
            5,
            {"qty": 10, "token": "hidden-token"},
        )

    monkeypatch.setattr(center, "FULL_EXPORT_PAGE_SIZE", 2)
    monkeypatch.setattr(center, "resolve_execute_report", lambda: fake_execute)
    content, filename = await center.export_full_excel(
        report["id"],
        {"warehouse": "A", "limit": 1, "offset": 99},
    )
    assert filename == "inv_ledger.xlsx"
    assert content[:2] == b"PK"
    assert [item["offset"] for item in calls] == [0, 2, 4]
    assert all(item["limit"] == 2 and item["warehouse"] == "A" for item in calls)
    assert all("offset" in item and item["offset"] != 99 for item in calls)
    sheet = load_workbook(BytesIO(content)).active
    headers = [cell.value for cell in next(sheet.iter_rows(min_row=1, max_row=1))]
    assert "qty" in headers and "note" in headers
    assert "password" not in headers
    qty_at = headers.index("qty")
    note_at = headers.index("note")
    data_rows = list(sheet.iter_rows(min_row=2, max_row=6))
    assert [row[qty_at].value for row in data_rows] == list(range(5))
    assert [row[note_at].value for row in data_rows] == [f"n{index}" for index in range(5)]
    flat = [cell.value for row in sheet.iter_rows() for cell in row]
    assert "hidden" not in flat
    assert "hidden-token" not in flat
    assert r"C:\secret\a.xlsx" not in flat
    assert "合计" in flat
    assert "qty" in flat


@pytest.mark.asyncio
async def test_publish_writes_published_status(store: MemoryStore):
    await center.seed_system_reports("source-uuid-1")
    report = next(row for row in store.rows if row["code"] == "inv_ledger")
    assert report["report_config"]["extra"]["data_source_uuid"] == "source-uuid-1"
    published = await center.publish_report(report["id"])
    assert published["status"] == "PUBLISHED"
    assert published["status"] == center.STATUS_PUBLISHED


@pytest.mark.asyncio
async def test_lifecycle_seed_skips_without_tenant_context():
    clear_tenant_context()
    assert await center.seed_system_reports_on_lifecycle(TENANT) == []


@pytest.mark.asyncio
async def test_list_rebinds_unbound_system_reports(store: MemoryStore):
    """种入时无数据源的空绑定，在列表路径幂等回绑本租户第一条 dataset 源。"""
    await center.seed_system_reports()
    assert all(
        row["report_config"]["extra"]["data_source_uuid"] is None
        for row in store.rows
    )
    store.dataset_uuid = "ds-uuid-1"
    rows = await center.list_reports()
    assert len(rows) == 10
    assert all(
        row["report_config"]["extra"]["data_source_uuid"] == "ds-uuid-1"
        for row in rows
    )
    assert store.binds == 10
    # 已绑定的行不再重复回写
    assert (await center.list_reports()) == rows
    assert store.binds == 10


@pytest.mark.asyncio
async def test_list_keeps_unbound_when_no_dataset_source(store: MemoryStore):
    await center.seed_system_reports()
    rows = await center.list_reports()
    assert all(
        row["report_config"]["extra"]["data_source_uuid"] is None
        for row in rows
    )
    assert store.binds == 0


@pytest.mark.asyncio
async def test_full_excel_pages_until_short_page_even_when_total_lies(
    store: MemoryStore, monkeypatch
):
    """total 不可信时（上报恒 0 或夸大）仍翻页到短页为止，保证全量导出完整。"""
    await center.seed_system_reports()
    report = next(row for row in store.rows if row["code"] == "inv_ledger")
    calls: list[int] = []

    class _Page:
        def __init__(self, data):
            self.data = data
            self.total = 0  # 上游 total 失真场景
            self.summary = {}

        def model_dump(self):
            return {"data": self.data, "total": self.total, "summary": self.summary}

    async def fake_execute(tenant_id, report_id, filters):
        calls.append(filters["offset"])
        all_rows = [{"qty": index} for index in range(5)]
        return _Page(all_rows[filters["offset"] : filters["offset"] + filters["limit"]])

    monkeypatch.setattr(center, "FULL_EXPORT_PAGE_SIZE", 2)
    monkeypatch.setattr(center, "resolve_execute_report", lambda: fake_execute)
    content, _filename = await center.export_full_excel(report["id"], {})
    assert calls == [0, 2, 4]
    sheet = load_workbook(BytesIO(content)).active
    values = [row[0].value for row in sheet.iter_rows(min_row=2)]
    assert values == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_full_excel_stops_on_exact_page_boundary(
    store: MemoryStore, monkeypatch
):
    await center.seed_system_reports()
    report = next(row for row in store.rows if row["code"] == "inv_ledger")

    class _Page:
        def __init__(self, data):
            self.data = data
            self.total = 4
            self.summary = {}

    async def fake_execute(tenant_id, report_id, filters):
        all_rows = [{"qty": index} for index in range(4)]
        return _Page(all_rows[filters["offset"] : filters["offset"] + filters["limit"]])

    monkeypatch.setattr(center, "FULL_EXPORT_PAGE_SIZE", 2)
    monkeypatch.setattr(center, "resolve_execute_report", lambda: fake_execute)
    content, _ = await center.export_full_excel(report["id"], {})
    sheet = load_workbook(BytesIO(content)).active
    assert [row[0].value for row in sheet.iter_rows(min_row=2)] == [0, 1, 2, 3]


def test_safe_filename_strips_quotes_crlf_and_non_ascii():
    assert center._safe_filename("inv_ledger") == "inv_ledger.xlsx"
    name = center._safe_filename('a"b\r\nc:\\报表.xlsx')
    assert '"' not in name and "\r" not in name and "\n" not in name
    assert name.isascii() and name.endswith(".xlsx")
    assert center._safe_filename("") == "report.xlsx"
    assert center._safe_filename("报表") == "report.xlsx"


def test_safe_cell_blocks_excel_formula_injection():
    assert center._safe_cell("=SUM(A1:A9)") == "'=SUM(A1:A9)"
    assert center._safe_cell("+1+1") == "'+1+1"
    assert center._safe_cell("-2") == "'-2"
    assert center._safe_cell("@cmd") == "'@cmd"
    assert center._safe_cell("normal") == "normal"
    assert center._safe_cell(42) == 42
    # 密钥/路径掩码优先级不变
    assert center._safe_cell("password=abc") is None


def _http_app(store: MemoryStore, monkeypatch, *, authed: bool = True):
    """带真实路由与依赖的 ASGI app；认证、权限、数据源查询全部打桩。"""
    from types import SimpleNamespace

    from fastapi import FastAPI

    from apps.kuaireport.api.router import router as api_router

    app = FastAPI()
    app.include_router(api_router)
    if authed:
        user = SimpleNamespace(
            id=1, tenant_id=TENANT, is_infra_admin=False, is_tenant_admin=False
        )
        from infra.api.deps import deps as soil_deps

        app.dependency_overrides[soil_deps.get_current_user] = lambda: user

        def _tenant() -> int:
            set_current_tenant_id(TENANT)
            return TENANT

        from core.api.deps import deps as core_deps

        app.dependency_overrides[core_deps.get_current_tenant] = _tenant

        from core.services.authorization.access_control_service import (
            AccessControlService,
        )

        async def _allow(*args, **kwargs):
            return SimpleNamespace(allowed=True, reason="test")

        monkeypatch.setattr(AccessControlService, "check_access", _allow)
    return app


@pytest.mark.asyncio
async def test_s146_endpoints_require_authentication(store: MemoryStore):
    import httpx

    app = _http_app(store, None, authed=False)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://fixture"
    ) as client:
        assert (await client.get("/reports")).status_code == 401
        assert (await client.get("/reports/1")).status_code == 401
        assert (await client.post("/reports/1/publish")).status_code == 401
        assert (
            await client.post("/reports/1/excel", json={"filters": {}})
        ).status_code == 401


@pytest.mark.asyncio
async def test_s146_endpoints_route_with_tenant_context(
    store: MemoryStore, monkeypatch
):
    """带租户依赖时四端点可路由到服务层，不再恒 500。"""
    import httpx

    await center.seed_system_reports()
    app = _http_app(store, monkeypatch)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://fixture"
    ) as client:
        listed = await client.get("/reports")
        assert listed.status_code == 200
        assert len(listed.json()) == 10
        report_id = next(row["id"] for row in store.rows if row["code"] == "inv_ledger")
        detail = await client.get(f"/reports/{report_id}")
        assert detail.status_code == 200
        assert detail.json()["code"] == "inv_ledger"
        published = await client.post(f"/reports/{report_id}/publish")
        assert published.status_code == 200
        assert published.json()["status"] == "PUBLISHED"

        class _Page:
            def __init__(self):
                self.data = [{"qty": 1}]
                self.total = 1
                self.summary = {"qty": 1}

        async def fake_execute(tenant_id, rid, filters):
            assert tenant_id == TENANT
            return _Page()

        monkeypatch.setattr(center, "resolve_execute_report", lambda: fake_execute)
        exported = await client.post(f"/reports/{report_id}/excel", json={"filters": {}})
        assert exported.status_code == 200
        assert exported.content[:2] == b"PK"
        disposition = exported.headers["content-disposition"]
        assert "inv_ledger.xlsx" in disposition


def test_reports_shared_route_not_shadowed_by_report_id():
    """GET /reports/shared 必须落到 s148 的分享路由，不被 /reports/{report_id} 吞掉。"""
    from starlette.routing import Match

    from apps.kuaireport.api.router import router

    def first_match(path: str, method: str = "GET"):
        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "query_string": b"",
            "path_params": {},
            "route_path": path,
        }
        for route in router.routes:
            match, _child = route.matches(scope)
            if match == Match.FULL:
                return getattr(route, "path", "")
        return None

    assert first_match("/reports/shared") == "/reports/shared"
    assert first_match("/reports/42") == "/reports/{report_id:int}"
    assert first_match("/reports/abc") != "/reports/{report_id:int}"


def test_slice_does_not_implement_a_second_executor():
    source = Path(center.__file__).read_text(encoding="utf-8")
    assert "def execute_report" not in source
    assert "core_datasets" not in source
    assert "useUniReportExport" not in source
    assert "exportDomainReport" not in source


def test_preview_page_uses_unireport_not_browser_export():
    preview = (FRONTEND_REPORTS / "preview.tsx").read_text(encoding="utf-8")
    assert "UniReport" in preview
    assert 'mode="config"' in preview
    assert "showPrintButton" in preview
    assert "showExportButton={false}" in preview
    assert "useUniReportExport" not in preview
    assert "exportDomainReport" not in preview
    joined = "\n".join(path.read_text(encoding="utf-8") for path in FRONTEND_REPORTS.glob("*.tsx"))
    assert "效能中心" not in joined
    assert "ReportSharedView" not in joined
    assert "DashboardSharedView" not in joined
