"""金蝶供应链业务员/领用人等 Operator 工号解析（禁止用登录名或姓名冒充）。"""

from __future__ import annotations

from typing import Optional

from loguru import logger


async def resolve_kingdee_bizuser_number(tenant_id: int, user_id: Optional[int]) -> Optional[str]:
    """
    按用户 ID 解析金蝶人员工号。
    无工号则返回 None，由调用方决定是否使用单据字段或业务配置。
    """
    uid = int(user_id or 0)
    if uid <= 0:
        return None
    try:
        from infra.models.user import User

        user = await User.get_or_none(tenant_id=tenant_id, id=uid, deleted_at__isnull=True)
        if not user:
            return None
        code = str(getattr(user, "employee_number", "") or "").strip()
        return code or None
    except Exception as exc:
        logger.warning("resolve_kingdee_bizuser_number failed user_id={} err={}", uid, exc)
        return None
