"""
KU-AI 会话与消息模型（KR-D6/D7）

- KuaiaiChatSession：会话（tenant_id + user_id 归属，agent_id 预留档案挂接）
- KuaiaiChatMessage：消息（role user|assistant|tool；tool_calls/tool_call_id/tool_name
  为全宽历史工具轨迹列，S1 纯对话不落 tool 行但表结构保留；token 回填）

消息表回放是发送历史的唯一来源（无 checkpointer）。
"""

from tortoise import fields

from core.models.base import BaseModel


class KuaiaiChatSession(BaseModel):
    """KU-AI 对话会话（按 tenant_id + user_id 归属）。"""

    class Meta:
        table = "apps_kuaiai_chat_sessions"
        table_description = "KU-AI 对话会话"
        indexes = [
            ("tenant_id", "user_id"),
            ("tenant_id", "last_message_at"),
        ]
        unique_together = (("tenant_id", "uuid"),)

    id = fields.IntField(pk=True, description="主键ID")
    tenant_id = fields.IntField(description="组织 ID")
    # user_id 不单独建索引：查询一律 tenant_id+user_id，由 Meta.indexes 复合索引覆盖
    # （保持 Meta 与手写迁移 20260924130000_kuaiai_chat_tables 物理索引一致，
    #  避免声明了不存在的索引）
    user_id = fields.IntField(description="归属用户 ID")
    title = fields.CharField(max_length=300, default="", description="会话标题")
    agent_id = fields.IntField(null=True, description="Agent 档案 ID（S2 起装配使用）")
    model = fields.CharField(max_length=100, null=True, description="会话选用模型名（无档案全宽对话）")
    last_message_at = fields.DatetimeField(null=True, description="最后一条消息时间")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    def __str__(self) -> str:
        return f"KuaiaiChatSession: {self.id} ({self.title})"


class KuaiaiChatMessage(BaseModel):
    """KU-AI 会话消息（含工具轨迹列；回放为唯一历史来源）。"""

    class Meta:
        table = "apps_kuaiai_chat_messages"
        table_description = "KU-AI 会话消息"
        indexes = [
            ("tenant_id", "session_id"),
        ]
        unique_together = (("tenant_id", "session_id", "seq"),)

    id = fields.IntField(pk=True, description="主键ID")
    tenant_id = fields.IntField(description="组织 ID")
    # session_id 同理：查询一律 tenant_id+session_id，由复合索引覆盖
    session_id = fields.IntField(description="所属会话 ID")
    seq = fields.IntField(description="会话内序号（单调递增）")
    role = fields.CharField(max_length=20, description="user|assistant|tool")
    content = fields.TextField(null=True, description="文本内容")
    # 形态约定：该列存 OpenAI 线格式 [{id, type, function:{name, arguments}}]，
    # 回放进 LangChain 前经 chat_service._normalize_tool_calls 转 {name,args,id}。
    tool_calls = fields.JSONField(null=True, description="assistant 行工具调用（OpenAI 线格式，回放时转 LangChain 形态）")
    tool_call_id = fields.CharField(max_length=100, null=True, description="tool 行对应的调用 id")
    tool_name = fields.CharField(max_length=100, null=True, description="tool 行工具名")
    prompt_tokens = fields.IntField(null=True, description="提示 token 数")
    completion_tokens = fields.IntField(null=True, description="补全 token 数")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    def __str__(self) -> str:
        return f"KuaiaiChatMessage: session={self.session_id} seq={self.seq} role={self.role}"
