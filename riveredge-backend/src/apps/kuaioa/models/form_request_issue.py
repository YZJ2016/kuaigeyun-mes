"""会签申请单下发对象（L54 勾选下发）。"""

from tortoise import fields

from core.models.base import BaseModel


class KuaioaFormRequestIssueGrant(BaseModel):
    tenant_id = fields.IntField(description="租户ID")
    request_id = fields.IntField(description="申请单ID")
    target_type = fields.CharField(max_length=20, description="user|role|department")
    target_id = fields.IntField(description="对象ID")
    target_label = fields.CharField(max_length=200, null=True, description="展示快照")
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "apps_kuaioa_form_request_issue_grants"
        table_description = "轻办公 - 会签申请下发对象"
        indexes = [
            ("tenant_id", "request_id"),
            ("tenant_id", "target_type", "target_id"),
        ]

    class PydanticMeta:
        exclude = ["deleted_at"]
