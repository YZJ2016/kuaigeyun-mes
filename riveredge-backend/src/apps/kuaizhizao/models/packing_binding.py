"""
装箱打包绑定记录数据模型模块

定义装箱打包绑定记录数据模型，支持成品入库/销售出库来源行关联、
序列号列表、封箱状态与箱托层级字段。
"""

from tortoise import fields
from core.models.base import BaseModel


class PackingBinding(BaseModel):
    """装箱打包绑定记录模型。"""

    class Meta:
        table = "apps_kuaizhizao_packing_bindings"
        table_description = "快格轻制造 - 装箱打包绑定记录"
        indexes = [
            ("tenant_id",),
            ("finished_goods_receipt_id",),
            ("sales_delivery_id",),
            ("source_line_id",),
            ("product_id",),
            ("product_serial_no",),
            ("packing_material_id",),
            ("seal_status",),
            ("parent_box_no",),
            ("pallet_no",),
            ("bound_at",),
            ("created_at",),
        ]

    id = fields.IntField(pk=True, description="主键ID")

    finished_goods_receipt_id = fields.IntField(
        null=True,
        description="成品入库单ID（与 sales_delivery_id 二选一）",
    )
    sales_delivery_id = fields.IntField(
        null=True,
        description="销售出库单ID（与 finished_goods_receipt_id 二选一）",
    )
    source_line_id = fields.IntField(
        null=True,
        description="来源明细行ID（入库行或出库行）",
    )

    product_id = fields.IntField(description="产品ID")
    product_code = fields.CharField(max_length=50, description="产品编码")
    product_name = fields.CharField(max_length=200, description="产品名称")
    product_serial_no = fields.CharField(max_length=200, null=True, description="主序列号（可选）")
    serial_numbers = fields.JSONField(null=True, description="箱内序列号列表")

    packing_material_id = fields.IntField(null=True, description="包装物料ID")
    packing_material_code = fields.CharField(max_length=50, null=True, description="包装物料编码")
    packing_material_name = fields.CharField(max_length=200, null=True, description="包装物料名称")
    packing_quantity = fields.DecimalField(max_digits=14, decimal_places=4, description="装箱数量")
    box_no = fields.CharField(max_length=100, null=True, description="箱号")
    packing_level = fields.CharField(
        max_length=20,
        default="carton",
        description="包装层级 carton/inner/pallet",
    )
    parent_box_no = fields.CharField(max_length=100, null=True, description="父箱号（内箱挂外箱）")
    pallet_no = fields.CharField(max_length=100, null=True, description="托盘号")

    binding_method = fields.CharField(max_length=20, default="manual", description="绑定方式 scan/manual")
    barcode = fields.CharField(max_length=200, null=True, description="条码")
    seal_status = fields.CharField(
        max_length=20,
        default="bound",
        description="封箱状态 bound/sealed",
    )
    bound_by = fields.IntField(description="绑定人ID")
    bound_by_name = fields.CharField(max_length=100, description="绑定人姓名")
    bound_at = fields.DatetimeField(description="绑定时间")

    remarks = fields.TextField(null=True, description="备注")
    attachments = fields.JSONField(null=True, description="附件列表")
    deleted_at = fields.DatetimeField(null=True, description="删除时间（软删除）")

    def __str__(self):
        return f"{self.product_name} - {self.packing_quantity} ({self.box_no or '无箱号'})"
