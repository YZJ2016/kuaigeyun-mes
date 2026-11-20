"""产线可生产自制件绑定（软依赖：未装 ind_relay 时查找返回空）。"""

from tortoise import fields

from core.models.base import BaseModel


class RelayLineProduct(BaseModel):
    """产线可生产自制件绑定表（行业表，不污染通用产线主数据）。"""

    class Meta:
        table = "apps_ind_relay_line_products"
        table_description = "继电器行业 - 产线可生产自制件"
        app = "models"
        indexes = [
            ("tenant_id",),
            ("production_line_id",),
            ("product_id",),
            ("uuid",),
        ]

    id = fields.IntField(pk=True)
    production_line_id = fields.IntField(description="产线ID")
    product_id = fields.IntField(description="自制件物料ID")
    product_code = fields.CharField(max_length=50, null=True, description="自制件编码")
    product_name = fields.CharField(max_length=200, null=True, description="自制件名称")
    deleted_at = fields.DatetimeField(null=True)
