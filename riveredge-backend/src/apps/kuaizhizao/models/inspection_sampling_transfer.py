"""
GB/T 2828.1 抽检严格度转移状态（租户 + 物料 + 方案 + 步骤）
"""

from tortoise import fields

from core.models.base import BaseModel


class InspectionSamplingTransferState(BaseModel):
    class Meta:
        table = "apps_kuaizhizao_inspection_sampling_transfer_states"
        table_description = "快格轻制造 - 国标抽检严格度转移状态"
        unique_together = (("tenant_id", "material_id", "plan_id", "step_key"),)
        indexes = [
            ("tenant_id", "material_id"),
            ("tenant_id", "plan_id"),
        ]

    id = fields.IntField(pk=True)
    material_id = fields.IntField(description="物料 ID")
    plan_id = fields.IntField(description="质检方案 ID")
    step_key = fields.CharField(max_length=36, description="方案步骤 step_key")
    strictness = fields.CharField(max_length=20, default="normal", description="当前严格度")
    recent_lot_verdicts = fields.JSONField(default=list, description="最近批结论序列 accept/reject")
    consecutive_accept = fields.IntField(default=0)
    consecutive_reject = fields.IntField(default=0)
