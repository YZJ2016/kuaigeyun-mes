"""生产延期 detector（spec 182 T3）。

规则（代码事实，非文案推断）：
- 候选：``WorkOrder.planned_end_date`` 早于当前站点墙钟，且 ``status`` 不在
  ``work_order_service.WORK_ORDER_DELAY_EXCLUDED_STATUSES`` 闭集
  （completed/已完成/COMPLETED、cancelled/已取消/CANCELLED、
  split/已拆分/SPLIT），与菜单工单「逾期」徽章同一口径；
- 逾期天数：站点业务日历日差值；同日已超过计划时刻为 0，并显示
  “今日已逾时”；跨日按实际日差显示；
- 权限锚点 ``kuaizhizao:work-order:read``（kuaizhizao manifest 工单菜单），
  数据范围 ``kuaizhizao:work-order``；无权限 → PulsePermissionDenied，
  不泄露数量/ID/标题/路由；
- 严重度/优先级矩阵（确定性）：
  逾期 >=7 天 → critical/high；3..6 天 → error/high；
  0..2 天 → warning，工单自身 priority 为 high/urgent 时 high 否则 medium。
"""

from __future__ import annotations

from typing import List, Tuple

from apps.kuaiai.schemas.pulse import PulseItemOut
from apps.kuaiai.services.pulse.base import (
    PulseContext,
    apply_scope,
    business_date,
    ensure_permission,
    site_wallclock_naive,
)

DOMAIN = "production"
RULE_CODE = "production.delay"
REQUIRED_PERMISSION = "kuaizhizao:work-order:read"
SCOPE_RESOURCE = "kuaizhizao:work-order"
ROUTE = "/apps/kuaizhizao/production-execution/work-orders"

# 单次数据库读取上限；完整 detector 在 wait_for/cancellation 约束内分批扫描。
SCAN_BATCH_SIZE = 200

_HIGH_WO_PRIORITIES = frozenset({"high", "urgent"})


def _severity_priority(delay_days: int, wo_priority: str) -> Tuple[str, str]:
    if delay_days >= 7:
        return "critical", "high"
    if delay_days >= 3:
        return "error", "high"
    priority = (
        "high"
        if str(wo_priority or "").strip().lower() in _HIGH_WO_PRIORITIES
        else "medium"
    )
    return "warning", priority


class ProductionDelayDetector:
    domain = DOMAIN
    timeout_seconds = 8.0

    async def detect(self, ctx: PulseContext) -> List[PulseItemOut]:
        await ensure_permission(ctx, REQUIRED_PERMISSION)

        from apps.kuaizhizao.models.work_order import WorkOrder
        from apps.kuaizhizao.services.work_order_service import (
            WORK_ORDER_DELAY_EXCLUDED_STATUSES,
        )

        qs = WorkOrder.filter(
            tenant_id=ctx.tenant_id,
            deleted_at__isnull=True,
            planned_end_date__isnull=False,
            planned_end_date__lt=site_wallclock_naive(ctx.now),
        ).exclude(status__in=list(WORK_ORDER_DELAY_EXCLUDED_STATUSES))
        qs = await apply_scope(qs, ctx, SCOPE_RESOURCE)
        items: List[PulseItemOut] = []
        ordered = qs.order_by("planned_end_date", "id")
        offset = 0
        while True:
            work_orders = await (
                ordered.offset(offset).limit(SCAN_BATCH_SIZE).all()
            )
            for wo in work_orders:
                planned = business_date(wo.planned_end_date)
                if planned is None or planned > ctx.today:
                    continue
                delay_days = max(0, (ctx.today - planned).days)
                severity, priority = _severity_priority(
                    delay_days, getattr(wo, "priority", None)
                )
                code = str(getattr(wo, "code", "") or "")
                qty = getattr(wo, "quantity", None)
                done = getattr(wo, "completed_quantity", None)
                elapsed = (
                    "今日已逾时"
                    if delay_days == 0
                    else f"已逾期 {delay_days} 天"
                )
                items.append(
                    PulseItemOut(
                        id=f"{DOMAIN}:{RULE_CODE}:{wo.id}",
                        domain=DOMAIN,
                        severity=severity,
                        priority=priority,
                        title=f"工单 {code} 生产延期",
                        fact=(
                            f"计划完工 {planned.isoformat()}，{elapsed}，"
                            f"计划 {qty or 0}，已完成 {done or 0}"
                        ),
                        suggestion=(
                            "请跟进该工单生产进度，必要时调整排程或与客户确认交期"
                        ),
                        resource_type="work_order",
                        resource_id=str(wo.id),
                        resource_uuid=getattr(wo, "uuid", None),
                        route=ROUTE,
                        detected_at=ctx.now,
                        rule_code=RULE_CODE,
                    )
                )
            if len(work_orders) < SCAN_BATCH_SIZE:
                break
            offset += SCAN_BATCH_SIZE
        return items
