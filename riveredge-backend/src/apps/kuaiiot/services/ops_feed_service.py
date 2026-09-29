"""设备运营馈送。只读本租户绑定设备，并登记一条报表 HTTP 数据源。"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional
from urllib.parse import urlparse

from apps.kuaiiot.constants import SENSOR_DATA_SOURCE
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaireport.models.dashboard import KuaireportDashboard
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
# 迁移 464：未删除行上 (tenant_id, code) 唯一。已有该 code 不覆盖。
EQUIPMENT_OPS_DASHBOARD_CODE = "equipment-ops"
EQUIPMENT_OPS_DASHBOARD_NAME = "设备运营大屏"
_PG_PLACEHOLDER = re.compile(r"\$\d+(?:::jsonb)?")
_SITE_ROOT_MESSAGE = "请配置站点根地址"
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


def _feed_url() -> str:
    return _public_site_root() + FEED_PATH


def _path_is_feed(url: Any) -> bool:
    if not isinstance(url, str) or not url.strip():
        return False
    path = urlparse(url.strip()).path.rstrip("/")
    return path == FEED_PATH or path.endswith(FEED_PATH)


def _is_internal_address_error(exc: ValidationError) -> bool:
    return "内网" in exc.message or "本机" in exc.message


def _ops_widgets(source_id: int) -> list[dict[str, Any]]:
    """组件用执行器读取的 data_source_id。指标字段来自馈送 JSON。"""
    bound = int(source_id)

    def widget(
        widget_id: str,
        widget_type: str,
        title: str,
        options: dict[str, Any],
        layout: dict[str, int],
    ) -> dict[str, Any]:
        return {
            "id": widget_id,
            "type": widget_type,
            "data_source_id": bound,
            "refresh_seconds": 30,
            "title": title,
            "options": options,
            "layout": layout,
        }

    return [
        widget(
            "oee",
            "metric",
            "OEE",
            {"field": "ops_metrics.oee_live"},
            {"x": 0, "y": 0, "w": 4, "h": 4},
        ),
        widget(
            "availability",
            "metric",
            "可用率",
            {"field": "ops_metrics.availability_rate"},
            {"x": 4, "y": 0, "w": 4, "h": 4},
        ),
        widget(
            "quality",
            "metric",
            "良品率",
            {"field": "ops_metrics.quality_rate"},
            {"x": 8, "y": 0, "w": 4, "h": 4},
        ),
        widget(
            "status",
            "chart",
            "状态分布",
            {
                "chart_type": "bar",
                "field": "status_dist",
                "x_field": "status",
                "y_field": "count",
            },
            {"x": 0, "y": 4, "w": 6, "h": 8},
        ),
        widget(
            "workshop",
            "chart",
            "车间设备",
            {
                "chart_type": "bar",
                "field": "workshop_stats",
                "x_field": "workshop_name",
                "y_field": "equipment_count",
            },
            {"x": 6, "y": 4, "w": 6, "h": 8},
        ),
        widget(
            "ops",
            "chart",
            "设备OEE",
            {
                "chart_type": "bar",
                "field": "ops_metrics",
                "x_field": "code",
                "y_field": "oee_live",
            },
            {"x": 0, "y": 12, "w": 12, "h": 8},
        ),
    ]


class _SqliteVersionConn:
    """149 的版本插入使用 $n / ::jsonb。sqlite 测试改成 ?，生产连接原样传递。"""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    async def execute_query_dict(self, sql: str, params: Optional[list] = None) -> list:
        return await self._conn.execute_query_dict(_PG_PLACEHOLDER.sub("?", sql), params)

    async def execute_query(self, sql: str, params: Optional[list] = None) -> Any:
        return await self._conn.execute_query(_PG_PLACEHOLDER.sub("?", sql), params)


def _version_conn(conn: Any) -> Any:
    dialect = getattr(getattr(conn, "capabilities", None), "dialect", "")
    if dialect == "sqlite":
        return _SqliteVersionConn(conn)
    return conn


async def _feed_source(tenant_id: int) -> Optional[KuaireportDataSource]:
    rows = await KuaireportDataSource.filter(tenant_id=tenant_id, type="http").order_by("id")
    matches = [row for row in rows if _path_is_feed((row.config or {}).get("url"))]
    return matches[0] if matches else None


async def _seed_equipment_ops_dashboard(tenant_id: int, source: KuaireportDataSource) -> None:
    """本租户已有同 code 大屏则保留。无租户上下文不写。"""
    current = get_current_tenant_id()
    if current is None or int(current) != int(tenant_id):
        return
    if source.id is None:
        return
    from tortoise.exceptions import IntegrityError
    from tortoise.transactions import in_transaction

    from apps.kuaireport.slices.s148_share import validate_widgets
    from apps.kuaireport.slices.s149_distribution import (
        TortoiseDistributionStore,
        append_dashboard_version,
    )

    widgets = validate_widgets(_ops_widgets(int(source.id)))
    configs = {
        "layout_config": {"cols": 12},
        "widgets_config": widgets,
        "theme_config": {"background": "#001529"},
        "tv_config": {"rotate_seconds": 60},
    }
    try:
        async with in_transaction() as conn:
            existing = await KuaireportDashboard.filter(
                tenant_id=tenant_id,
                code=EQUIPMENT_OPS_DASHBOARD_CODE,
            ).using_db(conn).first()
            if existing is not None:
                return
            row = await KuaireportDashboard.create(
                tenant_id=tenant_id,
                code=EQUIPMENT_OPS_DASHBOARD_CODE,
                name=EQUIPMENT_OPS_DASHBOARD_NAME,
                layout_config=configs["layout_config"],
                widgets_config=widgets,
                theme_config=configs["theme_config"],
                tv_config=configs["tv_config"],
                status="DRAFT",
                is_shared=False,
                current_version=1,
                using_db=conn,
            )
            await append_dashboard_version(
                TortoiseDistributionStore(_version_conn(conn)),
                tenant_id,
                int(row.id),
                configs,
                version_no=1,
            )
    except IntegrityError:
        return


async def ensure_equipment_ops_http_source(tenant_id: int) -> None:
    """本租户只保留一条馈送 HTTP 登记。登记成功后再种入大屏。

    一律经星报表服务层登记（审计字段与 spec145 校验一致，localhost/127.0.0.1 已放行）。
    服务层因内网地址校验拒绝时跳过登记与种入，馈送本身照常返回。
    """
    url = _feed_url()
    current = await _feed_source(tenant_id)
    if current is not None and (current.config or {}).get("url") == url:
        await _seed_equipment_ops_dashboard(tenant_id, current)
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
        else:
            await update_data_source(
                tenant_id,
                current.id,
                DataSourceUpdate(config={"url": url}),
            )
    except ValidationError as exc:
        if _is_internal_address_error(exc):
            return
        raise
    saved = await _feed_source(tenant_id)
    if saved is not None:
        await _seed_equipment_ops_dashboard(tenant_id, saved)


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
    if isinstance(hours, bool) or not isinstance(hours, int) or hours < 1 or hours > 720:
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
