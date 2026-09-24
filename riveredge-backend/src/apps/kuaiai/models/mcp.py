"""KU-AI MCP 白名单数据面（KR-D11，S4）

- KuaiaiMcpServer：租户 MCP 服务器白名单（≈ ktg-ai ai_mcp_server）。
- 连接密文口径同 llm_providers.api_key（KR-D5 惯例）：token 列存、出参
  打码（"****" + token_configured）、写路径打码占位/空白视为保留原值；
  ``decrypt_token`` 为服务端解析 seam——当前按列存原值返回，将来引入
  at-rest cipher 只改这里，调用方不变（不新建第二套 cipher、不复用
  数据库口令密钥）。
- transport 仅放行 http（映射 langchain-mcp-adapters streamable_http）；
  endpoint/allowed_tools 的合法性由 services/mcp_guard 在保存与建连两侧
  复核，不落库 SQL/匿名/非 http 行。
"""

from tortoise import fields

from core.models.base import BaseModel


class KuaiaiMcpServer(BaseModel):
    """KU-AI MCP 服务器白名单行（远程 http MCP 连接配置）。"""

    class Meta:
        table = "apps_kuaiai_mcp_servers"
        table_description = "KU-AI MCP 白名单"
        indexes = [
            ("tenant_id",),
        ]
        # unique_together 中 (tenant_id, code) 对应 DB 侧
        # deleted_at IS NULL 部分唯一索引（迁移
        # 20260925130000_kuaiai_mcp_servers），软删行不占唯一键、
        # 可重建同名 code
        unique_together = (("tenant_id", "uuid"), ("tenant_id", "code"))

    id = fields.IntField(pk=True, description="主键ID")
    tenant_id = fields.IntField(description="组织 ID")
    code = fields.CharField(max_length=64, description="服务器代码（组织内唯一）")
    name = fields.CharField(max_length=100, description="服务器名称")
    transport = fields.CharField(
        max_length=20, default="http", description="传输类型（仅 http）"
    )
    endpoint = fields.CharField(
        max_length=500, description="MCP 服务端点 URL（http/https，守卫校验）"
    )
    token = fields.TextField(
        null=True, description="Bearer Token（出参打码，不回明文）"
    )
    allowed_tools = fields.TextField(
        description="允许工具名 CSV（必填非空；SQL 类工具名守卫拒绝）"
    )
    status = fields.CharField(max_length=20, default="启用", description="启用|停用")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    def decrypt_token(self) -> str:
        """服务端 token 解析 seam（mcp_client_service 建连调用此钩子）。

        当前与 IntegrationConfig/api_key 口径一致按列存原值返回；将来若
        引入 at-rest cipher，只改这里，调用方不变。
        """
        return (self.token or "").strip()

    def __str__(self) -> str:
        return f"KuaiaiMcpServer: {self.id} ({self.code})"
