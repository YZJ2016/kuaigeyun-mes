"""体系文件发放、回收、宣贯记录。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_qms_system_document_circulations" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT,
            "document_id" INT NOT NULL,
            "record_type" VARCHAR(20) NOT NULL,
            "document_version" VARCHAR(30) NOT NULL,
            "copies" INT,
            "party_name" VARCHAR(200) NOT NULL,
            "event_on" DATE NOT NULL,
            "signer_name" VARCHAR(100),
            "signed_on" DATE,
            "destroyed" BOOL NOT NULL DEFAULT FALSE,
            "completed" BOOL NOT NULL DEFAULT FALSE,
            "training_ref" VARCHAR(100),
            "remarks" TEXT,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_qms_sysdoc_circulation_uuid"
            ON "apps_kuaizhizao_qms_system_document_circulations" ("uuid");
        CREATE INDEX IF NOT EXISTS "idx_qms_sysdoc_circulation_tenant_doc"
            ON "apps_kuaizhizao_qms_system_document_circulations" ("tenant_id", "document_id");
        COMMENT ON TABLE "apps_kuaizhizao_qms_system_document_circulations"
            IS '体系文件发放、回收、宣贯记录';
    """
