"""8D D3/D5/D6 行动项"""

from tortoise import fields

from core.models.base import BaseModel


class Quality8DActionItem(BaseModel):
    class Meta:
        table = "apps_kuaizhizao_quality_8d_action_items"
        table_description = "快格轻制造 - 8D 行动项"
        indexes = [
            ("tenant_id",),
            ("report_id",),
            ("discipline",),
            ("assignee_user_id",),
            ("status",),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    report_id = fields.IntField(description="8D 报告ID")
    discipline = fields.CharField(
        max_length=30,
        description="d3_containment/d5_corrective/d6_verification",
    )
    title = fields.CharField(max_length=200, description="行动项标题")
    description = fields.TextField(null=True, description="说明")
    assignee_user_id = fields.IntField(null=True, description="责任人用户ID")
    assignee_name = fields.CharField(max_length=100, null=True, description="责任人姓名快照")
    due_date = fields.DatetimeField(null=True, description="截止")
    status = fields.CharField(
        max_length=20,
        default="open",
        description="open/done/verified/cancelled",
    )
    sort_order = fields.IntField(default=0, description="排序")
    evidence_attachments = fields.JSONField(null=True, description="证据附件")
    completed_at = fields.DatetimeField(null=True, description="完成时间")
    verified_by = fields.IntField(null=True, description="验证人ID")
    verified_by_name = fields.CharField(max_length=100, null=True, description="验证人姓名")
    verified_at = fields.DatetimeField(null=True, description="验证时间")
