"""
工单 BOM 子件明细行（开单保存后可改；领料/齐套以已保存行为准）。
"""

from tortoise import fields

from core.models.base import BaseModel


class WorkOrderBomLine(BaseModel):
    """工单物料子件行。"""

    class Meta:
        table = "apps_kuaizhizao_work_order_bom_lines"
        table_description = "快格轻制造 - 工单子件明细"
        indexes = [
            ("tenant_id", "work_order_id"),
            ("tenant_id", "material_id"),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    work_order_id = fields.IntField(description="工单ID")
    sequence = fields.IntField(default=1, description="行序")

    material_id = fields.IntField(description="物料ID")
    material_code = fields.CharField(max_length=50, description="物料编码")
    material_name = fields.CharField(max_length=200, description="物料名称")
    material_spec = fields.CharField(max_length=500, null=True, description="规格")

    warehouse_id = fields.IntField(null=True, description="仓库ID")
    warehouse_name = fields.CharField(max_length=200, null=True, description="仓库名称")
    unit = fields.CharField(max_length=50, null=True, description="单位")

    required_quantity = fields.DecimalField(
        max_digits=14, decimal_places=4, default=0, description="应发量"
    )
    batch_no = fields.CharField(max_length=100, null=True, description="批号")
    bom_version = fields.CharField(max_length=20, null=True, description="BOM版本")
    line_remarks = fields.TextField(null=True, description="行备注")

    deleted_at = fields.DatetimeField(null=True, description="软删除")