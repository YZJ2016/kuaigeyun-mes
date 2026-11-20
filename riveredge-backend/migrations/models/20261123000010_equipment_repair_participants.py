"""设备维修：开始时间 + 参与人（协作/转派）台账。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_equipment_repairs"
            ADD COLUMN IF NOT EXISTS "started_at" TIMESTAMPTZ;

        CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_equipment_repair_participants" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "created_at" TIMESTAMPTZ NOT NULL,
            "updated_at" TIMESTAMPTZ NOT NULL,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "repair_id" INT NOT NULL,
            "repair_uuid" VARCHAR(36) NOT NULL,
            "user_id" INT NOT NULL,
            "user_name" VARCHAR(100) NOT NULL,
            "role" VARCHAR(20) NOT NULL DEFAULT '主责',
            "status" VARCHAR(20) NOT NULL DEFAULT '进行中',
            "joined_at" TIMESTAMPTZ NOT NULL,
            "left_at" TIMESTAMPTZ,
            "reassigned_to_id" INT,
            "reassigned_to_name" VARCHAR(100),
            "remark" VARCHAR(500),
            "deleted_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS "idx_eq_repair_part_tenant"
            ON "apps_kuaizhizao_equipment_repair_participants" ("tenant_id");
        CREATE INDEX IF NOT EXISTS "idx_eq_repair_part_repair"
            ON "apps_kuaizhizao_equipment_repair_participants" ("tenant_id", "repair_id");
        CREATE INDEX IF NOT EXISTS "idx_eq_repair_part_user"
            ON "apps_kuaizhizao_equipment_repair_participants" ("tenant_id", "user_id");
        CREATE INDEX IF NOT EXISTS "idx_eq_repair_part_status"
            ON "apps_kuaizhizao_equipment_repair_participants" ("tenant_id", "status");
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_eq_repair_part_uuid"
            ON "apps_kuaizhizao_equipment_repair_participants" ("uuid");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "uid_eq_repair_part_uuid";
        DROP INDEX IF EXISTS "idx_eq_repair_part_status";
        DROP INDEX IF EXISTS "idx_eq_repair_part_user";
        DROP INDEX IF EXISTS "idx_eq_repair_part_repair";
        DROP INDEX IF EXISTS "idx_eq_repair_part_tenant";
        DROP TABLE IF EXISTS "apps_kuaizhizao_equipment_repair_participants";
        ALTER TABLE "apps_kuaizhizao_equipment_repairs"
            DROP COLUMN IF EXISTS "started_at";
    """
