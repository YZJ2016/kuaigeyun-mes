"""Centrifugo HTTP API 发布实现。"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from core.services.realtime.channels import personal_channel
from core.services.realtime.publisher import RealtimePublisher
from core.utils.timezone_utils import resolve_business_datetime, to_api_isoformat
from infra.config.infra_config import infra_settings


class CentrifugoRealtimePublisher(RealtimePublisher):
    def is_configured(self) -> bool:
        api_url = (infra_settings.CENTRIFUGO_API_URL or "").strip().rstrip("/")
        api_key = (infra_settings.CENTRIFUGO_API_KEY or "").strip()
        return bool(api_url and api_key)

    def _envelope(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "event": event,
            "payload": payload,
            "ts": to_api_isoformat(resolve_business_datetime()),
        }

    async def publish_to_channel(
        self,
        *,
        channel: str,
        event: str,
        payload: dict[str, Any],
    ) -> bool:
        if not self.is_configured():
            return False
        api_url = infra_settings.CENTRIFUGO_API_URL.strip().rstrip("/")
        api_key = infra_settings.CENTRIFUGO_API_KEY.strip()
        body = {
            "channel": channel,
            "data": self._envelope(event, payload),
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.post(
                    f"{api_url}/api/publish",
                    json=body,
                    headers={
                        "Authorization": f"apikey {api_key}",
                        "Content-Type": "application/json",
                    },
                )
            if response.status_code != 200:
                logger.warning(
                    "Centrifugo publish 失败 channel={} status={} body={}",
                    channel,
                    response.status_code,
                    response.text[:500],
                )
                return False
            parsed = response.json()
            if parsed.get("error"):
                logger.warning(
                    "Centrifugo publish 错误 channel={} error={}",
                    channel,
                    parsed.get("error"),
                )
                return False
            return True
        except Exception as exc:
            logger.warning("Centrifugo publish 异常 channel={}: {}", channel, exc)
            return False

    async def publish_to_user(
        self,
        *,
        tenant_id: int,
        user_id: int,
        event: str,
        payload: dict[str, Any],
    ) -> bool:
        channel = personal_channel(tenant_id=tenant_id, user_id=user_id)
        return await self.publish_to_channel(channel=channel, event=event, payload=payload)
