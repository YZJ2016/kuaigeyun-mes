"""InfluxDB 点位历史存储。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from decimal import Decimal
from typing import Any, Optional
from zoneinfo import ZoneInfo

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from apps.kuaiiot.constants import TSDB_INTEGRATION_CODE
from apps.kuaiiot.schemas.iot import TagHistoryResponse
from core.models.integration_config import IntegrationConfig
from core.utils.timezone_utils import resolve_business_datetime, site_timezone_name, to_site_date
from infra.exceptions.exceptions import ValidationError


@dataclass(frozen=True)
class TagHistoryPoint:
    tag_key: str
    value_text: Optional[str]
    value_number: Optional[Decimal]
    value_bool: Optional[bool]
    sampled_at: datetime


class TagHistoryStore:
    MEASUREMENT = "tag_point"

    @staticmethod
    def _build_url(config: dict[str, Any]) -> str:
        url = str(config.get("url") or "").strip()
        if url:
            return url.rstrip("/")
        host = str(config.get("host") or "localhost").strip()
        port = int(config.get("port") or 8086)
        scheme = "https" if config.get("use_tls") else "http"
        return f"{scheme}://{host}:{port}"

    @staticmethod
    async def _load_config(tenant_id: int) -> Optional[dict[str, Any]]:
        item = await IntegrationConfig.filter(
            tenant_id=tenant_id,
            code=TSDB_INTEGRATION_CODE,
            type="influxdb",
            is_active=True,
            deleted_at__isnull=True,
        ).first()
        if not item or not item.config:
            return None
        config = dict(item.config)
        token = str(
            config.get("token") or config.get("password") or ""
        ).strip()
        org = str(
            config.get("org") or config.get("username") or config.get("user") or ""
        ).strip()
        bucket = str(config.get("bucket") or config.get("database") or "").strip()
        if not token or not org or not bucket:
            return None
        config["token"] = token
        config["org"] = org
        config["bucket"] = bucket
        config["url"] = TagHistoryStore._build_url(config)
        return config

    @staticmethod
    async def is_configured(tenant_id: int) -> bool:
        return (await TagHistoryStore._load_config(tenant_id)) is not None

    @staticmethod
    def _require_config(config: Optional[dict[str, Any]]) -> dict[str, Any]:
        if not config:
            raise ValidationError(
                f"未配置 InfluxDB 时序库，请在系统数据源创建 type=influxdb、code={TSDB_INTEGRATION_CODE} 的集成"
            )
        return config

    @staticmethod
    def _client(config: dict[str, Any]) -> InfluxDBClient:
        return InfluxDBClient(
            url=config["url"],
            token=config["token"],
            org=config["org"],
        )

    @staticmethod
    def _point_from_values(
        tenant_id: int,
        device_id: int,
        tag_key: str,
        value_text: Optional[str],
        value_number: Optional[Decimal],
        value_bool: Optional[bool],
        sampled_at: datetime,
    ) -> Point:
        point = (
            Point(TagHistoryStore.MEASUREMENT)
            .tag("tenant_id", str(tenant_id))
            .tag("device_id", str(device_id))
            .tag("tag_key", tag_key)
        )
        if value_text is not None:
            point = point.field("value_text", value_text)
        if value_number is not None:
            point = point.field("value_number", float(value_number))
        if value_bool is not None:
            point = point.field("value_bool", value_bool)
        if value_text is None and value_number is None and value_bool is None:
            point = point.field("value_text", "")
        timestamp = sampled_at
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return point.time(timestamp)

    @staticmethod
    async def write_points(
        tenant_id: int,
        device_id: int,
        points: list[TagHistoryPoint],
    ) -> None:
        if not points:
            return
        config = await TagHistoryStore._load_config(tenant_id)
        if not config:
            return
        influx_points = [
            TagHistoryStore._point_from_values(
                tenant_id=tenant_id,
                device_id=device_id,
                tag_key=item.tag_key,
                value_text=item.value_text,
                value_number=item.value_number,
                value_bool=item.value_bool,
                sampled_at=item.sampled_at,
            )
            for item in points
        ]
        client = TagHistoryStore._client(config)
        try:
            write_api = client.write_api(write_options=SYNCHRONOUS)
            write_api.write(bucket=config["bucket"], org=config["org"], record=influx_points)
        finally:
            client.close()

    @staticmethod
    def _site_day_start_utc() -> datetime:
        now = resolve_business_datetime()
        site_date = to_site_date(now)
        site_midnight = datetime.combine(site_date, time.min, tzinfo=ZoneInfo(site_timezone_name()))
        return site_midnight.astimezone(timezone.utc)

    @staticmethod
    async def count_points_today(tenant_id: int) -> int:
        config = await TagHistoryStore._load_config(tenant_id)
        if not config:
            return 0
        start = TagHistoryStore._site_day_start_utc().isoformat()
        flux = f'''
from(bucket: "{config["bucket"]}")
  |> range(start: {start})
  |> filter(fn: (r) => r._measurement == "{TagHistoryStore.MEASUREMENT}")
  |> filter(fn: (r) => r.tenant_id == "{tenant_id}")
  |> count()
  |> group()
  |> sum()
'''
        client = TagHistoryStore._client(config)
        try:
            tables = client.query_api().query(flux, org=config["org"])
        finally:
            client.close()
        total = 0
        for table in tables:
            for record in table.records:
                value = record.get_value()
                if isinstance(value, (int, float)):
                    total += int(value)
        return total

    @staticmethod
    async def query_history(
        tenant_id: int,
        device_id: int,
        tag_key: Optional[str] = None,
        limit: int = 100,
    ) -> list[TagHistoryResponse]:
        config = TagHistoryStore._require_config(await TagHistoryStore._load_config(tenant_id))
        limit = max(1, min(limit, 500))
        tag_filter = ""
        if tag_key:
            tag_filter = f'|> filter(fn: (r) => r.tag_key == "{tag_key}")'
        flux = f'''
from(bucket: "{config["bucket"]}")
  |> range(start: -7d)
  |> filter(fn: (r) => r._measurement == "{TagHistoryStore.MEASUREMENT}")
  |> filter(fn: (r) => r.tenant_id == "{tenant_id}")
  |> filter(fn: (r) => r.device_id == "{device_id}")
  {tag_filter}
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: {limit * 3})
'''
        client = TagHistoryStore._client(config)
        try:
            tables = client.query_api().query(flux, org=config["org"])
        finally:
            client.close()

        rows: dict[str, TagHistoryResponse] = {}
        for table in tables:
            for record in table.records:
                sampled_at = record.get_time()
                key = record.values.get("tag_key") or tag_key or ""
                if not key:
                    continue
                row_key = f"{key}:{sampled_at.isoformat()}"
                item = rows.get(row_key)
                if item is None:
                    item = TagHistoryResponse(
                        tag_key=key,
                        value_text=None,
                        value_number=None,
                        value_bool=None,
                        quality="good",
                        sampled_at=sampled_at,
                    )
                    rows[row_key] = item
                field_name = record.get_field()
                value = record.get_value()
                if field_name == "value_text":
                    item.value_text = str(value) if value is not None else None
                elif field_name == "value_number":
                    item.value_number = Decimal(str(value)) if value is not None else None
                elif field_name == "value_bool":
                    item.value_bool = bool(value) if value is not None else None
        ordered = sorted(rows.values(), key=lambda item: item.sampled_at, reverse=True)
        return ordered[:limit]
