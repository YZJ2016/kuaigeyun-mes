"""持久投递；失败保留待重试，错误不携带外部地址与凭据。"""
from datetime import datetime, timedelta

from tortoise.transactions import in_transaction
from tortoise.expressions import Q

from apps.kuaiiot.models.delivery import KuaiiotDelivery
from apps.kuaiiot.services.trend_service import write_trend
from core.services.business.business_notification_service import BusinessNotificationService
from core.utils.timezone_utils import resolve_business_datetime
from infra.domain.tenant_context import unscoped, with_tenant


async def enqueue(tenant_id: int, kind: str, key: str, payload: dict) -> KuaiiotDelivery:
    row, _ = await KuaiiotDelivery.get_or_create(
        tenant_id=tenant_id, delivery_key=key, defaults={"kind": kind, "payload": payload},
    )
    return row


async def process_pending(limit: int = 100) -> dict:
    now = resolve_business_datetime()
    async with unscoped(reason="投递任务扫描各租户待投递记录", resource="KuaiiotDelivery"):
        rows = await KuaiiotDelivery.filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now), status__in=["pending", "blocked"]).order_by("id").limit(limit)
    sent = 0
    for candidate in rows:
        async with with_tenant(int(candidate.tenant_id), reason="投递到记录所属租户公共服务"):
            async with in_transaction():
                row = await KuaiiotDelivery.filter(id=candidate.id, tenant_id=candidate.tenant_id).select_for_update().get()
                if row.status not in {"pending", "blocked"} or (row.next_attempt_at and row.next_attempt_at > now):
                    continue
                row.attempts += 1
                row.next_attempt_at = now + timedelta(seconds=min(300, 5 * 2 ** min(row.attempts, 6)))
                try:
                    payload = row.payload
                    if row.kind == "trend":
                        await write_trend(int(row.tenant_id), device_id=payload["device_id"], tag_key=payload["tag_key"], value=payload["value"], sampled_at=datetime.fromisoformat(payload["sampled_at"]))
                        count = 1
                    elif row.kind == "notification":
                        count = await BusinessNotificationService.dispatch(
                            int(row.tenant_id), trigger_document="kuaiiot_alert", trigger_action=payload["action"],
                            variables={"message": payload["message"], "alert_id": payload["alert_id"]},
                            context={"entity_type": "kuaiiot_alert", "entity_id": payload["alert_id"]},
                        )
                    else:
                        raise ValueError("unsupported delivery")
                    row.status = "delivered" if count else "blocked"
                    row.last_error = None if count else "未配置规则或接收人，或本次无发送"
                    sent += bool(count)
                except Exception:
                    row.status = "pending"
                    row.last_error = "外部投递失败，等待重试"
                await row.save()
    return {"delivered": sent, "checked": len(rows)}
