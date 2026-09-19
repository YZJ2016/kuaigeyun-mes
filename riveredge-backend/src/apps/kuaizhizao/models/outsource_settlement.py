"""委外结算单数据模型"""

from tortoise import fields

from core.models.base import BaseModel


class OutsourceSettlement(BaseModel):
    """委外加工费结算单"""

    id = fields.IntField(pk=True, description="主键ID")
    tenant_id = fields.IntField(description="租户ID")

    settlement_code = fields.CharField(max_length=50, db_index=True, description="结算单号")
    supplier_id = fields.IntField(description="供应商ID")
    supplier_code = fields.CharField(max_length=50, description="供应商编码")
    supplier_name = fields.CharField(max_length=200, description="供应商名称")

    business_date = fields.DateField(null=True, description="业务日期")
    total_amount = fields.DecimalField(max_digits=16, decimal_places=4, default=0, description="结算总金额")

    status = fields.CharField(max_length=20, default="草稿", description="状态 草稿/待审核/已审核")
    reviewer_id = fields.IntField(null=True, description="审核人ID")
    reviewer_name = fields.CharField(max_length=100, null=True, description="审核人姓名")
    reviewed_at = fields.DatetimeField(null=True, description="审核时间")
    review_remarks = fields.TextField(null=True, description="审核备注")

    payable_id = fields.IntField(null=True, description="审核生成的差额应付单ID")
    payable_code = fields.CharField(max_length=50, null=True, description="审核生成的差额应付单号")

    settlement_kind = fields.CharField(max_length=20, default="normal", description="结算类型 normal/credit")
    source_settlement_id = fields.IntField(null=True, description="红字单关联蓝字结算单ID")
    auto_generated = fields.BooleanField(default=False, description="是否业务自动生成")
    source_doc_type = fields.CharField(max_length=50, null=True, description="来源单据类型")
    source_doc_id = fields.IntField(null=True, description="来源单据ID")

    notes = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    class Meta:
        table = "apps_kuaizhizao_outsource_settlements"
        indexes = [
            ("tenant_id", "settlement_code"),
            ("tenant_id", "supplier_id"),
            ("tenant_id", "status"),
        ]


class OutsourceSettlementItem(BaseModel):
    """委外结算明细（按委外收货行）"""

    id = fields.IntField(pk=True, description="主键ID")
    tenant_id = fields.IntField(description="租户ID")
    settlement_id = fields.IntField(description="结算单ID")
    line_no = fields.IntField(description="行号")
    line_type = fields.CharField(max_length=30, default="processing", description="行类型 processing/material_deduction/return_credit")

    outsource_material_receipt_id = fields.IntField(null=True, description="委外收货单ID")
    receipt_code = fields.CharField(max_length=50, null=True, description="委外收货单号")
    outsource_work_order_id = fields.IntField(null=True, description="委外工单ID")
    outsource_work_order_code = fields.CharField(max_length=50, null=True, description="委外工单编码")
    product_code = fields.CharField(max_length=50, null=True, description="产品编码")
    product_name = fields.CharField(max_length=200, null=True, description="产品名称")
    unit = fields.CharField(max_length=20, null=True, description="单位")

    outsource_product_return_id = fields.IntField(null=True, description="委外退货单ID")
    deduction_basis_qty = fields.DecimalField(max_digits=14, decimal_places=4, null=True, description="超耗扣款基准数量")
    deduction_basis_amount = fields.DecimalField(max_digits=16, decimal_places=4, null=True, description="超耗扣款基准金额")

    settlement_quantity = fields.DecimalField(max_digits=14, decimal_places=4, default=0, description="本次结算数量")
    unit_price = fields.DecimalField(max_digits=14, decimal_places=4, default=0, description="结算单价")
    amount = fields.DecimalField(max_digits=16, decimal_places=4, default=0, description="结算金额")

    notes = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    class Meta:
        table = "apps_kuaizhizao_outsource_settlement_items"
        indexes = [
            ("tenant_id", "settlement_id"),
            ("tenant_id", "outsource_material_receipt_id"),
        ]
