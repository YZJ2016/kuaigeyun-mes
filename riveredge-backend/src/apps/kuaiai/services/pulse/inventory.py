"""库存预警 detector（spec 202 T2）。

规则（代码事实，非文案推断）：
- 候选：``InventoryAlert.status`` 在未处理闭集 ``UNRESOLVED_ALERT_STATUSES``
  （pending/processing）内；闭集对齐
  ``document_action_policy.inventory_alert._HANDLEABLE_STATUSES``——可处理即
  未处理；resolved/ignored 为已处理终态（模型注释
  ``status: pending/processing/resolved/ignored``，
  inventory_alert.py:183）；
- 权限锚点 ``kuaizhizao:warehouse-management-inventory-alert:read``，数据范
  围 ``kuaizhizao:warehouse-management-inventory-alert``（与
  production/sales 同一约定：scope 键=页面功能码去 ``:read`` 段；manifest
  ``reference_resources`` 无预警专属 data_scope_key，无显式策略=全部，
  有策略按行级范围收敛）；
- 路由 ``/apps/kuaizhizao/warehouse-management/inventory-alert``
  （kuaizhizao manifest 菜单）；
- 严重度/优先级矩阵（确定性，由 ``alert_level`` 枚举
  ``info/warning/critical`` 决定；未知值兜底 warning/medium 不臆造级别）：
  critical → critical/high；warning → warning/medium；info → info/low。
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

DOMAIN = "inventory"
RULE_CODE = "inventory_alert"
REQUIRED_PERMISSION = "kuaizhizao:warehouse-management-inventory-alert:read"
SCOPE_RESOURCE = "kuaizhizao:warehouse-management-inventory-alert"
ROUTE = "/apps/kuaizhizao/warehouse-management/inventory-alert"

# 单次数据库读取上限；完整 detector 在 wait_for/cancellation 约束内分批扫描。
SCAN_BATCH_SIZE = 200

# 未处理闭集：与 document_action_policy.inventory_alert._HANDLEABLE_STATUSES
# （pending/processing）逐项对齐；resolved/ignored 已处理不出现。
UNRESOLVED_ALERT_STATUSES: Tuple[str, ...] = ("pending", "processing")

_ALERT_TYPE_LABELS = {
    "low_stock": "低库存",
    "high_stock": "高库存",
    "expired": "过期",
}


def _severity_priority(alert_level: str) -> Tuple[str, str]:
    level = str(alert_level or "").strip().lower()
    if level == "critical":
        return "critical", "high"
    if level == "info":
        return "info", "low"
    # warning 及未知值统一 warning/medium
    return "warning", "medium"


class InventoryAlertDetector:
    domain = DOMAIN
    timeout_seconds = 8.0

    async def detect(self, ctx: PulseContext) -> List[PulseItemOut]:
        await ensure_permission(ctx, REQUIRED_PERMISSION)

        from apps.kuaizhizao.models.inventory_alert import InventoryAlert

        qs = InventoryAlert.filter(
            tenant_id=ctx.tenant_id,
            deleted_at__isnull=True,
            status__in=list(UNRESOLVED_ALERT_STATUSES),
        )
        qs = await apply_scope(qs, ctx, SCOPE_RESOURCE)
        items: List[PulseItemOut] = []
        ordered = qs.order_by("triggered_at", "id")
        offset = 0
        while True:
            alerts = await (
                ordered.offset(offset).limit(SCAN_BATCH_SIZE).all()
            )
            for alert in alerts:
                severity, priority = _severity_priority(
                    getattr(alert, "alert_level", None)
                )
                code = str(getattr(alert, "material_code", "") or "")
                name = str(getattr(alert, "material_name", "") or "")
                warehouse = str(getattr(alert, "warehouse_name", "") or "")
                alert_type = str(getattr(alert, "alert_type", "") or "")
                type_label = _ALERT_TYPE_LABELS.get(alert_type, alert_type or "未知")
                triggered = business_date(getattr(alert, "triggered_at", None))
                items.append(
                    PulseItemOut(
                        id=f"{DOMAIN}:{RULE_CODE}:{alert.id}",
                        domain=DOMAIN,
                        severity=severity,
                        priority=priority,
                        title=f"物料 {code} 库存预警",
                        fact=(
                            f"物料 {code}（{name or '未命名'}）"
                            f" @ {warehouse or '未配置仓库'}："
                            f"类型 {type_label}，"
                            f"当前 {getattr(alert, 'current_quantity', '')}"
                            f"/阈值 {getattr(alert, 'threshold_value', '')}，"
                            f"状态 {getattr(alert, 'status', '') or '未知'}，"
                            f"触发 {triggered.isoformat() if triggered else '未知'}"
                        ),
                        suggestion=(
                            "请跟进该物料库存预警，必要时补货或调整库存"
                        ),
                        resource_type="inventory_alert",
                        resource_id=str(alert.id),
                        resource_uuid=getattr(alert, "uuid", None),
                        route=ROUTE,
                        detected_at=ctx.now,
                        rule_code=RULE_CODE,
                    )
                )
            if len(alerts) < SCAN_BATCH_SIZE:
                break
            offset += SCAN_BATCH_SIZE
        return items
