"""质量体系 - 纠正预防（菜单名不用 CAPA）。"""

from tortoise import fields

from core.models.base import BaseModel


class QmsCorrectiveAction(BaseModel):
    class Meta:
        table = "apps_kuaizhizao_qms_corrective_actions"
        table_description = "快格轻制造 - 纠正预防"
        indexes = [
            ("tenant_id",),
            ("action_code",),
            ("status",),
            ("source_type", "source_id"),
        ]
        unique_together = [("tenant_id", "action_code")]

    id = fields.IntField(pk=True, description="主键ID")
    action_code = fields.CharField(max_length=50, description="纠正预防编号")
    source_type = fields.CharField(
        max_length=40,
        description="nonconformity_report/quality_complaint/management_review_resolution",
    )
    source_id = fields.IntField(null=True, description="来源单据ID")
    source_code = fields.CharField(max_length=50, null=True, description="来源单号")
    problem_summary = fields.TextField(description="问题摘要")
    cause = fields.TextField(null=True, description="原因")
    correction = fields.TextField(null=True, description="纠正")
    prevention = fields.TextField(null=True, description="预防")
    responsible_person = fields.CharField(max_length=100, null=True, description="责任人")
    due_on = fields.DateField(null=True, description="要求完成日")
    verifier_name = fields.CharField(max_length=100, null=True, description="验证人")
    verified_on = fields.DateField(null=True, description="验证日")
    verification_conclusion = fields.TextField(null=True, description="验证结论")
    need_eight_d = fields.BooleanField(default=False, description="是否需要8D")
    eight_d_code = fields.CharField(max_length=50, null=True, description="已有8D单号")
    status = fields.CharField(
        max_length=20,
        default="registered",
        description="registered/in_progress/pending_verify/closed",
    )
    remarks = fields.TextField(null=True, description="备注")
    attachments = fields.JSONField(null=True, description="附件")
    deleted_at = fields.DatetimeField(null=True, description="软删除")
