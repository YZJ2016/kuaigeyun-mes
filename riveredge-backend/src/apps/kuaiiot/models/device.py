"""星数采 IoT 设备（apps_kuaiiot_devices）。"""

from tortoise import fields

from core.models.base import BaseModel


class KuaiiotDevice(BaseModel):
    class Meta:
        table = "apps_kuaiiot_devices"
        table_description = "快数采 - IoT 设备"
        unique_together = (("tenant_id", "code"),)
        indexes = [
            ("tenant_id", "connection_id"),
            ("tenant_id", "equipment_uuid"),
            ("device_token",),
            ("tenant_id", "is_online"),
            ("tenant_id", "product_id"),
            ("tenant_id", "group_id"),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    connection_id = fields.IntField(null=True, description="连接源ID")
    external_device_id = fields.CharField(max_length=100, description="外部设备标识")
    code = fields.CharField(max_length=50, description="设备编码")
    name = fields.CharField(max_length=100, description="设备名称")
    device_token = fields.CharField(max_length=64, description="设备鉴权凭据")
    equipment_uuid = fields.CharField(max_length=36, null=True, description="星制造设备UUID")
    product_id = fields.IntField(null=True, description="产品物模型ID")
    group_id = fields.IntField(null=True, description="设备分组ID")
    is_online = fields.BooleanField(default=False, description="是否在线")
    last_seen_at = fields.DatetimeField(null=True, description="最近入站时间")
    last_mes_sync_at = fields.DatetimeField(null=True, description="最近 MES 同步时间")
    remark = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")
