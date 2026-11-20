"""审批待办企微可更新卡片落库（msgid / response_code）。"""

from tortoise import fields

from .base import BaseModel


class ApprovalWecomCard(BaseModel):
    """
    一张审批实例 × 一位审批人 的企微待办卡片追踪。

    撤回/结束时用 response_code 更新模板卡；无 code 时回退 msgid 撤回。
    """

    id = fields.IntField(pk=True, description="主键")
    approval_instance_id = fields.IntField(description="审批实例 ID")
    recipient_user_id = fields.IntField(description="平台用户 ID")
    wecom_userid = fields.CharField(max_length=64, description="企微 userid")
    msgid = fields.CharField(max_length=128, null=True, description="企微 msgid（可撤回）")
    response_code = fields.CharField(
        max_length=128,
        null=True,
        description="模板卡更新码（72h 内一次性）",
    )
    card_kind = fields.CharField(
        max_length=32,
        default="template_card",
        description="template_card | textcard",
    )
    status = fields.CharField(
        max_length=20,
        default="active",
        description="active | updated | recalled | superseded | failed",
    )
    subject = fields.CharField(max_length=200, null=True, description="卡片标题快照")
    content = fields.TextField(null=True, description="卡片正文快照")
    document_url = fields.CharField(max_length=2048, null=True, description="详情链接")
    task_id = fields.CharField(max_length=128, null=True, description="模板卡 task_id")
    invalidate_label = fields.CharField(
        max_length=64,
        null=True,
        description="失效后按钮/状态文案",
    )
    deleted_at = fields.DatetimeField(null=True, description="软删除")

    class Meta:
        table = "core_approval_wecom_cards"
        indexes = [
            ("tenant_id", "approval_instance_id", "status"),
            ("tenant_id", "approval_instance_id", "recipient_user_id"),
            ("tenant_id", "status"),
        ]
