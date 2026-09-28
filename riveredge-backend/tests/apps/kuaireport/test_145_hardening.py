"""spec 145 加固：内网地址拒绝、引用中数据源禁删、is_system 只读、参数收敛、SQL 键深扫。"""

import pytest
import pytest_asyncio
from pydantic import ValidationError as PydanticValidationError
from tortoise import Tortoise

from apps.kuaireport.models.report import KuaireportReport
from apps.kuaireport.schemas.data_source import DataSourceCreate, DataSourceUpdate
from apps.kuaireport.services import data_source_service, execute_service
from infra.domain.tenant_context import clear_tenant_context, set_current_tenant_id
from infra.exceptions.exceptions import ConflictError, NotFoundError, ValidationError


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


def _report_config(source_uuid: str) -> dict:
    return {
        "page_size": 20,
        "fields": [{"field": "qty", "label": "数量", "format": "number"}],
        "filters": [{"field": "name", "label": "名称", "operator": "eq"}],
        "extra": {"data_source_uuid": source_uuid},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data",
        "http://10.1.2.3/internal",
        "http://172.16.5.5/internal",
        "http://192.168.1.1/router",
        "http://0.0.0.0:9000/",
        "http://[::1]:8080/",
        "http://[fe80::1]/",
        "http://2130706433/",
        "ftp://example.com/file",
    ],
)
async def test_http_source_rejects_internal_addresses(db, url):
    set_current_tenant_id(1)
    with pytest.raises(ValidationError):
        await data_source_service.create_data_source(
            1, DataSourceCreate(name="内网", type="http", config={"url": url})
        )


@pytest.mark.asyncio
async def test_http_source_accepts_public_https_and_update_also_checked(db):
    set_current_tenant_id(1)
    row = await data_source_service.create_data_source(
        1,
        DataSourceCreate(
            name="公网", type="http", config={"url": "https://tenant.example.com/feed"}
        ),
    )
    assert row.config["url"] == "https://tenant.example.com/feed"
    with pytest.raises(ValidationError):
        await data_source_service.update_data_source(
            1, row.id, DataSourceUpdate(config={"url": "http://192.168.1.1/x"})
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8080/admin",
        "http://localhost:8000/api",
    ],
)
async def test_http_source_accepts_localhost_for_local_test(db, url):
    set_current_tenant_id(1)
    row = await data_source_service.create_data_source(
        1, DataSourceCreate(name="本机", type="http", config={"url": url})
    )
    assert row.config["url"] == url
    updated = await data_source_service.update_data_source(
        1, row.id, DataSourceUpdate(config={"url": url})
    )
    assert updated.config["url"] == url


@pytest.mark.asyncio
async def test_delete_rejects_source_still_bound_by_report(db):
    set_current_tenant_id(1)
    source = await data_source_service.create_data_source(
        1,
        DataSourceCreate(
            name="台账",
            type="static",
            config={"rows": [{"name": "a", "qty": 1}]},
        ),
    )
    await KuaireportReport.create(
        tenant_id=1,
        code="ref_demo",
        name="引用中",
        report_config=_report_config(source.uuid),
    )
    with pytest.raises(ConflictError):
        await data_source_service.delete_data_source(1, source.id)

    other = await data_source_service.create_data_source(
        1, DataSourceCreate(name="闲置", type="static", config={"rows": []})
    )
    await data_source_service.delete_data_source(1, other.id)
    with pytest.raises(NotFoundError):
        await data_source_service.get_data_source(1, other.id)


def test_input_schemas_cannot_set_is_system():
    with pytest.raises(PydanticValidationError):
        DataSourceCreate(name="x", type="static", config={}, is_system=True)
    with pytest.raises(PydanticValidationError):
        DataSourceUpdate(is_system=True)


def test_reject_sql_keys_scans_nested_levels():
    with pytest.raises(ValidationError):
        execute_service._reject_sql_keys({"extra": {"deep": {"sql": "select 1"}}})
    with pytest.raises(ValidationError):
        execute_service._reject_sql_keys({"fields": [{"query_config": {"x": 1}}]})
    # 正常配置不受影响
    execute_service._reject_sql_keys(
        {"fields": [{"field": "qty"}], "extra": {"data_source_uuid": "u"}}
    )


def test_parameters_converge_to_declared_filters():
    config = {
        "filters": [
            {"field": "name", "operator": "eq"},
            {"field": "biz_date", "operator": "between"},
        ]
    }
    filters = {
        "name": "a",
        "biz_date_start": "2026-01-01",
        "biz_date_end": "2026-02-01",
        "biz_date": "should-not-pass-as-plain",
        "undeclared": "x",
        "limit": 20,
        "offset": 0,
        "url": "http://evil.example",
    }
    params = execute_service._parameters(filters, config)
    assert params == {
        "name": "a",
        "biz_date_start": "2026-01-01",
        "biz_date_end": "2026-02-01",
    }
    # 未声明任何筛选时不透传参数
    assert execute_service._parameters(filters, {"filters": []}) is None
