"""Pulse detector 基座（spec 182 T2）。

约定：
- ``PulseContext`` 由 registry 在扫描开始时生成一次，所有 detector 共享同一
  业务时刻（``now``=UTC aware；``today``=站点业务日历日），避免跨 detector
  取时不一致；
- detector 一律先调 :func:`ensure_permission` 校验领域读权限，无权限抛
  ``PulsePermissionDenied``——registry 转成脱敏 errors[]，不外泄数量/ID；
- ``business_date`` 口径与 work_order_service._normalize_naive_local_datetime
  一致：aware 按站点时区取日，naive 视作站点墙钟（历史业务字段口径）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, List, Optional, Protocol

from loguru import logger

from apps.kuaiai.schemas.pulse import PulseItemOut
from infra.models.user import User


class PulsePermissionDenied(Exception):
    """领域读权限缺失/判权失败（失败关闭）。detector 内部抛出，registry 脱敏。"""


@dataclass(frozen=True)
class PulseContext:
    tenant_id: int
    user: Optional[User]
    now: datetime
    today: date


class PulseDetector(Protocol):
    """确定性 detector 接口：只读、显式 tenant_id、产出统一异常项。"""

    domain: str
    timeout_seconds: float

    async def detect(self, ctx: PulseContext) -> List[PulseItemOut]:
        ...


def business_date(value: Any) -> Optional[date]:
    """业务日历日：aware→站点时区取日；naive→视为站点墙钟直接取日。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            from core.utils.timezone_utils import to_site_timezone

            return to_site_timezone(value).date()
        return value.date()
    if isinstance(value, date):
        return value
    return None


def site_wallclock_naive(value: datetime) -> datetime:
    """aware→站点墙钟 naive（与工单延期检测 SQL 比较口径一致）。"""
    from zoneinfo import ZoneInfo

    from core.utils.timezone_utils import site_timezone_name

    if value.tzinfo is not None:
        return value.astimezone(ZoneInfo(site_timezone_name())).replace(
            tzinfo=None
        )
    return value


async def has_permission(ctx: PulseContext, code: str) -> bool:
    """当前用户领域读权限判定：管理员身份由 has_permission 内部处理，失败关闭。"""
    uid = getattr(ctx.user, "id", None)
    if not uid or not ctx.tenant_id:
        return False
    try:
        from core.services.authorization.user_permission_service import (
            UserPermissionService,
        )

        return bool(
            await UserPermissionService.has_permission(
                uid, ctx.tenant_id, code
            )
        )
    except Exception as exc:
        logger.warning(
            "pulse 权限判定失败 tenant_id={} code={} error_type={}",
            ctx.tenant_id,
            code,
            type(exc).__name__,
        )
        return False


async def ensure_permission(ctx: PulseContext, code: str) -> None:
    if not await has_permission(ctx, code):
        raise PulsePermissionDenied(code)


async def apply_scope(queryset, ctx: PulseContext, resource: str):
    """DataScopeService 统一入口（与 scene_tools 适配层同一数据范围机制）。"""
    from core.services.authorization.data_scope_service import DataScopeService

    return await DataScopeService.apply(
        queryset,
        tenant_id=ctx.tenant_id,
        user=ctx.user,
        resource=resource,
    )
