"""产品物模型（apps_kuaiiot_products）。点位、事件与指令都写在产品行上。"""

from tortoise import fields

from core.models.base import BaseModel


class KuaiiotProduct(BaseModel):
    class Meta:
        table = "apps_kuaiiot_products"
        table_description = "快数采 - 产品物模型"
        unique_together = (("tenant_id", "code"),)
        indexes = [("tenant_id", "name")]

    id = fields.IntField(pk=True, description="主键ID")
    code = fields.CharField(max_length=50, description="产品编码")
    name = fields.CharField(max_length=100, description="产品名称")
    description = fields.TextField(null=True, description="说明")
    tags = fields.JSONField(default=list, description="点位模板")
    events = fields.JSONField(default=list, description="事件定义")
    functions = fields.JSONField(default=list, description="指令定义")
    remark = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")
    deleted_by = fields.IntField(null=True, description="删除人ID")
    deleted_by_name = fields.CharField(max_length=100, null=True, description="删除人姓名")
