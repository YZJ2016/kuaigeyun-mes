"""
销售订单模型

提供销售订单数据模型定义。

Author: Luigi Lu
Date: 2025-12-30
"""

from tortoise import fields
from core.models.base import BaseModel
from apps.kuaizhizao.constants import DemandStatus, ReviewStatus
from apps.kuaizhizao.constants.price_type import DEFAULT_SALES_PRICE_TYPE


class SalesOrder(BaseModel):
    """
    销售订单

    用于记录客户销售订单信息，支持MTO（Make-To-Order）模式的生产
    """
    tenant_id = fields.IntField(description="租户ID")
    order_code = fields.CharField(max_length=50, db_index=True, description="订单编码")  # 租户内未删除唯一，见迁移 462

    # 客户信息
    customer_id = fields.IntField(description="客户ID")
    customer_name = fields.CharField(max_length=200, description="客户名称")
    customer_contact = fields.CharField(max_length=100, null=True, description="客户联系人")
    customer_phone = fields.CharField(max_length=20, null=True, description="客户电话")
    customer_order_no = fields.CharField(max_length=100, null=True, description="客户订单号")

    # 订单基本信息
    order_date = fields.DateField(description="订单日期")
    delivery_date = fields.DateField(description="交货日期")
    order_type = fields.CharField(max_length=20, default="MTO", description="订单类型")

    # 金额信息（与 core.utils.decimal_limits DECIMAL(18,4) 对齐）
    total_quantity = fields.DecimalField(max_digits=18, decimal_places=4, default=0, description="总数量")
    total_amount = fields.DecimalField(max_digits=18, decimal_places=4, default=0, description="总金额")
    price_type = fields.CharField(max_length=20, default=DEFAULT_SALES_PRICE_TYPE, description="价格类型：含税/不含税")
    discount_amount = fields.DecimalField(max_digits=18, decimal_places=4, default=0, description="整单优惠金额")

    # 费用信息
    fee_details = fields.JSONField(null=True, description="费用明细 (JSON)")
    total_fee_amount = fields.DecimalField(max_digits=18, decimal_places=4, default=0, description="总费用金额")

    # 状态
    status = fields.CharField(max_length=20, default=DemandStatus.DRAFT, description="订单状态")

    # 审核信息
    reviewer_id = fields.IntField(null=True, description="审核人ID")
    reviewer_name = fields.CharField(max_length=100, null=True, description="审核人姓名")
    review_time = fields.DatetimeField(null=True, description="审核时间")
    review_status = fields.CharField(max_length=20, default=ReviewStatus.PENDING, description="审核状态")
    review_remarks = fields.TextField(null=True, description="审核备注")

    # 销售信息
    salesman_id = fields.IntField(null=True, description="销售员ID")
    salesman_name = fields.CharField(max_length=100, null=True, description="销售员姓名")

    # 物流信息
    shipping_address = fields.TextField(null=True, description="收货地址")
    shipping_method = fields.CharField(max_length=50, null=True, description="发货方式")
    payment_method_code = fields.CharField(
        max_length=50, null=True, description="付款方式（现金/转账/承兑等）"
    )
    payment_wire_percent = fields.DecimalField(
        max_digits=5, decimal_places=2, null=True, description="电汇比例（%，组合付款）"
    )
    payment_acceptance_percent = fields.DecimalField(
        max_digits=5, decimal_places=2, null=True, description="承兑比例（%，组合付款）"
    )
    settlement_terms_code = fields.CharField(
        max_length=50, null=True, description="结算方式（预付/账期/货到付款等）"
    )
    payment_terms_days = fields.IntField(null=True, description="付款周期（天），对齐客商付款账期")
    payment_terms = fields.CharField(
        max_length=100, null=True, description="付款周期（历史字典码，新单以 payment_terms_days 为准）"
    )
    currency_code = fields.CharField(max_length=20, null=True, default="CNY", description="币种（如 CNY 人民币）")
    exchange_rate = fields.DecimalField(max_digits=8, decimal_places=4, default=1, description="汇率（相对本位币）")

    contract_id = fields.IntField(null=True, description="关联销售合同ID")
    contract_code = fields.CharField(max_length=50, null=True, description="关联销售合同编码")
    is_release_order = fields.BooleanField(default=False, description="是否为框架合同释放单")

    # 预收款（审核通过后自动生成预收收款单）
    prepayment_amount = fields.DecimalField(
        max_digits=18, decimal_places=4, null=True, description="预收款金额"
    )
    prepayment_bank_account_id = fields.IntField(null=True, description="预收款银行账户ID")

    term_group_id = fields.IntField(null=True, description="条款组ID")
    term_group_name = fields.CharField(max_length=200, null=True, description="条款组名称（快照）")
    contract_terms = fields.JSONField(null=True, description="订单条款快照")

    revenue_recognition = fields.CharField(
        max_length=32,
        default="on_shipment",
        description="立账策略（应收确认时点，单据真源）",
    )

    notes = fields.TextField(null=True, description="备注")
    attachments = fields.JSONField(null=True, description="附件列表")

    # 计划/MRP 维度：与关联 Demand 下推需求计算同进同退（不改订单主状态机）
    planning_pushed_to_computation = fields.BooleanField(
        default=False, description="计划侧已下推需求计算"
    )
    planning_computation_id = fields.IntField(null=True, description="关联需求计算ID")
    planning_computation_code = fields.CharField(max_length=50, null=True, description="关联需求计算编码")
    planning_computation_pushed_at = fields.DatetimeField(null=True, description="下推需求计算时间")

    procurement_fulfillment_mode = fields.CharField(
        max_length=32,
        null=True,
        description="外购履单路径 purchase_requisition|purchase_order，首张采购下游落库后锁定",
    )

    is_active = fields.BooleanField(default=True, description="是否有效")
    external_sync_at = fields.DatetimeField(null=True, description="最近从外部接口/数据集同步时间")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    class Meta:
        table = "apps_kuaizhizao_sales_orders"
        table_description = "快格轻制造 - 销售订单"
        indexes = [
            ("tenant_id", "customer_id"),
            ("tenant_id", "status"),
            ("order_date",),
            ("delivery_date",),
        ]

    class PydanticMeta:
        exclude = ["deleted_at"]
