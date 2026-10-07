"""数值点位趋势。只使用本租户已启用的 kuaiiot_tsdb 集成，不读写 tag_history。"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from typing import Any

from apps.kuaiiot.constants import TSDB_INTEGRATION_CODE, TSDB_INTEGRATION_TYPE
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.models.tag import KuaiiotTagDefinition
from apps.kuaiiot.services.tag_template_service import _require_tenant
from core.models.integration_config import IntegrationConfig
from infra.exceptions.exceptions import NotFoundError, ValidationError

_UNAVAILABLE = "趋势不可用"
_MEASUREMENT = "kuaiiot_numeric"


def _config_text(config: dict, key: str) -> str:
    value = config.get(key)
    if not isinstance(value, str):
        raise ValidationError(_UNAVAILABLE)
    text = value.strip()
    if not text or any(char in text for char in '"\\\n\r'):
        raise ValidationError(_UNAVAILABLE)
    return text


async def _active_tsdb(tenant_id: int) -> dict[str, str]:
    tid = _require_tenant(tenant_id)
    row = await IntegrationConfig.filter(
        tenant_id=tid,
        code=TSDB_INTEGRATION_CODE,
        type=TSDB_INTEGRATION_TYPE,
        is_active=True,
        deleted_at__isnull=True,
    ).first()
    if row is None:
        raise ValidationError(_UNAVAILABLE)
    config = row.get_config()
    if not isinstance(config, dict):
        raise ValidationError(_UNAVAILABLE)
    return {
        "url": _config_text(config, "url"),
        "org": _config_text(config, "org"),
        "bucket": _config_text(config, "bucket"),
        "token": _config_text(config, "token"),
    }


def _flux_time(value: datetime) -> str:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def _numeric_tag(tenant_id: int, device_id: int, tag_key: str) -> KuaiiotTagDefinition:
    device = await KuaiiotDevice.filter(
        tenant_id=tenant_id,
        id=device_id,
        deleted_at__isnull=True,
    ).first()
    if device is None:
        raise NotFoundError("IoT 设备不存在")
    key = (tag_key or "").strip()
    if not key or any(char in key for char in ',=\'"\\\n\r {}'):
        raise ValidationError("点位键无效")
    definition = await KuaiiotTagDefinition.filter(
        tenant_id=tenant_id,
        device_id=device.id,
        tag_key=key,
        deleted_at__isnull=True,
    ).first()
    if definition is None:
        raise NotFoundError("点位不存在")
    if definition.value_type != "number":
        raise ValidationError("趋势只接受数值点位")
    return definition


def _open_client(settings: dict[str, str]):
    from influxdb_client import InfluxDBClient

    return InfluxDBClient(url=settings["url"], token=settings["token"], org=settings["org"])


def _unavailable_from_client(exc: Exception) -> ValidationError:
    del exc
    return ValidationError(_UNAVAILABLE)


async def write_trend(
    tenant_id: int,
    *,
    device_id: int,
    tag_key: str,
    value: float | None,
    quality: str = "good",
    sampled_at: datetime | None = None,
) -> None:
    tid = _require_tenant(tenant_id)
    settings = await _active_tsdb(tid)
    if quality not in {"good", "bad", "uncertain"}:
        raise ValidationError("趋势质量无效")
    number = None
    if quality == "good":
        if isinstance(value, bool):
            raise ValidationError("趋势只接受数值点位")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError("趋势只接受数值点位") from exc
        if not math.isfinite(number):
            raise ValidationError("趋势值必须是有限数值")
    definition = await _numeric_tag(tid, device_id, tag_key)
    when = sampled_at or datetime.now(timezone.utc)
    # naive 时间戳统一按 UTC 解释，与 _flux_time 口径一致
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    delta = when.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    timestamp_ns = (delta.days * 86400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1000
    fields = f'quality="{quality}"'
    if number is not None:
        fields = f"value={number}," + fields
    line = (
        f"{_MEASUREMENT},device_id={definition.device_id},tag_key={definition.tag_key} "
        f"{fields} {timestamp_ns}"
    )
    try:
        from influxdb_client.client.write_api import SYNCHRONOUS

        client = _open_client(settings)
        try:
            # InfluxDBClient 是同步客户端，读写放到线程避免阻塞事件循环
            await asyncio.to_thread(
                client.write_api(write_options=SYNCHRONOUS).write,
                bucket=settings["bucket"],
                org=settings["org"],
                record=line,
            )
        finally:
            client.close()
    except ValidationError:
        raise
    except Exception:
        raise ValidationError(_UNAVAILABLE) from None


async def query_trend(
    tenant_id: int,
    *,
    device_id: int,
    tag_key: str,
    start: datetime,
    stop: datetime,
) -> list[dict[str, Any]]:
    tid = _require_tenant(tenant_id)
    settings = await _active_tsdb(tid)
    if start >= stop:
        raise ValidationError("趋势时间范围无效")
    definition = await _numeric_tag(tid, device_id, tag_key)
    flux = (
        f'from(bucket: "{settings["bucket"]}")'
        f" |> range(start: {_flux_time(start)}, stop: {_flux_time(stop)})"
        f' |> filter(fn: (r) => r._measurement == "{_MEASUREMENT}"'
        f' and r.device_id == "{definition.device_id}"'
        f' and r.tag_key == "{definition.tag_key}"'
        f' and r._field == "value")'
    )
    try:
        client = _open_client(settings)
        try:
            tables = await asyncio.to_thread(
                client.query_api().query, flux, org=settings["org"]
            )
        finally:
            client.close()
    except ValidationError:
        raise
    except Exception as exc:
        raise _unavailable_from_client(exc) from None
    if not isinstance(tables, (list, tuple)):
        raise ValidationError(_UNAVAILABLE)
    points: list[dict[str, Any]] = []
    for table in tables:
        for record in getattr(table, "records", []) or []:
            points.append({"time": record.get_time(), "value": float(record.get_value())})
    return points
