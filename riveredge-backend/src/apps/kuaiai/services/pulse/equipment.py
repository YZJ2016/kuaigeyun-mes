"""设备 detector（spec 203 T2；spec 220 接入 kuaiiot 设备告警来源）。

规则（代码事实，非文案推断）：
- MES 故障单候选：``EquipmentFault.status`` 在未闭环闭集
  ``OPEN_FAULT_STATUSES``（待处理/处理中）内；闭集对齐
  ``equipment_fault_service._OPEN_FAULT_STATUSES``——驱动设备「故障」状态的
  同一口径；已修复/已关闭为终态（模型注释 ``status`` 取值
  待处理/处理中/已修复/已关闭，equipment_fault.py:88）；
- MES 故障单权限锚点 ``kuaizhizao:equipment-fault:read``，数据范围
  ``kuaizhizao:equipment-fault``（scope 键=页面功能码去 ``:read`` 段；
  manifest ``reference_resources`` 无故障专属 data_scope_key，无显式策略
  =全部，有策略按行级范围收敛）；
- MES 故障单路由 ``/apps/kuaizhizao/equipment-management/equipment-faults``
  （kuaizhizao manifest code_rule_pages.page_path）；
- MES 故障单严重度/优先级矩阵（确定性，由 ``fault_level`` 枚举
  轻微/一般/严重/紧急（模型注释 equipment_fault.py:81）决定；未知值兜底
  warning/medium 不臆造级别）：
  紧急 → critical/high；严重 → error/high；一般 → warning/medium；
  轻微 → info/low。故障持续时长只用于排序与事实描述，不改判定。

spec 220（X8=a 来源级权限）：
- 设备领域升级为两来源：``equipment_fault``（MES 故障单）与
  ``iot_alert``（kuaiiot 未处理告警，按设备聚合：告警数/最新级别/最新时间）。
  同设备两源并存时各出一条信号，不合并去重（不同事实：有人报修 vs
  传感器告警）；
- 两来源独立判权：均无权限 → 抛 ``PulsePermissionDenied``（沿用
  「无权限整领域隐藏」）；仅一方有权 → 有权来源出信号，无权来源出
  ``no_permission`` 占位（signals 恒空，不查数不泄露）；
- kuaiiot 可用性沿用 spec 212 ``_plm_enabled`` 模式：
  ``ApplicationService.get_application_by_code`` 的
  ``is_installed``+``is_active``；未安装/判不可用 → 整体跳过该来源
  （不出现在 sources，不产生占位）；
- IoT 来源独立短超时 ``IOT_SOURCE_TIMEOUT``：超时/读取失败 →
  ``unavailable``，不影响 MES 故障单部分；
- kuaiiot ``IotAlert`` 事实表：status 闭集 open|acknowledged（模型注释，
  代码另写 recovered/closed 终态），「未处理」口径=status=='open'
  （与 kuaiiot dashboard 未处理告警同一口径）；severity 闭集
  info|warning|critical；告警路由 ``/apps/kuaiiot/alerts``（kuaiiot
  manifest menu_config，权限 ``kuaiiot:alert:read``）；
- 跨应用调用只传 tenant_id 与已判权参数；IoT 告警无 data_scope_key
  （kuaiiot manifest 无 reference_resources），仅租户隔离；
- IoT 级别映射：critical→critical/high；warning→warning/medium；
  info→info/low；未知值兜底 warning/medium。
"""

from __future__ import annotations

import asyncio
from typing import Dict, List, Optional, Tuple

from loguru import logger

from apps.kuaiai.schemas.pulse import PulseItemOut
from apps.kuaiai.services.pulse.base import (
    PulseContext,
    PulseDetectResult,
    PulsePermissionDenied,
    PulseSourceResult,
    apply_scope,
    business_date,
    has_permission,
)

DOMAIN = "equipment"
RULE_CODE = "equipment_fault"
REQUIRED_PERMISSION = "kuaizhizao:equipment-fault:read"
SCOPE_RESOURCE = "kuaizhizao:equipment-fault"
ROUTE = "/apps/kuaizhizao/equipment-management/equipment-faults"
FAULT_SOURCE_LABEL = "设备故障单"

# spec 220：kuaiiot 告警来源
IOT_APP = "kuaiiot"
IOT_RULE_CODE = "iot_alert"
IOT_PERMISSION = "kuaiiot:alert:read"
IOT_ROUTE = "/apps/kuaiiot/alerts"
IOT_SOURCE_LABEL = "IoT 设备告警"
IOT_SOURCE_TIMEOUT = 3.0
IOT_ALERT_PAGE_SIZE = 200
# 翻页硬上限：并发新增令 total 前移时窗口内仍有界（外层 3s 超时为最终兜底）；
# 达到上限照常按已拉取部分聚合，并在日志注明截断
IOT_ALERT_MAX_PAGES = 10

# 单次数据库读取上限；完整 detector 在 wait_for/cancellation 约束内分批扫描。
SCAN_BATCH_SIZE = 200

# 未闭环闭集：与 equipment_fault_service._OPEN_FAULT_STATUSES
# （待处理/处理中）逐项对齐；已修复/已关闭不出现。
OPEN_FAULT_STATUSES: Tuple[str, ...] = ("待处理", "处理中")

# IoT「未处理」闭集：open（acknowledged/recovered/closed 均视为已介入）。
OPEN_ALERT_STATUSES: Tuple[str, ...] = ("open",)

# 故障描述摘要长度上限（fact 只放摘要，不回全文）。
_DESCRIPTION_SUMMARY_MAX = 80

_IOT_SEVERITY_ZH = {"critical": "紧急", "warning": "警告", "info": "提示"}


def _severity_priority(fault_level: str) -> Tuple[str, str]:
    level = str(fault_level or "").strip()
    if level == "紧急":
        return "critical", "high"
    if level == "严重":
        return "error", "high"
    if level == "轻微":
        return "info", "low"
    # 一般及未知值统一 warning/medium
    return "warning", "medium"


def _iot_severity_priority(alert_severity: str) -> Tuple[str, str]:
    level = str(alert_severity or "").strip()
    if level == "critical":
        return "critical", "high"
    if level == "info":
        return "info", "low"
    # warning 及未知值统一 warning/medium
    return "warning", "medium"


def _description_summary(value) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > _DESCRIPTION_SUMMARY_MAX:
        return text[:_DESCRIPTION_SUMMARY_MAX] + "…"
    return text or "未填写"


def _fmt_triggered_at(value) -> str:
    """告警触发时间 → 站点时区 'YYYY-MM-DD HH:MM'（naive 视作站点墙钟）。"""
    if value is None:
        return "未知"
    if getattr(value, "tzinfo", None) is not None:
        from core.utils.timezone_utils import to_site_timezone

        value = to_site_timezone(value)
    try:
        return value.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "未知"


async def _kuaiiot_enabled(tenant_id: int) -> bool:
    """kuaiiot 是否已安装且启用（本租户）；判定失败按未安装处理（不泄露）。"""
    try:
        from core.services.application.application_service import (
            ApplicationService,
        )

        row = await ApplicationService.get_application_by_code(
            tenant_id, IOT_APP
        )
        return bool(row and row.get("is_installed") and row.get("is_active"))
    except Exception as exc:
        logger.warning(
            "pulse kuaiiot 可用性判定失败 tenant_id={} error_type={}",
            tenant_id,
            type(exc).__name__,
        )
        return False


class EquipmentFaultDetector:
    domain = DOMAIN
    timeout_seconds = 8.0

    async def detect(self, ctx: PulseContext) -> List[PulseItemOut]:
        """兼容旧契约：展平 detect_sources 的全部来源信号。"""
        result = await self.detect_sources(ctx)
        items: List[PulseItemOut] = []
        for source in result.sources:
            items.extend(source.signals)
        return items

    async def detect_sources(self, ctx: PulseContext) -> PulseDetectResult:
        """spec 220 X8=a：来源级判权 + kuaiiot 告警聚合。"""
        fault_allowed = await has_permission(ctx, REQUIRED_PERMISSION)
        iot_installed = await _kuaiiot_enabled(ctx.tenant_id)
        iot_allowed = iot_installed and await has_permission(
            ctx, IOT_PERMISSION
        )
        # 两来源均无权限：沿用「无权限整领域隐藏」（spec 203 语义不变）。
        if not fault_allowed and not iot_allowed:
            raise PulsePermissionDenied(REQUIRED_PERMISSION)

        sources: List[PulseSourceResult] = []
        if fault_allowed:
            sources.append(
                PulseSourceResult(
                    key=RULE_CODE,
                    label=FAULT_SOURCE_LABEL,
                    status="ok",
                    signals=await self._fault_signals(ctx),
                )
            )
        else:
            sources.append(
                PulseSourceResult(
                    key=RULE_CODE,
                    label=FAULT_SOURCE_LABEL,
                    status="no_permission",
                )
            )

        if iot_installed:
            if not iot_allowed:
                sources.append(
                    PulseSourceResult(
                        key=IOT_RULE_CODE,
                        label=IOT_SOURCE_LABEL,
                        status="no_permission",
                    )
                )
            else:
                try:
                    signals = await asyncio.wait_for(
                        self._iot_alert_signals(ctx),
                        timeout=IOT_SOURCE_TIMEOUT,
                    )
                except Exception as exc:
                    # 超时/读取失败：该来源标记 unavailable，不拖垮 MES 部分
                    logger.warning(
                        "pulse iot 告警来源失败 tenant_id={} error_type={}",
                        ctx.tenant_id,
                        type(exc).__name__,
                    )
                    sources.append(
                        PulseSourceResult(
                            key=IOT_RULE_CODE,
                            label=IOT_SOURCE_LABEL,
                            status="unavailable",
                        )
                    )
                else:
                    sources.append(
                        PulseSourceResult(
                            key=IOT_RULE_CODE,
                            label=IOT_SOURCE_LABEL,
                            status="ok",
                            signals=signals,
                        )
                    )
        return PulseDetectResult(sources=sources)

    async def _fault_signals(self, ctx: PulseContext) -> List[PulseItemOut]:
        from apps.kuaizhizao.models.equipment_fault import EquipmentFault

        qs = EquipmentFault.filter(
            tenant_id=ctx.tenant_id,
            deleted_at__isnull=True,
            status__in=list(OPEN_FAULT_STATUSES),
        )
        qs = await apply_scope(qs, ctx, SCOPE_RESOURCE)
        items: List[PulseItemOut] = []
        # 发生时间早的持续故障排前；稳定次序供跨批次扫描。
        ordered = qs.order_by("fault_date", "id")
        offset = 0
        while True:
            faults = await (
                ordered.offset(offset).limit(SCAN_BATCH_SIZE).all()
            )
            for fault in faults:
                severity, priority = _severity_priority(
                    getattr(fault, "fault_level", None)
                )
                code = str(getattr(fault, "equipment_code", "") or "")
                name = str(getattr(fault, "equipment_name", "") or "")
                fault_date = business_date(getattr(fault, "fault_date", None))
                days = (
                    max(0, (ctx.today - fault_date).days)
                    if fault_date is not None
                    else None
                )
                items.append(
                    PulseItemOut(
                        id=f"{DOMAIN}:{RULE_CODE}:{fault.id}",
                        domain=DOMAIN,
                        severity=severity,
                        priority=priority,
                        title=(
                            f"设备故障 {getattr(fault, 'fault_no', '') or fault.id}"
                        ),
                        fact=(
                            f"设备 {code or '-'}（{name or '未命名'}）："
                            f"{_description_summary(getattr(fault, 'fault_description', None))}，"
                            f"状态 {getattr(fault, 'status', '') or '未知'}，"
                            f"发生 "
                            f"{fault_date.isoformat() if fault_date else '未知'}"
                            + (
                                f"（持续 {days} 天）"
                                if days is not None
                                else ""
                            )
                        ),
                        suggestion=(
                            "请跟进该设备故障的处理与维修闭环"
                        ),
                        resource_type="equipment_fault",
                        resource_id=str(fault.id),
                        resource_uuid=getattr(fault, "uuid", None),
                        route=ROUTE,
                        detected_at=ctx.now,
                        rule_code=RULE_CODE,
                    )
                )
            if len(faults) < SCAN_BATCH_SIZE:
                break
            offset += SCAN_BATCH_SIZE
        return items

    async def _iot_alert_signals(self, ctx: PulseContext) -> List[PulseItemOut]:
        """kuaiiot 未处理告警按设备聚合（只读；跨应用调用只传 tenant_id）。"""
        from apps.kuaiiot.models.iot import IotDevice
        from apps.kuaiiot.services.alert_service import AlertService

        alerts = []
        page = 1
        while True:
            batch, total = await AlertService.list_alerts(
                ctx.tenant_id,
                page=page,
                page_size=IOT_ALERT_PAGE_SIZE,
                status="open",
            )
            alerts.extend(batch)
            if len(batch) < IOT_ALERT_PAGE_SIZE or len(alerts) >= total:
                break
            if page >= IOT_ALERT_MAX_PAGES:
                logger.warning(
                    "pulse iot 告警翻页达上限 tenant_id={} pages={} "
                    "collected={} total={}（按已拉取部分聚合）",
                    ctx.tenant_id,
                    page,
                    len(alerts),
                    total,
                )
                break
            page += 1

        # 按设备聚合：告警数 / 最新告警级别 / 最新告警时间。
        aggregated: Dict[int, dict] = {}
        for alert in alerts:
            device_id = getattr(alert, "device_id", None)
            if device_id is None:
                continue
            entry = aggregated.setdefault(
                device_id,
                {
                    "count": 0,
                    "latest_at": None,
                    "latest_severity": None,
                    "equipment_uuid": getattr(
                        alert, "equipment_uuid", None
                    ),
                },
            )
            entry["count"] += 1
            triggered_at = getattr(alert, "triggered_at", None)
            if entry["latest_at"] is None or (
                triggered_at is not None
                and triggered_at > entry["latest_at"]
            ):
                entry["latest_at"] = triggered_at
                entry["latest_severity"] = getattr(alert, "severity", None)

        if not aggregated:
            return []

        devices = await IotDevice.filter(
            tenant_id=ctx.tenant_id,
            id__in=list(aggregated.keys()),
            deleted_at__isnull=True,
        )
        name_map = {
            device.id: (
                str(getattr(device, "code", "") or ""),
                str(getattr(device, "name", "") or ""),
            )
            for device in devices
        }

        items: List[PulseItemOut] = []
        for device_id, entry in sorted(
            aggregated.items(),
            key=lambda kv: (
                kv[1]["latest_at"].timestamp()
                if getattr(kv[1]["latest_at"], "timestamp", None)
                else 0.0
            ),
            reverse=True,
        ):
            code, name = name_map.get(device_id, ("", ""))
            severity, priority = _iot_severity_priority(
                entry["latest_severity"]
            )
            severity_zh = _IOT_SEVERITY_ZH.get(
                str(entry["latest_severity"] or "").strip(), "未知"
            )
            items.append(
                PulseItemOut(
                    id=f"{DOMAIN}:{IOT_RULE_CODE}:{device_id}",
                    domain=DOMAIN,
                    severity=severity,
                    priority=priority,
                    title=f"设备告警 {code or device_id}",
                    fact=(
                        f"设备 {code or '-'}（{name or '未命名'}）："
                        f"{entry['count']} 条未处理 IoT 告警，"
                        f"最新级别 {severity_zh}，"
                        f"最新时间 {_fmt_triggered_at(entry['latest_at'])}"
                    ),
                    suggestion="请检查设备状态并处理未确认告警",
                    resource_type="iot_device",
                    resource_id=str(device_id),
                    # 设计决策：IoT 告警信号以 MES 设备为资源主体（一条信号
                    # 聚合该设备全部未处理告警，无单一告警 uuid 可指），故
                    # resource_uuid 取设备 uuid，与其他 detector
                    # 「资源自身 uuid」口径不同属有意为之
                    resource_uuid=entry["equipment_uuid"],
                    route=IOT_ROUTE,
                    detected_at=ctx.now,
                    rule_code=IOT_RULE_CODE,
                )
            )
        return items
