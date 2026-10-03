"""手机工作台工单 KPI：单次聚合，不含 PC 看板 7 日趋势。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from loguru import logger


async def fetch_work_order_mobile_kpi(tenant_id: int) -> dict[str, int]:
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())

    in_progress_count = 0
    completed_today_count = 0
    overdue_count = 0
    draft_count = 0
    completed_count = 0

    try:
        from tortoise import Tortoise

        conn = Tortoise.get_connection("default")
        if hasattr(conn, "execute_query_dict"):
            rows = await conn.execute_query_dict(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status IN ('released', 'in_progress')) AS in_progress_count,
                    COUNT(*) FILTER (
                        WHERE status = 'completed'
                          AND actual_end_date >= $1
                          AND actual_end_date <= $2
                    ) AS completed_today_count,
                    COUNT(*) FILTER (
                        WHERE status IN ('released', 'in_progress')
                          AND planned_end_date < $1
                    ) AS overdue_count,
                    COUNT(*) FILTER (WHERE status = 'draft') AS draft_count,
                    COUNT(*) FILTER (WHERE status = 'completed') AS completed_count
                FROM apps_kuaizhizao_work_orders
                WHERE tenant_id = $3 AND deleted_at IS NULL
                """,
                [today_start, today_end, tenant_id],
            )
            if rows:
                r = rows[0]
                in_progress_count = int(r.get("in_progress_count", 0) or 0)
                completed_today_count = int(r.get("completed_today_count", 0) or 0)
                overdue_count = int(r.get("overdue_count", 0) or 0)
                draft_count = int(r.get("draft_count", 0) or 0)
                completed_count = int(r.get("completed_count", 0) or 0)
                return {
                    "in_progress_count": in_progress_count,
                    "completed_today_count": completed_today_count,
                    "overdue_count": overdue_count,
                    "draft_count": draft_count,
                    "completed_count": completed_count,
                }
    except Exception as e:
        logger.warning(f"work-order-mobile-kpi 聚合失败，回退 ORM: {e}")

    from apps.kuaizhizao.models.work_order import WorkOrder

    base = WorkOrder.filter(tenant_id=tenant_id, deleted_at__isnull=True)
    in_progress_count = await base.filter(status__in=["released", "in_progress"]).count()
    completed_today_count = await base.filter(
        status="completed",
        actual_end_date__gte=today_start,
        actual_end_date__lte=today_end,
    ).count()
    overdue_count = await base.filter(
        status__in=["released", "in_progress"],
        planned_end_date__lt=today_start,
    ).count()
    draft_count = await base.filter(status="draft").count()
    completed_count = await base.filter(status="completed").count()
    return {
        "in_progress_count": in_progress_count,
        "completed_today_count": completed_today_count,
        "overdue_count": overdue_count,
        "draft_count": draft_count,
        "completed_count": completed_count,
    }
