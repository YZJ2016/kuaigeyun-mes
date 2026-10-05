"""手机收件箱聚合 API。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from core.api.deps.deps import get_current_tenant
from core.services.personal.mobile_inbox_service import fetch_mobile_inbox_snapshot
from infra.api.deps.deps import get_current_user
from infra.models.user import User

router = APIRouter(prefix="/mobile", tags=["Core - Mobile Personal"])


@router.get("/inbox-snapshot", summary="手机消息中心快照（聊天+通知+待办）")
async def get_mobile_inbox_snapshot(
    tenant_id: Annotated[int, Depends(get_current_tenant)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    return await fetch_mobile_inbox_snapshot(tenant_id=tenant_id, user=user)
