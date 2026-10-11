"""KU-AI 租户场景实例（spec 181）

- KuaiaiAgentScene：六个出厂模板 → 本租户实例/档案映射。
  ``instance_key=template_key`` 为该租户的系统预置行（``origin=system_seed``），
  复制场景生成新唯一 instance_key、保留源 ``template_key``（``origin=copy``）。
- ``overrides`` 仅存白名单覆盖字段（name/description/image_key/sample_prompt/
  capability_tags/scene_route），由服务层闭集校验；
  ``agent_profile_id`` 无 DB FK，同租户归属由服务层复核。
- DB 侧 ``(tenant_id, instance_key)`` 为 deleted_at IS NULL 部分唯一索引
  （软删行不占唯一键，但服务层不因手动解绑/软删悄然重建预置行）。
"""

from tortoise import fields

from core.models.base import BaseModel

SCENE_ORIGIN_SYSTEM_SEED = "system_seed"
SCENE_ORIGIN_COPY = "copy"
SCENE_ORIGINS = frozenset({SCENE_ORIGIN_SYSTEM_SEED, SCENE_ORIGIN_COPY})


class KuaiaiAgentScene(BaseModel):
    """KU-AI 租户场景实例：稳定 key → 模板元数据 + 覆盖字段 + 档案绑定。"""

    class Meta:
        table = "apps_kuaiai_agent_scenes"
        table_description = "KU-AI 租户场景实例"
        indexes = [
            ("tenant_id", "template_key"),
        ]
        unique_together = (("tenant_id", "uuid"),)

    id = fields.IntField(pk=True, description="主键ID")
    tenant_id = fields.IntField(description="组织 ID")
    instance_key = fields.CharField(
        max_length=80, description="实例稳定 key（预置=template_key，复制=服务端生成）"
    )
    template_key = fields.CharField(max_length=80, description="后端模板 key（不可改）")
    origin = fields.CharField(
        max_length=20,
        default=SCENE_ORIGIN_SYSTEM_SEED,
        description="来源：system_seed|copy",
    )
    agent_profile_id = fields.IntField(
        null=True,
        description="绑定的 Agent 档案 ID（apps_kuaiai_agent_profiles.id；无 DB FK，服务层复核归属）",
    )
    overrides = fields.JSONField(
        default=dict, description="白名单覆盖字段 JSON（name/description/image_key 等）"
    )
    enabled = fields.BooleanField(default=True, description="实例单项开关")
    deleted_at = fields.DatetimeField(null=True, description="删除时间")

    def __str__(self) -> str:
        return f"KuaiaiAgentScene: {self.id} ({self.instance_key})"
