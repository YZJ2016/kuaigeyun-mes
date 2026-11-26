from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_packing_profiles" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "profile_code" VARCHAR(50) NOT NULL DEFAULT 'default',
            "material_id" INT,
            "pack_mode" VARCHAR(20) NOT NULL DEFAULT 'box_first',
            "mix_policy" VARCHAR(20) NOT NULL DEFAULT 'same_material',
            "max_quantity" DECIMAL(14,4),
            "seal_policy" VARCHAR(20) NOT NULL DEFAULT 'manual',
            "refill_open_box" BOOL NOT NULL DEFAULT FALSE,
            "require_sealed_for_consume" BOOL NOT NULL DEFAULT TRUE,
            "allow_manual_box_code" BOOL NOT NULL DEFAULT TRUE,
            "is_active" BOOL NOT NULL DEFAULT TRUE,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS "idx_packing_profiles_tenant_code"
            ON "apps_kuaizhizao_packing_profiles" ("tenant_id", "profile_code");
        CREATE INDEX IF NOT EXISTS "idx_packing_profiles_tenant_material"
            ON "apps_kuaizhizao_packing_profiles" ("tenant_id", "material_id");

        CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_packing_binding_lines" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "binding_id" INT NOT NULL,
            "product_id" INT NOT NULL,
            "product_serial_no" VARCHAR(200) NOT NULL,
            "quantity" DECIMAL(14,4) NOT NULL DEFAULT 1,
            "line_status" VARCHAR(20) NOT NULL DEFAULT 'active',
            "scanned_at" TIMESTAMPTZ NOT NULL,
            "unbound_at" TIMESTAMPTZ,
            "consumed_at" TIMESTAMPTZ,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS "idx_packing_binding_lines_binding"
            ON "apps_kuaizhizao_packing_binding_lines" ("tenant_id", "binding_id");
        CREATE INDEX IF NOT EXISTS "idx_packing_binding_lines_serial"
            ON "apps_kuaizhizao_packing_binding_lines" ("tenant_id", "product_serial_no");
        CREATE INDEX IF NOT EXISTS "idx_packing_binding_lines_status"
            ON "apps_kuaizhizao_packing_binding_lines" ("tenant_id", "line_status");

        ALTER TABLE "apps_kuaizhizao_packing_bindings"
            ADD COLUMN IF NOT EXISTS "target_quantity" DECIMAL(14,4);
        ALTER TABLE "apps_kuaizhizao_packing_bindings"
            ADD COLUMN IF NOT EXISTS "consumed_at" TIMESTAMPTZ;
        ALTER TABLE "apps_kuaizhizao_packing_bindings"
            ADD COLUMN IF NOT EXISTS "packing_profile_id" INT;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_packing_bindings"
            DROP COLUMN IF EXISTS "packing_profile_id";
        ALTER TABLE "apps_kuaizhizao_packing_bindings"
            DROP COLUMN IF EXISTS "consumed_at";
        ALTER TABLE "apps_kuaizhizao_packing_bindings"
            DROP COLUMN IF EXISTS "target_quantity";
        DROP TABLE IF EXISTS "apps_kuaizhizao_packing_binding_lines";
        DROP TABLE IF EXISTS "apps_kuaizhizao_packing_profiles";
    """
