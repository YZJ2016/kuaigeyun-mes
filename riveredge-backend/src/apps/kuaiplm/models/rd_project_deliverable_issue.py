"""研发交付物下发对象（L53 #59 勾选下发）。"""

from tortoise import fields

from core.models.base import BaseModel


class RdProjectDeliverableIssueGrant(BaseModel):
    tenant_id = fields.IntField(description="租户ID")
    deliverable_id = fields.IntField(description="交付物ID")
    target_type = fields.CharField(max_length=20, description="user|role|department")
    target_id = fields.IntField(description="对象ID")
    target_label = fields.CharField(max_length=200, null=True, description="展示快照")
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "apps_kuaiplm_rd_project_deliverable_issue_grants"
        table_description = "快研发 - 交付物下发对象"
        indexes = [
            ("tenant_id", "deliverable_id"),
            ("tenant_id", "target_type", "target_id"),
        ]

    class PydanticMeta:
        exclude = ["deleted_at"]
