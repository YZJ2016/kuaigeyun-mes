"""其他入库单出站绑定 schema。"""

from typing import List, Optional

from pydantic import Field

from core.schemas.base import BaseSchema
from core.schemas.sync_binding_contract import DocumentPushTargetItem


class OtherInboundPushBindingOut(BaseSchema):
    """targets_configured 为 false 表示尚未保存过出站目标；为 true 时按 targets 展示（可为空列表）。"""

    targets: List[DocumentPushTargetItem] = Field(default_factory=list)
    trigger_actions: List[str] = Field(default_factory=list)
    connection_code: Optional[str] = None
    save_api_uuid: Optional[str] = None
    sync_mode: str = "manual_full"
    schedule_interval_minutes: int = 15
    targets_configured: bool = False


class OtherInboundPushBindingUpsert(BaseSchema):
    targets: List[DocumentPushTargetItem] = Field(default_factory=list)
    trigger_actions: List[str] = Field(default_factory=list)
    connection_code: Optional[str] = None
    save_api_uuid: Optional[str] = None
    sync_mode: Optional[str] = None
    schedule_interval_minutes: Optional[int] = None
