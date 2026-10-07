"""入站事务的外部历史/通知待投递记录，不作为历史查询替身。"""
from tortoise import fields
from core.models.base import BaseModel


class KuaiiotDelivery(BaseModel):
    class Meta:
        table = "apps_kuaiiot_deliveries"
        unique_together = (("tenant_id", "delivery_key"),)
        indexes = [("status", "next_attempt_at")]

    id = fields.IntField(pk=True)
    kind = fields.CharField(max_length=20)
    delivery_key = fields.CharField(max_length=128)
    payload = fields.JSONField()
    status = fields.CharField(max_length=20, default="pending")
    attempts = fields.IntField(default=0)
    next_attempt_at = fields.DatetimeField(null=True)
    last_error = fields.CharField(max_length=200, null=True)

