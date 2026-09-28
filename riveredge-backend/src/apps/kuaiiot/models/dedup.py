"""入站幂等（apps_kuaiiot_ingest_dedup）。"""

from tortoise import fields

from core.models.base import BaseModel


class KuaiiotIngestDedup(BaseModel):
    class Meta:
        table = "apps_kuaiiot_ingest_dedup"
        table_description = "快数采 - 入站幂等"
        unique_together = (("tenant_id", "device_id", "idempotency_key"),)
        indexes = [("tenant_id", "device_id")]

    id = fields.IntField(pk=True, description="主键ID")
    device_id = fields.IntField(description="IoT 设备ID")
    idempotency_key = fields.CharField(max_length=128, description="幂等键")
    response_json = fields.TextField(description="首次入站响应")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")
