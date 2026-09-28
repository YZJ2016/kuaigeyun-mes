"""设备运营馈送。只读本租户绑定设备，并登记一条报表 HTTP 数据源。"""

from __future__ import annotations

import ipaddress
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional
from urllib.parse import urlparse

from apps.kuaiiot.constants import SENSOR_DATA_SOURCE
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaireport.models.data_source import KuaireportDataSource
from apps.kuaireport.schemas.data_source import DataSourceCreate, DataSourceUpdate
from apps.kuaireport.services.data_source_service import create_data_source, update_data_source
from apps.kuaizhizao.models.equipment import Equipment
from apps.kuaizhizao.models.equipment_ops import EquipmentSpotCheck
from apps.kuaizhizao.models.equipment_status_monitor import EquipmentStatusMonitor
from apps.kuaizhizao.models.reporting_record import ReportingRecord
from core.utils.timezone_utils import resolve_business_datetime, to_site_date
from infra.config.infra_config import infra_settings as settings
from infra.domain.tenant_context import get_current_tenant_id
from infra.exceptions.exceptions import ValidationError

FEED_PATH = "/api/v1/apps/kuaiiot/analytics/equipment-ops-feed"
FEED_SOURCE_NAME = "设备运营馈送"
_SITE_ROOT_MESSAGE = "请配置站点根地址"
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_RUNNING_STATUS = "运行中"
_RATE = Decimal("0.0001")
_RECENT_SPOT_CHECKS = 20


def _empty_feed() -> dict[str, list]:
    return {
        "equipment_list": [],
        "ops_metrics": [],
        "status_dist": [],
        "workshop_stats": [],
        "spot_check_recent": [],
    }


def _utc(value: datetime) -> datetime:
    return resolve_business_datetime(value)


def _public_site_root() -> str:
    raw = (settings.BASE_URL or "").strip().rstrip("/")
    if not raw:
        raise ValidationError(_SITE_ROOT_MESSAGE)
    return raw


def _feed_host(url: str) -> str:
    return (urlparse(url).hostname or "").strip().lower()


def _is_loopback_url(url: str) -> bool:
    host = _feed_host(url)
    if host in _LOOPBACK_HOSTS or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _skip_private_registration(url: str) -> bool:
    """内网地址不登记，避免报表执行器去拉内网。回环地址留给本地测试。"""
    if _is_loopback_url(url):
        return False
    host = _feed_host(url)
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(
        ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_multicast
    )


def _feed_url() -> str:
    return _public_site_root() + FEED_PATH


def _path_is_feed(url: Any) -> bool:
    if not isinstance(url, str) or not url.strip():
        return False
    path = urlparse(url.strip()).path.rstrip("/")
    return path == FEED_PATH or path.endswith(FEED_PATH)


def _is_internal_address_error(exc: ValidationError) -> bool:
    return "内网" in exc.message or "本机" in exc.message


async def _write_loopback_feed_row(
    tenant_id: int,
    url: str,
    existing: Optional[KuaireportDataSource],
) -> None:
    """回环地址写登记行。星报表校验拒绝本机地址，本地测试不走那条拒绝。"""
    if existing is None:
        await KuaireportDataSource.create(
            tenant_id=tenant_id,
            name=FEED_SOURCE_NAME,
            type="http",
            config={"url": url},
        )
        return
    existing.config = {"url": url}
    await existing.save(update_fields=["config", "updated_at"])


async def ensure_equipment_ops_http_source(tenant_id: int) -> None:
    """本租户只保留一条馈送 HTTP 登记。内网地址不插行，调用方仍返回馈送。"""
    url = _feed_url()
    if _skip_private_registration(url):
        return
    rows = await KuaireportDataSource.filter(tenant_id=tenant_id, type="http").order_by("id")
    matches = [row for row in rows if _path_is_feed((row.config or {}).get("url"))]
    current = matches[0] if matches else None
    if current is not None and (current.config or {}).get("url") == url:
        return
    if _is_loopback_url(url):
        await _write_loopback_feed_row(tenant_id, url, current)
        return
    try:
        if current is None:
            await create_data_source(
                tenant_id,
                DataSourceCreate(
                    name=FEED_SOURCE_NAME,
                    type="http",
                    config={"url": url},
                ),
            )
            return
        await update_data_source(
            tenant_id,
            current.id,
            DataSourceUpdate(config={"url": url}),
        )
    except ValidationError as exc:
        if _is_internal_address_error(exc):
            return
        raise


def _matches_equipment(device_info: Any, equipment: Equipment) -> bool:
    if not isinstance(device_info, dict):
        return False
    device_id = device_info.get("equipment_id") or device_info.get("id")
    device_code = device_info.get("equipment_code") or device_info.get("code")
    return device_id == equipment.id or device_code == equipment.code


def _availability(rows: list[EquipmentStatusMonitor], end: datetime) -> Optional[float]:
    ordered = sorted(rows, key=lambda row: (_utc(row.monitored_at), row.id))
    if not ordered:
        return None
    running = Decimal(0)
    total = Decimal(0)
    window_end = _utc(end)
    for index, row in enumerate(ordered):
        start_at = _utc(row.monitored_at)
        stop_at = _utc(ordered[index + 1].monitored_at) if index + 1 < len(ordered) else window_end
        seconds = Decimal(str((stop_at - start_at).total_seconds()))
        if seconds <= 0:
            continue
        total += seconds
        if row.status == _RUNNING_STATUS:
            running += seconds
    if total <= 0:
        return None
    return float((running / total).quantize(_RATE))


def _quality(records: list[ReportingRecord], equipment: Equipment) -> Optional[float]:
    reported = Decimal(0)
    qualified = Decimal(0)
    for record in records:
        if not _matches_equipment(record.device_info, equipment):
            continue
        quantity = record.reported_quantity
        if quantity is None or Decimal(quantity) <= 0:
            continue
        reported += Decimal(quantity)
        qualified += Decimal(record.qualified_quantity or 0)
    if reported <= 0:
        return None
    return float((qualified / reported).quantize(_RATE))


def _oee(availability: Optional[float], quality: Optional[float]) -> Optional[float]:
    if availability is None or quality is None:
        return None
    return float((Decimal(str(availability)) * Decimal(str(quality))).quantize(_RATE))


def _latest(rows: list[EquipmentStatusMonitor]) -> Optional[EquipmentStatusMonitor]:
    if not rows:
        return None
    return max(rows, key=lambda row: (_utc(row.monitored_at), row.id))


async def _bound_equipment(tenant_id: int) -> list[Equipment]:
    devices = await KuaiiotDevice.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
        equipment_uuid__isnull=False,
    )
    uuids: list[str] = []
    seen: set[str] = set()
    for device in devices:
        text = (device.equipment_uuid or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        uuids.append(text)
    if not uuids:
        return []
    rows = await Equipment.filter(
        tenant_id=tenant_id,
        uuid__in=uuids,
        deleted_at__isnull=True,
    )
    return sorted(rows, key=lambda row: (row.code or "", row.id))


async def read_equipment_ops_feed(
    tenant_id: int,
    hours: int = 24,
    *,
    at: Optional[datetime] = None,
) -> dict[str, Any]:
    current = get_current_tenant_id()
    if current is None or int(current) != int(tenant_id):
        return _empty_feed()
    if isinstance(hours, bool) or not isinstance(hours, int) or hours < 1:
        raise ValidationError("查询窗口小时数无效")
    end = resolve_business_datetime(at)
    start = end - timedelta(hours=hours)
    equipment_rows = await _bound_equipment(tenant_id)
    if not equipment_rows:
        await ensure_equipment_ops_http_source(tenant_id)
        return _empty_feed()

    uuids = [row.uuid for row in equipment_rows]
    monitors = await EquipmentStatusMonitor.filter(
        tenant_id=tenant_id,
        equipment_uuid__in=uuids,
        data_source=SENSOR_DATA_SOURCE,
        deleted_at__isnull=True,
        monitored_at__gte=start,
        monitored_at__lte=end,
    )
    by_equipment: dict[str, list[EquipmentStatusMonitor]] = defaultdict(list)
    for row in monitors:
        by_equipment[row.equipment_uuid].append(row)

    reports = await ReportingRecord.filter(
        tenant_id=tenant_id,
        status="approved",
        deleted_at__isnull=True,
        reported_at__gte=start,
        reported_at__lte=end,
    )
    checks = await EquipmentSpotCheck.filter(
        tenant_id=tenant_id,
        equipment_uuid__in=uuids,
        deleted_at__isnull=True,
        check_date__gte=to_site_date(start),
        check_date__lte=to_site_date(end),
    ).order_by("-check_date", "-id").limit(_RECENT_SPOT_CHECKS)

    equipment_list: list[dict[str, Any]] = []
    ops_metrics: list[dict[str, Any]] = []
    status_counts: dict[str, int] = defaultdict(int)
    workshop_counts: dict[tuple[Any, Any], int] = defaultdict(int)
    for equipment in equipment_rows:
        segments = by_equipment.get(equipment.uuid, [])
        latest = _latest(segments)
        status = latest.status if latest is not None else None
        equipment_list.append(
            {
                "equipment_uuid": equipment.uuid,
                "equipment_id": equipment.id,
                "code": equipment.code,
                "name": equipment.name,
                "workshop_id": equipment.workshop_id,
                "workshop_name": equipment.workshop_name,
                "status": status,
                "is_online": latest.is_online if latest is not None else None,
            }
        )
        availability = _availability(segments, end)
        quality = _quality(reports, equipment)
        ops_metrics.append(
            {
                "equipment_uuid": equipment.uuid,
                "equipment_id": equipment.id,
                "code": equipment.code,
                "name": equipment.name,
                "availability_rate": availability,
                "quality_rate": quality,
                "oee_live": _oee(availability, quality),
            }
        )
        if status is not None:
            status_counts[status] += 1
        workshop_counts[(equipment.workshop_id, equipment.workshop_name)] += 1

    payload = {
        "equipment_list": equipment_list,
        "ops_metrics": ops_metrics,
        "status_dist": [
            {"status": status, "count": status_counts[status]}
            for status in sorted(status_counts)
        ],
        "workshop_stats": [
            {
                "workshop_id": workshop_id,
                "workshop_name": workshop_name,
                "equipment_count": workshop_counts[(workshop_id, workshop_name)],
            }
            for workshop_id, workshop_name in sorted(
                workshop_counts,
                key=lambda item: (item[0] is None, item[0] or 0, item[1] or ""),
            )
        ],
        "spot_check_recent": [
            {
                "equipment_uuid": row.equipment_uuid,
                "equipment_code": row.equipment_code,
                "equipment_name": row.equipment_name,
                "document_no": row.document_no,
                "check_date": row.check_date.isoformat() if row.check_date else None,
                "status": row.status,
                "has_abnormality": row.has_abnormality,
            }
            for row in checks
        ],
    }
    await ensure_equipment_ops_http_source(tenant_id)
    return payload
