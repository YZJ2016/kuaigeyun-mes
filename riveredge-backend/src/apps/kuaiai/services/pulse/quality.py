"""质量异常 detector（spec 202 T3）。

规则（代码事实，非文案推断）：
- 候选：``QualityException.status`` 在未闭环闭集
  ``exception_service.ACTIVE_QUALITY_EXCEPTION_STATUSES``
  （pending/investigating/correcting）内；closed/cancelled 为终态
  （``_QUALITY_STATUSES`` 闭集见 kitting_exceptions.py，handle 落地值
  closed，exception_service.py:1342）；
- 权限锚点 ``kuaizhizao:production-execution-quality-exceptions:read``，数
  据范围 ``kuaizhizao:production-execution-quality-exceptions``（scope 键
  =页面功能码去 ``:read`` 段；manifest ``reference_resources`` 无质量异常
  专属 data_scope_key，无显式策略=全部，有策略按行级范围收敛）；
- 路由 ``/apps/kuaizhizao/production-execution/quality-exceptions``（已在
  ``SCENE_ROUTE_PERMISSIONS`` 白名单）；
- 严重度/优先级矩阵（确定性，由 ``severity`` 枚举
  ``minor/major/critical``（exception_service._normalize_severity 闭集）
  决定；未知值兜底 warning/medium 不臆造级别）：
  critical → critical/high；major → error/high；minor → warning/medium。
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

DOMAIN = "quality"
RULE_CODE = "quality_exception"
REQUIRED_PERMISSION = "kuaizhizao:production-execution-quality-exceptions:read"
SCOPE_RESOURCE = "kuaizhizao:production-execution-quality-exceptions"
ROUTE = "/apps/kuaizhizao/production-execution/quality-exceptions"

# 单次数据库读取上限；完整 detector 在 wait_for/cancellation 约束内分批扫描。
SCAN_BATCH_SIZE = 200

# 问题描述摘要长度上限（fact 只放摘要，不回全文）。
_PROBLEM_SUMMARY_MAX = 80


def _severity_priority(severity: str) -> Tuple[str, str]:
    level = str(severity or "").strip().lower()
    if level == "critical":
        return "critical", "high"
    if level == "major":
        return "error", "high"
    # minor 及未知值统一 warning/medium
    return "warning", "medium"


def _problem_summary(value) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > _PROBLEM_SUMMARY_MAX:
        return text[:_PROBLEM_SUMMARY_MAX] + "…"
    return text or "未填写"


class QualityExceptionDetector:
    domain = DOMAIN
    timeout_seconds = 8.0

    async def detect(self, ctx: PulseContext) -> List[PulseItemOut]:
        await ensure_permission(ctx, REQUIRED_PERMISSION)

        from apps.kuaizhizao.models.quality_exception import QualityException
        from apps.kuaizhizao.services.exception_service import (
            ACTIVE_QUALITY_EXCEPTION_STATUSES,
        )

        qs = QualityException.filter(
            tenant_id=ctx.tenant_id,
            deleted_at__isnull=True,
            status__in=list(ACTIVE_QUALITY_EXCEPTION_STATUSES),
        )
        qs = await apply_scope(qs, ctx, SCOPE_RESOURCE)
        items: List[PulseItemOut] = []
        ordered = qs.order_by("created_at", "id")
        offset = 0
        while True:
            exceptions = await (
                ordered.offset(offset).limit(SCAN_BATCH_SIZE).all()
            )
            for exc in exceptions:
                severity, priority = _severity_priority(
                    getattr(exc, "severity", None)
                )
                created = business_date(getattr(exc, "created_at", None))
                items.append(
                    PulseItemOut(
                        id=f"{DOMAIN}:{RULE_CODE}:{exc.id}",
                        domain=DOMAIN,
                        severity=severity,
                        priority=priority,
                        title=(
                            f"质量异常 "
                            f"{getattr(exc, 'work_order_code', None) or exc.id}"
                        ),
                        fact=(
                            f"类型 {getattr(exc, 'exception_type', '') or '未知'} "
                            f"工单 {getattr(exc, 'work_order_code', None) or '-'} "
                            f"物料 {getattr(exc, 'material_code', None) or '-'}"
                            f"（{getattr(exc, 'material_name', None) or '未命名'}）"
                            f"批号 {getattr(exc, 'batch_no', None) or '-'}："
                            f"{_problem_summary(getattr(exc, 'problem_description', None))}，"
                            f"状态 {getattr(exc, 'status', '') or '未知'}，"
                            f"登记 {created.isoformat() if created else '未知'}"
                        ),
                        suggestion=(
                            "请跟进该质量异常的原因分析与纠正措施闭环"
                        ),
                        resource_type="quality_exception",
                        resource_id=str(exc.id),
                        resource_uuid=getattr(exc, "uuid", None),
                        route=ROUTE,
                        detected_at=ctx.now,
                        rule_code=RULE_CODE,
                    )
                )
            if len(exceptions) < SCAN_BATCH_SIZE:
                break
            offset += SCAN_BATCH_SIZE
        return items
