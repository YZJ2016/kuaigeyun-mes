"""快数采数据留存清理。"""

from __future__ import annotations

from datetime import timedelta

from apps.kuaiiot.constants import ALERT_RETENTION_DAYS, INGEST_DEDUP_RETENTION_DAYS, MESSAGE_LOG_RETENTION_DAYS
from apps.kuaiiot.models.iot import IotAlert, IotIngestDedup, IotMessageLog
from core.utils.timezone_utils import resolve_business_datetime


class RetentionService:
    @staticmethod
    async def purge_expired_records() -> dict[str, int]:
        now = resolve_business_datetime()
        dedup_cutoff = now - timedelta(days=INGEST_DEDUP_RETENTION_DAYS)
        alert_cutoff = now - timedelta(days=ALERT_RETENTION_DAYS)
        message_log_cutoff = now - timedelta(days=MESSAGE_LOG_RETENTION_DAYS)

        dedup_deleted = await IotIngestDedup.filter(created_at__lt=dedup_cutoff).delete()
        alerts_deleted = await IotAlert.filter(
            status="acknowledged",
            triggered_at__lt=alert_cutoff,
        ).delete()
        message_logs_deleted = await IotMessageLog.filter(created_at__lt=message_log_cutoff).delete()

        return {
            "dedup_deleted": int(dedup_deleted or 0),
            "alerts_deleted": int(alerts_deleted or 0),
            "message_logs_deleted": int(message_logs_deleted or 0),
        }
