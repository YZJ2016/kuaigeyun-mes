"""KU-AI Agent 档案与使用授权（KR-D8/D9）

- KuaiaiAgentProfile：档案（system_prompt / default_model_id / knowledge_ids /
  enabled_tools / mcp_server_ids / status / grant_mode）
- KuaiaiAgentGrant：授权名单行（target_type role|user + target_id）

授权是档案上的数据名单：grant_mode 仅 ROLE|USER 互斥，切换时同一事务清空
对侧名单；启用档案名单不得为空（400），停用允许空；悬挂 role/user id 不产生
授权。配置权（kuaiai:agent:*）≠ 使用权（名单命中）。
"""

from tortoise import fields

from core.models.base import BaseModel


class KuaiaiAgentProfile(BaseModel):
    """KU-AI Agent 档案（装配单元：prompt + 默认模型 + 工具/知识库/MCP 勾选）。"""

    class Meta:
        table = "apps_kuaiai_agent_profiles"
        table_description = "KU-AI Agent 档案"
        indexes = [
            ("tenant_id",),
        ]
        unique_together = (("tenant_id", "uuid"), ("tenant_id", "name"))

    id = fields.IntField(pk=True, description="主键ID")
    tenant_id = fields.IntField(description="组织 ID")
    name = fields.CharField(max_length=100, description="档案名称（组织内唯一）")
    description = fields.TextField(null=True, description="档案描述")
    system_prompt = fields.TextField(null=True, description="系统提示词")
    default_model_id = fields.IntField(
        null=True, description="默认模型目录行 ID（apps_kuaiai_llm_models.id，须 model_type=chat 且启用）"
    )
    # 知识库 id 列表（库表属 S3，本期仅存 JSONB；调用时复核归属）
    knowledge_ids = fields.JSONField(default=list, description="知识库 ID 列表")
    # Tool 五值闭集子集：search_knowledge / query_workorder / list_workorder_tasks /
    # submit_production_feedback / update_workorder_status
    enabled_tools = fields.JSONField(default=list, description="启用工具名列表（闭集子集）")
    # MCP 白名单 id 列表（表属 S4，本期仅存 JSONB）
    mcp_server_ids = fields.JSONField(default=list, description="MCP 白名单 ID 列表")
    status = fields.CharField(max_length=20, default="停用", description="启用|停用")
    grant_mode = fields.CharField(max_length=10, description="ROLE|USER（互斥）")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    def __str__(self) -> str:
        return f"KuaiaiAgentProfile: {self.id} ({self.name})"


class KuaiaiAgentGrant(BaseModel):
    """KU-AI Agent 档案使用授权名单行。"""

    class Meta:
        table = "apps_kuaiai_agent_grants"
        table_description = "KU-AI Agent 档案使用授权名单"
        indexes = [
            ("tenant_id", "agent_id"),
        ]
        unique_together = (
            ("tenant_id", "uuid"),
            ("tenant_id", "agent_id", "target_type", "target_id"),
        )

    id = fields.IntField(pk=True, description="主键ID")
    tenant_id = fields.IntField(description="组织 ID")
    agent_id = fields.IntField(description="Agent 档案 ID（apps_kuaiai_agent_profiles.id）")
    target_type = fields.CharField(max_length=10, description="role|user")
    target_id = fields.IntField(description="目标 ID（角色或用户，悬挂 id 不产生授权）")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    def __str__(self) -> str:
        return (
            f"KuaiaiAgentGrant: agent={self.agent_id} "
            f"{self.target_type}={self.target_id}"
        )
