"""快数采测试公共 mock。"""

import sys
import types
from unittest.mock import MagicMock

import pytest_asyncio
from tortoise import Tortoise

from infra.domain.tenant_context import clear_tenant_context

sys.modules.setdefault("aiomqtt", MagicMock())

_influx_root = types.ModuleType("influxdb_client")
_influx_root.InfluxDBClient = MagicMock
_influx_root.Point = MagicMock
_influx_client = types.ModuleType("influxdb_client.client")
_influx_write = types.ModuleType("influxdb_client.client.write_api")
_influx_write.SYNCHRONOUS = "sync"
_influx_client.write_api = _influx_write
_influx_root.client = _influx_client
sys.modules["influxdb_client"] = _influx_root
sys.modules["influxdb_client.client"] = _influx_client
sys.modules["influxdb_client.client.write_api"] = _influx_write


@pytest_asyncio.fixture
async def db():
    clear_tenant_context()
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={
            "models": [
                "apps.kuaiiot.models.connection",
                "apps.kuaiiot.models.device",
                "apps.kuaiiot.models.tag",
                "apps.kuaiiot.models.dedup",
                "apps.kuaiiot.models.delivery",
                "apps.kuaiiot.models.alert",
                "apps.kuaiiot.models.edge_config",
                "apps.kuaiiot.models.product",
                "apps.kuaiiot.models.group",
                "apps.kuaiiot.models.command",
                "apps.kuaiiot.models.message_log",
                "core.models.integration_config",
                "apps.kuaizhizao.models.equipment",
                "apps.kuaizhizao.models.equipment_status_monitor",
                "apps.kuaizhizao.models.equipment_fault",
                "apps.kuaizhizao.models.reporting_record",
                "apps.kuaizhizao.models.equipment_ops",
            ]
        },
    )
    await Tortoise.generate_schemas()
    try:
        yield
    finally:
        clear_tenant_context()
        await Tortoise.close_connections()
