"""KU-AI 助手对话历史（按租户 + 用户隔离）。"""

from tortoise import fields

from core.models.base import BaseModel


class KuaiaiAssistantConversation(BaseModel):
    """core_kuaiai_assistant_conversations：标签页助手会话与消息 JSON。"""

    id = fields.IntField(pk=True)
    user_id = fields.IntField(db_index=True, description="所属用户 ID")
    title = fields.CharField(max_length=200, description="会话标题")
    messages = fields.JSONField(default=list, description="OpenAI 风格消息列表 [{role, content}]")

    class Meta:
        table = "core_kuaiai_assistant_conversations"
        unique_together = (("tenant_id", "user_id", "uuid"),)
        indexes = (("tenant_id", "user_id", "updated_at"),)
