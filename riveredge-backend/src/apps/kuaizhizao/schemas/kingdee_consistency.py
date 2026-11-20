"""金蝶强一致：审计与编排（走系统 sync-from-source / 外推，禁止旁路写批次）。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import Field

from core.schemas.base import BaseSchema


class KingdeeConsistencyRemediation(BaseSchema):
    action: str
    method: str
    path: str
    body: Optional[Dict[str, Any]] = None
    note: Optional[str] = None


class KingdeeConsistencyBlocker(BaseSchema):
    reason: str
    label: str
    code: str
    source_type: str
    source_id: int
    remediation: List[KingdeeConsistencyRemediation] = Field(default_factory=list)


class KingdeeConsistencyDuplicateWarehouse(BaseSchema):
    name: str
    codes: List[str]
    warehouse_ids: List[int]


class KingdeeConsistencyEmptyLocationBatch(BaseSchema):
    material_id: int
    warehouse_code: str
    quantity: str
    batch_no: Optional[str] = None
    expected_location_code: str
    repair_via: str = "inventory_sync_from_source"


class KingdeeConsistencyAuditOut(BaseSchema):
    inventory_pull_blockers: List[KingdeeConsistencyBlocker] = Field(default_factory=list)
    duplicate_warehouse_names: List[KingdeeConsistencyDuplicateWarehouse] = Field(
        default_factory=list
    )
    empty_location_batches: List[KingdeeConsistencyEmptyLocationBatch] = Field(
        default_factory=list
    )
    inventory_sync_allowed: bool = False
    notes: List[str] = Field(default_factory=list)


class KingdeeConsistencyMasterDataRequest(BaseSchema):
    incremental: bool = False
    skip_unconfigured_bindings: bool = True


class KingdeeConsistencyMasterDataStepOut(BaseSchema):
    entity_type: str
    status: str
    detail: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


class KingdeeConsistencyMasterDataOut(BaseSchema):
    steps: List[KingdeeConsistencyMasterDataStepOut] = Field(default_factory=list)


class KingdeeConsistencyInventoryRequest(BaseSchema):
    incremental: bool = False
    active_only: bool = True


class KingdeeConsistencyInventoryOut(BaseSchema):
    skipped: bool = False
    reason: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
