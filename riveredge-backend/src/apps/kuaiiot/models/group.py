"""设备分组（apps_kuaiiot_device_groups）。列来自迁移 525。"""

from tortoise import fields

from core.models.base import BaseModel


class KuaiiotDeviceGroup(BaseModel):
    class Meta:
        table = "apps_kuaiiot_device_groups"
        table_description = "快数采 - 设备分组"
        unique_together = (("tenant_id", "code"),)
        indexes = [("tenant_id", "parent_id")]

    id = fields.IntField(pk=True, description="主键ID")
    code = fields.CharField(max_length=50, description="分组编码")
    name = fields.CharField(max_length=100, description="分组名称")
    parent_id = fields.IntField(null=True, description="上级分组ID")
    sort_order = fields.IntField(default=0, description="排序")
    remark = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")
