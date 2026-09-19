from tortoise import fields

from core.models.base import BaseModel


class MoldMaterialArrival(BaseModel):
    class Meta:
        table = "apps_industry_mold_material_arrivals"
        table_description = "行业插件 模具到料单"
        app = "models"

    id = fields.IntField(pk=True)
    code = fields.CharField(max_length=50, description="到料单号")
    work_order_id = fields.IntField(null=True, description="绑定工单ID")
    work_order_code = fields.CharField(max_length=50, null=True, description="绑定工单编码")
    material_name = fields.CharField(max_length=200, description="物料名称")
    material_spec = fields.CharField(max_length=200, null=True, description="规格")
    weight = fields.DecimalField(max_digits=14, decimal_places=4, null=True, description="重量")
    status = fields.CharField(max_length=20, default="pending", description="pending/arrived/void")
    remarks = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True)
