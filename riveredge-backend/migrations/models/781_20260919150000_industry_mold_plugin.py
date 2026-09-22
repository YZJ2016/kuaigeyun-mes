from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_industry_mold_program_sheets" (
            "id" SERIAL PRIMARY KEY,
            "uuid" UUID NOT NULL UNIQUE,
            "tenant_id" INT NOT NULL,
            "code" VARCHAR(50) NOT NULL,
            "work_order_id" INT NOT NULL,
            "work_order_code" VARCHAR(50) NOT NULL,
            "program_name" VARCHAR(200) NOT NULL,
            "program_status" VARCHAR(20) NOT NULL DEFAULT 'pending',
            "nc_file_path" VARCHAR(500),
            "remarks" TEXT,
            "created_by" INT,
            "updated_by" INT,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "deleted_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS "idx_industry_mold_program_tenant"
            ON "apps_industry_mold_program_sheets" ("tenant_id");

        CREATE TABLE IF NOT EXISTS "apps_industry_mold_material_arrivals" (
            "id" SERIAL PRIMARY KEY,
            "uuid" UUID NOT NULL UNIQUE,
            "tenant_id" INT NOT NULL,
            "code" VARCHAR(50) NOT NULL,
            "work_order_id" INT,
            "work_order_code" VARCHAR(50),
            "material_name" VARCHAR(200) NOT NULL,
            "material_spec" VARCHAR(200),
            "weight" NUMERIC(14,4),
            "status" VARCHAR(20) NOT NULL DEFAULT 'pending',
            "remarks" TEXT,
            "created_by" INT,
            "updated_by" INT,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "deleted_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS "idx_industry_mold_arrival_tenant"
            ON "apps_industry_mold_material_arrivals" ("tenant_id");

        INSERT INTO core_applications (
            uuid, tenant_id, code, name, description, version,
            entry_point, route_path, sort_order,
            is_system, is_active, is_installed,
            created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            t.id,
            'industry-mold',
            '模具机加',
            '模具机加行业插件：程序单与到料单',
            '1.0.0',
            '../apps/industry-mold/index.tsx',
            '/apps/industry-mold',
            320,
            FALSE, TRUE, FALSE,
            NOW(), NOW()
        FROM infra_tenants t
        WHERE NOT EXISTS (
            SELECT 1 FROM core_applications
            WHERE code = 'industry-mold' AND tenant_id = t.id AND deleted_at IS NULL
        );
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_industry_mold_material_arrivals";
        DROP TABLE IF EXISTS "apps_industry_mold_program_sheets";
        DELETE FROM core_applications
        WHERE code = 'industry-mold' AND is_installed = FALSE AND deleted_at IS NULL;
    """
