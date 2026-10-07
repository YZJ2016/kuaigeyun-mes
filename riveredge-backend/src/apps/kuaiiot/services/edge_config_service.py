"""边缘配置校验、下发、心跳与批量续传。批量每条走 IngestService.ingest。"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional
from uuid import uuid4

from apps.kuaiiot.constants import (
    EDGE_PROTOCOLS,
    INGEST_BATCH_MAX_ITEMS,
    MODBUS_DATA_TYPES,
    PUBLISH_MODES,
)
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.models.edge_config import KuaiiotEdgeConfig
from apps.kuaiiot.schemas.ingest import IngestBody
from apps.kuaiiot.services.command_service import claim_pending_commands
from apps.kuaiiot.services.connection_runtime import ensure_device_connection
from apps.kuaiiot.services.ingest_service import IngestService
from core.utils.timezone_utils import resolve_business_datetime
from infra.domain.tenant_context import TenantContextError, get_current_tenant_id, unscoped, with_tenant
from infra.exceptions.exceptions import AuthenticationError, NotFoundError, ValidationError

# 与 message_log_service._SECRET_PARTS 同款口径：键名包含任意子串即视为口令。
_SECRET_PARTS = (
    "token",
    "password",
    "passwd",
    "secret",
    "api_key",
    "access_key",
    "credential",
)
_API_PREFIX = "/api/v1/apps/kuaiiot"
_DEVICE_OFFLINE = timedelta(minutes=5)
_AGENT_OFFLINE = timedelta(minutes=3)


def _require_tenant(explicit: int) -> int:
    current = get_current_tenant_id()
    if current is None:
        raise TenantContextError("组织上下文未设置")
    if int(current) != int(explicit):
        raise ValidationError("租户上下文不匹配")
    return int(current)


def _reject_secrets(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).strip().lower()
            if any(part in lowered for part in _SECRET_PARTS):
                raise ValidationError("配置不能包含口令")
            _reject_secrets(item)
        return
    if isinstance(value, list):
        for item in value:
            _reject_secrets(item)


def _require_publish(config: dict) -> None:
    publish = config.get("publish")
    mode = publish.get("mode") if isinstance(publish, dict) else None
    if mode not in PUBLISH_MODES:
        raise ValidationError("publish.mode 只能是 http_ingest 或 mqtt")


def _missing(name: str) -> ValidationError:
    return ValidationError(f"缺少字段 {name}")


class EdgeConfigService:
    @staticmethod
    def _validate_config(protocol: str, config: dict) -> None:
        if protocol not in EDGE_PROTOCOLS:
            raise ValidationError("不支持的协议")
        if not isinstance(config, dict):
            raise ValidationError("config 必须是对象")
        _reject_secrets(config)
        _require_publish(config)
        if protocol in {"modbus_tcp", "modbus_rtu"}:
            EdgeConfigService._validate_modbus(config)
            return
        if protocol == "opc_ua":
            EdgeConfigService._validate_opc(config)
            return
        EdgeConfigService._validate_s7(config)

    @staticmethod
    def _validate_modbus(config: dict) -> None:
        registers = config.get("registers")
        if not isinstance(registers, list) or not registers:
            raise _missing("registers")
        for item in registers:
            if not isinstance(item, dict):
                raise _missing("registers")
            if not str(item.get("tag_key") or "").strip():
                raise _missing("tag_key")
            if "address" not in item or item.get("address") is None:
                raise _missing("address")
            try:
                address = int(item.get("address"))
            except (TypeError, ValueError) as exc:
                raise _missing("address") from exc
            if address < 0:
                raise _missing("address")
            data_type = item.get("data_type")
            if not isinstance(data_type, str) or not data_type.strip():
                raise _missing("data_type")
            if data_type.strip().lower() not in MODBUS_DATA_TYPES:
                raise ValidationError("data_type 无效")
        if not str(config.get("host") or "").strip():
            raise _missing("host")
        port = config.get("port")
        unit_id = config.get("unit_id")
        if isinstance(port, bool) or not isinstance(port, int) or port < 1 or port > 65535:
            raise _missing("port")
        if isinstance(unit_id, bool) or not isinstance(unit_id, int) or unit_id < 0:
            raise _missing("unit_id")

    @staticmethod
    def _validate_opc(config: dict) -> None:
        if not str(config.get("endpoint") or "").strip():
            raise _missing("endpoint")
        nodes = config.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            raise _missing("nodes")

    @staticmethod
    def _validate_s7(config: dict) -> None:
        if not str(config.get("host") or "").strip():
            raise _missing("host")
        if config.get("rack") is None or isinstance(config.get("rack"), bool):
            raise _missing("rack")
        if config.get("slot") is None or isinstance(config.get("slot"), bool):
            raise _missing("slot")
        blocks = config.get("db_blocks")
        if not isinstance(blocks, list) or not blocks:
            raise _missing("db_blocks")

    @staticmethod
    async def _device_for_token(device_token: str) -> KuaiiotDevice:
        token = (device_token or "").strip()
        if not token:
            raise AuthenticationError("设备凭据无效")
        async with unscoped(reason="按设备凭据匹配唯一未删除设备", resource="KuaiiotDevice"):
            rows = await KuaiiotDevice.filter(device_token=token, deleted_at__isnull=True).limit(2)
        if len(rows) != 1 or rows[0].tenant_id is None:
            raise AuthenticationError("设备凭据无效")
        return rows[0]

    @staticmethod
    async def _enabled_config(device: KuaiiotDevice, edge_config_code: str, *, allow_disabled: bool = False) -> KuaiiotEdgeConfig:
        code = (edge_config_code or "").strip()
        if not code:
            raise NotFoundError("边缘配置不存在")
        tenant_id = int(device.tenant_id)
        async with with_tenant(tenant_id, reason="边缘配置按凭据命中的设备租户读取"):
            row = await KuaiiotEdgeConfig.filter(
                tenant_id=tenant_id,
                device_id=device.id,
                code=code,
                deleted_at__isnull=True,
            ).first()
        if row is None or (not allow_disabled and not row.is_enabled):
            raise NotFoundError("边缘配置不存在")
        return row

    @staticmethod
    def _runtime_paths(device_token: str) -> dict[str, str]:
        token = device_token.strip()
        return {
            "ingest_path": f"{_API_PREFIX}/ingest/{token}",
            "batch_ingest_path": f"{_API_PREFIX}/ingest/{token}/batch",
            "heartbeat_path": f"{_API_PREFIX}/edge-runtime/{token}/heartbeat",
            "command_result_path": f"{_API_PREFIX}/edge-runtime/{token}/command-result",
        }

    @staticmethod
    async def pull_runtime_config(device_token: str, edge_config_code: str) -> dict[str, Any]:
        device = await EdgeConfigService._device_for_token(device_token)
        async with with_tenant(int(device.tenant_id), reason="校验边缘配置公共连接"):
            await ensure_device_connection(device)
        row = await EdgeConfigService._enabled_config(device, edge_config_code)
        body = {
            "config_version": int(row.config_version),
            "protocol": row.protocol,
            "config": row.config,
        }
        body.update(EdgeConfigService._runtime_paths(device.device_token))
        return body

    @staticmethod
    async def record_heartbeat(
        device_token: str,
        *,
        edge_config_code: str,
        config_version: int,
        agent_version: str,
        buffer_pending_count: int,
        status: str,
        trial_result: Optional[dict] = None,
    ) -> dict[str, Any]:
        version_text = (agent_version or "").strip()
        status_text = (status or "").strip()
        if not version_text or len(version_text) > 50:
            raise ValidationError("agent_version 无效")
        if not status_text or len(status_text) > 20:
            raise ValidationError("status 无效")
        if isinstance(buffer_pending_count, bool) or not isinstance(buffer_pending_count, int):
            raise ValidationError("buffer_pending_count 无效")
        if buffer_pending_count < 0:
            raise ValidationError("buffer_pending_count 无效")
        device = await EdgeConfigService._device_for_token(device_token)
        row = await EdgeConfigService._enabled_config(device, edge_config_code, allow_disabled=True)
        changed = int(row.config_version) != int(config_version)
        tenant_id = int(device.tenant_id)
        async with with_tenant(tenant_id, reason="心跳写入凭据命中的边缘配置"):
            # 校验到写入之间可能被禁用/删除，重取时复查（TOCTOU）。
            current = await KuaiiotEdgeConfig.get_or_none(
                id=row.id, tenant_id=tenant_id, deleted_at__isnull=True
            )
            if current is None:
                raise NotFoundError("边缘配置不存在")
            current.last_agent_heartbeat_at = resolve_business_datetime()
            current.agent_config_version = int(config_version)
            current.agent_version = version_text
            current.agent_status = status_text
            current.buffer_pending_count = buffer_pending_count
            if trial_result and trial_result.get("request_uuid") == current.trial_request_uuid:
                _reject_secrets(trial_result)
                tags = trial_result.get("tags")
                if not isinstance(tags, dict) or len(tags) > 200:
                    raise ValidationError("试读结果无效")
                raw_values = trial_result.get("raw_values") or {}
                if not isinstance(raw_values, dict) or len(raw_values) > 200:
                    raise ValidationError("试读原始值无效")
                current.trial_result = {"request_uuid": current.trial_request_uuid, "tags": tags, "raw_values": {key: value for key, value in raw_values.items() if key in tags}, "qualities": {key: "bad" if value is None else "good" for key, value in tags.items()}, "config_version": int(config_version), "received_at": resolve_business_datetime().isoformat()}
            await current.save(
                update_fields=[
                    "last_agent_heartbeat_at",
                    "agent_version",
                    "agent_config_version",
                    "agent_status",
                    "buffer_pending_count",
                    "updated_at",
                    "trial_result",
                ]
            )
            try:
                await ensure_device_connection(device)
                collection_enabled = bool(current.is_enabled)
            except ValidationError:
                collection_enabled = False
            pending_commands = await claim_pending_commands(tenant_id, device.id) if collection_enabled else []
        return {"config_changed": changed, "pending_commands": pending_commands, "collection_enabled": collection_enabled, "trial_request_uuid": current.trial_request_uuid if collection_enabled else None}

    @staticmethod
    async def request_trial(tenant_id: int, config_id: int) -> dict:
        tid = _require_tenant(tenant_id)
        row = await KuaiiotEdgeConfig.filter(id=config_id, tenant_id=tid, deleted_at__isnull=True).first()
        if row is None or not row.is_enabled or row.protocol != "modbus_tcp":
            raise ValidationError("试读需要已启用的 Modbus TCP 配置和在线 Agent")
        row.trial_request_uuid = str(uuid4())
        row.trial_result = None
        await row.save(update_fields=["trial_request_uuid", "trial_result", "updated_at"])
        return EdgeConfigService._public(row)

    @staticmethod
    async def ingest_batch(device_token: str, items: list[IngestBody]) -> dict[str, int]:
        count = len(items or [])
        if count < 1 or count > INGEST_BATCH_MAX_ITEMS:
            raise ValidationError("单批须为 1 到 100 条")
        token = (device_token or "").strip()
        if not token:
            raise AuthenticationError("设备凭据无效")
        device = await IngestService._match_device(token)
        async with with_tenant(int(device.tenant_id), reason="批量续传写入设备所属租户"):
            for item in items:
                await IngestService._ingest_matched(device, item)
        return {"count": count}

    @staticmethod
    def _public(row: KuaiiotEdgeConfig) -> dict[str, Any]:
        seen = row.last_agent_heartbeat_at
        return {
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "device_id": row.device_id,
            "protocol": row.protocol,
            "config": row.config,
            "is_enabled": row.is_enabled,
            "config_version": int(row.config_version),
            "agent_status": row.agent_status,
            "agent_version": row.agent_version,
            "agent_config_version": row.agent_config_version,
            "buffer_pending_count": int(row.buffer_pending_count),
            "last_agent_heartbeat_at": seen.isoformat() if seen else None,
            "trial_request_uuid": row.trial_request_uuid,
            "trial_result": row.trial_result,
        }

    @staticmethod
    async def list_configs(tenant_id: int) -> list[dict[str, Any]]:
        tid = _require_tenant(tenant_id)
        rows = await KuaiiotEdgeConfig.filter(tenant_id=tid, deleted_at__isnull=True).order_by("id").limit(500)
        return [EdgeConfigService._public(row) for row in rows]

    @staticmethod
    async def get_config(tenant_id: int, config_id: int) -> dict[str, Any]:
        tid = _require_tenant(tenant_id)
        row = await KuaiiotEdgeConfig.filter(
            tenant_id=tid, id=config_id, deleted_at__isnull=True
        ).first()
        if row is None:
            raise NotFoundError("边缘配置不存在")
        return EdgeConfigService._public(row)

    @staticmethod
    async def update_config(
        tenant_id: int,
        config_id: int,
        *,
        code: str,
        name: str,
        device_id: int,
        protocol: str,
        config: dict,
        is_enabled: bool = True,
        user_id: Optional[int] = None,
    ) -> dict[str, Any]:
        tid = _require_tenant(tenant_id)
        row = await KuaiiotEdgeConfig.filter(
            tenant_id=tid, id=config_id, deleted_at__isnull=True
        ).first()
        if row is None:
            raise NotFoundError("边缘配置不存在")
        text = (code or "").strip()
        title = (name or "").strip()
        if not text or len(text) > 50 or not title or len(title) > 100:
            raise ValidationError("配置编码和名称不能为空")
        EdgeConfigService._validate_config(protocol, config)
        device = await KuaiiotDevice.filter(tenant_id=tid, id=device_id, deleted_at__isnull=True).first()
        if device is None:
            raise ValidationError("设备不存在")
        conflict = await KuaiiotEdgeConfig.filter(
            tenant_id=tid, code=text, deleted_at__isnull=True
        ).exclude(id=row.id).exists()
        if conflict:
            raise ValidationError("配置编码已存在")
        content_changed = (
            row.code != text
            or row.protocol != protocol
            or row.config != config
            or int(row.device_id) != int(device.id)
            or bool(row.is_enabled) != bool(is_enabled)
        )
        row.code = text
        row.name = title
        row.device_id = device.id
        row.protocol = protocol
        row.config = config
        row.is_enabled = is_enabled
        row.updated_by = user_id
        if content_changed:
            row.config_version = int(row.config_version) + 1
        await row.save(
            update_fields=[
                "code",
                "name",
                "device_id",
                "protocol",
                "config",
                "is_enabled",
                "config_version",
                "updated_by",
                "updated_at",
            ]
        )
        return EdgeConfigService._public(row)

    @staticmethod
    async def delete_config(tenant_id: int, config_id: int, *, user_id: Optional[int] = None) -> None:
        tid = _require_tenant(tenant_id)
        row = await KuaiiotEdgeConfig.filter(
            tenant_id=tid, id=config_id, deleted_at__isnull=True
        ).first()
        if row is None:
            raise NotFoundError("边缘配置不存在")
        row.deleted_at = resolve_business_datetime()
        row.deleted_by = user_id
        await row.save(update_fields=["deleted_at", "deleted_by", "updated_at"])

    @staticmethod
    async def save_config(
        tenant_id: int,
        *,
        code: str,
        name: str,
        device_id: int,
        protocol: str,
        config: dict,
        is_enabled: bool = True,
        user_id: Optional[int] = None,
    ) -> dict[str, Any]:
        tid = _require_tenant(tenant_id)
        text = (code or "").strip()
        title = (name or "").strip()
        if not text or len(text) > 50 or not title or len(title) > 100:
            raise ValidationError("配置编码和名称不能为空")
        EdgeConfigService._validate_config(protocol, config)
        device = await KuaiiotDevice.filter(tenant_id=tid, id=device_id, deleted_at__isnull=True).first()
        if device is None:
            raise ValidationError("设备不存在")
        existing = await KuaiiotEdgeConfig.filter(tenant_id=tid, code=text, deleted_at__isnull=True).first()
        if existing is None:
            created = await KuaiiotEdgeConfig.create(
                tenant_id=tid,
                code=text,
                name=title,
                device_id=device.id,
                protocol=protocol,
                config=config,
                is_enabled=is_enabled,
                created_by=user_id,
                updated_by=user_id,
            )
            return EdgeConfigService._public(created)
        content_changed = (
            existing.protocol != protocol
            or existing.config != config
            or int(existing.device_id) != int(device.id)
            or bool(existing.is_enabled) != bool(is_enabled)
        )
        existing.name = title
        existing.device_id = device.id
        existing.protocol = protocol
        existing.config = config
        existing.is_enabled = is_enabled
        existing.updated_by = user_id
        if content_changed:
            existing.config_version = int(existing.config_version) + 1
        await existing.save(
            update_fields=[
                "name",
                "device_id",
                "protocol",
                "config",
                "is_enabled",
                "config_version",
                "updated_by",
                "updated_at",
            ]
        )
        return EdgeConfigService._public(existing)

    @staticmethod
    async def mark_devices_offline() -> dict[str, Any]:
        checked_at = resolve_business_datetime()
        cutoff = checked_at - _DEVICE_OFFLINE
        async with unscoped(reason="定时任务标记超过5分钟无入站的在线设备", resource="KuaiiotDevice"):
            rows = await KuaiiotDevice.filter(
                is_online=True,
                last_seen_at__lt=cutoff,
                deleted_at__isnull=True,
            )
            flipped: list[dict[str, Any]] = []
            for row in rows:
                flipped.append(
                    {
                        "id": int(row.id),
                        "tenant_id": int(row.tenant_id),
                        "equipment_uuid": row.equipment_uuid,
                        "code": row.code,
                        "last_seen_at": row.last_seen_at,
                    }
                )
                row.is_online = False
                await row.save(update_fields=["is_online", "updated_at"])
        return {
            "devices_marked_offline": len(rows),
            "checked_at": checked_at,
            "flipped": flipped,
        }

    @staticmethod
    async def mark_agents_offline() -> dict[str, int]:
        cutoff = resolve_business_datetime() - _AGENT_OFFLINE
        marked = 0
        async with unscoped(reason="定时任务标记超过3分钟无心跳的边缘配置", resource="KuaiiotEdgeConfig"):
            rows = await KuaiiotEdgeConfig.filter(
                last_agent_heartbeat_at__lt=cutoff,
                deleted_at__isnull=True,
            )
            for row in rows:
                if row.agent_status == "offline":
                    continue
                row.agent_status = "offline"
                await row.save(update_fields=["agent_status", "updated_at"])
                marked += 1
        return {"agents_marked_offline": marked}
