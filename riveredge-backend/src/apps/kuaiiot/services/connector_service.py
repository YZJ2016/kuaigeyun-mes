"""ThingsBoard / JetLinks 连接器适配。"""

from __future__ import annotations

from typing import Any, Dict, List

import httpx
from loguru import logger

from apps.kuaiiot.models.iot import IotConnection, IotDevice
from apps.kuaiiot.schemas.iot import ConnectorSyncResponse
from apps.kuaiiot.services.connection_service import ConnectionService
from apps.kuaiiot.services.mqtt_subscriber_service import MqttSubscriberService
from infra.exceptions.exceptions import ValidationError


class ConnectorService:
    @staticmethod
    async def sync_connection(tenant_id: int, connection_uuid: str) -> ConnectorSyncResponse:
        connection = await ConnectionService.get_by_uuid(tenant_id, connection_uuid)
        if not connection.is_enabled:
            raise ValidationError("连接源未启用")

        if connection.connection_type == "thingsboard":
            devices = await ConnectorService._fetch_thingsboard_devices(connection)
        elif connection.connection_type == "jetlinks":
            devices = await ConnectorService._fetch_jetlinks_devices(connection)
        else:
            raise ValidationError(f"连接类型不支持同步: {connection.connection_type}")

        synced = 0
        for item in devices:
            external_id = str(item.get("id") or item.get("deviceId") or item.get("name"))
            name = str(item.get("name") or external_id)
            code = external_id[:50]
            existing = await IotDevice.filter(
                tenant_id=tenant_id,
                connection_id=connection.id,
                external_device_id=external_id,
                deleted_at__isnull=True,
            ).first()
            if existing:
                existing.name = name
                await existing.save()
                continue
            code_exists = await IotDevice.filter(
                tenant_id=tenant_id, code=code, deleted_at__isnull=True
            ).exists()
            if code_exists:
                code = f"{code[:40]}-{connection.id}"
            await IotDevice.create(
                tenant_id=tenant_id,
                connection_id=connection.id,
                external_device_id=external_id,
                code=code,
                name=name,
            )
            synced += 1

        await ConnectionService.touch_health(tenant_id, connection_uuid, healthy=True)
        return ConnectorSyncResponse(synced_devices=synced, message="ok")

    @staticmethod
    async def _fetch_thingsboard_devices(connection: IotConnection) -> List[Dict[str, Any]]:
        config = connection.config or {}
        base_url = (config.get("base_url") or "").rstrip("/")
        username = config.get("username")
        password = config.get("password")
        if not base_url or not username or not password:
            raise ValidationError("ThingsBoard 配置不完整，需要 base_url / username / password")

        async with httpx.AsyncClient(timeout=20.0) as client:
            login_resp = await client.post(
                f"{base_url}/api/auth/login",
                json={"username": username, "password": password},
            )
            login_resp.raise_for_status()
            token = login_resp.json().get("token")
            if not token:
                raise ValidationError("ThingsBoard 登录失败：未返回 token")

            devices_resp = await client.get(
                f"{base_url}/api/tenant/devices",
                params={"pageSize": 100, "page": 0},
                headers={"X-Authorization": f"Bearer {token}"},
            )
            devices_resp.raise_for_status()
            data = devices_resp.json()
            return data.get("data") or []

    @staticmethod
    async def _fetch_jetlinks_devices(connection: IotConnection) -> List[Dict[str, Any]]:
        config = connection.config or {}
        base_url = (config.get("base_url") or "").rstrip("/")
        token = config.get("token")
        if not base_url or not token:
            raise ValidationError("JetLinks 配置不完整，需要 base_url / token")

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{base_url}/device/instance/_query",
                json={"pageIndex": 0, "pageSize": 100},
                headers={"X-Access-Token": token},
            )
            resp.raise_for_status()
            payload = resp.json()
            result = payload.get("result") or {}
            return result.get("data") or []

    @staticmethod
    async def health_check(tenant_id: int, connection_uuid: str) -> IotConnection:
        connection = await ConnectionService.get_by_uuid(tenant_id, connection_uuid)
        healthy = False
        try:
            if connection.connection_type == "thingsboard":
                await ConnectorService._fetch_thingsboard_devices(connection)
                healthy = True
            elif connection.connection_type == "jetlinks":
                await ConnectorService._fetch_jetlinks_devices(connection)
                healthy = True
            elif connection.connection_type == "mqtt":
                healthy = await MqttSubscriberService.probe_broker(connection)
            elif connection.connection_type == "http_webhook":
                healthy = True
        except Exception as exc:  # pragma: no cover
            logger.warning("kuaiiot connection health failed: {}", exc)
            healthy = False
        return await ConnectionService.touch_health(tenant_id, connection_uuid, healthy=healthy)

    @staticmethod
    async def invoke_device_function(
        tenant_id: int,
        device: IotDevice,
        *,
        function_key: str,
        params: dict[str, Any],
        function_def: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not device.connection_id:
            raise ValidationError("设备未绑定连接源，无法调用上游功能")
        connection = await IotConnection.filter(
            tenant_id=tenant_id,
            id=device.connection_id,
            deleted_at__isnull=True,
        ).first()
        if not connection or not connection.is_enabled:
            raise ValidationError("连接源不存在或未启用")
        if connection.connection_type == "thingsboard":
            return await ConnectorService._invoke_thingsboard_rpc(connection, device, function_key, params)
        if connection.connection_type == "jetlinks":
            return await ConnectorService._invoke_jetlinks_function(connection, device, function_key, params)
        raise ValidationError(f"连接类型不支持 RPC: {connection.connection_type}")

    @staticmethod
    async def _invoke_thingsboard_rpc(
        connection: IotConnection,
        device: IotDevice,
        function_key: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        config = connection.config or {}
        base_url = (config.get("base_url") or "").rstrip("/")
        username = config.get("username")
        password = config.get("password")
        if not base_url or not username or not password:
            raise ValidationError("ThingsBoard 配置不完整")
        async with httpx.AsyncClient(timeout=20.0) as client:
            login_resp = await client.post(
                f"{base_url}/api/auth/login",
                json={"username": username, "password": password},
            )
            login_resp.raise_for_status()
            token = login_resp.json().get("token")
            if not token:
                raise ValidationError("ThingsBoard 登录失败")
            device_id = device.external_device_id
            resp = await client.post(
                f"{base_url}/api/plugins/rpc/twoway/{device_id}",
                json={"method": function_key, "params": params},
                headers={"X-Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            payload = resp.json()
            return payload if isinstance(payload, dict) else {"result": payload}

    @staticmethod
    async def _invoke_jetlinks_function(
        connection: IotConnection,
        device: IotDevice,
        function_key: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        config = connection.config or {}
        base_url = (config.get("base_url") or "").rstrip("/")
        token = config.get("token")
        if not base_url or not token:
            raise ValidationError("JetLinks 配置不完整")
        device_id = device.external_device_id
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{base_url}/device/instance/{device_id}/function/{function_key}",
                json=params,
                headers={"X-Access-Token": token},
            )
            resp.raise_for_status()
            payload = resp.json()
            result = payload.get("result") if isinstance(payload, dict) else payload
            return result if isinstance(result, dict) else {"result": result}

    @staticmethod
    async def invoke_device_function(
        tenant_id: int,
        device: IotDevice,
        *,
        function_key: str,
        params: dict[str, Any],
        function_def: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not device.connection_id:
            raise ValidationError("设备未绑定连接源，无法调用上游功能")
        connection = await IotConnection.filter(
            tenant_id=tenant_id,
            id=device.connection_id,
            deleted_at__isnull=True,
        ).first()
        if not connection or not connection.is_enabled:
            raise ValidationError("连接源不存在或未启用")
        if connection.connection_type == "thingsboard":
            return await ConnectorService._invoke_thingsboard_rpc(connection, device, function_key, params)
        if connection.connection_type == "jetlinks":
            return await ConnectorService._invoke_jetlinks_function(connection, device, function_key, params)
        raise ValidationError(f"连接类型不支持 RPC: {connection.connection_type}")

    @staticmethod
    async def _invoke_thingsboard_rpc(
        connection: IotConnection,
        device: IotDevice,
        function_key: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        config = connection.config or {}
        base_url = (config.get("base_url") or "").rstrip("/")
        username = config.get("username")
        password = config.get("password")
        if not base_url or not username or not password:
            raise ValidationError("ThingsBoard 配置不完整")
        async with httpx.AsyncClient(timeout=20.0) as client:
            login_resp = await client.post(
                f"{base_url}/api/auth/login",
                json={"username": username, "password": password},
            )
            login_resp.raise_for_status()
            token = login_resp.json().get("token")
            if not token:
                raise ValidationError("ThingsBoard 登录失败")
            device_id = device.external_device_id
            resp = await client.post(
                f"{base_url}/api/plugins/rpc/twoway/{device_id}",
                json={"method": function_key, "params": params},
                headers={"X-Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            payload = resp.json()
            return payload if isinstance(payload, dict) else {"result": payload}

    @staticmethod
    async def _invoke_jetlinks_function(
        connection: IotConnection,
        device: IotDevice,
        function_key: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        config = connection.config or {}
        base_url = (config.get("base_url") or "").rstrip("/")
        token = config.get("token")
        if not base_url or not token:
            raise ValidationError("JetLinks 配置不完整")
        device_id = device.external_device_id
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{base_url}/device/instance/{device_id}/function/{function_key}",
                json=params,
                headers={"X-Access-Token": token},
            )
            resp.raise_for_status()
            payload = resp.json()
            result = payload.get("result") if isinstance(payload, dict) else payload
            return result if isinstance(result, dict) else {"result": result}
