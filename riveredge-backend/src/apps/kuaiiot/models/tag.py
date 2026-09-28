"""点位定义、最新快照。历史表只映射，本切片不写入。"""

from tortoise import fields

from core.models.base import BaseModel


class KuaiiotTagDefinition(BaseModel):
    class Meta:
        table = "apps_kuaiiot_tag_definitions"
        table_description = "快数采 - 点位定义"
        unique_together = (("tenant_id", "device_id", "tag_key"),)
        indexes = [("tenant_id", "device_id")]

    id = fields.IntField(pk=True, description="主键ID")
    device_id = fields.IntField(description="IoT 设备ID")
    tag_key = fields.CharField(max_length=100, description="点位键")
    name = fields.CharField(max_length=100, description="点位名称")
    value_type = fields.CharField(max_length=20, default="number", description="值类型")
    unit = fields.CharField(max_length=30, null=True, description="单位")
    map_target = fields.CharField(max_length=100, description="监控字段映射")
    fill_target = fields.CharField(max_length=100, null=True, description="预填目标")
    is_enabled = fields.BooleanField(default=True, description="是否启用")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")


class KuaiiotTagSnapshot(BaseModel):
    class Meta:
        table = "apps_kuaiiot_tag_snapshots"
        table_description = "快数采 - 点位快照"
        unique_together = (("tenant_id", "device_id", "tag_key"),)
        indexes = [
            ("tenant_id", "device_id"),
            ("sampled_at",),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    device_id = fields.IntField(description="IoT 设备ID")
    tag_key = fields.CharField(max_length=100, description="点位键")
    value_text = fields.TextField(null=True, description="文本值")
    value_number = fields.DecimalField(max_digits=18, decimal_places=6, null=True, description="数值")
    value_bool = fields.BooleanField(null=True, description="布尔值")
    quality = fields.CharField(max_length=20, default="good", description="质量戳")
    sampled_at = fields.DatetimeField(description="采样时间")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")


class KuaiiotTagHistory(BaseModel):
    """迁移 519 已有表。本切片不插入采样。"""

    class Meta:
        table = "apps_kuaiiot_tag_history"
        table_description = "快数采 - 点位历史"
        indexes = [
            ("tenant_id", "device_id", "tag_key"),
            ("sampled_at",),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    device_id = fields.IntField(description="IoT 设备ID")
    tag_key = fields.CharField(max_length=100, description="点位键")
    value_text = fields.TextField(null=True, description="文本值")
    value_number = fields.DecimalField(max_digits=18, decimal_places=6, null=True, description="数值")
    value_bool = fields.BooleanField(null=True, description="布尔值")
    quality = fields.CharField(max_length=20, default="good", description="质量戳")
    sampled_at = fields.DatetimeField(description="采样时间")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")
