"""
其他出库单模型

提供其他出库单数据模型定义，用于盘亏/样品/报废/其他等杂项出库。

Author: RiverEdge Team
Date: 2026-02-19
"""

from tortoise import fields
from core.models.base import BaseModel


class OtherOutbound(BaseModel):
    """
    其他出库单

    用于记录无上游单据的杂项出库，通过 reason_type 区分（盘亏/样品/报废/其他）
    """
    tenant_id = fields.IntField(description="租户ID")
    outbound_code = fields.CharField(max_length=50, db_index=True, description="出库单编码")  # 租户内未删除唯一，见迁移 462

    outbound_type = fields.CharField(
        max_length=20,
        null=True,
        default="物料出库",
        description="出库类型（物料出库/资产出库；空则外推按行类别推断）",
    )

    # 出库原因
    reason_type = fields.CharField(max_length=20, description="原因类型：盘亏/样品/报废/其他")
    reason_desc = fields.TextField(null=True, description="原因说明")

    # 出库信息
    warehouse_id = fields.IntField(description="出库仓库ID")
    warehouse_name = fields.CharField(max_length=100, description="出库仓库名称")
    delivery_time = fields.DatetimeField(null=True, description="实际出库时间")

    # 出库人信息
    deliverer_id = fields.IntField(null=True, description="出库人ID")
    deliverer_name = fields.CharField(max_length=100, null=True, description="出库人姓名")

    # 金蝶其他出库表头（领用部门 / 领用人 / 客户领用）
    pick_department_id = fields.IntField(null=True, description="领用部门ID")
    pick_department_code = fields.CharField(max_length=64, null=True, description="领用部门编码（金蝶 pickdept_number）")
    pick_department_name = fields.CharField(max_length=100, null=True, description="领用部门名称")
    picker_id = fields.IntField(null=True, description="领用人用户ID")
    picker_name = fields.CharField(max_length=100, null=True, description="领用人姓名")
    picker_operator_number = fields.CharField(
        max_length=64,
        null=True,
        description="金蝶领用人工号 pickeroperator_number",
    )
    customer_id = fields.IntField(null=True, description="客户ID（客户领用）")
    customer_name = fields.CharField(max_length=200, null=True, description="客户名称")
    customer_number = fields.CharField(max_length=64, null=True, description="金蝶客户编码 customer_number")

    # 审核信息
    reviewer_id = fields.IntField(null=True, description="审核人ID")
    reviewer_name = fields.CharField(max_length=100, null=True, description="审核人姓名")
    review_time = fields.DatetimeField(null=True, description="审核时间")
    review_status = fields.CharField(max_length=20, default="待审核", description="审核状态")
    review_remarks = fields.TextField(null=True, description="审核备注")

    status = fields.CharField(max_length=20, default="待出库", description="出库状态")
    total_quantity = fields.DecimalField(max_digits=12, decimal_places=4, default=0, description="总出库数量")
    total_amount = fields.DecimalField(max_digits=14, decimal_places=4, default=0, description="总金额")

    notes = fields.TextField(null=True, description="备注")
    attachments = fields.JSONField(null=True, description="附件列表")
    is_active = fields.BooleanField(default=True, description="是否有效")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    class Meta:
        table = "apps_kuaizhizao_other_outbounds"
        table_description = "快格轻制造 - 其他出库单"
        indexes = [
            ("tenant_id",),
            ("outbound_code",),
            ("warehouse_id",),
            ("reason_type",),
            ("status",),
        ]

    class PydanticMeta:
        exclude = ["deleted_at"]
