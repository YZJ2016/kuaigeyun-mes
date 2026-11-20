"""
物料分组产品工艺配置（单表聚合）

按物料分组存储工艺路线指派与工序行；物料级产品工艺优先于本表。
"""

from tortoise import fields

from infra.models.base import BaseModel


class MaterialGroupProductProcess(BaseModel):
    """物料分组产品工艺配置（每分组一行）"""

    class Meta:
        table = "apps_master_data_material_group_product_process"
        table_description = "基础数据管理 - 物料分组产品工艺"
        indexes = [
            ("tenant_id",),
            ("material_group_id",),
            ("uuid",),
        ]
        unique_together = [("tenant_id", "material_group_id")]

    id = fields.IntField(pk=True, description="主键ID")
    material_group_id = fields.IntField(description="物料分组ID")
    process_route_id = fields.IntField(null=True, description="工艺路线ID")
    allow_operation_jump = fields.BooleanField(default=False, description="是否允许工序跳转")
    lines = fields.JSONField(default=list, description="工序行 JSON 数组")

    deleted_at = fields.DatetimeField(null=True, description="删除时间（软删除）")

    def __str__(self):
        return f"MaterialGroupProductProcess material_group_id={self.material_group_id}"