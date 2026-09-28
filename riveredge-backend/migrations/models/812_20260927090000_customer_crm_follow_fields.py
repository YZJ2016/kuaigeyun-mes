"""客户跟进 CRM 字段：跟进状态、意向物料、市场范围、跟进附件；定级字典补 D/已成交。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True

_LEVEL_ITEMS = [
    (5, "D级", "D", "D级"),
    (6, "已成交", "DEAL", "已成交客户"),
]


async def upgrade(db: BaseDBAsyncClient) -> str:
    ddl = """
        ALTER TABLE "apps_master_data_customers"
            ADD COLUMN IF NOT EXISTS "follow_status" VARCHAR(20) NOT NULL DEFAULT 'pending',
            ADD COLUMN IF NOT EXISTS "project_description" TEXT,
            ADD COLUMN IF NOT EXISTS "intent_material_name" VARCHAR(200),
            ADD COLUMN IF NOT EXISTS "region_text" VARCHAR(100),
            ADD COLUMN IF NOT EXISTS "market_scope" VARCHAR(20) NOT NULL DEFAULT 'domestic',
            ADD COLUMN IF NOT EXISTS "country_code" VARCHAR(50),
            ADD COLUMN IF NOT EXISTS "campaign_name" VARCHAR(200),
            ADD COLUMN IF NOT EXISTS "required_capacity_text" VARCHAR(200);
        CREATE INDEX IF NOT EXISTS "idx_md_customers_follow_status"
            ON "apps_master_data_customers" ("tenant_id", "follow_status");
        CREATE INDEX IF NOT EXISTS "idx_md_customers_market_scope"
            ON "apps_master_data_customers" ("tenant_id", "market_scope");
        COMMENT ON COLUMN "apps_master_data_customers"."follow_status" IS '跟进状态：pending/followed';
        COMMENT ON COLUMN "apps_master_data_customers"."project_description" IS '项目描述';
        COMMENT ON COLUMN "apps_master_data_customers"."intent_material_name" IS '意向物料名称';
        COMMENT ON COLUMN "apps_master_data_customers"."region_text" IS '客户地区（自由文本）';
        COMMENT ON COLUMN "apps_master_data_customers"."market_scope" IS '市场范围：domestic/export';
        COMMENT ON COLUMN "apps_master_data_customers"."country_code" IS '国家/地区编码或名称';
        COMMENT ON COLUMN "apps_master_data_customers"."campaign_name" IS '广告系列名称';
        COMMENT ON COLUMN "apps_master_data_customers"."required_capacity_text" IS '所需生产能力';

        UPDATE "apps_master_data_customers"
        SET follow_status = 'followed'
        WHERE deleted_at IS NULL
          AND last_follow_up_at IS NOT NULL
          AND follow_status = 'pending';

        ALTER TABLE "apps_kuaizhizao_customer_follow_ups"
            ADD COLUMN IF NOT EXISTS "attachment_uuids" JSONB NOT NULL DEFAULT '[]'::jsonb;
        COMMENT ON COLUMN "apps_kuaizhizao_customer_follow_ups"."attachment_uuids" IS '跟进附件 UUID 列表';
    """
    item_inserts = []
    for sort_order, label, value, description in _LEVEL_ITEMS:
        item_inserts.append(
            f"""
        INSERT INTO core_dictionary_items (
            uuid, tenant_id, dictionary_id, label, value, description, sort_order, is_active, created_at, updated_at
        )
        SELECT
            gen_random_uuid()::text,
            d.tenant_id,
            d.id,
            '{label}',
            '{value}',
            '{description}',
            {sort_order},
            TRUE,
            NOW(),
            NOW()
        FROM core_data_dictionaries d
        WHERE d.code = 'CUSTOMER_LEVEL'
          AND d.deleted_at IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM core_dictionary_items i
            WHERE i.tenant_id = d.tenant_id
              AND i.dictionary_id = d.id
              AND i.value = '{value}'
              AND i.deleted_at IS NULL
          );
        """
        )
    return ddl + "\n".join(item_inserts)


async def downgrade(db: BaseDBAsyncClient) -> str:
    values = ", ".join(f"'{v}'" for _, _, v, _ in _LEVEL_ITEMS)
    return f"""
        DELETE FROM core_dictionary_items i
        USING core_data_dictionaries d
        WHERE i.dictionary_id = d.id
          AND d.code = 'CUSTOMER_LEVEL'
          AND i.value IN ({values});

        ALTER TABLE "apps_kuaizhizao_customer_follow_ups"
            DROP COLUMN IF EXISTS "attachment_uuids";

        DROP INDEX IF EXISTS "idx_md_customers_follow_status";
        DROP INDEX IF EXISTS "idx_md_customers_market_scope";
        ALTER TABLE "apps_master_data_customers"
            DROP COLUMN IF EXISTS "follow_status",
            DROP COLUMN IF EXISTS "project_description",
            DROP COLUMN IF EXISTS "intent_material_name",
            DROP COLUMN IF EXISTS "region_text",
            DROP COLUMN IF EXISTS "market_scope",
            DROP COLUMN IF EXISTS "country_code",
            DROP COLUMN IF EXISTS "campaign_name",
            DROP COLUMN IF EXISTS "required_capacity_text";
    """
