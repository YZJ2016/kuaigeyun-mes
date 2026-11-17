"""
采购入库单明细模型

提供采购入库单明细数据模型定义。

Author: Luigi Lu
Date: 2025-12-30
"""

from tortoise import fields
from core.models.base import BaseModel
from apps.kuaizhizao.models.mixins.document_line_partner_material import (
    DocumentLinePartnerMaterialSnapshotMixin,
)


class PurchaseReceiptItem(DocumentLinePartnerMaterialSnapshotMixin, BaseModel):
    """
    采购入库单明细

    用于记录采购入库单中每个物料的详细信息
    """
    tenant_id = fields.IntField(description="租户ID")
    receipt_id = fields.IntField(description="入库单ID")

    # 采购订单明细关联
    purchase_order_item_id = fields.IntField(null=True, description="采购订单明细ID（空白建单可空）")
    receipt_notice_item_id = fields.IntField(null=True, description="收货通知明细ID")

    material_id = fields.IntField(description="物料ID")
    material_code = fields.CharField(max_length=50, description="物料编码")
    material_name = fields.CharField(max_length=200, description="物料名称")
    material_spec = fields.CharField(max_length=200, null=True, description="物料规格")
    material_unit = fields.CharField(max_length=20, description="物料单位")

    # 入库数量和价格
    receipt_quantity = fields.DecimalField(max_digits=12, decimal_places=4, description="入库数量")
    unit_price = fields.DecimalField(max_digits=12, decimal_places=4, description="单价")
    display_unit_price = fields.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        description="录入单价（表单口径，含税录入时存用户输入值，只读展示不反算）",
    )
    total_amount = fields.DecimalField(max_digits=14, decimal_places=4, description="金额")
    tax_amount = fields.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        description="行税额（财务 rollup 写回，只读展示禁止前端重算）",
    )
    net_amount = fields.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        description="行价税合计（财务 rollup 写回）",
    )
    tax_rate = fields.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        description="行税率（百分比，与采购订单明细一致）",
    )

    # 质量信息
    qualified_quantity = fields.DecimalField(max_digits=12, decimal_places=4, description="合格数量")
    unqualified_quantity = fields.DecimalField(max_digits=12, decimal_places=4, description="不合格数量")
    quality_status = fields.CharField(max_length=20, default="合格", description="质量状态")

    # 行级入库仓库（可与表头不同；确认入库过账时优先于表头）
    warehouse_id = fields.IntField(null=True, description="行入库仓库ID")
    warehouse_name = fields.CharField(max_length=100, null=True, description="行入库仓库名称")

    # 库位信息
    location_id = fields.IntField(null=True, description="库位ID")
    location_code = fields.CharField(max_length=50, null=True, description="库位编码")

    # 批次信息
    batch_number = fields.CharField(max_length=50, null=True, description="批次号")
    expiry_date = fields.DateField(null=True, description="到期日期")
    manufacturing_date = fields.DateField(null=True, description="生产日期")

    # 序列号信息
    serial_numbers = fields.JSONField(null=True, description="序列号列表（JSON格式，存储多个序列号）")

    # 状态
    status = fields.CharField(max_length=20, default="待入库", description="入库状态")
    receipt_time = fields.DatetimeField(null=True, description="实际入库时间")

    notes = fields.TextField(null=True, description="备注")
    attachments = fields.JSONField(null=True, description="行附件列表")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    class Meta:
        table = "apps_kuaizhizao_purchase_receipt_items"
        table_description = "快格轻制造 - 采购入库单明细"
        indexes = [
            ("tenant_id", "receipt_id"),
            ("material_id",),
            ("location_id",),
            ("receipt_notice_item_id",),
        ]
