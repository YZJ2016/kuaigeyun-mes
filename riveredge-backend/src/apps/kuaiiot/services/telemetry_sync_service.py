"""ThingsBoard / JetLinks 遥测拉取并入站。"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from apps.kuaiiot.models.iot import IotConnection, IotDevice
from apps.kuaiiot.schemas.iot import ConnectorPullTelemetryResponse, IngestPayload
from apps.kuaiiot.services.connection_service import ConnectionService
from apps.kuaiiot.services.ingest_service import IngestService
from infra.domain.tenant_context import unscoped, with_tenant
from infra.exceptions.exceptions import ValidationError


class TelemetrySyncService:
    @staticmethod
    async def pull_connection(tenant_id: int, connection_uuid: str) -> ConnectorPullTelemetryResponse:
        connection = await ConnectionService.get_by_uuid(tenant_id, connection_uuid)
        if not connection.is_enabled:
            raise ValidationError("连接源未启用")
        if connection.connection_type not in {"thingsboard", "jetlinks"}:
            raise ValidationError(f"连接类型不支持遥测拉取: {connection.connection_type}")

        devices = await IotDevice.filter(
            tenant_id=tenant_id,
            connection_id=connection.id,
            deleted_at__isnull=True,
        )
        ingested = 0
        skipped = 0
        async with httpx.AsyncClient(timeout=20.0) as client:
            for device in devices:
                try:
                    tags = await TelemetrySyncService._fetch_device_tags(client, connection, device)
                except Exception as exc:  # pragma: no cover
                    logger.warning(
                        "kuaiiot telemetry pull failed tenant={} device={}: {}",
                        tenant_id,
                        device.uuid,
                        exc,
                    )
                    skipped += 1
                    continue
                if not tags:
                    skipped += 1
                    continue
                await IngestService.ingest(device.device_token, IngestPayload(tags=tags))
                ingested += 1

        return ConnectorPullTelemetryResponse(
            ingested_devices=ingested,
            skipped_devices=skipped,
            message="ok",
        )

    @staticmethod
    async def pull_all_enabled_connections() -> dict[str, int]:
        async with unscoped(reason="扫描已启用连接器遥测拉取连接", resource="IotConnection"):
            connections = await IotConnection.filter(
                connection_type__in=["thingsboard", "jetlinks"],
                is_enabled=True,
                deleted_at__isnull=True,
            )
        ingested = 0
        skipped = 0
        connections_processed = 0
        for connection in connections:
            async with with_tenant(int(connection.tenant_id), reason="连接器遥测拉取写入所属租户"):
                result = await TelemetrySyncService.pull_connection(connection.tenant_id, connection.uuid)
            ingested += result.ingested_devices
            skipped += result.skipped_devices
            connections_processed += 1
        return {
            "connections_processed": connections_processed,
            "ingested_devices": ingested,
            "skipped_devices": skipped,
        }

    @staticmethod
    async def _fetch_device_tags(
        client: httpx.AsyncClient,
        connection: IotConnection,
        device: IotDevice,
    ) -> dict[str, Any]:
        if connection.connection_type == "thingsboard":
            return await TelemetrySyncService._fetch_thingsboard_tags(client, connection, device)
        return await TelemetrySyncService._fetch_jetlinks_tags(client, connection, device)

    @staticmethod
    async def _fetch_thingsboard_tags(
        client: httpx.AsyncClient,
        connection: IotConnection,
        device: IotDevice,
    ) -> dict[str, Any]:
        config = connection.config or {}
        base_url = (config.get("base_url") or "").rstrip("/")
        username = config.get("username")
        password = config.get("password")
        if not base_url or not username or not password:
            raise ValidationError("ThingsBoard 配置不完整，需要 base_url / username / password")

        login_resp = await client.post(
            f"{base_url}/api/auth/login",
            json={"username": username, "password": password},
        )
        login_resp.raise_for_status()
        token = login_resp.json().get("token")
        if not token:
            raise ValidationError("ThingsBoard 登录失败：未返回 token")

        resp = await client.get(
            f"{base_url}/api/plugins/telemetry/DEVICE/{device.external_device_id}/values/timeseries",
            headers={"X-Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        payload = resp.json() or {}
        tags: dict[str, Any] = {}
        for key, values in payload.items():
            if not values:
                continue
            latest = values[0]
            tags[key] = latest.get("value")
        return tags

    @staticmethod
    async def _fetch_jetlinks_tags(
        client: httpx.AsyncClient,
        connection: IotConnection,
        device: IotDevice,
    ) -> dict[str, Any]:
        config = connection.config or {}
        base_url = (config.get("base_url") or "").rstrip("/")
        token = config.get("token")
        if not base_url or not token:
            raise ValidationError("JetLinks 配置不完整，需要 base_url / token")

        headers = {"X-Access-Token": token}
        resp = await client.get(
            f"{base_url}/device/instance/{device.external_device_id}/properties/latest",
            headers=headers,
        )
        if resp.status_code == 404:
            resp = await client.post(
                f"{base_url}/device/instance/{device.external_device_id}/properties/_latest",
                headers=headers,
            )
        resp.raise_for_status()
        payload = resp.json()
        rows = payload.get("result") if isinstance(payload, dict) and "result" in payload else payload
        if not isinstance(rows, list):
            return {}
        tags: dict[str, Any] = {}
        for item in rows:
            if not isinstance(item, dict):
                continue
            key = item.get("property") or item.get("id")
            if key is None:
                continue
            tags[str(key)] = item.get("value")
        return tags
