"""设备凭据入站。错误响应不回显凭据。"""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from apps.kuaiiot.schemas.ingest import IngestBody
from apps.kuaiiot.services.edge_config_service import EdgeConfigService
from apps.kuaiiot.services.ingest_service import IngestService

router = APIRouter(prefix="/ingest", tags=["App - 星数采 - 入站"])


class IngestBatchBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[IngestBody]


@router.post("/{device_token}")
async def api_ingest(device_token: str, body: IngestBody) -> dict:
    return await IngestService.ingest(device_token, body)


@router.post("/{device_token}/batch")
async def api_ingest_batch(device_token: str, body: IngestBatchBody) -> dict:
    return await EdgeConfigService.ingest_batch(device_token, body.items)
