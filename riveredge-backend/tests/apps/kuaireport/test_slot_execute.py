"""spec 145：槽位、数据源登记、executeReport 契约。"""

import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from tortoise import Tortoise

from apps.kuaireport.models.report import KuaireportReport
from apps.kuaireport.schemas.data_source import DataSourceCreate
from apps.kuaireport.services import data_source_service
from apps.kuaireport.services.execute_service import execute_report
from core.schemas.dataset import ExecuteQueryResponse
from infra.domain.tenant_context import clear_tenant_context, set_current_tenant_id
from infra.exceptions.exceptions import NotFoundError, TenantError, ValidationError

REPO = Path(__file__).resolve().parents[4]


@pytest_asyncio.fixture
async def db():
    clear_tenant_context()
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={
            "models": [
                "apps.kuaireport.models.data_source",
                "apps.kuaireport.models.report",
            ]
        },
    )
    await Tortoise.generate_schemas()
    try:
        yield
    finally:
        clear_tenant_context()
        await Tortoise.close_connections()


def _report_config(source_uuid: str, **extra) -> dict:
    config = {
        "page_size": 20,
        "fields": [
            {"field": "name", "label": "名称"},
            {"field": "qty", "label": "数量", "format": "number"},
        ],
        "filters": [
            {"field": "name", "label": "名称", "operator": "eq"},
            {"field": "biz_date", "label": "日期", "operator": "between"},
        ],
        "extra": {
            "data_source_uuid": source_uuid,
            "uni_report": {"summaryFields": ["qty"]},
        },
    }
    config.update(extra)
    return config


@pytest.mark.asyncio
async def test_data_source_types_and_http_address(db):
    set_current_tenant_id(1)
    static_row = await data_source_service.create_data_source(
        1,
        DataSourceCreate(name="静态", type="static", config={"rows": [{"name": "a", "qty": 1}]}),
    )
    assert static_row.type == "static"
    assert "query_config" not in (static_row.config or {})
    assert "sql" not in (static_row.config or {})

    dataset_row = await data_source_service.create_data_source(
        1,
        DataSourceCreate(
            name="数据集",
            type="dataset",
            config={
                "dataset_uuid": "11111111-1111-1111-1111-111111111111",
                "display_name": "库存",
            },
        ),
    )
    assert dataset_row.config == {
        "dataset_uuid": "11111111-1111-1111-1111-111111111111",
        "display_name": "库存",
    }

    http_row = await data_source_service.create_data_source(
        1,
        DataSourceCreate(name="HTTP", type="http", config={"url": "https://tenant.example/feed"}),
    )
    assert http_row.config == {"url": "https://tenant.example/feed"}

    with pytest.raises(ValidationError):
        await data_source_service.create_data_source(
            1, DataSourceCreate(name="坏类型", type="sql", config={})
        )
    with pytest.raises(ValidationError):
        await data_source_service.create_data_source(
            1,
            DataSourceCreate(
                name="带SQL",
                type="dataset",
                config={
                    "dataset_uuid": "11111111-1111-1111-1111-111111111111",
                    "query_config": {"sql": "select 1"},
                },
            ),
        )

    set_current_tenant_id(2)
    with pytest.raises(NotFoundError):
        await data_source_service.get_data_source(2, http_row.id)


@pytest.mark.asyncio
async def test_static_execute_page_filter_and_summary(db):
    set_current_tenant_id(1)
    source = await data_source_service.create_data_source(
        1,
        DataSourceCreate(
            name="台账",
            type="static",
            config={
                "rows": [
                    {"name": "a", "qty": 1, "biz_date": "2026-01-01"},
                    {"name": "a", "qty": 2, "biz_date": "2026-02-01"},
                    {"name": "b", "qty": 9, "biz_date": "2026-02-01"},
                ]
            },
        ),
    )
    report = await KuaireportReport.create(
        tenant_id=1,
        code="static_demo",
        name="静态账",
        report_config=_report_config(source.uuid),
    )
    result = await execute_report(
        1,
        report.id,
        {
            "name": "a",
            "biz_date_start": "2026-01-15",
            "biz_date_end": "2026-02-15",
            "limit": 1,
            "offset": 0,
        },
    )
    assert result.success is True
    assert result.total == 1
    assert result.data == [{"name": "a", "qty": 2}]
    assert result.summary == {"qty": 2}
    assert "select" not in str(report.report_config).lower()


@pytest.mark.asyncio
async def test_static_summary_uses_filtered_rows_not_only_page(db):
    set_current_tenant_id(1)
    source = await data_source_service.create_data_source(
        1,
        DataSourceCreate(
            name="合计",
            type="static",
            config={"rows": [{"name": "a", "qty": 1}, {"name": "a", "qty": 2}, {"name": "a", "qty": 3}]},
        ),
    )
    report = await KuaireportReport.create(
        tenant_id=1,
        code="sum_demo",
        name="合计",
        report_config=_report_config(source.uuid),
    )
    result = await execute_report(1, report.id, {"name": "a", "limit": 1, "offset": 0})
    assert result.data == [{"name": "a", "qty": 1}]
    assert result.total == 3
    assert result.summary == {"qty": 6}


@pytest.mark.asyncio
async def test_dataset_calls_existing_executor_without_summary_field(db):
    assert "summary" not in ExecuteQueryResponse.model_fields

    set_current_tenant_id(1)
    source = await data_source_service.create_data_source(
        1,
        DataSourceCreate(
            name="数据集",
            type="dataset",
            config={"dataset_uuid": "22222222-2222-2222-2222-222222222222"},
        ),
    )
    report = await KuaireportReport.create(
        tenant_id=1,
        code="ds_demo",
        name="数据集账",
        report_config=_report_config(source.uuid),
    )
    captured: dict = {}

    async def fake_load(dataset_uuid: str):
        return SimpleNamespace(query_type="sql", uuid=dataset_uuid)

    async def fake_run(tenant_id: int, dataset_uuid: str, request):
        captured["tenant_id"] = tenant_id
        captured["dataset_uuid"] = dataset_uuid
        captured["request"] = request
        return SimpleNamespace(success=True, data=[{"name": "a", "qty": 1}, {"name": "a", "qty": 4}], total=9)

    with (
        patch("apps.kuaireport.services.execute_service.load_dataset", fake_load),
        patch("apps.kuaireport.services.execute_service.run_dataset_query", fake_run),
    ):
        result = await execute_report(
            1,
            str(report.uuid),
            {"name": "a", "limit": 2, "offset": 0},
        )

    request = captured["request"]
    assert captured["tenant_id"] == 1
    assert request.parameters == {"name": "a"}
    assert request.limit == 2
    assert request.offset == 0
    assert request.query_config is None
    assert result.data == [{"name": "a", "qty": 1}, {"name": "a", "qty": 4}]
    assert result.total == 9
    assert result.summary == {"qty": 5}


@pytest.mark.asyncio
async def test_sql_write_dataset_is_not_executed(db):
    set_current_tenant_id(1)
    source = await data_source_service.create_data_source(
        1,
        DataSourceCreate(
            name="写入集",
            type="dataset",
            config={"dataset_uuid": "33333333-3333-3333-3333-333333333333"},
        ),
    )
    report = await KuaireportReport.create(
        tenant_id=1,
        code="write_demo",
        name="不绑定写入",
        report_config=_report_config(source.uuid),
    )
    runner = AsyncMock()
    with (
        patch(
            "apps.kuaireport.services.execute_service.load_dataset",
            AsyncMock(return_value=SimpleNamespace(query_type="sql_write")),
        ),
        patch("apps.kuaireport.services.execute_service.run_dataset_query", runner),
    ):
        with pytest.raises(ValidationError):
            await execute_report(1, report.id, {"limit": 10, "offset": 0})
    runner.assert_not_called()


@pytest.mark.asyncio
async def test_http_rejects_unregistered_address(db):
    set_current_tenant_id(1)
    source = await data_source_service.create_data_source(
        1,
        DataSourceCreate(name="HTTP", type="http", config={"url": "https://tenant.example/feed"}),
    )
    report = await KuaireportReport.create(
        tenant_id=1,
        code="http_demo",
        name="HTTP账",
        report_config=_report_config(source.uuid),
    )
    fetched: list[str] = []

    async def http_get(url: str):
        fetched.append(url)
        return [{"name": "a", "qty": 3}]

    result = await execute_report(1, report.id, {"limit": 20, "offset": 0}, http_get=http_get)
    assert fetched == ["https://tenant.example/feed"]
    assert result.data == [{"name": "a", "qty": 3}]
    assert result.summary == {"qty": 3}

    fetched.clear()
    with pytest.raises(ValidationError, match="HTTP 地址未登记"):
        await execute_report(
            1,
            report.id,
            {"url": "https://other.example/secret", "limit": 20, "offset": 0},
            http_get=http_get,
        )
    assert fetched == []


@pytest.mark.asyncio
async def test_other_tenant_report_and_dataset_are_not_executed(db):
    set_current_tenant_id(1)
    source = await data_source_service.create_data_source(
        1,
        DataSourceCreate(
            name="数据集",
            type="dataset",
            config={"dataset_uuid": "44444444-4444-4444-4444-444444444444"},
        ),
    )
    report = await KuaireportReport.create(
        tenant_id=1,
        code="tenant_demo",
        name="租户隔离",
        report_config=_report_config(source.uuid),
    )
    set_current_tenant_id(2)
    with pytest.raises(NotFoundError):
        await execute_report(2, report.id, {"limit": 20, "offset": 0})

    set_current_tenant_id(1)
    runner = AsyncMock()
    with (
        patch(
            "apps.kuaireport.services.execute_service.load_dataset",
            AsyncMock(return_value=None),
        ),
        patch("apps.kuaireport.services.execute_service.run_dataset_query", runner),
    ):
        with pytest.raises(NotFoundError):
            await execute_report(1, report.id, {"limit": 20, "offset": 0})
    runner.assert_not_called()


@pytest.mark.asyncio
async def test_no_tenant_context_does_not_read(db):
    clear_tenant_context()
    with pytest.raises(TenantError, match="组织上下文未设置"):
        await execute_report(1, 1, {"limit": 20, "offset": 0})
    with pytest.raises(TenantError, match="组织上下文未设置"):
        await data_source_service.list_data_sources(1)


def test_slot_files_and_execute_report_export():
    gitignore = (REPO / ".gitignore").read_text(encoding="utf-8")
    rules = [
        line.strip()
        for line in gitignore.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert "riveredge-backend/src/apps/kuaireport/" not in rules
    assert "riveredge-frontend/src/apps/kuaireport/" not in rules

    workspace = (REPO / "fast-deploy/tools/workspace/generate_workspace.py").read_text(encoding="utf-8")
    pro_line = next(line for line in workspace.splitlines() if line.startswith("PRO_APPS"))
    assert "kuaireport" not in pro_line

    service = REPO / "riveredge-frontend/src/apps/kuaireport/services/kuaireport.ts"
    uni = REPO / "riveredge-frontend/src/components/uni-report/UniReport.tsx"
    glob_target = (uni.parent / "../../apps/kuaireport/services/kuaireport.ts").resolve()
    assert service.resolve() == glob_target
    assert "export async function executeReport" in service.read_text(encoding="utf-8")
    assert (REPO / "riveredge-backend/src/apps/kuaireport/manifest.json").is_file()
    assert (REPO / "riveredge-frontend/src/apps/kuaireport/manifest.json").is_file()


def test_slice_routers_are_mounted_once():
    slices_dir = REPO / "riveredge-backend/src/apps/kuaireport/api/slices"
    names = {path.name for path in slices_dir.glob("*.py")}
    assert "s146_center.py" in names
    assert "s147_designer.py" in names
    assert "s148_share.py" in names
    assert "s149_distribution.py" in names

    from apps.kuaireport.api.router import include_slice_routers, router

    source = inspect.getsource(include_slice_routers)
    assert "slices_dir.glob" in source

    paths = [getattr(route, "path", "") for route in router.routes]
    assert "/data-sources" in paths
    assert "/reports/{report_id}/execute" in paths
    assert paths.count("/dashboards/shared") == 1
    assert "/reports/{report_id:int}/excel" in paths
    assert "/designer/reports" in paths
    assert "/distribution/subscriptions" in paths
