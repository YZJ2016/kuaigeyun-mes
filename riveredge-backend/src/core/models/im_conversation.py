"""IM 会话与成员（与 MessageLog 站内信分层）。"""

from tortoise import fields

from core.models.base import BaseModel


class ImConversation(BaseModel):
    id = fields.IntField(pk=True)
    kind = fields.CharField(max_length=20, description="direct | group | system")
    title = fields.CharField(max_length=200, null=True)
    is_public = fields.BooleanField(default=False, description="租户默认公共群")
    last_message_at = fields.DatetimeField(null=True)
    last_message_preview = fields.CharField(max_length=500, null=True)
    created_by_id = fields.IntField(null=True)
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "core_im_conversations"
        indexes = (("tenant_id", "last_message_at"), ("tenant_id", "is_public"))


class ImConversationMember(BaseModel):
    id = fields.IntField(pk=True)
    conversation_id = fields.IntField(db_index=True)
    user_id = fields.IntField(db_index=True)
    role = fields.CharField(max_length=20, default="member")
    last_read_at = fields.DatetimeField(null=True)
    is_pinned = fields.BooleanField(default=False, description="当前用户是否置顶该会话")
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "core_im_conversation_members"
        unique_together = (("tenant_id", "conversation_id", "user_id"),)
        indexes = (("tenant_id", "user_id", "is_pinned"),)


class ImConversationModule(BaseModel):
    """群聊绑定的业务模块（应用 code，可多选）。"""

    id = fields.IntField(pk=True)
    conversation_id = fields.IntField(db_index=True)
    module_code = fields.CharField(max_length=64)
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "core_im_conversation_modules"
        unique_together = (("tenant_id", "conversation_id", "module_code"),)
        indexes = (("tenant_id", "module_code"),)
