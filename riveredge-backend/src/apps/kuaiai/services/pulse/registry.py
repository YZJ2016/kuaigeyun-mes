"""Pulse detector registry 与聚合（spec 182 T2）。

- 五领域固定注册：production/sales 已实现；inventory/quality/equipment 仅保留
  注册位，查询时回 ``not_connected`` 局部错误（KO-04「尚未接入检测器」，不伪
  造 0 正常、不计入 complete）；
- 每 detector 独立超时（``asyncio.wait_for``，超时即取消，不留无界后台查询），
  ``gather(return_exceptions=True)`` 单点失败不拖垮其它领域；
- errors[] 只放脱敏 code/message：permission_denied / timeout /
  detector_error / not_connected；complete=false 仅当任一已实现 detector
  失败（含无权限、读配置失败、超时、未捕获异常）；
- 去重键 ``domain+rule_code+resource_id``；稳定排序 严重度→优先级→
  detected_at（新→旧）→resource_id；summary 只统计成功 detector；
- 分页对合并排序后的全集切片；group.count 为该领域筛选后总数（非本页条数）。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from loguru import logger

from apps.kuaiai.schemas.pulse import (
    PulseErrorOut,
    PulseGroupOut,
    PulseItemOut,
    PulseOut,
    PulseSummaryOut,
)
from apps.kuaiai.services.pulse.base import (
    PulseContext,
    PulseDetector,
    PulsePermissionDenied,
)
from apps.kuaiai.services.pulse.production import ProductionDelayDetector
from apps.kuaiai.services.pulse.sales import SalesDeliveryRiskDetector
from infra.models.user import User

PULSE_DOMAINS: Tuple[str, ...] = (
    "production",
    "inventory",
    "sales",
    "quality",
    "equipment",
)
DOMAIN_SET = frozenset(PULSE_DOMAINS)
DOMAIN_LABELS: Dict[str, str] = {
    "production": "生产",
    "inventory": "库存",
    "sales": "销售",
    "quality": "质量",
    "equipment": "设备",
}

SEVERITIES = frozenset({"info", "warning", "error", "critical"})
_SEVERITY_ORDER = {"critical": 0, "error": 1, "warning": 2, "info": 3}
_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

_ERROR_CODE_BY_EXC = {
    PulsePermissionDenied: ("permission_denied", "当前用户缺少该领域数据读取权限"),
    TimeoutError: ("timeout", "该领域异常检测超时"),
}

DETECTORS: Dict[str, PulseDetector] = {
    "production": ProductionDelayDetector(),
    "sales": SalesDeliveryRiskDetector(),
}
IMPLEMENTED_DOMAINS = frozenset(DETECTORS.keys())


def _context(tenant_id: int, user: Optional[User]) -> PulseContext:
    from core.utils.timezone_utils import (
        resolve_business_datetime,
        to_site_timezone,
    )

    now = resolve_business_datetime()
    return PulseContext(
        tenant_id=tenant_id,
        user=user,
        now=now,
        today=to_site_timezone(now).date(),
    )


def _classify_error(domain: str, exc: BaseException) -> PulseErrorOut:
    for exc_type, (code, message) in _ERROR_CODE_BY_EXC.items():
        if isinstance(exc, exc_type):
            return PulseErrorOut(domain=domain, code=code, message=message)
    logger.warning(
        "pulse detector 失败 domain={} error_type={}",
        domain,
        type(exc).__name__,
    )
    return PulseErrorOut(
        domain=domain,
        code="detector_error",
        message="该领域异常检测失败，请稍后重试",
    )


def _dedup_sort(items: Iterable[PulseItemOut]) -> List[PulseItemOut]:
    seen = set()
    unique: List[PulseItemOut] = []
    for item in items:
        key = (item.domain, item.rule_code, item.resource_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    def sort_key(item: PulseItemOut):
        ts = (
            item.detected_at.timestamp()
            if isinstance(item.detected_at, datetime)
            else 0.0
        )
        return (
            _SEVERITY_ORDER.get(item.severity, 99),
            _PRIORITY_ORDER.get(item.priority, 99),
            -ts,
            item.resource_id,
        )

    unique.sort(key=sort_key)
    return unique


def _summary(items: List[PulseItemOut]) -> PulseSummaryOut:
    return PulseSummaryOut(
        total=len(items),
        high_priority=sum(1 for i in items if i.priority == "high"),
        critical=sum(1 for i in items if i.severity == "critical"),
        warning_or_error=sum(
            1 for i in items if i.severity in ("warning", "error")
        ),
        domain_count=len({i.domain for i in items}),
    )


async def run_pulse(
    tenant_id: int,
    user: Optional[User],
    *,
    domains: Optional[List[str]] = None,
    severity: Optional[str] = None,
    page: int = 1,
    page_size: int = 60,
) -> PulseOut:
    """聚合全部请求领域：过滤/去重/排序/分页/汇总，局部失败脱敏。"""
    requested = list(domains) if domains else list(PULSE_DOMAINS)
    ctx = _context(tenant_id, user)

    concrete = [d for d in requested if d in DETECTORS]
    pending = [d for d in requested if d not in DETECTORS]

    async def _guarded(
        detector: PulseDetector,
    ) -> List[PulseItemOut]:
        return await asyncio.wait_for(
            detector.detect(ctx), timeout=detector.timeout_seconds
        )

    results = await asyncio.gather(
        *[_guarded(DETECTORS[d]) for d in concrete],
        return_exceptions=True,
    )

    items: List[PulseItemOut] = []
    errors: List[PulseErrorOut] = []
    failed_domains = set()
    for domain, result in zip(concrete, results):
        if isinstance(result, BaseException):
            errors.append(_classify_error(domain, result))
            failed_domains.add(domain)
        else:
            items.extend(result)
    for domain in pending:
        errors.append(
            PulseErrorOut(
                domain=domain,
                code="not_connected",
                message="该领域尚未接入检测器",
            )
        )

    if severity:
        items = [i for i in items if i.severity == severity]
    items = _dedup_sort(items)

    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 60), 100))
    domain_totals: Dict[str, int] = {}
    for item in items:
        domain_totals[item.domain] = domain_totals.get(item.domain, 0) + 1

    start = (page - 1) * page_size
    page_items = items[start : start + page_size]

    groups: List[PulseGroupOut] = []
    for domain in PULSE_DOMAINS:
        domain_items = [i for i in page_items if i.domain == domain]
        if not domain_items:
            continue
        groups.append(
            PulseGroupOut(
                domain=domain,
                label=DOMAIN_LABELS.get(domain, domain),
                count=domain_totals.get(domain, len(domain_items)),
                items=domain_items,
            )
        )

    # complete=false 只由已实现 detector 的失败触发；not_connected 不算失败
    complete = not failed_domains

    return PulseOut(
        summary=_summary(items),
        groups=groups,
        errors=errors,
        complete=complete,
        generated_at=ctx.now,
    )


async def pulse_total_count(tenant_id: int, user: Optional[User]) -> Optional[int]:
    """hub 指标用真实聚合：全部已实现 detector 失败 → None（不伪造 0）。"""
    try:
        result = await run_pulse(tenant_id, user, page=1, page_size=1)
    except Exception as exc:
        logger.warning(
            "pulse 聚合失败 tenant_id={} error_type={}",
            tenant_id,
            type(exc).__name__,
        )
        return None
    failed = {
        e.domain for e in result.errors if e.code != "not_connected"
    }
    if IMPLEMENTED_DOMAINS and IMPLEMENTED_DOMAINS <= failed:
        return None
    return int(result.summary.total)


def parse_domains(raw: Optional[str]) -> Optional[List[str]]:
    """逗号分隔单参数 → 去重保序领域列表；非法值抛 ValueError 由路由判 422。"""
    if raw is None or not str(raw).strip():
        return None
    parts = [p.strip() for p in str(raw).split(",") if p.strip()]
    if not parts or any(p not in DOMAIN_SET for p in parts):
        raise ValueError("domain 仅支持 production,inventory,sales,quality,equipment")
    out: List[str] = []
    for p in parts:
        if p not in out:
            out.append(p)
    return out
