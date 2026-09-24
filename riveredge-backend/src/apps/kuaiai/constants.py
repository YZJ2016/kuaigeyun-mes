"""KU-AI S2 共享常量（目录/档案/授权语义钉死值）。

下游消费方（agent_assembler / model_factory / chat_service 路径 B）统一从这里取，
不要在各自模块里再写字面值。
"""

# 目录行与档案通用状态（KR-D8：status=启用 才参与装配/options）
STATUS_ENABLED = "启用"
STATUS_DISABLED = "停用"
CATALOG_STATUSES = frozenset({STATUS_ENABLED, STATUS_DISABLED})

# llm_models.model_type 闭集（KR-D5：至少 chat|embed|vision）
MODEL_TYPES = frozenset({"chat", "embed", "vision"})
MODEL_TYPE_CHAT = "chat"

# KR-D10 受控写 Tool 闭集五值：保存时校验，未知名 400；写 Tool 默认不勾
ENABLED_TOOL_NAMES = frozenset(
    {
        "search_knowledge",
        "query_workorder",
        "list_workorder_tasks",
        "submit_production_feedback",
        "update_workorder_status",
    }
)

# KR-D9 授权模式（档案列，大写互斥）；grant 行 target_type 用小写 role|user
GRANT_MODE_ROLE = "ROLE"
GRANT_MODE_USER = "USER"
GRANT_MODES = frozenset({GRANT_MODE_ROLE, GRANT_MODE_USER})
GRANT_TARGET_TYPE_ROLE = "role"
GRANT_TARGET_TYPE_USER = "user"

# KR-D8 租户默认档案：对齐 ktg-ai A31（``AiAgentProfileServiceImpl.DEFAULT_NAME``）。
# 仅按名称解析；不强制种子。若租户自行建同名档案，enabled_tools 约定仅
# ``search_knowledge``（种子非强制，本仓不自动插入）。
DEFAULT_AGENT_PROFILE_NAME = "默认助手"
