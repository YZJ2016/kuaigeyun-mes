from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_packing_bindings"
            ADD COLUMN IF NOT EXISTS "source_line_id" INT;

        ALTER TABLE "apps_kuaizhizao_packing_bindings"
            ADD COLUMN IF NOT EXISTS "seal_status" VARCHAR(20) NOT NULL DEFAULT 'bound';

        ALTER TABLE "apps_kuaizhizao_packing_bindings"
            ADD COLUMN IF NOT EXISTS "serial_numbers" JSONB;

        ALTER TABLE "apps_kuaizhizao_packing_bindings"
            ADD COLUMN IF NOT EXISTS "parent_box_no" VARCHAR(100);

        ALTER TABLE "apps_kuaizhizao_packing_bindings"
            ADD COLUMN IF NOT EXISTS "pallet_no" VARCHAR(100);

        ALTER TABLE "apps_kuaizhizao_packing_bindings"
            ADD COLUMN IF NOT EXISTS "packing_level" VARCHAR(20) NOT NULL DEFAULT 'carton';

        CREATE INDEX IF NOT EXISTS "idx_packing_bindings_source_line_id"
            ON "apps_kuaizhizao_packing_bindings" ("source_line_id");

        CREATE INDEX IF NOT EXISTS "idx_packing_bindings_seal_status"
            ON "apps_kuaizhizao_packing_bindings" ("seal_status");

        CREATE INDEX IF NOT EXISTS "idx_packing_bindings_parent_box_no"
            ON "apps_kuaizhizao_packing_bindings" ("parent_box_no");

        CREATE INDEX IF NOT EXISTS "idx_packing_bindings_pallet_no"
            ON "apps_kuaizhizao_packing_bindings" ("pallet_no");

        UPDATE "apps_kuaizhizao_packing_bindings" AS pb
        SET "deleted_at" = CURRENT_TIMESTAMP
        FROM (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY tenant_id, box_no
                       ORDER BY updated_at DESC NULLS LAST, id DESC
                   ) AS rn
            FROM "apps_kuaizhizao_packing_bindings"
            WHERE "deleted_at" IS NULL
              AND "box_no" IS NOT NULL
              AND "box_no" <> ''
        ) ranked
        WHERE pb.id = ranked.id
          AND ranked.rn > 1;

        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_packing_bindings_tenant_box_no_alive"
            ON "apps_kuaizhizao_packing_bindings" ("tenant_id", "box_no")
            WHERE "deleted_at" IS NULL AND "box_no" IS NOT NULL AND "box_no" <> '';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "uidx_packing_bindings_tenant_box_no_alive";
        DROP INDEX IF EXISTS "idx_packing_bindings_pallet_no";
        DROP INDEX IF EXISTS "idx_packing_bindings_parent_box_no";
        DROP INDEX IF EXISTS "idx_packing_bindings_seal_status";
        DROP INDEX IF EXISTS "idx_packing_bindings_source_line_id";

        ALTER TABLE "apps_kuaizhizao_packing_bindings" DROP COLUMN IF EXISTS "packing_level";
        ALTER TABLE "apps_kuaizhizao_packing_bindings" DROP COLUMN IF EXISTS "pallet_no";
        ALTER TABLE "apps_kuaizhizao_packing_bindings" DROP COLUMN IF EXISTS "parent_box_no";
        ALTER TABLE "apps_kuaizhizao_packing_bindings" DROP COLUMN IF EXISTS "serial_numbers";
        ALTER TABLE "apps_kuaizhizao_packing_bindings" DROP COLUMN IF EXISTS "seal_status";
        ALTER TABLE "apps_kuaizhizao_packing_bindings" DROP COLUMN IF EXISTS "source_line_id";
    """
