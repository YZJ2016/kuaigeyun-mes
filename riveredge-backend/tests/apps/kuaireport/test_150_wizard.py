"""自制报表向导：只绑平台数据集，系统报表只有管理员能新建，已有系统报表不能改。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from tortoise import Tortoise

from apps.kuaireport.models.report import KuaireportReport
from apps.kuaireport.services.execute_service import execute_report
from apps.kuaireport.slices.s150_wizard import PreviewBody, WizardSaveBody, preview_dataset, save_wizard_report
from infra.domain.tenant_context import clear_tenant_context, set_current_tenant_id
from infra.exceptions.exceptions import AuthorizationError, ValidationError


DATASET = "44444444-4444-4444-4444-444444444444"


@pytest_asyncio.fixture
async def db():
    clear_tenant_context()
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["apps.kuaireport.models.report"]},
    )
    await Tortoise.generate_schemas()
    try:
        yield
    finally:
        clear_tenant_context()
        await Tortoise.close_connections()


def _user():
    return SimpleNamespace(id=7, full_name="管理员", username="admin")


def _config(**overrides):
    payload = {
        "chart_type": "line",
        "dataset_uuid": DATASET,
        "dataset_code": "sales",
        "fields": [
            {"field": "code", "label": "编号", "x_axis": True},
            {"field": "qty", "label": "数量", "y_axis": True},
        ],
        "parameters": [{"key": "param_1", "label": "关键字", "control": "text"}],
        "interaction": {"drilldown": {"enabled": True, "dimension_field": "code"}},
    }
    payload.update(overrides)
    return payload


def _body(**overrides) -> WizardSaveBody:
    payload = {
        "code": "sales_custom",
        "name": "销售自制",
        "description": "备注",
        "category": "custom",
        "classify": "销售",
        "status": "DRAFT",
        "report_config": _config(),
    }
    payload.update(overrides)
    return WizardSaveBody(**payload)


@pytest.mark.asyncio
async def test_wizard_rejects_sql_and_non_admin_system(db):
    set_current_tenant_id(1)
    dataset = SimpleNamespace(query_type="sql", tenant_id=1, uuid=DATASET)
    with patch("apps.kuaireport.slices.s150_wizard.load_dataset", AsyncMock(return_value=dataset)):
        with pytest.raises(ValidationError, match="SQL"):
            await save_wizard_report(
                _body(report_config=_config(sql="select 1")),
                report_id=None,
                user=_user(),
                is_admin=True,
            )
        with pytest.raises(AuthorizationError):
            await save_wizard_report(
                _body(code="sys_one", category="system", report_config=_config(chart_type="table")),
                report_id=None,
                user=_user(),
                is_admin=False,
            )


@pytest.mark.asyncio
async def test_wizard_saves_dataset_binding_and_execute_skips_data_source(db):
    set_current_tenant_id(1)
    dataset = SimpleNamespace(query_type="sql", tenant_id=1, uuid=DATASET, display_config={})
    captured: dict = {}

    async def fake_run(tenant_id, dataset_uuid, request):
        captured["dataset_uuid"] = dataset_uuid
        captured["parameters"] = request.parameters
        captured["limit"] = request.limit
        return SimpleNamespace(success=True, data=[{"code": "A", "qty": 3}], total=1)

    with patch("apps.kuaireport.slices.s150_wizard.load_dataset", AsyncMock(return_value=dataset)):
        saved = await save_wizard_report(_body(), report_id=None, user=_user(), is_admin=False)

    assert saved["category"] == "custom"
    assert saved["report_config"]["dataset_uuid"] == DATASET
    assert saved["report_config"]["interaction"]["drilldown"]["enabled"] is True
    row = await KuaireportReport.get(id=saved["id"])
    assert row.owner_id == 7
    assert row.is_system is False

    with (
        patch("apps.kuaireport.services.execute_service.load_dataset", AsyncMock(return_value=dataset)),
        patch("apps.kuaireport.services.execute_service.run_dataset_query", fake_run),
    ):
        result = await execute_report(1, saved["id"], {"param_1": "泵", "limit": 50, "offset": 0})

    assert captured["dataset_uuid"] == DATASET
    assert captured["parameters"] == {"param_1": "泵"}
    assert captured["limit"] == 50
    assert result.data == [{"code": "A", "qty": 3}]

    row.is_system = True
    row.category = "system"
    await row.save()
    with (
        patch("apps.kuaireport.slices.s150_wizard.load_dataset", AsyncMock(return_value=dataset)),
        pytest.raises(AuthorizationError),
    ):
        await save_wizard_report(_body(), report_id=saved["id"], user=_user(), is_admin=True)


@pytest.mark.asyncio
async def test_preview_caps_sample_at_50(db):
    set_current_tenant_id(1)
    dataset = SimpleNamespace(query_type="api", tenant_id=1, uuid=DATASET)
    captured: dict = {}

    async def fake_run(tenant_id, dataset_uuid, request):
        captured["limit"] = request.limit
        return SimpleNamespace(success=True, data=[{"code": "A"}], total=80)

    with (
        patch("apps.kuaireport.slices.s150_wizard.load_dataset", AsyncMock(return_value=dataset)),
        patch("apps.kuaireport.services.execute_service.load_dataset", AsyncMock(return_value=dataset)),
        patch("apps.kuaireport.services.execute_service.run_dataset_query", fake_run),
    ):
        result = await preview_dataset(PreviewBody(dataset_uuid=DATASET, page_size=500))

    assert captured["limit"] == 50
    assert result["success"] is True
    assert result["data"] == [{"code": "A"}]
    assert result["total"] == 80
