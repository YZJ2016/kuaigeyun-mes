"""快数采边缘 Agent 运行时（device token 鉴权）。

三个入口统一委托 EdgeConfigService 的凭据作用域实现：
token 匹配走 unscoped 失败关闭，业务读写走 with_tenant，
心跳含试读（trial_result）回传与采集启停门禁。
"""

from __future__ import annotations

from apps.kuaiiot.schemas.iot import (
    EdgeAgentCommandResultPayload,
    EdgeAgentHeartbeatPayload,
    EdgeAgentHeartbeatResponse,
    EdgeRuntimeConfigResponse,
)
from apps.kuaiiot.services.command_service import submit_command_result
from apps.kuaiiot.services.edge_config_service import EdgeConfigService


class EdgeRuntimeService:
    @staticmethod
    async def pull_config(device_token: str, edge_config_code: str) -> EdgeRuntimeConfigResponse:
        body = await EdgeConfigService.pull_runtime_config(device_token, edge_config_code)
        return EdgeRuntimeConfigResponse.model_validate(body)

    @staticmethod
    async def heartbeat(device_token: str, payload: EdgeAgentHeartbeatPayload) -> EdgeAgentHeartbeatResponse:
        body = await EdgeConfigService.record_heartbeat(
            device_token,
            edge_config_code=payload.edge_config_code,
            config_version=int(payload.config_version or 0),
            agent_version=payload.agent_version or "",
            buffer_pending_count=int(payload.buffer_pending_count or 0),
            status=payload.status,
            trial_result=payload.trial_result,
        )
        return EdgeAgentHeartbeatResponse.model_validate(body)

    @staticmethod
    async def submit_command_result(device_token: str, payload: EdgeAgentCommandResultPayload) -> dict[str, str]:
        return await submit_command_result(
            device_token,
            command_uuid=payload.command_uuid,
            success=payload.success,
            result=payload.result,
            error_message=payload.error_message,
        )
