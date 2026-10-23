"""设备故障 detector（spec 203 T2；E1=a 只接 MES 故障单，不接 kuaiiot 告警）。

规则（代码事实，非文案推断）：
- 候选：``EquipmentFault.status`` 在未闭环闭集 ``OPEN_FAULT_STATUSES``
  （待处理/处理中）内；闭集对齐
  ``equipment_fault_service._OPEN_FAULT_STATUSES``——驱动设备「故障」状态的
  同一口径；已修复/已关闭为终态（模型注释 ``status`` 取值
  待处理/处理中/已修复/已关闭，equipment_fault.py:88）；
- 权限锚点 ``kuaizhizao:equipment-fault:read``，数据范围
  ``kuaizhizao:equipment-fault``（scope 键=页面功能码去 ``:read`` 段；
  manifest ``reference_resources`` 无故障专属 data_scope_key，无显式策略
  =全部，有策略按行级范围收敛）；
- 路由 ``/apps/kuaizhizao/equipment-management/equipment-faults``
  （kuaizhizao manifest code_rule_pages.page_path）；
- 严重度/优先级矩阵（确定性，由 ``fault_level`` 枚举
  轻微/一般/严重/紧急（模型注释 equipment_fault.py:81）决定；未知值兜底
  warning/medium 不臆造级别）：
  紧急 → critical/high；严重 → error/high；一般 → warning/medium；
  轻微 → info/low。故障持续时长只用于排序与事实描述，不改判定。
"""

from __future__ import annotations

from typing import List, Tuple

from apps.kuaiai.schemas.pulse import PulseItemOut
from apps.kuaiai.services.pulse.base import (
    PulseContext,
    apply_scope,
    business_date,
    ensure_permission,
)

DOMAIN = "equipment"
RULE_CODE = "equipment_fault"
REQUIRED_PERMISSION = "kuaizhizao:equipment-fault:read"
SCOPE_RESOURCE = "kuaizhizao:equipment-fault"
ROUTE = "/apps/kuaizhizao/equipment-management/equipment-faults"

# 单次数据库读取上限；完整 detector 在 wait_for/cancellation 约束内分批扫描。
SCAN_BATCH_SIZE = 200

# 未闭环闭集：与 equipment_fault_service._OPEN_FAULT_STATUSES
# （待处理/处理中）逐项对齐；已修复/已关闭不出现。
OPEN_FAULT_STATUSES: Tuple[str, ...] = ("待处理", "处理中")

# 故障描述摘要长度上限（fact 只放摘要，不回全文）。
_DESCRIPTION_SUMMARY_MAX = 80


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


def _description_summary(value) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > _DESCRIPTION_SUMMARY_MAX:
        return text[:_DESCRIPTION_SUMMARY_MAX] + "…"
    return text or "未填写"


class EquipmentFaultDetector:
    domain = DOMAIN
    timeout_seconds = 8.0

    async def detect(self, ctx: PulseContext) -> List[PulseItemOut]:
        await ensure_permission(ctx, REQUIRED_PERMISSION)

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
