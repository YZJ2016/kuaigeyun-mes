"""KU-AI Agent 执行现场 checkpoint 表（spec 192 / SC-D8）

- KuaiaiAgentCheckpoint：checkpoint 主表（checkpoint/metadata 以 (type, bytes) 存储）
- KuaiaiAgentCheckpointWrite：pending writes 表

只存 LangGraph 执行现场（HITL 中断/续跑），不是审计或会话历史真源——
消息表（apps_kuaiai_chat_messages）仍是历史真源（KR-G3 方案 C）。
数据经 TortoiseCheckpointSaver 读写，不进入任何对外接口；
内容可能含业务参数，日志只允许出现 thread_id 与序列化类型，不出现值。
删除为硬删（执行现场为瞬态数据，配合完成即删与过期清理控制增长）。
"""

from tortoise import fields

from core.models.base import BaseModel


class KuaiaiAgentCheckpoint(BaseModel):
    """LangGraph checkpoint 主表。"""

    class Meta:
        table = "apps_kuaiai_agent_checkpoints"
        table_description = "KU-AI Agent 执行现场 checkpoint（非审计真源）"
        indexes = [
            ("created_at",),
        ]
        unique_together = (("tenant_id", "thread_id", "checkpoint_ns", "checkpoint_id"),)

    id = fields.IntField(pk=True, description="主键ID")
    tenant_id = fields.IntField(description="组织 ID")
    # 形如 "{tenant}:{user}:{session}"，只由服务端生成，禁止客户端传入
    thread_id = fields.CharField(max_length=255, description="LangGraph 线程 ID（服务端生成）")
    checkpoint_ns = fields.CharField(max_length=255, default="", description="checkpoint 命名空间")
    checkpoint_id = fields.CharField(max_length=64, description="checkpoint ID（uuid6，字典序即时间序）")
    parent_checkpoint_id = fields.CharField(max_length=64, null=True, description="父 checkpoint ID")
    checkpoint_type = fields.CharField(max_length=64, description="checkpoint 序列化类型（serde dumps_typed type）")
    checkpoint_blob = fields.BinaryField(description="checkpoint 序列化内容（serde dumps_typed bytes）")
    metadata_type = fields.CharField(max_length=64, description="metadata 序列化类型")
    metadata_blob = fields.BinaryField(description="metadata 序列化内容")

    def __str__(self) -> str:
        return f"KuaiaiAgentCheckpoint: {self.thread_id}@{self.checkpoint_id}"


class KuaiaiAgentCheckpointWrite(BaseModel):
    """LangGraph pending writes 表（task 粒度中间写入，随 checkpoint 回放）。"""

    class Meta:
        table = "apps_kuaiai_agent_checkpoint_writes"
        table_description = "KU-AI Agent 执行现场 pending writes（非审计真源）"
        indexes = [
            ("tenant_id", "thread_id", "checkpoint_ns", "checkpoint_id"),
            ("created_at",),
        ]
        unique_together = (
            ("tenant_id", "thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "idx"),
        )

    id = fields.IntField(pk=True, description="主键ID")
    tenant_id = fields.IntField(description="组织 ID")
    thread_id = fields.CharField(max_length=255, description="LangGraph 线程 ID（服务端生成）")
    checkpoint_ns = fields.CharField(max_length=255, default="", description="checkpoint 命名空间")
    checkpoint_id = fields.CharField(max_length=64, description="所属 checkpoint ID")
    task_id = fields.CharField(max_length=255, description="产生写入的 task ID")
    # >=0 为常规写入序号；<0 为 WRITES_IDX_MAP 特殊写入（ERROR/INTERRUPT 等）
    idx = fields.IntField(description="task 内写入序号（负数保留给特殊写入）")
    channel = fields.CharField(max_length=255, description="写入的 channel 名")
    value_type = fields.CharField(max_length=64, description="值序列化类型（serde dumps_typed type）")
    value_blob = fields.BinaryField(description="值序列化内容（serde dumps_typed bytes）")
    task_path = fields.CharField(max_length=255, default="", description="task 路径")

    def __str__(self) -> str:
        return f"KuaiaiAgentCheckpointWrite: {self.thread_id}@{self.checkpoint_id} {self.task_id}#{self.idx}"
