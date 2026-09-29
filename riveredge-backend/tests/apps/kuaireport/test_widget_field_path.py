"""大屏预览按组件 options.field 读取嵌套 HTTP，列表源仍可用。"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from tortoise import Tortoise

from apps.kuaireport.schemas.data_source import DataSourceCreate
from apps.kuaireport.services import data_source_service
from apps.kuaireport.services.execute_service import (
    _rows_from_http,
    project_widget_field,
)
from apps.kuaireport.slices.s148_share import ShareService, MemoryShareStore
from infra.domain.tenant_context import clear_tenant_context, set_current_tenant_id
from infra.exceptions.exceptions import ValidationError

NOW = datetime(2026, 9, 29, 8, 0, tzinfo=timezone.utc)
FEED = {
    "ops_metrics": [
        {"code": "EQ-1", "oee_live": 0.4, "availability_rate": 0.5, "quality_rate": 0.8}
    ],
    "status_dist": [{"status": "待机", "count": 1}],
    "workshop_stats": [{"workshop_name": "一车间", "equipment_count": 1}],
}


def _shaped_document() -> dict:
    return {"data": [FEED], "total": 1, "summary": {}}


@pytest_asyncio.fixture
async def db():
    clear_tenant_context()
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["apps.kuaireport.models.data_source"]},
    )
    await Tortoise.generate_schemas()
    try:
        yield
    finally:
        clear_tenant_context()
        await Tortoise.close_connections()


def test_nested_field_reads_oee_and_list_paths_keep_element_columns():
    metric = project_widget_field(
        {"type": "metric", "options": {"field": "ops_metrics.oee_live"}},
        _shaped_document(),
    )
    assert metric["summary"]["ops_metrics.oee_live"] == 0.4
    assert metric["data"] == [{"oee_live": 0.4}]

    status = project_widget_field(
        {
            "type": "chart",
            "options": {
                "field": "status_dist",
                "x_field": "status",
                "y_field": "count",
            },
        },
        _shaped_document(),
    )
    assert status["data"] == [{"status": "待机", "count": 1}]
    assert status["data"][0]["status"] == "待机"
    assert status["data"][0]["count"] == 1

    workshop = project_widget_field(
        {
            "type": "chart",
            "options": {
                "field": "workshop_stats",
                "x_field": "workshop_name",
                "y_field": "equipment_count",
            },
        },
        _shaped_document(),
    )
    assert workshop["data"][0]["workshop_name"] == "一车间"
    assert workshop["data"][0]["equipment_count"] == 1


def test_missing_path_is_empty_without_error():
    empty = project_widget_field(
        {"type": "metric", "options": {"field": "ops_metrics.missing"}},
        _shaped_document(),
    )
    assert empty == {"data": [], "total": 0, "summary": {}}
    gone = project_widget_field(
        {"type": "metric", "options": {"field": "no_such.oee_live"}},
        _shaped_document(),
    )
    assert gone == {"data": [], "total": 0, "summary": {}}


def test_list_and_data_list_sources_stay_rows():
    rows = [{"name": "a", "qty": 3}]
    assert _rows_from_http(rows) == rows
    assert _rows_from_http({"data": rows}) == rows
    shaped = {"data": rows, "total": 1, "summary": {"qty": 3}}
    assert project_widget_field({"type": "table", "options": {"field": "qty"}}, shaped) == shaped
    assert project_widget_field({"type": "chart", "options": {"x_field": "name", "y_field": "qty"}}, shaped) == shaped
    with pytest.raises(ValidationError):
        _rows_from_http(FEED)


@pytest.mark.asyncio
async def test_preview_empty_widget_does_not_fail_dashboard():
    store = MemoryShareStore()

    async def source(tenant_id, data_source_id):
        return _shaped_document()

    service = ShareService(store, secret="test-share-secret", execute_source=source, clock=lambda: NOW)
    saved = await service.save_dashboard(
        tenant_id=7,
        dashboard_id=None,
        code="equipment-ops",
        name="设备运营",
        layout_config={"cols": 12},
        widgets_config=[
            {
                "id": "oee",
                "type": "metric",
                "data_source_id": 1,
                "refresh_seconds": 30,
                "options": {"field": "ops_metrics.oee_live"},
            },
            {
                "id": "missing",
                "type": "metric",
                "data_source_id": 1,
                "refresh_seconds": 30,
                "options": {"field": "ops_metrics.missing"},
            },
            {
                "id": "status",
                "type": "chart",
                "data_source_id": 1,
                "refresh_seconds": 30,
                "options": {"field": "status_dist", "x_field": "status", "y_field": "count"},
            },
        ],
        theme_config={},
        tv_config={},
    )
    body = await service.preview_dashboard(tenant_id=7, dashboard_id=saved["id"])
    by_id = {item["id"]: item for item in body["widgets_config"]}
    assert by_id["oee"]["result"]["summary"]["ops_metrics.oee_live"] == 0.4
    assert by_id["missing"]["result"] == {"data": [], "total": 0, "summary": {}}
    assert by_id["status"]["result"]["data"] == [{"status": "待机", "count": 1}]


@pytest.mark.asyncio
async def test_http_executor_keeps_list_and_reads_nested_document(db):
    from apps.kuaireport.slices.s148_share import default_execute_source

    set_current_tenant_id(1)
    source = await data_source_service.create_data_source(
        1,
        DataSourceCreate(name="馈送", type="http", config={"url": "https://tenant.example/feed"}),
    )

    async def http_get(url: str):
        assert url == "https://tenant.example/feed"
        return [{"name": "a", "qty": 3}]

    with patch("apps.kuaireport.services.execute_service.default_http_get", http_get):
        listed = await default_execute_source(1, source.id)
    assert listed["data"] == [{"name": "a", "qty": 3}]

    async def http_data(url: str):
        return {"data": [{"name": "b", "qty": 1}]}

    with patch("apps.kuaireport.services.execute_service.default_http_get", http_data):
        wrapped = await default_execute_source(1, source.id)
    assert wrapped["data"] == [{"name": "b", "qty": 1}]

    async def http_nested(url: str):
        return FEED

    with patch("apps.kuaireport.services.execute_service.default_http_get", http_nested):
        nested = await default_execute_source(1, source.id)
    assert nested["data"] == [FEED]
    metric = project_widget_field(
        {"type": "metric", "options": {"field": "ops_metrics.oee_live"}},
        nested,
    )
    assert metric["summary"]["ops_metrics.oee_live"] == 0.4
