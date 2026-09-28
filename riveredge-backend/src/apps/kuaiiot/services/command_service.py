"""指令闭环。下发只走边缘心跳，回执只改凭据命中的那台设备。"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from tortoise.transactions import in_transaction

from apps.kuaiiot.models.command import KuaiiotDeviceCommand
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.services.message_log_service import MessageLogService, sanitize_payload
from apps.kuaiiot.services.product_service import get_product
from core.utils.timezone_utils import resolve_business_datetime
from infra.domain.tenant_context import TenantContextError, get_current_tenant_id, unscoped, with_tenant
from infra.exceptions.exceptions import AuthenticationError, NotFoundError, ValidationError

DISPATCH_CHANNEL = "edge_heartbeat"


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


async def _device_for_token(device_token: str) -> KuaiiotDevice:
    token = (device_token or "").strip()
    if not token:
        raise AuthenticationError("设备凭据无效")
    async with unscoped(reason="按设备凭据匹配唯一未删除设备", resource="KuaiiotDevice"):
        rows = await KuaiiotDevice.filter(device_token=token, deleted_at__isnull=True).limit(2)
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
) -> KuaiiotDeviceCommand:
    tid = _require_tenant(tenant_id)
    key = (function_key or "").strip()
    if not key:
        raise ValidationError("function_key 不能为空")
    body = dict(params or {})
    device = await KuaiiotDevice.filter(tenant_id=tid, id=device_id, deleted_at__isnull=True).first()
    if device is None:
        raise NotFoundError("设备不存在")
    if not device.product_id:
        raise ValidationError("设备未绑定产品")
    product = await get_product(tid, int(device.product_id))
    function = _find_function(product.functions or [], key)
    if function is None:
        raise ValidationError("function_key 不在产品指令中")
    _executable_edge_action(function)
    _check_required_params(function, body)
    timeout = function.get("timeout_seconds")
    expires_at = None
    if isinstance(timeout, int) and not isinstance(timeout, bool) and timeout > 0:
        expires_at = resolve_business_datetime() + timedelta(seconds=timeout)
    async with in_transaction():
        command = await KuaiiotDeviceCommand.create(
            tenant_id=tid,
            device_id=device.id,
            function_key=str(function["function_key"]).strip(),
            params=body,
            dispatch_channel=DISPATCH_CHANNEL,
            status="pending",
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
            status="pending",
            direction="out",
        )
    return command


async def list_commands(tenant_id: int, device_id: int) -> list[KuaiiotDeviceCommand]:
    tid = _require_tenant(tenant_id)
    return await KuaiiotDeviceCommand.filter(
        tenant_id=tid,
        device_id=device_id,
        deleted_at__isnull=True,
    ).order_by("-id")


async def claim_pending_commands(tenant_id: int, device_id: int) -> list[dict[str, Any]]:
    """心跳取走 pending，并标成 sent。调用方需已处于该设备租户。"""
    now = resolve_business_datetime()
    device = await KuaiiotDevice.filter(tenant_id=tenant_id, id=device_id, deleted_at__isnull=True).first()
    if device is None:
        return []
    functions = await _functions_by_key(tenant_id, device.product_id)
    rows = await KuaiiotDeviceCommand.filter(
        tenant_id=tenant_id,
        device_id=device_id,
        status="pending",
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
            updated = await KuaiiotDeviceCommand.filter(
                id=row.id,
                tenant_id=tenant_id,
                status="pending",
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
            row = await KuaiiotDeviceCommand.filter(
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
            row.status = status
            row.result = sanitize_payload(result, (device.device_token,)) if result else None
            row.error_message = error_message.replace(device.device_token, "") if error_message else None
            row.completed_at = resolve_business_datetime()
            await row.save(update_fields=["status", "result", "error_message", "completed_at", "updated_at"])
            await _log_command(
                tenant_id=tenant_id,
                device_id=device.id,
                device_token=device.device_token,
                command_uuid=row.uuid,
                function_key=row.function_key,
                status=status,
                direction="in",
                error_message=row.error_message,
            )
    return {"status": status}


async def timeout_sent_commands() -> int:
    now = resolve_business_datetime()
    async with unscoped(reason="定时任务扫描已下发且超过到期时间的指令", resource="KuaiiotDeviceCommand"):
        rows = await KuaiiotDeviceCommand.filter(
            status="sent",
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
            device = await KuaiiotDevice.filter(tenant_id=tenant_id, id=device_id).first()
            token = device.device_token if device is not None else ""
            async with in_transaction():
                updated = await KuaiiotDeviceCommand.filter(
                    id=command_id,
                    tenant_id=tenant_id,
                    status="sent",
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
