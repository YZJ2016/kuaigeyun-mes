"""主数据同步 schema。"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import Field

from core.schemas.base import BaseSchema
from core.schemas.sync_binding_contract import SyncSourceItem

VALID_SYNC_MODES = frozenset({"manual_full", "scheduled_full", "scheduled_incremental"})
VALID_SYNC_DIRECTIONS = frozenset({"pull", "push", "bidirectional"})


class MasterDataSyncBindingOut(BaseSchema):
    sources: List[SyncSourceItem] = Field(default_factory=list)
    source_type: Optional[str] = None
    api_uuid: Optional[str] = None
    dataset_uuid: Optional[str] = None
    field_mapping: Dict[str, str] = Field(default_factory=dict)
    match_key_field: str = "code"
    sync_mode: str = "manual_full"
    schedule_interval_minutes: int = 15
    last_success_at: Optional[datetime] = None
    last_attempt_at: Optional[datetime] = None
    last_error: Optional[str] = None


class MasterDataSyncBindingUpsert(BaseSchema):
    sources: Optional[List[SyncSourceItem]] = None
    source_type: Optional[str] = None
    api_uuid: Optional[str] = None
    dataset_uuid: Optional[str] = None
    field_mapping: Optional[Dict[str, str]] = None
    match_key_field: Optional[str] = None
    sync_mode: Optional[str] = None
    schedule_interval_minutes: Optional[int] = None


class MasterDataSyncFromSourceRequest(BaseSchema):
    sources: Optional[List[SyncSourceItem]] = None
    source_type: Optional[str] = None
    api_uuid: Optional[str] = None
    dataset_uuid: Optional[str] = None
    field_mapping: Optional[Dict[str, str]] = None
    save_binding: bool = False
    skip_prerequisite_syncs: bool = False
    sync_mode: Optional[str] = None
    schedule_interval_minutes: Optional[int] = None
    incremental: Optional[bool] = None
    """仅同步有效主数据（已审核未禁用）或未完成单据（已审核未关闭）。默认开启。"""
    active_only: bool = True
    """物料分组：按编码段（如 06.01→06）智能推断父级；默认关闭，由同步弹窗勾选。"""
    infer_parent_by_code: bool = False


class MasterDataSyncFromSourceOut(BaseSchema):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    """源端本轮拉取行数（过滤前；增量无变更时为 0）。"""
    fetched: int = 0
    """活跃/组织等过滤后行数（映射前）。"""
    after_filter: int = 0
    """全量且无写入时的空结果原因：source_empty | filtered_all | mapping_empty。"""
    empty_reason: Optional[str] = None
    """full=全量拉取；incremental=按水位增量。"""
    mode: str = "full"
    errors: List[str] = Field(default_factory=list)
