"""质量体系 - 内审年度计划。单次内审必须挂在年度计划下。"""

from tortoise import fields

from core.models.base import BaseModel


class QmsInternalAuditAnnualPlan(BaseModel):
    class Meta:
        table = "apps_kuaizhizao_qms_internal_audit_annual_plans"
        table_description = "快格轻制造 - 内审年度计划"
        indexes = [("tenant_id",), ("plan_year",)]
        unique_together = [("tenant_id", "plan_year")]

    id = fields.IntField(pk=True, description="主键ID")
    plan_year = fields.IntField(description="年度")
    covered_processes = fields.TextField(null=True, description="覆盖过程")
    planned_months = fields.JSONField(null=True, description="计划月份 1-12")
    lead_auditor = fields.CharField(max_length=100, null=True, description="审核组长")
    remarks = fields.TextField(null=True, description="备注")
    deleted_at = fields.DatetimeField(null=True, description="软删除")
