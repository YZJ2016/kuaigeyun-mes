"""单据行主/副数量与行换算率字段。"""

from tortoise import fields


class DocumentLineDualQuantityMixin:
    aux_quantity = fields.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        description="副数量",
    )
    aux_unit = fields.CharField(max_length=20, null=True, description="副单位")
    unit_conversion_rate = fields.DecimalField(
        max_digits=18,
        decimal_places=8,
        null=True,
        description="行换算率（1 副单位 = rate 主单位）",
    )
