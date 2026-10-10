"""快数采边缘 Agent 运行时（device token 鉴权）。"""

from __future__ import annotations

from typing import Any, Optional

from apps.kuaiiot.models.iot import IotDevice, IotEdgeConfig
from apps.kuaiiot.schemas.iot import (
    EdgeAgentCommandResultPayload,
    EdgeAgentHeartbeatPayload,
    EdgeAgentHeartbeatResponse,
    EdgeRuntimeConfigResponse,
)
from apps.kuaiiot.services.command_service import CommandService
from apps.kuaiiot.services.edge_config_service import EdgeConfigService
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import NotFoundError, ValidationError


class EdgeRuntimeService:
    @staticmethod
    async def _resolve_device(device_token: str) -> IotDevice:
        device = await IotDevice.filter(device_token=device_token, deleted_at__isnull=True).first()
        if not device:
            raise ValidationError("无效的设备 token")
        return device

    @staticmethod
    async def _resolve_edge_config(device: IotDevice, edge_config_code: str) -> IotEdgeConfig:
        item = await IotEdgeConfig.filter(
            tenant_id=device.tenant_id,
            code=edge_config_code,
            device_id=device.id,
            deleted_at__isnull=True,
        ).first()
        if not item:
            raise NotFoundError(f"边缘配置不存在: {edge_config_code}")
        if not item.is_enabled:
            raise ValidationError("边缘配置未启用")
        return item

    @staticmethod
    def _build_runtime_spec(device: IotDevice, item: IotEdgeConfig) -> dict[str, Any]:
        base = EdgeConfigService.build_agent_spec(device, item)
        base["config_version"] = item.config_version
        base["ingest_path"] = f"/api/v1/apps/kuaiiot/ingest/{device.device_token}"
        base["batch_ingest_path"] = f"/api/v1/apps/kuaiiot/ingest/{device.device_token}/batch"
        base["heartbeat_path"] = f"/api/v1/apps/kuaiiot/edge-runtime/{device.device_token}/heartbeat"
        base["command_result_path"] = f"/api/v1/apps/kuaiiot/edge-runtime/{device.device_token}/command-result"
        return base

    @staticmethod
    async def pull_config(device_token: str, edge_config_code: str) -> EdgeRuntimeConfigResponse:
        device = await EdgeRuntimeService._resolve_device(device_token)
        item = await EdgeRuntimeService._resolve_edge_config(device, edge_config_code)
        return EdgeRuntimeConfigResponse.model_validate(
            EdgeRuntimeService._build_runtime_spec(device, item)
        )

    @staticmethod
    async def heartbeat(device_token: str, payload: EdgeAgentHeartbeatPayload) -> EdgeAgentHeartbeatResponse:
        device = await EdgeRuntimeService._resolve_device(device_token)
        item = await EdgeRuntimeService._resolve_edge_config(device, payload.edge_config_code)
        now = resolve_business_datetime()
        item.last_agent_heartbeat_at = now
        item.agent_version = payload.agent_version
        item.agent_status = "online" if payload.status == "online" else "error"
        item.buffer_pending_count = max(int(payload.buffer_pending_count or 0), 0)
        await item.save()
        config_changed = payload.config_version is not None and payload.config_version != item.config_version
        pending_commands = await CommandService.claim_pending_for_edge(
            tenant_id=device.tenant_id,
            device_id=device.id,
        )
        return EdgeAgentHeartbeatResponse(
            config_version=item.config_version,
            config_changed=config_changed,
            pending_commands=pending_commands,
            message=payload.message or "ok",
        )

    @staticmethod
    async def submit_command_result(device_token: str, payload: EdgeAgentCommandResultPayload) -> dict[str, str]:
        device = await EdgeRuntimeService._resolve_device(device_token)
        await CommandService.complete_edge_command(
            tenant_id=device.tenant_id,
            device_id=device.id,
            command_uuid=payload.command_uuid,
            success=payload.success,
            result=payload.result,
            error_message=payload.error_message,
        )
        return {"message": "ok"}
