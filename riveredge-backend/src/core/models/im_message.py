"""IM 消息（业务真源；Centrifugo 仅推送）。"""

from tortoise import fields

from core.models.base import BaseModel


class ImMessage(BaseModel):
    id = fields.IntField(pk=True)
    conversation_id = fields.IntField(db_index=True)
    sender_id = fields.IntField(db_index=True)
    body = fields.TextField()
    kind = fields.CharField(
        max_length=20,
        default="text",
        description="text | system | approval_ref | ai_ref",
    )
    ref_type = fields.CharField(max_length=50, null=True)
    ref_id = fields.CharField(max_length=64, null=True)
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "core_im_messages"
        indexes = (("tenant_id", "conversation_id", "created_at"),)
