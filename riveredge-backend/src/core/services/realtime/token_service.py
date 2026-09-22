"""Centrifugo 连接 JWT。"""

from __future__ import annotations

import time

from jose import jwt

from core.services.realtime.channels import personal_channel
from infra.config.infra_config import infra_settings


def create_centrifugo_connection_token(*, tenant_id: int, user_id: int) -> str:
    secret = (infra_settings.CENTRIFUGO_TOKEN_HMAC_SECRET or "").strip()
    if not secret:
        raise ValueError("CENTRIFUGO_TOKEN_HMAC_SECRET 未配置")
    channel = personal_channel(tenant_id=tenant_id, user_id=user_id)
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "exp": now + max(300, int(infra_settings.REALTIME_TOKEN_TTL_SECONDS)),
        "channels": [channel],
    }
    return jwt.encode(payload, secret, algorithm="HS256")
