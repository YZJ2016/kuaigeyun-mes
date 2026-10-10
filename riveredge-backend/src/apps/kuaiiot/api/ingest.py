"""数据入站 API（device token 鉴权，无需用户登录）。"""

from typing import Optional

from fastapi import APIRouter, Header

from apps.kuaiiot.schemas.iot import IngestBatchPayload, IngestBatchResponse, IngestPayload, IngestResponse
from apps.kuaiiot.services.ingest_service import IngestService

router = APIRouter(prefix="/ingest", tags=["App - KuaiIoT - Ingest"])


@router.post("/{device_token}", response_model=IngestResponse)
async def ingest_device_data(
    device_token: str,
    payload: IngestPayload,
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
):
    if x_idempotency_key and not payload.idempotency_key:
        payload = payload.model_copy(update={"idempotency_key": x_idempotency_key})
    return await IngestService.ingest(device_token, payload)


@router.post("/{device_token}/batch", response_model=IngestBatchResponse)
async def ingest_device_batch(device_token: str, payload: IngestBatchPayload):
    return await IngestService.ingest_batch(device_token, payload)
