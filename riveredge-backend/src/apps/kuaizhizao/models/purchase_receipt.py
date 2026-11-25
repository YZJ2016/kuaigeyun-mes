"""
采购入库单模型

提供采购入库单数据模型定义。

Author: Luigi Lu
Date: 2025-12-30
"""

from tortoise import fields
from core.models.base import BaseModel


class PurchaseReceipt(BaseModel):
    """
    采购入库单

    用于记录采购物料入库的详细信息
    """
    tenant_id = fields.IntField(description="租户ID")
    receipt_code = fields.CharField(max_length=50, db_index=True, description="入库单编码")  # 租户内未删除唯一，见迁移 462

    # 采购订单信息（空白建单无来源订单时为 NULL；禁止写 0，与 FK 冲突）
    purchase_order_id = fields.IntField(null=True, description="采购订单ID（空白建单可空）")
    purchase_order_code = fields.CharField(max_length=50, description="采购订单编码")
    order_type = fields.CharField(
        max_length=20,
        default="标准采购",
        description="采购类型（标准采购/资产采购，与采购订单及金蝶单据类型对齐）",
    )
    supplier_id = fields.IntField(description="供应商ID")
    supplier_name = fields.CharField(max_length=200, description="供应商名称")
    payable_recognition = fields.CharField(
        max_length=32,
        default="on_receipt",
        description="立账策略（应付确认时点，单据真源）",
    )

    # 采购员（对齐采购订单；外推苍穹 → bizoperator_operatornumber）
    buyer_id = fields.IntField(null=True, description="采购员用户ID")
    buyer_name = fields.CharField(max_length=100, null=True, description="采购员姓名")
    buyer_operator_number = fields.CharField(
        max_length=64,
        null=True,
        description="金蝶供应链业务员工号（推送 bizoperator_operatornumber）",
    )

    department_id = fields.IntField(null=True, description="部门ID")
    department_name = fields.CharField(max_length=100, null=True, description="部门名称")

    # 价税/结算（存客商付款方式码；外推苍穹时映射 paymode CREDIT/CASH）
    pay_mode = fields.CharField(
        max_length=32,
        null=True,
        default=None,
        description="付款方式（客商码；历史可含 CREDIT/CASH）",
    )
    advance_payee_id = fields.IntField(null=True, description="员工垫付领款人ID")
    advance_payee_name = fields.CharField(
        max_length=100, null=True, description="员工垫付领款人姓名"
    )
    # 苍穹出站常用编码：单据可改；空则回落接口管理默认值 / 业务配置
    org_number = fields.CharField(max_length=64, null=True, description="库存组织编码（推送 org_number）")
    bizorg_number = fields.CharField(max_length=64, null=True, description="采购组织编码（推送 bizorg_number）")
    billtype_number = fields.CharField(
        max_length=64,
        null=True,
        description="单据类型编码（推送 billtype_number）",
    )
    biztype_number = fields.CharField(
        max_length=64,
        null=True,
        default="110",
        description="业务类型编码（推送 biztype_number，默认物料类采购 110）",
    )
    invscheme_number = fields.CharField(
        max_length=64,
        null=True,
        default="110",
        description="库存事务编码（推送 invscheme_number，默认普通采购入库 110）",
    )
    tax_rate = fields.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        description="税率（百分比，外推明细 taxrate）",
    )
    currency = fields.CharField(max_length=10, null=True, default="CNY", description="币别")

    # 入库信息（服务采购不过账，仓库可空；标准/资产采购由服务层要求填写）
    warehouse_id = fields.IntField(null=True, description="入库仓库ID（服务采购可空）")
    warehouse_name = fields.CharField(max_length=100, null=True, description="入库仓库名称（服务采购可空）")
    receipt_time = fields.DatetimeField(null=True, description="实际入库时间")

    # 入库人/验收人（外推自定义 add2 → fd81_yanshou 等 acceptor_field）
    receiver_id = fields.IntField(null=True, description="入库人/验收人ID")
    receiver_name = fields.CharField(max_length=100, null=True, description="入库人/验收人姓名")

    # 审核信息
    reviewer_id = fields.IntField(null=True, description="审核人ID")
    reviewer_name = fields.CharField(max_length=100, null=True, description="审核人姓名")
    review_time = fields.DatetimeField(null=True, description="审核时间")
    review_status = fields.CharField(max_length=20, default="草稿", description="审核状态")
    review_remarks = fields.TextField(null=True, description="审核备注")

    status = fields.CharField(max_length=20, default="待入库", description="入库状态")
    total_quantity = fields.DecimalField(max_digits=12, decimal_places=4, default=0, description="总入库数量")
    total_amount = fields.DecimalField(max_digits=14, decimal_places=4, default=0, description="未税合计")
    tax_amount = fields.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
        description="税额",
    )
    net_amount = fields.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
        description="价税合计（财务结算额）",
    )

    # 物流信息
    delivery_note = fields.CharField(max_length=100, null=True, description="送货单号")
    invoice_number = fields.CharField(max_length=100, null=True, description="发票号")

    notes = fields.TextField(null=True, description="备注")
    attachments = fields.JSONField(null=True, description="附件列表")
    is_active = fields.BooleanField(default=True, description="是否有效")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    class Meta:
        table = "apps_kuaizhizao_purchase_receipts"
        table_description = "快格轻制造 - 采购入库单"

    class PydanticMeta:
        exclude = ["deleted_at"]
