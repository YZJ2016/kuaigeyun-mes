"""质量目标、法律法规、外审、证书。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


def _rule_components_json(prefix: str) -> str:
    return (
        '[{"type":"fixed_text","order":0,"text":"'
        + prefix
        + '"},{"type":"date","order":1,"format_type":"preset","preset_format":"YYYYMMDD"},'
        '{"type":"auto_counter","order":2,"digits":4,"fixed_width":true,'
        '"reset_cycle":"daily","initial_value":1}]'
    )


def _seed_rule_sql(rule_code: str, rule_name: str, prefix: str, description: str) -> str:
    components = _rule_components_json(prefix).replace("'", "''")
    desc = description.replace("'", "''")
    name = rule_name.replace("'", "''")
    return f"""
INSERT INTO "core_code_rules" (
    "uuid", "tenant_id", "name", "code", "rule_components", "description",
    "seq_start", "seq_step", "seq_reset_rule", "is_system", "is_active",
    "allow_manual_edit", "created_at", "updated_at"
)
SELECT
    gen_random_uuid()::text,
    t."tenant_id",
    '{name}',
    '{rule_code}',
    '{components}'::jsonb,
    '{desc}',
    1, 1, 'daily', TRUE, TRUE, TRUE, NOW(), NOW()
FROM (
    SELECT DISTINCT "tenant_id"
    FROM "core_code_rules"
    WHERE "tenant_id" IS NOT NULL AND "deleted_at" IS NULL
) t
WHERE NOT EXISTS (
    SELECT 1 FROM "core_code_rules" r
    WHERE r."tenant_id" = t."tenant_id"
      AND r."code" = '{rule_code}'
      AND r."deleted_at" IS NULL
);
"""


async def upgrade(db: BaseDBAsyncClient) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_qms_quality_objectives" (
    "id" SERIAL PRIMARY KEY,
    "uuid" VARCHAR(36) NOT NULL,
    "tenant_id" INT,
    "objective_code" VARCHAR(50) NOT NULL,
    "plan_year" INT NOT NULL,
    "standard_id" INT,
    "status" VARCHAR(20) NOT NULL DEFAULT 'draft',
    "remarks" TEXT,
    "created_by" INT,
    "created_by_name" VARCHAR(100),
    "updated_by" INT,
    "updated_by_name" VARCHAR(100),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "deleted_at" TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS "uid_qms_quality_objective_uuid"
    ON "apps_kuaizhizao_qms_quality_objectives" ("uuid");
CREATE UNIQUE INDEX IF NOT EXISTS "uid_qms_quality_objective_tenant_code"
    ON "apps_kuaizhizao_qms_quality_objectives" ("tenant_id", "objective_code");

CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_qms_quality_objective_lines" (
    "id" SERIAL PRIMARY KEY,
    "uuid" VARCHAR(36) NOT NULL,
    "tenant_id" INT,
    "objective_id" INT NOT NULL,
    "sort_order" INT NOT NULL DEFAULT 0,
    "name" VARCHAR(200) NOT NULL,
    "metric_scope" VARCHAR(200),
    "target_value" VARCHAR(100) NOT NULL,
    "responsible_dept" VARCHAR(200),
    "period" VARCHAR(20) NOT NULL,
    "actual_value" VARCHAR(100),
    "achieved" BOOL,
    "remarks" TEXT,
    "created_by" INT,
    "created_by_name" VARCHAR(100),
    "updated_by" INT,
    "updated_by_name" VARCHAR(100),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "deleted_at" TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS "uid_qms_quality_objective_line_uuid"
    ON "apps_kuaizhizao_qms_quality_objective_lines" ("uuid");
CREATE INDEX IF NOT EXISTS "idx_qms_quality_objective_line_obj"
    ON "apps_kuaizhizao_qms_quality_objective_lines" ("tenant_id", "objective_id");

CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_qms_legal_regulations" (
    "id" SERIAL PRIMARY KEY,
    "uuid" VARCHAR(36) NOT NULL,
    "tenant_id" INT,
    "name" VARCHAR(200) NOT NULL,
    "doc_no" VARCHAR(100) NOT NULL,
    "issuing_authority" VARCHAR(200),
    "effective_on" DATE,
    "applicable_scope" TEXT,
    "evaluation_conclusion" VARCHAR(20),
    "evaluated_on" DATE,
    "next_evaluation_on" DATE,
    "capa_code" VARCHAR(50),
    "evaluation_completed" BOOL NOT NULL DEFAULT FALSE,
    "remarks" TEXT,
    "created_by" INT,
    "created_by_name" VARCHAR(100),
    "updated_by" INT,
    "updated_by_name" VARCHAR(100),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "deleted_at" TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS "uid_qms_legal_regulation_uuid"
    ON "apps_kuaizhizao_qms_legal_regulations" ("uuid");
CREATE INDEX IF NOT EXISTS "idx_qms_legal_regulation_next_eval"
    ON "apps_kuaizhizao_qms_legal_regulations" ("tenant_id", "next_evaluation_on");

CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_qms_external_audits" (
    "id" SERIAL PRIMARY KEY,
    "uuid" VARCHAR(36) NOT NULL,
    "tenant_id" INT,
    "audit_code" VARCHAR(50) NOT NULL,
    "body_name" VARCHAR(200) NOT NULL,
    "audit_type" VARCHAR(30) NOT NULL,
    "planned_on" DATE,
    "actual_on" DATE,
    "audit_scope" TEXT,
    "remarks" TEXT,
    "created_by" INT,
    "created_by_name" VARCHAR(100),
    "updated_by" INT,
    "updated_by_name" VARCHAR(100),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "deleted_at" TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS "uid_qms_external_audit_uuid"
    ON "apps_kuaizhizao_qms_external_audits" ("uuid");
CREATE UNIQUE INDEX IF NOT EXISTS "uid_qms_external_audit_tenant_code"
    ON "apps_kuaizhizao_qms_external_audits" ("tenant_id", "audit_code");

CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_qms_certificates" (
    "id" SERIAL PRIMARY KEY,
    "uuid" VARCHAR(36) NOT NULL,
    "tenant_id" INT,
    "name" VARCHAR(200) NOT NULL,
    "standard_name" VARCHAR(200),
    "certificate_no" VARCHAR(100) NOT NULL,
    "issuer" VARCHAR(200),
    "effective_on" DATE,
    "expire_on" DATE NOT NULL,
    "remarks" TEXT,
    "created_by" INT,
    "created_by_name" VARCHAR(100),
    "updated_by" INT,
    "updated_by_name" VARCHAR(100),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "deleted_at" TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS "uid_qms_certificate_uuid"
    ON "apps_kuaizhizao_qms_certificates" ("uuid");
CREATE UNIQUE INDEX IF NOT EXISTS "uid_qms_certificate_tenant_no"
    ON "apps_kuaizhizao_qms_certificates" ("tenant_id", "certificate_no");

{_seed_rule_sql("QMS_QUALITY_OBJECTIVE_CODE", "质量目标编号", "ZLMB", "质量体系质量目标自动编号")}
{_seed_rule_sql("QMS_EXTERNAL_AUDIT_CODE", "外审编号", "WS", "质量体系外审自动编号")}
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
DROP TABLE IF EXISTS "apps_kuaizhizao_qms_certificates";
DROP TABLE IF EXISTS "apps_kuaizhizao_qms_external_audits";
DROP TABLE IF EXISTS "apps_kuaizhizao_qms_legal_regulations";
DROP TABLE IF EXISTS "apps_kuaizhizao_qms_quality_objective_lines";
DROP TABLE IF EXISTS "apps_kuaizhizao_qms_quality_objectives";
"""
