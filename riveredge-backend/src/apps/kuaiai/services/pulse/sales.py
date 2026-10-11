"""销售订单交期风险 detector（spec 182 T4）。

规则（代码事实，非文案推断）：
- 候选：``SalesOrder.delivery_date``（DateField 必填）在 ``today..today+N``
  或已逾期（即 delivery_date <= today+N），``is_active`` 且 ``status`` 不在
  履约终态闭集；终态闭集对齐 ``SalesOrderService._is_terminal_business_status``
  （closed/completed/cancelled/rejected 及其存量中文/小写别名）；
- N 来自 ``TenantService.get_tenant_config(tenant_id,
  "kuaiai.pulse.sales_delivery_risk")`` → ``config_value.warning_days``：
  仅接受非布尔 int 0..365；配置行缺失回落 3；键缺失/类型非法/越界回落 3 并记
  脱敏配置告警；``get_tenant_config`` 读取异常不向回落，直接向上传播为本
  detector 局部失败；
- 权限锚点 ``kuaizhizao:sales-order:read``，数据范围
  ``kuaizhizao:sales-order``（与 list_sales_orders 同一资源键）；
- 严重度/优先级矩阵（确定性）：
  逾期 >=7 天 → critical/high；逾期 1..6 天 → error/high；
  今日到期 → error/high；未来 1..N 天 → warning/medium。
"""

from __future__ import annotations

from datetime import timedelta
from typing import List, Tuple

from loguru import logger

from apps.kuaiai.schemas.pulse import PulseItemOut
from apps.kuaiai.services.pulse.base import (
    PulseContext,
    apply_scope,
    ensure_permission,
)

DOMAIN = "sales"
RULE_CODE = "sales.delivery_risk"
REQUIRED_PERMISSION = "kuaizhizao:sales-order:read"
SCOPE_RESOURCE = "kuaizhizao:sales-order"
ROUTE = "/apps/kuaizhizao/sales-management/sales-orders"

CONFIG_KEY = "kuaiai.pulse.sales_delivery_risk"
DEFAULT_WARNING_DAYS = 3
MAX_WARNING_DAYS = 365

# 单次数据库读取上限；完整 detector 在 wait_for/cancellation 约束内分批扫描。
SCAN_BATCH_SIZE = 200

# 履约终态原始值闭集：与 SalesOrderService._is_terminal_business_status
# 逐项对齐（_is_closed/_is_completed_status/_is_cancelled_status/
# _is_rejected_status 的 normalize_status + 原始值比较全集）
SALES_TERMINAL_STATUSES: Tuple[str, ...] = (
    "CLOSED",
    "closed",
    "已关闭",
    "COMPLETED",
    "completed",
    "已完成",
    "FINISHED",
    "CANCELLED",
    "cancelled",
    "已取消",
    "REJECTED",
    "已驳回",
)


async def _warning_days(ctx: PulseContext) -> int:
    """阈值读取：行缺失→3；键缺失/非 int/越界→3 + 脱敏告警；读取异常上抛。"""
    from infra.services.tenant_service import TenantService

    config = await TenantService().get_tenant_config(
        ctx.tenant_id, CONFIG_KEY
    )
    if config is None:
        return DEFAULT_WARNING_DAYS
    value = getattr(config, "config_value", None)
    raw = value.get("warning_days") if isinstance(value, dict) else None
    if (
        raw is None
        or isinstance(raw, bool)
        or not isinstance(raw, int)
        or not 0 <= raw <= MAX_WARNING_DAYS
    ):
        logger.warning(
            "pulse 销售交期阈值配置非法 tenant_id={} 回落默认 {} 天",
            ctx.tenant_id,
            DEFAULT_WARNING_DAYS,
        )
        return DEFAULT_WARNING_DAYS
    return raw


def _severity_priority(days_to_due: int) -> Tuple[str, str]:
    if days_to_due <= -7:
        return "critical", "high"
    if days_to_due <= 0:
        return "error", "high"
    return "warning", "medium"


class SalesDeliveryRiskDetector:
    domain = DOMAIN
    timeout_seconds = 8.0

    async def detect(self, ctx: PulseContext) -> List[PulseItemOut]:
        await ensure_permission(ctx, REQUIRED_PERMISSION)
        warning_days = await _warning_days(ctx)

        from apps.kuaizhizao.models.sales_order import SalesOrder

        qs = SalesOrder.filter(
            tenant_id=ctx.tenant_id,
            deleted_at__isnull=True,
            is_active=True,
            delivery_date__lte=ctx.today + timedelta(days=warning_days),
        ).exclude(status__in=list(SALES_TERMINAL_STATUSES))
        qs = await apply_scope(qs, ctx, SCOPE_RESOURCE)
        items: List[PulseItemOut] = []
        ordered = qs.order_by("delivery_date", "id")
        offset = 0
        while True:
            orders = await (
                ordered.offset(offset).limit(SCAN_BATCH_SIZE).all()
            )
            for order in orders:
                due = order.delivery_date
                if due is None:
                    continue
                days_to_due = (due - ctx.today).days
                severity, priority = _severity_priority(days_to_due)
                code = str(getattr(order, "order_code", "") or "")
                status = str(getattr(order, "status", "") or "")
                if days_to_due < 0:
                    fact = (
                        f"约定交期 {due.isoformat()}，已逾期 {-days_to_due} 天，"
                        f"履约未完成（当前状态 {status}）"
                    )
                elif days_to_due == 0:
                    fact = (
                        f"约定交期 {due.isoformat()}（今日到期），"
                        f"履约未完成（当前状态 {status}）"
                    )
                else:
                    fact = (
                        f"约定交期 {due.isoformat()}，距交期 {days_to_due} 天，"
                        f"履约未完成（当前状态 {status}）"
                    )
                items.append(
                    PulseItemOut(
                        id=f"{DOMAIN}:{RULE_CODE}:{order.id}",
                        domain=DOMAIN,
                        severity=severity,
                        priority=priority,
                        title=f"销售订单 {code} 交期风险",
                        fact=fact,
                        suggestion=(
                            "请跟进该订单交付安排，必要时与客户确认或调整交期"
                        ),
                        resource_type="sales_order",
                        resource_id=str(order.id),
                        resource_uuid=getattr(order, "uuid", None),
                        route=ROUTE,
                        detected_at=ctx.now,
                        rule_code=RULE_CODE,
                    )
                )
            if len(orders) < SCAN_BATCH_SIZE:
                break
            offset += SCAN_BATCH_SIZE
        return items
