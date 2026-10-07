"""spec 179 基座：补齐详情、编辑与软删除标准动作。设备凭据仍只出现在建机当次。"""

from __future__ import annotations

import pytest

from apps.kuaiiot.api.router import router
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.schemas.control import (
    ConnectionCreate,
    ConnectionUpdate,
    DeviceCreate,
    DeviceOut,
    DeviceUpdate,
    TagCreate,
    TagUpdate,
)
from apps.kuaiiot.schemas.prefill import AlertRuleCreate, AlertRuleUpdate
from apps.kuaiiot.services import alert_service, control_service
from apps.kuaiiot.services.edge_config_service import EdgeConfigService
from apps.kuaiiot.services.offline_alert_service import create_offline_rule
from infra.domain.tenant_context import set_current_tenant_id
from infra.exceptions.exceptions import NotFoundError, ValidationError


def _modbus_config() -> dict:
    return {
        "host": "127.0.0.1",
        "port": 502,
        "unit_id": 1,
        "registers": [{"tag_key": "temp", "address": 0, "data_type": "uint16"}],
        "publish": {"mode": "http_ingest"},
    }


def test_standard_action_routes_are_mounted():
    paths = {getattr(route, "path", "") for route in router.routes}
    assert "/connections/{connection_id}" in paths
    assert "/devices/{device_id}" in paths
    assert "/tags" in paths
    assert "/tags/{tag_id}" in paths
    assert "/alert-rules" in paths
    assert "/alert-rules/{rule_id}" in paths
    assert "/edge-configs/{config_id}" in paths


@pytest.mark.asyncio
async def test_device_detail_and_soft_delete(db):
    set_current_tenant_id(1)
    device = await control_service.create_device(
        1,
        DeviceCreate(external_device_id="plc-01", code="plc-01", name="一线 PLC"),
    )
    found = await control_service.get_device(1, device.id)
    assert found.code == "plc-01"
    assert "device_token" not in DeviceOut.model_validate(found).model_dump()
    await control_service.delete_device(1, device.id)
    with pytest.raises(NotFoundError):
        await control_service.get_device(1, device.id)
    assert await control_service.list_devices(1) == []


@pytest.mark.asyncio
async def test_device_detail_rejects_other_tenant(db):
    set_current_tenant_id(1)
    device = await control_service.create_device(
        1,
        DeviceCreate(external_device_id="plc-01", code="plc-01", name="一线 PLC"),
    )
    set_current_tenant_id(2)
    with pytest.raises(NotFoundError):
        await control_service.get_device(2, device.id)
    with pytest.raises(NotFoundError):
        await control_service.delete_device(2, device.id)


@pytest.mark.asyncio
async def test_connection_detail_update_and_delete(db):
    set_current_tenant_id(1)
    connection = await control_service.create_connection(
        1,
        ConnectionCreate(code="line", name="一线", connection_type="http"),
    )
    found = await control_service.get_connection(1, connection.id)
    assert found.code == "line"

    updated = await control_service.update_connection(
        1,
        connection.id,
        ConnectionUpdate(name="一线改造", is_enabled=False, config={"topic": "plant/+"}),
    )
    assert updated.name == "一线改造"
    assert updated.is_enabled is False
    assert updated.config == {"topic": "plant/+"}

    with pytest.raises(ValidationError):
        await control_service.update_connection(
            1,
            connection.id,
            ConnectionUpdate(config={"broker_url": "tcp://internal"}),
        )

    await control_service.delete_connection(1, connection.id)
    with pytest.raises(NotFoundError):
        await control_service.get_connection(1, connection.id)
    assert await control_service.list_connections(1) == []


@pytest.mark.asyncio
async def test_tags_list_update_and_delete(db):
    set_current_tenant_id(1)
    device = await control_service.create_device(
        1,
        DeviceCreate(external_device_id="plc-01", code="plc-01", name="一线 PLC"),
    )
    other = await control_service.create_device(
        1,
        DeviceCreate(external_device_id="plc-02", code="plc-02", name="二线 PLC"),
    )
    tag = await control_service.create_tag(
        1,
        device.id,
        TagCreate(tag_key="temp", name="温度", value_type="number", map_target="temperature"),
    )
    await control_service.create_tag(
        1,
        other.id,
        TagCreate(tag_key="run", name="运行", value_type="boolean", map_target="status"),
    )

    rows = await control_service.list_tags(1)
    assert {row.tag_key for row in rows} == {"temp", "run"}
    only = await control_service.list_tags(1, device_id=device.id)
    assert [row.tag_key for row in only] == ["temp"]

    found = await control_service.get_tag(1, tag.id)
    assert found.tag_key == "temp"

    updated = await control_service.update_tag(
        1,
        tag.id,
        TagUpdate(name="炉温", unit="℃", map_target="other_parameters.temp"),
    )
    assert updated.name == "炉温"
    assert updated.unit == "℃"
    assert updated.map_target == "other_parameters.temp"
    assert updated.tag_key == "temp"

    with pytest.raises(ValidationError):
        await control_service.update_tag(1, tag.id, TagUpdate(map_target="secret_field"))
    with pytest.raises(ValidationError):
        await control_service.update_tag(1, tag.id, TagUpdate(value_type="json"))

    await control_service.delete_tag(1, tag.id)
    with pytest.raises(NotFoundError):
        await control_service.get_tag(1, tag.id)
    assert {row.tag_key for row in await control_service.list_tags(1)} == {"run"}


@pytest.mark.asyncio
async def test_tags_of_deleted_device_are_hidden(db):
    set_current_tenant_id(1)
    device = await control_service.create_device(
        1,
        DeviceCreate(external_device_id="plc-01", code="plc-01", name="一线 PLC"),
    )
    tag = await control_service.create_tag(
        1,
        device.id,
        TagCreate(tag_key="temp", name="温度", value_type="number", map_target="temperature"),
    )
    await control_service.delete_device(1, device.id)
    assert await control_service.list_tags(1) == []
    with pytest.raises(NotFoundError):
        await control_service.get_tag(1, tag.id)


@pytest.mark.asyncio
async def test_alert_rule_list_update_and_delete(db):
    set_current_tenant_id(1)
    rule = await alert_service.create_rule(
        1,
        AlertRuleCreate(
            code="temp-high",
            name="温度上限",
            tag_key="temp",
            operator="gt",
            threshold_number=80,
        ),
    )
    offline = await create_offline_rule(1, code="offline", name="离线告警")

    rules = await alert_service.list_rules(1)
    assert {row.code for row in rules} == {"temp-high", "offline"}

    found = await alert_service.get_rule(1, rule.id)
    assert found.operator == "gt"

    updated = await alert_service.update_rule(
        1,
        rule.id,
        AlertRuleUpdate(name="温度上限改", threshold_number=90, is_enabled=False),
    )
    assert updated.name == "温度上限改"
    assert updated.is_enabled is False

    # 离线规则的 tag_key/operator 由服务固定，不允许编辑破坏离线评估。
    with pytest.raises(ValidationError):
        await alert_service.update_rule(
            1,
            offline.id,
            AlertRuleUpdate(operator="ne"),
        )
    renamed = await alert_service.update_rule(
        1,
        offline.id,
        AlertRuleUpdate(name="离线告警改", is_enabled=False),
    )
    assert renamed.name == "离线告警改"

    await alert_service.delete_rule(1, rule.id)
    with pytest.raises(NotFoundError):
        await alert_service.get_rule(1, rule.id)
    assert {row.code for row in await alert_service.list_rules(1)} == {"offline"}


@pytest.mark.asyncio
async def test_alert_record_soft_delete(db):
    set_current_tenant_id(1)
    device = await control_service.create_device(
        1,
        DeviceCreate(external_device_id="plc-01", code="plc-01", name="一线 PLC"),
    )
    rule = await alert_service.create_rule(
        1,
        AlertRuleCreate(
            code="temp-high",
            name="温度上限",
            tag_key="temp",
            operator="gt",
            threshold_number=80,
        ),
    )
    from apps.kuaiiot.models.alert import KuaiiotAlert
    from core.utils.timezone_utils import resolve_business_datetime

    alert = await KuaiiotAlert.create(
        tenant_id=1,
        rule_id=rule.id,
        device_id=device.id,
        tag_key="temp",
        severity="warning",
        message="温度上限 阈值命中",
        status="open",
        triggered_at=resolve_business_datetime(),
    )
    await alert_service.delete_alert(1, alert.id)
    assert await alert_service.list_alerts(1) == []


@pytest.mark.asyncio
async def test_edge_config_detail_update_and_delete(db):
    set_current_tenant_id(1)
    device = await control_service.create_device(
        1,
        DeviceCreate(external_device_id="plc-01", code="plc-01", name="一线 PLC"),
    )
    saved = await EdgeConfigService.save_config(
        1,
        code="agent-a",
        name="一号 Agent",
        device_id=device.id,
        protocol="modbus_tcp",
        config=_modbus_config(),
        is_enabled=True,
    )
    found = await EdgeConfigService.get_config(1, saved["id"])
    assert found["code"] == "agent-a"
    assert "device_token" not in str(found)

    updated = await EdgeConfigService.update_config(
        1,
        saved["id"],
        code="agent-a",
        name="一号 Agent 改",
        device_id=device.id,
        protocol="modbus_tcp",
        config=_modbus_config(),
        is_enabled=False,
    )
    assert updated["name"] == "一号 Agent 改"
    assert updated["is_enabled"] is False
    assert updated["config_version"] == saved["config_version"] + 1

    await EdgeConfigService.save_config(
        1,
        code="agent-b",
        name="二号 Agent",
        device_id=device.id,
        protocol="modbus_tcp",
        config=_modbus_config(),
        is_enabled=True,
    )
    with pytest.raises(ValidationError):
        await EdgeConfigService.update_config(
            1,
            saved["id"],
            code="agent-b",
            name="一号 Agent 改",
            device_id=device.id,
            protocol="modbus_tcp",
            config=_modbus_config(),
            is_enabled=False,
        )

    await EdgeConfigService.delete_config(1, saved["id"])
    with pytest.raises(NotFoundError):
        await EdgeConfigService.get_config(1, saved["id"])
    rows = await EdgeConfigService.list_configs(1)
    assert {row["code"] for row in rows} == {"agent-b"}


# ------------------------------------------------------- 运营闭环增量


def _required_permissions(route) -> set:
    """从 require_permission_codes 依赖闭包中取出权限码。"""
    perms = set()
    for dep in route.dependencies or []:
        fn = getattr(dep, "dependency", None)
        closure = getattr(fn, "__closure__", None)
        if fn is None or closure is None:
            continue
        for name, cell in zip(fn.__code__.co_freevars, closure):
            if name == "codes":
                perms.update(cell.cell_contents or [])
    return perms


def test_tags_read_endpoints_use_display_permission():
    """GET /tags 与 GET /tags/{id} 只读端点挂 tag:display，写操作仍走 tag:create。"""
    table = {}
    for route in router.routes:
        for method in getattr(route, "methods", set()) or set():
            table[(method, getattr(route, "path", ""))] = _required_permissions(route)
    assert table[("GET", "/tags")] == {"kuaiiot:tag:display"}
    assert table[("GET", "/tags/{tag_id}")] == {"kuaiiot:tag:display"}
    assert table[("PUT", "/tags/{tag_id}")] == {"kuaiiot:tag:create"}
    assert table[("DELETE", "/tags/{tag_id}")] == {"kuaiiot:tag:create"}


@pytest.mark.asyncio
async def test_update_device_rebinds_connection(db):
    set_current_tenant_id(1)
    conn_a = await control_service.create_connection(
        1, ConnectionCreate(code="line-a", name="一线", connection_type="http")
    )
    conn_b = await control_service.create_connection(
        1, ConnectionCreate(code="line-b", name="二线", connection_type="http")
    )
    device = await control_service.create_device(
        1,
        DeviceCreate(
            external_device_id="plc-01",
            code="plc-01",
            name="一线 PLC",
            connection_id=conn_a.id,
        ),
    )
    updated = await control_service.update_device(
        1, device.id, DeviceUpdate(connection_id=conn_b.id)
    )
    assert updated.connection_id == conn_b.id


@pytest.mark.asyncio
async def test_update_device_rebind_rejects_foreign_or_deleted_connection(db):
    set_current_tenant_id(1)
    conn = await control_service.create_connection(
        1, ConnectionCreate(code="line", name="一线", connection_type="http")
    )
    device = await control_service.create_device(
        1,
        DeviceCreate(external_device_id="plc-01", code="plc-01", name="一线 PLC"),
    )
    set_current_tenant_id(2)
    other = await control_service.create_connection(
        2, ConnectionCreate(code="line", name="他租户", connection_type="http")
    )
    set_current_tenant_id(1)
    with pytest.raises(ValidationError):
        await control_service.update_device(
            1, device.id, DeviceUpdate(connection_id=other.id)
        )
    await control_service.delete_connection(1, conn.id)
    with pytest.raises(ValidationError):
        await control_service.update_device(
            1, device.id, DeviceUpdate(connection_id=conn.id)
        )


@pytest.mark.asyncio
async def test_orphan_device_recovers_via_rebind(db):
    """连接已删的孤儿设备可经 update_device 改绑到新连接恢复。"""
    set_current_tenant_id(1)
    conn = await control_service.create_connection(
        1, ConnectionCreate(code="line-a", name="一线", connection_type="http")
    )
    conn_b = await control_service.create_connection(
        1, ConnectionCreate(code="line-b", name="二线", connection_type="http")
    )
    device = await control_service.create_device(
        1,
        DeviceCreate(
            external_device_id="plc-01",
            code="plc-01",
            name="一线 PLC",
            connection_id=conn.id,
        ),
    )
    await control_service.delete_connection(1, conn.id)
    updated = await control_service.update_device(
        1, device.id, DeviceUpdate(connection_id=conn_b.id)
    )
    assert updated.connection_id == conn_b.id


@pytest.mark.asyncio
async def test_delete_device_cascades_edge_config_and_alert_rule(db):
    """删设备时同事务软删其边缘配置与设备绑定告警规则；全租户规则不受影响。"""
    set_current_tenant_id(1)
    device = await control_service.create_device(
        1,
        DeviceCreate(external_device_id="plc-01", code="plc-01", name="一线 PLC"),
    )
    saved = await EdgeConfigService.save_config(
        1,
        code="agent-a",
        name="一号 Agent",
        device_id=device.id,
        protocol="modbus_tcp",
        config=_modbus_config(),
        is_enabled=True,
    )
    await alert_service.create_rule(
        1,
        AlertRuleCreate(
            code="temp-high",
            name="温度上限",
            tag_key="temp",
            operator="gt",
            threshold_number=80,
            device_id=device.id,
        ),
    )
    await alert_service.create_rule(
        1,
        AlertRuleCreate(
            code="tenant-wide",
            name="全租户规则",
            tag_key="temp",
            operator="gt",
            threshold_number=80,
        ),
    )
    await control_service.delete_device(1, device.id)
    with pytest.raises(NotFoundError):
        await EdgeConfigService.get_config(1, saved["id"])
    assert {row.code for row in await alert_service.list_rules(1)} == {"tenant-wide"}


@pytest.mark.asyncio
async def test_device_out_exposes_product_and_remark(db):
    set_current_tenant_id(1)
    device = await control_service.create_device(
        1,
        DeviceCreate(
            external_device_id="plc-01",
            code="plc-01",
            name="一线 PLC",
            remark="泵房备注",
        ),
    )
    out = DeviceOut.model_validate(device).model_dump()
    assert out["remark"] == "泵房备注"
    assert "product_id" in out
    assert out["product_id"] is None
