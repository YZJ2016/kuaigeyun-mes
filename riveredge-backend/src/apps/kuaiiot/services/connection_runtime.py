"""数采映射关联公共连接。凭据只从 core 原始配置读取。"""

from apps.kuaiiot.models.connection import KuaiiotConnection
from apps.kuaiiot.models.device import KuaiiotDevice
from core.models.integration_config import IntegrationConfig
from infra.exceptions.exceptions import ValidationError

EXTERNAL_TYPES = frozenset({"mqtt", "thingsboard", "jetlinks"})
MAPPING_KEYS = frozenset({
    "topic", "device_token_path", "tags_path", "events_path", "timestamp_path", "idempotency_key_path",
})


def validate_mapping(config: dict | None) -> None:
    if config and set(config) - MAPPING_KEYS:
        raise ValidationError("数采配置只允许映射字段；连接地址和凭据请在公共连接中配置")


def validate_type(kind: str, core_type: str) -> None:
    allowed = {"API", "api", "Webhook"} if kind == "http" else {kind}
    if core_type not in allowed:
        raise ValidationError("公共连接类型与数采连接类型不匹配")


async def resolve_core_connection(connection: KuaiiotConnection) -> IntegrationConfig | None:
    if not connection.is_enabled or connection.deleted_at is not None:
        raise ValidationError("数采连接已停用")
    kind = connection.connection_type.strip().lower()
    if connection.integration_id is None:
        if kind in EXTERNAL_TYPES:
            raise ValidationError("数采连接未关联公共连接")
        return None  # 直接 HTTP 入站没有外部服务器凭据。
    core = await IntegrationConfig.filter(
        id=connection.integration_id, tenant_id=connection.tenant_id, deleted_at__isnull=True,
    ).first()
    if core is None:
        raise ValidationError("公共连接不存在或不属于当前租户")
    validate_type(kind, core.type)
    if not core.is_active:
        raise ValidationError("公共连接已停用")
    return core


async def connection_is_active(connection: KuaiiotConnection) -> bool:
    try:
        await resolve_core_connection(connection)
    except ValidationError:
        return False
    return True


async def ensure_device_connection(device: KuaiiotDevice) -> None:
    if device.connection_id is None:
        return
    connection = await KuaiiotConnection.filter(
        id=device.connection_id, tenant_id=device.tenant_id, deleted_at__isnull=True,
    ).first()
    if connection is None:
        raise ValidationError("数采连接不存在")
    await resolve_core_connection(connection)
