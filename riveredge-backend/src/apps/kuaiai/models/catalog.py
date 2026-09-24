"""KU-AI 模型目录（KR-D5）

- KuaiaiLlmProvider：厂商目录（base_url + api_key；provider_type 仅作模板标签，
  非闭集枚举、不得挡自定义保存；api_key 只写、出参打码，不回明文）
- KuaiaiLlmModel：模型目录（挂 provider_id；model_name 自由填；
  model_type 闭集 chat|embed|vision）

消费方一律经 core/ai/runtime/model_factory 解析（目录行优先，IntegrationConfig
单活连接兜底）；运行时只用 base_url + api_key + model_name，无厂商分支。
"""

from tortoise import fields

from core.models.base import BaseModel


class KuaiaiLlmProvider(BaseModel):
    """KU-AI LLM 厂商目录行（OpenAI 兼容端点连接）。"""

    class Meta:
        table = "apps_kuaiai_llm_providers"
        table_description = "KU-AI LLM 厂商目录"
        indexes = [
            ("tenant_id",),
        ]
        # DB 侧为 deleted_at IS NULL 部分唯一索引
        # （迁移 20260925100000_kuaiai_catalog_agent_tables），
        # 软删行不占唯一键、可重建同名 code
        unique_together = (("tenant_id", "uuid"), ("tenant_id", "code"))

    id = fields.IntField(pk=True, description="主键ID")
    tenant_id = fields.IntField(description="组织 ID")
    code = fields.CharField(max_length=64, description="厂商代码（组织内唯一）")
    name = fields.CharField(max_length=100, description="厂商名称")
    base_url = fields.CharField(max_length=500, description="OpenAI 兼容端点 base_url")
    api_key = fields.CharField(max_length=500, null=True, description="API Key（出参打码，不回明文）")
    provider_type = fields.CharField(
        max_length=50, null=True, description="可选模板标签（非闭集枚举，不挡自定义保存）"
    )
    status = fields.CharField(max_length=20, default="启用", description="启用|停用")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    def decrypt_api_key(self) -> str:
        """服务端 api_key 解析 seam（model_factory 优先调用此钩子）。

        当前与 IntegrationConfig 口径一致按列存原值返回；将来若引入
        at-rest cipher，只改这里，调用方不变。
        """
        return (self.api_key or "").strip()

    def __str__(self) -> str:
        return f"KuaiaiLlmProvider: {self.id} ({self.code})"


class KuaiaiLlmModel(BaseModel):
    """KU-AI LLM 模型目录行（model_name 自由填）。"""

    class Meta:
        table = "apps_kuaiai_llm_models"
        table_description = "KU-AI LLM 模型目录"
        indexes = [
            ("tenant_id", "provider_id"),
        ]
        unique_together = (
            ("tenant_id", "uuid"),
            ("tenant_id", "provider_id", "model_name"),
        )

    id = fields.IntField(pk=True, description="主键ID")
    tenant_id = fields.IntField(description="组织 ID")
    provider_id = fields.IntField(description="所属厂商目录行 ID（apps_kuaiai_llm_providers.id）")
    model_name = fields.CharField(max_length=200, description="模型名（自由填，上游 model 参数）")
    model_type = fields.CharField(max_length=20, description="chat|embed|vision")
    status = fields.CharField(max_length=20, default="启用", description="启用|停用")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    def __str__(self) -> str:
        return f"KuaiaiLlmModel: {self.id} ({self.model_name})"
