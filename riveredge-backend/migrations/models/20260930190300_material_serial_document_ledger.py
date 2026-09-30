"""序列号出入库留痕台账。撤回只追加反向行，不改原行。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_material_serial_document_ledgers" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "serial_no" VARCHAR(100) NOT NULL,
            "material_id" INT NOT NULL,
            "direction" VARCHAR(8) NOT NULL,
            "movement_type" VARCHAR(50) NOT NULL,
            "source_type" VARCHAR(50) NOT NULL,
            "source_doc_id" INT,
            "source_doc_code" VARCHAR(64),
            "idempotency_key" VARCHAR(200) NOT NULL,
            "occurred_at" TIMESTAMPTZ NOT NULL,
            "operator_id" INT,
            "operator_name" VARCHAR(100),
            "reverses_id" INT,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_msdl_tenant_idem_serial"
            ON "apps_kuaizhizao_material_serial_document_ledgers" ("tenant_id", "idempotency_key", "serial_no");
        CREATE INDEX IF NOT EXISTS "idx_msdl_tenant_serial_occurred"
            ON "apps_kuaizhizao_material_serial_document_ledgers" ("tenant_id", "serial_no", "occurred_at");
        CREATE INDEX IF NOT EXISTS "idx_msdl_tenant_reverses"
            ON "apps_kuaizhizao_material_serial_document_ledgers" ("tenant_id", "reverses_id");
        COMMENT ON TABLE "apps_kuaizhizao_material_serial_document_ledgers" IS '序列号出入库留痕';
        COMMENT ON COLUMN "apps_kuaizhizao_material_serial_document_ledgers"."serial_no" IS '序列号，与物料序列号主数据相同';
        COMMENT ON COLUMN "apps_kuaizhizao_material_serial_document_ledgers"."direction" IS 'in 入 / out 出';
        COMMENT ON COLUMN "apps_kuaizhizao_material_serial_document_ledgers"."reverses_id" IS '反向指针，空表示正向流水';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaizhizao_material_serial_document_ledgers";
    """
