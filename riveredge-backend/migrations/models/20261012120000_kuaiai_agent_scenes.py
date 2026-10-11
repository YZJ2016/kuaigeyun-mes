"""
KU-AI spec 181 — 租户场景实例表

新建 apps_kuaiai_agent_scenes（六个出厂场景模板 → 本租户实例/档案映射）：
- instance_key 为实例稳定 key（预置=template_key，复制=服务端生成新 key），
  origin 闭集 system_seed|copy 标识系统预置来源；
- agent_profile_id 挂 apps_kuaiai_agent_profiles.id，不写 DB 级 FK，
  同租户归属由服务层复核（与既有 KU-AI 表风格一致）；
- overrides 仅存白名单覆盖字段 JSON；
- (tenant_id, instance_key) 为 deleted_at IS NULL 部分唯一索引
  （非软删唯一，与迁移 20260925110000_kuaiai_knowledge_base 既有惯例一致），
  (tenant_id, template_key) 查询索引。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaiai_agent_scenes" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "instance_key" VARCHAR(80) NOT NULL,
            "template_key" VARCHAR(80) NOT NULL,
            "origin" VARCHAR(20) NOT NULL DEFAULT 'system_seed',
            "agent_profile_id" INT,
            "overrides" JSONB NOT NULL DEFAULT '{}'::jsonb,
            "enabled" BOOL NOT NULL DEFAULT TRUE,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaiai_scene_tenant_uuid"
            ON "apps_kuaiai_agent_scenes" ("tenant_id", "uuid");
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaiai_scene_tenant_instance"
            ON "apps_kuaiai_agent_scenes" ("tenant_id", "instance_key")
            WHERE "deleted_at" IS NULL;
        CREATE INDEX IF NOT EXISTS "idx_kuaiai_scene_tenant_template"
            ON "apps_kuaiai_agent_scenes" ("tenant_id", "template_key");

        COMMENT ON TABLE "apps_kuaiai_agent_scenes" IS 'KU-AI 租户场景实例';
        COMMENT ON COLUMN "apps_kuaiai_agent_scenes"."instance_key" IS '实例稳定 key（预置=template_key，复制=服务端生成）';
        COMMENT ON COLUMN "apps_kuaiai_agent_scenes"."template_key" IS '后端模板 key（不可改）';
        COMMENT ON COLUMN "apps_kuaiai_agent_scenes"."origin" IS '来源：system_seed|copy';
        COMMENT ON COLUMN "apps_kuaiai_agent_scenes"."agent_profile_id" IS '绑定的 Agent 档案 ID（apps_kuaiai_agent_profiles.id；无 DB FK，服务层复核归属）';
        COMMENT ON COLUMN "apps_kuaiai_agent_scenes"."overrides" IS '白名单覆盖字段 JSON（name/description/image_key/sample_prompt/capability_tags/scene_route）';
        COMMENT ON COLUMN "apps_kuaiai_agent_scenes"."enabled" IS '实例单项开关';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaiai_agent_scenes" CASCADE;
    """
