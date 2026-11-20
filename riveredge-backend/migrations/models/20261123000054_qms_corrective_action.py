"""纠正预防台账；管理评审决议行（供纠正预防挂接）。"""

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
CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_qms_corrective_actions" (
    "id" SERIAL PRIMARY KEY,
    "uuid" VARCHAR(36) NOT NULL,
    "tenant_id" INT,
    "action_code" VARCHAR(50) NOT NULL,
    "source_type" VARCHAR(40) NOT NULL,
    "source_id" INT,
    "source_code" VARCHAR(50),
    "problem_summary" TEXT NOT NULL,
    "cause" TEXT,
    "correction" TEXT,
    "prevention" TEXT,
    "responsible_person" VARCHAR(100),
    "due_on" DATE,
    "verifier_name" VARCHAR(100),
    "verified_on" DATE,
    "verification_conclusion" TEXT,
    "need_eight_d" BOOL NOT NULL DEFAULT FALSE,
    "eight_d_code" VARCHAR(50),
    "status" VARCHAR(20) NOT NULL DEFAULT 'registered',
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
CREATE UNIQUE INDEX IF NOT EXISTS "uid_qms_corrective_action_uuid"
    ON "apps_kuaizhizao_qms_corrective_actions" ("uuid");
CREATE UNIQUE INDEX IF NOT EXISTS "uid_qms_corrective_action_tenant_code"
    ON "apps_kuaizhizao_qms_corrective_actions" ("tenant_id", "action_code");
CREATE INDEX IF NOT EXISTS "idx_qms_corrective_action_source"
    ON "apps_kuaizhizao_qms_corrective_actions" ("tenant_id", "source_type", "source_id");
CREATE INDEX IF NOT EXISTS "idx_qms_corrective_action_status"
    ON "apps_kuaizhizao_qms_corrective_actions" ("tenant_id", "status");

CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_qms_management_review_resolutions" (
    "id" SERIAL PRIMARY KEY,
    "uuid" VARCHAR(36) NOT NULL,
    "tenant_id" INT,
    "review_id" INT NOT NULL,
    "content" TEXT NOT NULL,
    "responsible_person" VARCHAR(100),
    "due_on" DATE,
    "convert_to_capa" BOOL NOT NULL DEFAULT FALSE,
    "capa_code" VARCHAR(50),
    "status" VARCHAR(20) NOT NULL DEFAULT 'open',
    "sort_order" INT NOT NULL DEFAULT 0,
    "remarks" TEXT,
    "created_by" INT,
    "created_by_name" VARCHAR(100),
    "updated_by" INT,
    "updated_by_name" VARCHAR(100),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "deleted_at" TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS "uid_qms_review_resolution_uuid"
    ON "apps_kuaizhizao_qms_management_review_resolutions" ("uuid");
CREATE INDEX IF NOT EXISTS "idx_qms_review_resolution_review"
    ON "apps_kuaizhizao_qms_management_review_resolutions" ("tenant_id", "review_id");

{_seed_rule_sql(
    "QMS_CORRECTIVE_ACTION_CODE",
    "纠正预防编号",
    "JZYF",
    "质量体系纠正预防自动编号",
)}
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
DROP TABLE IF EXISTS "apps_kuaizhizao_qms_management_review_resolutions";
DROP TABLE IF EXISTS "apps_kuaizhizao_qms_corrective_actions";
"""
