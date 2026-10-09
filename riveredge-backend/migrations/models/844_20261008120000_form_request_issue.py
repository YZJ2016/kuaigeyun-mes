"""会签申请：下发时间与下发对象 grant（L54 技术工作联系单）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaioa_form_requests"
    ADD COLUMN IF NOT EXISTS "issued_at" TIMESTAMPTZ;
ALTER TABLE "apps_kuaioa_form_requests"
    ADD COLUMN IF NOT EXISTS "issued_by" INT;
ALTER TABLE "apps_kuaioa_form_requests"
    ADD COLUMN IF NOT EXISTS "issued_by_name" VARCHAR(100);

CREATE TABLE IF NOT EXISTS "apps_kuaioa_form_request_issue_grants" (
    "id" SERIAL PRIMARY KEY,
    "uuid" VARCHAR(36) NOT NULL UNIQUE,
    "tenant_id" INT NOT NULL,
    "request_id" INT NOT NULL,
    "target_type" VARCHAR(20) NOT NULL,
    "target_id" INT NOT NULL,
    "target_label" VARCHAR(200),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" INT,
    "created_by_name" VARCHAR(100),
    "updated_by" INT,
    "updated_by_name" VARCHAR(100),
    "deleted_at" TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS "idx_kuaioa_fr_issue_grants_tenant_request"
    ON "apps_kuaioa_form_request_issue_grants" ("tenant_id", "request_id");
CREATE INDEX IF NOT EXISTS "idx_kuaioa_fr_issue_grants_tenant_target"
    ON "apps_kuaioa_form_request_issue_grants" ("tenant_id", "target_type", "target_id");
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
DROP TABLE IF EXISTS "apps_kuaioa_form_request_issue_grants";
ALTER TABLE "apps_kuaioa_form_requests"
    DROP COLUMN IF EXISTS "issued_by_name";
ALTER TABLE "apps_kuaioa_form_requests"
    DROP COLUMN IF EXISTS "issued_by";
ALTER TABLE "apps_kuaioa_form_requests"
    DROP COLUMN IF EXISTS "issued_at";
"""
