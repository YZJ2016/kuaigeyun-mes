"""实时通道 API Schema。"""

from pydantic import BaseModel, Field


class RealtimeConfigResponse(BaseModel):
    enabled: bool = Field(description="是否启用实时推送")
    backend: str = Field(default="noop", description="noop | socketio | centrifugo")
    ws_url: str = Field(
        default="",
        description="Centrifugo 专用 WS 地址；socketio 时留空，走同源",
    )
    socket_path: str = Field(
        default="/socket.io",
        description="python-socketio 路径（backend=socketio 时使用）",
    )


class RealtimeTokenResponse(BaseModel):
    token: str = Field(description="Centrifugo 连接 JWT（socketio 不需要此接口）")
    channel: str = Field(description="用户私有频道/房间名")
