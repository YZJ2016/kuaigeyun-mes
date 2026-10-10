"""快数采 Wave 3 分析 API。"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from apps.kuaiiot.schemas.iot import (
    EquipmentOpsFeedResponse,
    OeeLiveEquipmentResponse,
    OeeLiveListResponse,
    PipelineGraphResponse,
)
from apps.kuaiiot.services.equipment_ops_feed_service import EquipmentOpsFeedService
from apps.kuaiiot.services.oee_live_service import OeeLiveService
from apps.kuaiiot.services.pipeline_service import PipelineService
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant

router = APIRouter(prefix="/analytics", tags=["App - KuaiIoT - Analytics"])


@router.get("/oee-live", response_model=OeeLiveListResponse, dependencies=[Depends(require_permission_codes("kuaiiot:analytics:read"))])
async def list_oee_live(
    tenant_id: int = Depends(get_current_tenant),
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(50, ge=1, le=200),
):
    return await OeeLiveService.list_equipment_oee_live(tenant_id, hours=hours, limit=limit)


@router.get(
    "/oee-live/{equipment_uuid}",
    response_model=OeeLiveEquipmentResponse,
    dependencies=[Depends(require_permission_codes("kuaiiot:analytics:read"))],
)
async def get_oee_live(
    equipment_uuid: str,
    tenant_id: int = Depends(get_current_tenant),
    hours: int = Query(24, ge=1, le=168),
):
    return await OeeLiveService.get_equipment_oee_live(tenant_id, equipment_uuid, hours=hours)


@router.get("/pipeline", response_model=PipelineGraphResponse, dependencies=[Depends(require_permission_codes("kuaiiot:pipeline:read"))])
async def get_pipeline_graph(tenant_id: int = Depends(get_current_tenant)):
    return await PipelineService.build_graph(tenant_id)


@router.get(
    "/equipment-ops-feed",
    response_model=EquipmentOpsFeedResponse,
    dependencies=[Depends(require_permission_codes("kuaiiot:analytics:read"))],
)
async def get_equipment_ops_feed(
    tenant_id: int = Depends(get_current_tenant),
    hours: int = Query(24, ge=1, le=168),
):
    return await EquipmentOpsFeedService.build_feed(tenant_id, hours=hours)
