"""星数采设备指令下发服务。"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from apps.kuaiiot.constants import (
    COMMAND_DEFAULT_TIMEOUT_SECONDS,
    COMMAND_STATUSES,
    DISPATCH_CHANNELS,
    TAG_VALUE_TYPES,
)
from apps.kuaiiot.models.iot import IotConnection, IotDevice, IotDeviceCommand, IotEdgeConfig, IotProduct
from apps.kuaiiot.schemas.iot import DeviceCommandCreate
from apps.kuaiiot.services.connector_service import ConnectorService
from apps.kuaiiot.services.message_log_service import MessageLogService, sanitize_payload
from apps.kuaiiot.services.product_service import ProductService
from core.services.integration.iot_platform_client import PlatformClient
from core.utils.timezone_utils import resolve_business_datetime
from infra.domain.tenant_context import TenantContextError, get_current_tenant_id, unscoped, with_tenant
from infra.exceptions.exceptions import AuthenticationError, NotFoundError, ValidationError


class CommandService:
    @staticmethod
    def _find_function(product: IotProduct, function_key: str) -> dict[str, Any]:
        functions = product.functions if isinstance(product.functions, list) else []
        for item in functions:
            if isinstance(item, dict) and str(item.get("function_key") or "") == function_key:
                return item
        raise ValidationError(f"产品未定义功能: {function_key}")

    @staticmethod
    def _validate_params(function_def: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        param_defs = function_def.get("params") or []
        if not isinstance(param_defs, list):
            raise ValidationError("功能 params 定义无效")
        seen: set[str] = set()
        for item in param_defs:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            required = bool(item.get("required", True))
            value_type = str(item.get("value_type") or "number").strip()
            if value_type not in TAG_VALUE_TYPES:
                raise ValidationError(f"无效 value_type: {value_type}")
            if key not in params:
                if required:
                    raise ValidationError(f"缺少必填参数: {key}")
                continue
            raw = params[key]
            if value_type == "boolean" and not isinstance(raw, bool):
                normalized[key] = str(raw).strip().lower() in {"1", "true", "yes", "on"}
            elif value_type == "number":
                normalized[key] = float(raw)
            else:
                normalized[key] = str(raw)
        extra = set(params.keys()) - seen
        if extra:
            raise ValidationError(f"未知参数: {', '.join(sorted(extra))}")
        return normalized

    @staticmethod
    async def _resolve_dispatch_channel(
        tenant_id: int,
        device: IotDevice,
        requested: Optional[str],
    ) -> str:
        if requested:
            if requested not in DISPATCH_CHANNELS:
                raise ValidationError(f"无效 dispatch_channel: {requested}")
            return requested
        edge_exists = await IotEdgeConfig.filter(
            tenant_id=tenant_id,
            device_id=device.id,
            is_enabled=True,
            deleted_at__isnull=True,
        ).exists()
        if edge_exists:
            return "edge"
        if device.connection_id:
            connection = await IotConnection.filter(
                tenant_id=tenant_id,
                id=device.connection_id,
                deleted_at__isnull=True,
            ).first()
            if connection and connection.connection_type in {"thingsboard", "jetlinks"}:
                return connection.connection_type
        raise ValidationError("无法确定指令下发通道，请指定 dispatch_channel 或配置边缘 Agent / 连接源")

    @staticmethod
    async def create_command(
        tenant_id: int,
        device: IotDevice,
        data: DeviceCommandCreate,
        *,
        requested_by: Optional[int] = None,
    ) -> IotDeviceCommand:
        if not device.product_id:
            raise ValidationError("设备未绑定产品模型，无法下发指令")
        product = await ProductService.get_by_id(tenant_id, device.product_id)
        function_def = CommandService._find_function(product, data.function_key)
        params = CommandService._validate_params(function_def, dict(data.params or {}))
        channel = await CommandService._resolve_dispatch_channel(tenant_id, device, data.dispatch_channel)
        timeout_seconds = int(function_def.get("timeout_seconds") or COMMAND_DEFAULT_TIMEOUT_SECONDS)
        now = resolve_business_datetime()
        command = await IotDeviceCommand.create(
            tenant_id=tenant_id,
            device_id=device.id,
            function_key=data.function_key,
            params=params,
            dispatch_channel=channel,
            status="pending",
            requested_by=requested_by,
            expires_at=now + timedelta(seconds=max(timeout_seconds, 1)),
        )
        await MessageLogService.append(
            tenant_id=tenant_id,
            device_id=device.id,
            direction="down",
            msg_type="command",
            result="accepted",
            payload={
                "command_uuid": command.uuid,
                "function_key": command.function_key,
                "params": params,
                "dispatch_channel": channel,
            },
        )
        if channel in {"thingsboard", "jetlinks"}:
            await CommandService._dispatch_upstream(tenant_id, device, command, function_def)
        return command

    @staticmethod
    async def _dispatch_upstream(
        tenant_id: int,
        device: IotDevice,
        command: IotDeviceCommand,
        function_def: dict[str, Any],
    ) -> None:
        now = resolve_business_datetime()
        try:
            result = await ConnectorService.invoke_device_function(
                tenant_id=tenant_id,
                device=device,
                function_key=command.function_key,
                params=command.params,
                function_def=function_def,
            )
            command.status = "success"
            command.result = result
            command.sent_at = now
            command.completed_at = now
            await command.save()
            await MessageLogService.append(
                tenant_id=tenant_id,
                device_id=device.id,
                direction="up",
                msg_type="command_result",
                result="synced",
                payload={"command_uuid": command.uuid, "result": result},
            )
        except Exception as exc:
            command.status = "failed"
            command.error_message = str(exc)
            command.sent_at = now
            command.completed_at = now
            await command.save()
            await MessageLogService.append(
                tenant_id=tenant_id,
                device_id=device.id,
                direction="up",
                msg_type="command_result",
                result="error",
                payload={"command_uuid": command.uuid},
                error_message=str(exc),
            )

    @staticmethod
    async def list_commands(
        tenant_id: int,
        device_id: int,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[IotDeviceCommand], int]:
        query = IotDeviceCommand.filter(
            tenant_id=tenant_id,
            device_id=device_id,
            deleted_at__isnull=True,
        )
        total = await query.count()
        items = await query.order_by("-created_at").offset((page - 1) * page_size).limit(page_size)
        return items, total

    @staticmethod
    async def get_by_uuid(tenant_id: int, uuid: str) -> IotDeviceCommand:
        item = await IotDeviceCommand.filter(tenant_id=tenant_id, uuid=uuid, deleted_at__isnull=True).first()
        if not item:
            raise NotFoundError(f"指令不存在: {uuid}")
        return item

    @staticmethod
    async def claim_pending_for_edge(
        tenant_id: int,
        device_id: int,
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        now = resolve_business_datetime()
        pending = await IotDeviceCommand.filter(
            tenant_id=tenant_id,
            device_id=device_id,
            dispatch_channel="edge",
            status="pending",
            deleted_at__isnull=True,
        ).order_by("created_at").limit(limit)
        payloads: list[dict[str, Any]] = []
        device = await IotDevice.filter(tenant_id=tenant_id, id=device_id, deleted_at__isnull=True).first()
        edge_action: dict[str, Any] | None = None
        if device and device.product_id:
            product = await IotProduct.filter(tenant_id=tenant_id, id=device.product_id, deleted_at__isnull=True).first()
            if product:
                functions = product.functions if isinstance(product.functions, list) else []
                function_map = {
                    str(item.get("function_key")): item
                    for item in functions
                    if isinstance(item, dict) and item.get("function_key")
                }
        else:
            function_map = {}

        for command in pending:
            function_def = function_map.get(command.function_key, {})
            edge_action = function_def.get("edge_action") if isinstance(function_def, dict) else None
            command.status = "sent"
            command.sent_at = now
            await command.save()
            payloads.append(
                {
                    "command_uuid": command.uuid,
                    "function_key": command.function_key,
                    "params": command.params,
                    "edge_action": edge_action,
                    "expires_at": command.expires_at.isoformat() if command.expires_at else None,
                }
            )
        return payloads

    @staticmethod
    async def complete_edge_command(
        tenant_id: int,
        device_id: int,
        *,
        command_uuid: str,
        success: bool,
        result: Any = None,
        error_message: Optional[str] = None,
    ) -> IotDeviceCommand:
        command = await IotDeviceCommand.filter(
            tenant_id=tenant_id,
            device_id=device_id,
            uuid=command_uuid,
            deleted_at__isnull=True,
        ).first()
        if not command:
            raise NotFoundError(f"指令不存在: {command_uuid}")
        if command.status in {"success", "failed", "timeout"}:
            return command
        now = resolve_business_datetime()
        command.status = "success" if success else "failed"
        command.result = result if isinstance(result, dict) else {"value": result}
        command.error_message = error_message
        command.completed_at = now
        await command.save()
        await MessageLogService.append(
            tenant_id=tenant_id,
            device_id=device_id,
            direction="up",
            msg_type="command_result",
            result="synced" if success else "error",
            payload={"command_uuid": command.uuid, "result": command.result},
            error_message=error_message,
        )
        return command

    @staticmethod
    async def timeout_expired_commands() -> int:
        now = resolve_business_datetime()
        expired = await IotDeviceCommand.filter(
            status__in=["pending", "sent"],
            expires_at__lt=now,
            deleted_at__isnull=True,
        ).all()
        count = 0
        for command in expired:
            command.status = "timeout"
            command.completed_at = now
            command.error_message = "指令执行超时"
            await command.save()
            await MessageLogService.append(
                tenant_id=command.tenant_id,
                device_id=command.device_id,
                direction="up",
                msg_type="command_result",
                result="error",
                payload={"command_uuid": command.uuid},
                error_message=command.error_message,
            )
            count += 1
        return count


# ---- 星数采本地执行版：指令下发/领取/回执/超时（整型 ID 与凭据接口） ----

from apps.kuaiiot.services.connection_runtime import ensure_device_connection, resolve_core_connection
from apps.kuaiiot.services.product_service import get_product

DISPATCH_CHANNEL = "edge_heartbeat"
NOT_SENT = "not_sent"


PLATFORM_CHANNELS = frozenset({"thingsboard", "jetlinks"})


def _require_tenant(explicit: int) -> int:
    current = get_current_tenant_id()
    if current is None:
        raise TenantContextError("组织上下文未设置")
    if int(current) != int(explicit):
        raise ValidationError("租户上下文不匹配")
    return int(current)


def _executable_edge_action(function: dict) -> dict[str, Any]:
    """只返回 Agent 能执行的 modbus_write。缺地址或类型不对时拒绝下发。"""
    raw = function.get("edge_action") if isinstance(function, dict) else None
    action = raw if isinstance(raw, dict) else None
    if action is None:
        raise ValidationError("指令缺少可执行的写寄存器地址")
    action_type = str(action.get("type") or "modbus_write").strip() or "modbus_write"
    if action_type != "modbus_write":
        raise ValidationError("当前只下发 modbus_write")
    address = action.get("address")
    if isinstance(address, bool) or not isinstance(address, int) or address < 0:
        raise ValidationError("指令缺少可执行的写寄存器地址")
    scale = action.get("scale")
    return {
        "type": "modbus_write",
        "param_key": str(action.get("param_key") or "value"),
        "address": address,
        "data_type": str(action.get("data_type") or "uint16"),
        "scale": 1.0 if scale is None else scale,
    }


def _find_function(functions: list, function_key: str) -> Optional[dict]:
    key = function_key.strip()
    for item in functions or []:
        if isinstance(item, dict) and str(item.get("function_key") or "").strip() == key:
            return item
    return None


def _check_required_params(function: dict, params: dict) -> None:
    for item in function.get("params") or []:
        if not isinstance(item, dict) or not item.get("required"):
            continue
        name = str(item.get("key") or "").strip()
        if not name or name not in params or params.get(name) is None:
            raise ValidationError(f"缺少参数 {name or 'value'}")


async def _device_for_token(device_token: str) -> IotDevice:
    token = (device_token or "").strip()
    if not token:
        raise AuthenticationError("设备凭据无效")
    async with unscoped(reason="按设备凭据匹配唯一未删除设备", resource="IotDevice"):
        rows = await IotDevice.filter(device_token=token, deleted_at__isnull=True).limit(2)
    if len(rows) != 1 or rows[0].tenant_id is None:
        raise AuthenticationError("设备凭据无效")
    return rows[0]


async def _functions_by_key(tenant_id: int, product_id: Optional[int]) -> dict[str, dict]:
    if not product_id:
        return {}
    try:
        product = await get_product(tenant_id, int(product_id))
    except NotFoundError:
        return {}
    found: dict[str, dict] = {}
    for item in product.functions or []:
        if isinstance(item, dict):
            key = str(item.get("function_key") or "").strip()
            if key:
                found[key] = item
    return found


async def _log_command(
    *,
    tenant_id: int,
    device_id: int,
    device_token: str,
    command_uuid: str,
    function_key: str,
    status: str,
    direction: str,
    error_message: Optional[str] = None,
) -> None:
    await MessageLogService.append(
        tenant_id=tenant_id,
        device_id=device_id,
        direction=direction,
        msg_type="command",
        payload={
            "command_uuid": command_uuid,
            "function_key": function_key,
            "status": status,
        },
        result=status,
        error_message=error_message,
        forbidden_values=(device_token,),
    )


async def create_command(
    tenant_id: int,
    device_id: int,
    *,
    function_key: str,
    params: Optional[dict] = None,
    user_id: Optional[int] = None,
) -> IotDeviceCommand:
    tid = _require_tenant(tenant_id)
    key = (function_key or "").strip()
    if not key:
        raise ValidationError("function_key 不能为空")
    body = dict(params or {})
    device = await IotDevice.filter(tenant_id=tid, id=device_id, deleted_at__isnull=True).first()
    if device is None:
        raise NotFoundError("设备不存在")
    await ensure_device_connection(device)
    if not device.product_id:
        raise ValidationError("设备未绑定产品")
    product = await get_product(tid, int(device.product_id))
    function = _find_function(product.functions or [], key)
    if function is None:
        raise ValidationError("function_key 不在产品指令中")
    source = "http"
    if device.connection_id is not None:
        connection = await IotConnection.filter(
            tenant_id=tid,
            id=device.connection_id,
            deleted_at__isnull=True,
        ).first()
        if connection is not None and connection.connection_type:
            source = connection.connection_type.strip().lower()
    # 平台指令永不到边缘，不强制边缘动作；http/mqtt 仍按原顺序校验
    if source not in PLATFORM_CHANNELS:
        _executable_edge_action(function)
    _check_required_params(function, body)
    if source == "mqtt":
        raise ValidationError("MQTT 连接不做指令下发")
    platform_command = source in PLATFORM_CHANNELS
    if platform_command:
        channel = source
        status = "pending"
    else:
        channel = DISPATCH_CHANNEL
        status = "pending"
    timeout = function.get("timeout_seconds")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        timeout = COMMAND_DEFAULT_TIMEOUT_SECONDS
    expires_at = resolve_business_datetime() + timedelta(seconds=timeout)
    async with in_transaction():
        command = await IotDeviceCommand.create(
            tenant_id=tid,
            device_id=device.id,
            function_key=str(function["function_key"]).strip(),
            params=body,
            dispatch_channel=channel,
            status=status,
            requested_by=user_id,
            expires_at=expires_at,
            created_by=user_id,
            updated_by=user_id,
        )
        await _log_command(
            tenant_id=tid,
            device_id=device.id,
            device_token=device.device_token,
            command_uuid=command.uuid,
            function_key=command.function_key,
            status=status,
            direction="out",
        )
    if platform_command:
        try:
            core = await resolve_core_connection(connection)
            # 发送前持久标记；网络响应丢失不自动重发设备动作。
            command.status = "sent"
            command.sent_at = resolve_business_datetime()
            await command.save()
            async with PlatformClient(source, core.get_config()) as client:
                outcome = await client.command(device.external_device_id, command.function_key, body, command.uuid)
            command.result = sanitize_payload(outcome if isinstance(outcome, dict) else {"response": outcome}, tuple(str(value) for key, value in core.get_config().items() if key in {"password", "token", "api_key", "secret"} and value) + (device.device_token,))
            command.status = "success"
            command.completed_at = resolve_business_datetime()
        except Exception:
            command.status = "uncertain"
            command.error_message = "平台执行结果未确认；请核对设备，不自动重复发送"
        await command.save()
    return command


async def list_commands(tenant_id: int, device_id: int) -> list[IotDeviceCommand]:
    tid = _require_tenant(tenant_id)
    return await IotDeviceCommand.filter(
        tenant_id=tid,
        device_id=device_id,
        deleted_at__isnull=True,
    ).order_by("-id").limit(500)


async def claim_pending_commands(tenant_id: int, device_id: int) -> list[dict[str, Any]]:
    """心跳只领取 edge_heartbeat 的 pending，并标成 sent。调用方需已处于该设备租户。"""
    now = resolve_business_datetime()
    device = await IotDevice.filter(tenant_id=tenant_id, id=device_id, deleted_at__isnull=True).first()
    if device is None:
        return []
    try:
        await ensure_device_connection(device)
    except ValidationError:
        return []
    functions = await _functions_by_key(tenant_id, device.product_id)
    rows = await IotDeviceCommand.filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now),
        tenant_id=tenant_id,
        device_id=device_id,
        status="pending",
        dispatch_channel=DISPATCH_CHANNEL,
        deleted_at__isnull=True,
    ).order_by("id")
    claimed: list[dict[str, Any]] = []
    for row in rows:
        function = functions.get(row.function_key) or {}
        try:
            edge_action = _executable_edge_action(function)
        except ValidationError:
            continue
        async with in_transaction():
            updated = await IotDeviceCommand.filter(
                id=row.id,
                tenant_id=tenant_id,
                status="pending",
                dispatch_channel=DISPATCH_CHANNEL,
                deleted_at__isnull=True,
            ).update(status="sent", sent_at=now)
            if not updated:
                continue
            await _log_command(
                tenant_id=tenant_id,
                device_id=device_id,
                device_token=device.device_token,
                command_uuid=row.uuid,
                function_key=row.function_key,
                status="sent",
                direction="out",
            )
        claimed.append(
            {
                "command_uuid": row.uuid,
                "edge_action": edge_action,
                "params": row.params or {},
            }
        )
    return claimed


async def submit_command_result(
    device_token: str,
    *,
    command_uuid: str,
    success: bool,
    result: Optional[dict] = None,
    error_message: Optional[str] = None,
) -> dict[str, str]:
    if not isinstance(success, bool):
        raise ValidationError("success 无效")
    if result is not None and not isinstance(result, dict):
        raise ValidationError("result 无效")
    text = (command_uuid or "").strip()
    if not text:
        raise ValidationError("command_uuid 无效")
    device = await _device_for_token(device_token)
    tenant_id = int(device.tenant_id)
    async with with_tenant(tenant_id, reason="回执只更新凭据命中的设备指令"):
        async with in_transaction():
            row = await IotDeviceCommand.filter(
                tenant_id=tenant_id,
                device_id=device.id,
                uuid=text,
                deleted_at__isnull=True,
            ).first()
            if row is None:
                raise NotFoundError("指令不存在")
            if row.status != "sent":
                return {"status": row.status}
            status = "success" if success else "failed"
            cleaned_result = sanitize_payload(result, (device.device_token,)) if result else None
            cleaned_error = error_message.replace(device.device_token, "") if error_message else None
            # CAS：只覆盖仍停在 sent 的行；并发改态后不重写也不补日志
            updated = await IotDeviceCommand.filter(
                id=row.id,
                tenant_id=tenant_id,
                status="sent",
                deleted_at__isnull=True,
            ).update(
                status=status,
                result=cleaned_result,
                error_message=cleaned_error,
                completed_at=resolve_business_datetime(),
            )
            if not updated:
                await row.refresh_from_db(fields=["status"])
                return {"status": row.status}
            await _log_command(
                tenant_id=tenant_id,
                device_id=device.id,
                device_token=device.device_token,
                command_uuid=row.uuid,
                function_key=row.function_key,
                status=status,
                direction="in",
                error_message=cleaned_error,
            )
    return {"status": status}


async def timeout_sent_commands() -> int:
    """超时处理 pending 与 sent：超过 expires_at 仍未完结的指令改为 timeout。"""
    now = resolve_business_datetime()
    async with unscoped(reason="定时任务扫描 pending 与 sent 中超过到期时间的指令", resource="IotDeviceCommand"):
        rows = await IotDeviceCommand.filter(
            status__in=["pending", "sent"],
            expires_at__lt=now,
            deleted_at__isnull=True,
        )
        pending = [
            (int(row.id), int(row.tenant_id), int(row.device_id), row.uuid, row.function_key)
            for row in rows
            if row.tenant_id is not None
        ]
    count = 0
    for command_id, tenant_id, device_id, command_uuid, function_key in pending:
        async with with_tenant(tenant_id, reason="指令超时写入该指令所属租户"):
            device = await IotDevice.filter(tenant_id=tenant_id, id=device_id).first()
            token = device.device_token if device is not None else ""
            async with in_transaction():
                updated = await IotDeviceCommand.filter(
                    id=command_id,
                    tenant_id=tenant_id,
                    status__in=["pending", "sent"],
                    deleted_at__isnull=True,
                ).update(status="timeout", completed_at=now)
                if not updated:
                    continue
                await _log_command(
                    tenant_id=tenant_id,
                    device_id=device_id,
                    device_token=token,
                    command_uuid=command_uuid,
                    function_key=function_key,
                    status="timeout",
                    direction="out",
                )
        count += 1
    return count
