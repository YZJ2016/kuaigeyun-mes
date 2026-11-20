"""质量体系 - 外审。不符合走同一张不符合报告，来源 external_audit。"""

from tortoise import fields

from core.models.base import BaseModel


class QmsExternalAudit(BaseModel):
    class Meta:
        table = "apps_kuaizhizao_qms_external_audits"
        table_description = "快格轻制造 - 外审"
        indexes = [("tenant_id",), ("audit_code",), ("audit_type")]
        unique_together = [("tenant_id", "audit_code")]

    id = fields.IntField(pk=True, description="主键ID")
    audit_code = fields.CharField(max_length=50, description="外审编号")
    body_name = fields.CharField(max_length=200, description="机构")
    audit_type = fields.CharField(
        max_length=30,
        description="initial/surveillance/recertification",
    )
    planned_on = fields.DateField(null=True, description="计划日")
    actual_on = fields.DateField(null=True, description="实际日")
    audit_scope = fields.TextField(null=True, description="审核范围")
    remarks = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True, description="软删除")
