"""内审年度计划、检查表行、不符合报告；内审挂年度计划。"""

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
CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_qms_internal_audit_annual_plans" (
    "id" SERIAL PRIMARY KEY,
    "uuid" VARCHAR(36) NOT NULL,
    "tenant_id" INT,
    "plan_year" INT NOT NULL,
    "covered_processes" TEXT,
    "planned_months" JSONB,
    "lead_auditor" VARCHAR(100),
    "remarks" TEXT,
    "created_by" INT,
    "created_by_name" VARCHAR(100),
    "updated_by" INT,
    "updated_by_name" VARCHAR(100),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "deleted_at" TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS "uid_qms_audit_annual_plan_uuid"
    ON "apps_kuaizhizao_qms_internal_audit_annual_plans" ("uuid");
CREATE UNIQUE INDEX IF NOT EXISTS "uid_qms_audit_annual_plan_tenant_year"
    ON "apps_kuaizhizao_qms_internal_audit_annual_plans" ("tenant_id", "plan_year");

CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_qms_internal_audit_checklist_items" (
    "id" SERIAL PRIMARY KEY,
    "uuid" VARCHAR(36) NOT NULL,
    "tenant_id" INT,
    "audit_id" INT NOT NULL,
    "sort_order" INT NOT NULL DEFAULT 0,
    "clause_id" INT NOT NULL,
    "checkpoint" TEXT,
    "conclusion" VARCHAR(20) NOT NULL DEFAULT 'pending',
    "evidence" TEXT,
    "nc_report_id" INT,
    "remarks" TEXT,
    "created_by" INT,
    "created_by_name" VARCHAR(100),
    "updated_by" INT,
    "updated_by_name" VARCHAR(100),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "deleted_at" TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS "uid_qms_audit_checklist_uuid"
    ON "apps_kuaizhizao_qms_internal_audit_checklist_items" ("uuid");
CREATE INDEX IF NOT EXISTS "idx_qms_audit_checklist_tenant_audit"
    ON "apps_kuaizhizao_qms_internal_audit_checklist_items" ("tenant_id", "audit_id");

CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_qms_nonconformity_reports" (
    "id" SERIAL PRIMARY KEY,
    "uuid" VARCHAR(36) NOT NULL,
    "tenant_id" INT,
    "report_code" VARCHAR(50) NOT NULL,
    "source_type" VARCHAR(30) NOT NULL,
    "source_id" INT,
    "source_code" VARCHAR(50),
    "checklist_item_id" INT,
    "clause_id" INT,
    "fact" TEXT NOT NULL,
    "severity" VARCHAR(20) NOT NULL,
    "responsible_dept" VARCHAR(200),
    "due_on" DATE,
    "cause" TEXT,
    "correction" TEXT,
    "corrective_action" TEXT,
    "verifier_name" VARCHAR(100),
    "verified_on" DATE,
    "verification_conclusion" TEXT,
    "capa_code" VARCHAR(50),
    "status" VARCHAR(20) NOT NULL DEFAULT 'open',
    "remarks" TEXT,
    "attachments" JSONB,
    "created_by" INT,
    "created_by_name" VARCHAR(100),
    "updated_by" INT,
    "updated_by_name" VARCHAR(100),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "deleted_at" TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS "uid_qms_nc_report_uuid"
    ON "apps_kuaizhizao_qms_nonconformity_reports" ("uuid");
CREATE UNIQUE INDEX IF NOT EXISTS "uid_qms_nc_report_tenant_code"
    ON "apps_kuaizhizao_qms_nonconformity_reports" ("tenant_id", "report_code");
CREATE INDEX IF NOT EXISTS "idx_qms_nc_report_source"
    ON "apps_kuaizhizao_qms_nonconformity_reports" ("tenant_id", "source_type", "source_id");

ALTER TABLE "apps_kuaizhizao_qms_internal_audits"
    ADD COLUMN IF NOT EXISTS "annual_plan_id" INT;

{_seed_rule_sql("QMS_NONCONFORMITY_REPORT_CODE", "不符合报告编码规则", "BFH", "质量体系不符合报告：BFH+日期+序号")}
"""
