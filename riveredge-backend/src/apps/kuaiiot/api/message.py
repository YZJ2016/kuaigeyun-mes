"""消息追踪列表。无租户上下文不读。"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from apps.kuaiiot.schemas.command import MessageLogOut
from apps.kuaiiot.services.message_log_service import MessageLogService
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant

router = APIRouter(tags=["App - 星数采 - 消息追踪"])


@router.get(
    "/message-logs",
    response_model=list[MessageLogOut],
    dependencies=[Depends(require_permission_codes("kuaiiot:device:display"))],
)
async def api_list_message_logs(
    device_id: Optional[int] = Query(default=None),
    tenant_id: int = Depends(get_current_tenant),
):
    return await MessageLogService.list_messages(tenant_id, device_id)
