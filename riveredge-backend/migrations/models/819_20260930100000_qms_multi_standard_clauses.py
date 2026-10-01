"""
质量体系多标准：标准目录、条款 standard_id、文件/内审条款 M2M、管理评审挂标准。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_qms_standards" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "uuid" VARCHAR(36),
    "tenant_id" INT NOT NULL,
    "code" VARCHAR(30) NOT NULL,
    "name" VARCHAR(200) NOT NULL,
    "family" VARCHAR(30) NOT NULL DEFAULT 'custom',
    "is_preset" BOOL NOT NULL DEFAULT FALSE,
    "is_active" BOOL NOT NULL DEFAULT TRUE,
    "sort_order" INT NOT NULL DEFAULT 0,
    "deleted_at" TIMESTAMPTZ,
    "created_by" INT,
    "created_by_name" VARCHAR(100),
    "updated_by" INT,
    "updated_by_name" VARCHAR(100),
    "created_at" TIMESTAMPTZ,
    "updated_at" TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS "uidx_qms_standard_tenant_code"
    ON "apps_kuaizhizao_qms_standards" ("tenant_id", "code")
    WHERE "deleted_at" IS NULL;

INSERT INTO "apps_kuaizhizao_qms_standards" (
    "uuid", "tenant_id", "code", "name", "family", "is_preset", "is_active", "sort_order", "created_at", "updated_at"
)
SELECT
    gen_random_uuid()::text,
    t."tenant_id",
    v.code,
    v.name,
    v.family,
    TRUE,
    TRUE,
    v.sort_order,
    NOW(),
    NOW()
FROM (
    SELECT DISTINCT "tenant_id" FROM "apps_kuaizhizao_qms_iso_clauses" WHERE "deleted_at" IS NULL
    UNION
    SELECT DISTINCT "tenant_id" FROM "apps_kuaizhizao_qms_system_documents" WHERE "deleted_at" IS NULL
    UNION
    SELECT DISTINCT "tenant_id" FROM "apps_kuaizhizao_qms_internal_audits" WHERE "deleted_at" IS NULL
    UNION
    SELECT DISTINCT "tenant_id" FROM "apps_kuaizhizao_qms_management_reviews" WHERE "deleted_at" IS NULL
) t
CROSS JOIN (
    VALUES
        ('ISO9001:2015', 'ISO 9001:2015 质量管理体系', 'iso9001', 100),
        ('ISO14001:2015', 'ISO 14001:2015 环境管理体系', 'iso14001', 200),
        ('ISO45001:2018', 'ISO 45001:2018 职业健康安全管理体系', 'iso45001', 300),
        ('IATF16949:2016', 'IATF 16949:2016 汽车质量管理体系', 'iatf16949', 150)
) AS v(code, name, family, sort_order)
WHERE NOT EXISTS (
    SELECT 1 FROM "apps_kuaizhizao_qms_standards" s
    WHERE s."tenant_id" = t."tenant_id" AND s."code" = v.code AND s."deleted_at" IS NULL
);

INSERT INTO "apps_kuaizhizao_qms_standards" (
    "uuid", "tenant_id", "code", "name", "family", "is_preset", "is_active", "sort_order", "created_at", "updated_at"
)
SELECT DISTINCT
    gen_random_uuid()::text,
    c."tenant_id",
    c."standard_code",
    c."standard_code",
    'custom',
    FALSE,
    TRUE,
    900,
    NOW(),
    NOW()
FROM "apps_kuaizhizao_qms_iso_clauses" c
WHERE c."deleted_at" IS NULL
  AND c."standard_code" NOT IN ('ISO9001:2015', 'ISO14001:2015', 'ISO45001:2018', 'IATF16949:2016')
  AND NOT EXISTS (
    SELECT 1 FROM "apps_kuaizhizao_qms_standards" s
    WHERE s."tenant_id" = c."tenant_id" AND s."code" = c."standard_code" AND s."deleted_at" IS NULL
);

ALTER TABLE "apps_kuaizhizao_qms_iso_clauses"
    ADD COLUMN IF NOT EXISTS "standard_id" INT;

UPDATE "apps_kuaizhizao_qms_iso_clauses" c
SET "standard_id" = s."id"
FROM "apps_kuaizhizao_qms_standards" s
WHERE c."deleted_at" IS NULL
  AND s."deleted_at" IS NULL
  AND c."tenant_id" = s."tenant_id"
  AND c."standard_code" = s."code"
  AND c."standard_id" IS NULL;

ALTER TABLE "apps_kuaizhizao_qms_iso_clauses"
    ALTER COLUMN "standard_id" SET NOT NULL;

DROP INDEX IF EXISTS "uidx_qms_iso_clause_tenant_std_code";
CREATE UNIQUE INDEX IF NOT EXISTS "uidx_qms_clause_tenant_std_id_code"
    ON "apps_kuaizhizao_qms_iso_clauses" ("tenant_id", "standard_id", "clause_code")
    WHERE "deleted_at" IS NULL;
CREATE INDEX IF NOT EXISTS "idx_qms_iso_clause_standard_id"
    ON "apps_kuaizhizao_qms_iso_clauses" ("standard_id");

CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_qms_document_clauses" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "uuid" VARCHAR(36),
    "tenant_id" INT NOT NULL,
    "document_id" INT NOT NULL,
    "clause_id" INT NOT NULL,
    "is_primary" BOOL NOT NULL DEFAULT FALSE,
    "deleted_at" TIMESTAMPTZ,
    "created_by" INT,
    "created_by_name" VARCHAR(100),
    "updated_by" INT,
    "updated_by_name" VARCHAR(100),
    "created_at" TIMESTAMPTZ,
    "updated_at" TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS "uidx_qms_doc_clause"
    ON "apps_kuaizhizao_qms_document_clauses" ("tenant_id", "document_id", "clause_id")
    WHERE "deleted_at" IS NULL;

INSERT INTO "apps_kuaizhizao_qms_document_clauses" (
    "uuid", "tenant_id", "document_id", "clause_id", "is_primary", "created_at", "updated_at"
)
SELECT
    gen_random_uuid()::text,
    d."tenant_id",
    d."id",
    d."iso_clause_id",
    TRUE,
    NOW(),
    NOW()
FROM "apps_kuaizhizao_qms_system_documents" d
WHERE d."deleted_at" IS NULL
  AND d."iso_clause_id" IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM "apps_kuaizhizao_qms_document_clauses" x
    WHERE x."tenant_id" = d."tenant_id" AND x."document_id" = d."id"
      AND x."clause_id" = d."iso_clause_id" AND x."deleted_at" IS NULL
);

CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_qms_audit_clauses" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "uuid" VARCHAR(36),
    "tenant_id" INT NOT NULL,
    "audit_id" INT NOT NULL,
    "clause_id" INT NOT NULL,
    "is_primary" BOOL NOT NULL DEFAULT FALSE,
    "deleted_at" TIMESTAMPTZ,
    "created_by" INT,
    "created_by_name" VARCHAR(100),
    "updated_by" INT,
    "updated_by_name" VARCHAR(100),
    "created_at" TIMESTAMPTZ,
    "updated_at" TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS "uidx_qms_audit_clause"
    ON "apps_kuaizhizao_qms_audit_clauses" ("tenant_id", "audit_id", "clause_id")
    WHERE "deleted_at" IS NULL;

INSERT INTO "apps_kuaizhizao_qms_audit_clauses" (
    "uuid", "tenant_id", "audit_id", "clause_id", "is_primary", "created_at", "updated_at"
)
SELECT
    gen_random_uuid()::text,
    a."tenant_id",
    a."id",
    a."iso_clause_id",
    TRUE,
    NOW(),
    NOW()
FROM "apps_kuaizhizao_qms_internal_audits" a
WHERE a."deleted_at" IS NULL
  AND a."iso_clause_id" IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM "apps_kuaizhizao_qms_audit_clauses" x
    WHERE x."tenant_id" = a."tenant_id" AND x."audit_id" = a."id"
      AND x."clause_id" = a."iso_clause_id" AND x."deleted_at" IS NULL
);

ALTER TABLE "apps_kuaizhizao_qms_system_documents"
    ADD COLUMN IF NOT EXISTS "standard_id" INT;

UPDATE "apps_kuaizhizao_qms_system_documents" d
SET "standard_id" = c."standard_id"
FROM "apps_kuaizhizao_qms_iso_clauses" c
WHERE d."deleted_at" IS NULL
  AND d."iso_clause_id" IS NOT NULL
  AND c."id" = d."iso_clause_id"
  AND d."standard_id" IS NULL;

ALTER TABLE "apps_kuaizhizao_qms_internal_audits"
    ADD COLUMN IF NOT EXISTS "standard_id" INT;

UPDATE "apps_kuaizhizao_qms_internal_audits" a
SET "standard_id" = c."standard_id"
FROM "apps_kuaizhizao_qms_iso_clauses" c
WHERE a."deleted_at" IS NULL
  AND a."iso_clause_id" IS NOT NULL
  AND c."id" = a."iso_clause_id"
  AND a."standard_id" IS NULL;

CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_qms_review_standards" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "uuid" VARCHAR(36),
    "tenant_id" INT NOT NULL,
    "review_id" INT NOT NULL,
    "standard_id" INT NOT NULL,
    "deleted_at" TIMESTAMPTZ,
    "created_by" INT,
    "created_by_name" VARCHAR(100),
    "updated_by" INT,
    "updated_by_name" VARCHAR(100),
    "created_at" TIMESTAMPTZ,
    "updated_at" TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS "uidx_qms_review_standard"
    ON "apps_kuaizhizao_qms_review_standards" ("tenant_id", "review_id", "standard_id")
    WHERE "deleted_at" IS NULL;

DROP INDEX IF EXISTS "idx_qms_sys_doc_clause_id";
ALTER TABLE "apps_kuaizhizao_qms_system_documents" DROP COLUMN IF EXISTS "iso_clause_id";
ALTER TABLE "apps_kuaizhizao_qms_system_documents" DROP COLUMN IF EXISTS "iso_clause";
CREATE INDEX IF NOT EXISTS "idx_qms_sys_doc_standard_id"
    ON "apps_kuaizhizao_qms_system_documents" ("standard_id");

DROP INDEX IF EXISTS "idx_qms_internal_audit_clause_id";
ALTER TABLE "apps_kuaizhizao_qms_internal_audits" DROP COLUMN IF EXISTS "iso_clause_id";
ALTER TABLE "apps_kuaizhizao_qms_internal_audits" DROP COLUMN IF EXISTS "iso_clause";
CREATE INDEX IF NOT EXISTS "idx_qms_internal_audit_standard_id"
    ON "apps_kuaizhizao_qms_internal_audits" ("standard_id");
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaizhizao_qms_internal_audits" ADD COLUMN IF NOT EXISTS "iso_clause" VARCHAR(100);
ALTER TABLE "apps_kuaizhizao_qms_internal_audits" ADD COLUMN IF NOT EXISTS "iso_clause_id" INT;
ALTER TABLE "apps_kuaizhizao_qms_system_documents" ADD COLUMN IF NOT EXISTS "iso_clause" VARCHAR(50);
ALTER TABLE "apps_kuaizhizao_qms_system_documents" ADD COLUMN IF NOT EXISTS "iso_clause_id" INT;
DROP TABLE IF EXISTS "apps_kuaizhizao_qms_review_standards";
DROP TABLE IF EXISTS "apps_kuaizhizao_qms_audit_clauses";
DROP TABLE IF EXISTS "apps_kuaizhizao_qms_document_clauses";
ALTER TABLE "apps_kuaizhizao_qms_iso_clauses" DROP COLUMN IF EXISTS "standard_id";
DROP TABLE IF EXISTS "apps_kuaizhizao_qms_standards";
"""
