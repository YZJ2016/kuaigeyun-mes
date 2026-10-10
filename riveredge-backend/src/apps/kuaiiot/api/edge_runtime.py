"""边缘 Agent 运行时 API（device token 鉴权）。"""

from fastapi import APIRouter

from apps.kuaiiot.schemas.iot import (
    EdgeAgentCommandResultPayload,
    EdgeAgentHeartbeatPayload,
    EdgeAgentHeartbeatResponse,
    EdgeRuntimeConfigResponse,
)
from apps.kuaiiot.services.edge_runtime_service import EdgeRuntimeService

router = APIRouter(prefix="/edge-runtime", tags=["App - KuaiIoT - Edge Runtime"])


@router.get("/{device_token}/config/{edge_config_code}", response_model=EdgeRuntimeConfigResponse)
async def pull_edge_runtime_config(device_token: str, edge_config_code: str):
    return await EdgeRuntimeService.pull_config(device_token, edge_config_code)


@router.post("/{device_token}/heartbeat", response_model=EdgeAgentHeartbeatResponse)
async def edge_agent_heartbeat(device_token: str, payload: EdgeAgentHeartbeatPayload):
    return await EdgeRuntimeService.heartbeat(device_token, payload)


@router.post("/{device_token}/command-result")
async def edge_agent_command_result(device_token: str, payload: EdgeAgentCommandResultPayload):
    return await EdgeRuntimeService.submit_command_result(device_token, payload)
