"""实时通道：配置与连接令牌。"""

from fastapi import APIRouter, Depends, HTTPException, status

from core.api.deps.deps import get_current_tenant, get_current_user
from core.schemas.realtime import RealtimeConfigResponse, RealtimeTokenResponse
from core.services.realtime.channels import personal_channel
from core.services.realtime.publisher import realtime_backend, realtime_enabled
from core.services.realtime.token_service import create_centrifugo_connection_token
from infra.config.infra_config import infra_settings
from infra.models.user import User

router = APIRouter(prefix="/realtime", tags=["Core - Realtime"])


def _resolve_ws_public_url() -> str:
    explicit = (infra_settings.REALTIME_WS_PUBLIC_URL or "").strip()
    if explicit:
        return explicit.rstrip("/")
    return ""


@router.get("/config", response_model=RealtimeConfigResponse)
async def get_realtime_config() -> RealtimeConfigResponse:
    backend = realtime_backend()
    enabled = realtime_enabled()
    ws_url = _resolve_ws_public_url() if backend == "centrifugo" else ""
    return RealtimeConfigResponse(
        enabled=enabled,
        backend=backend if enabled else "noop",
        ws_url=ws_url,
        socket_path=(infra_settings.REALTIME_SOCKET_PATH or "/socket.io").strip()
        or "/socket.io",
    )


@router.get("/token", response_model=RealtimeTokenResponse)
async def get_realtime_token(
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> RealtimeTokenResponse:
    if realtime_backend() != "centrifugo":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="当前实时后端无需单独 token（socketio 使用登录 access token）",
        )
    try:
        token = create_centrifugo_connection_token(
            tenant_id=tenant_id,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    channel = personal_channel(tenant_id=tenant_id, user_id=current_user.id)
    return RealtimeTokenResponse(token=token, channel=channel)
