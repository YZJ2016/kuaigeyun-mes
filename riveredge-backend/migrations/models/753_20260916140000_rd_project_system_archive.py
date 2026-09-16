"""研发项目体系归档八类（R-01 #70）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaiplm_rd_project_system_archive_items" (
            "id" SERIAL PRIMARY KEY,
            "uuid" UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "tenant_id" INT NOT NULL,
            "project_id" INT NOT NULL,
            "archive_type_code" VARCHAR(50) NOT NULL,
            "archive_type_name" VARCHAR(100) NOT NULL,
            "sort_order" INT NOT NULL DEFAULT 0,
            "fill_status" VARCHAR(30) NOT NULL DEFAULT 'empty',
            "file_uuid" VARCHAR(36),
            "file_name" VARCHAR(200),
            "file_url" VARCHAR(500),
            "linked_target_type" VARCHAR(50),
            "linked_target_id" INT,
            "linked_target_uuid" VARCHAR(36),
            "linked_target_code" VARCHAR(100),
            "linked_target_name" VARCHAR(200),
            "acceptance_status" VARCHAR(30) NOT NULL DEFAULT 'none',
            "acceptance_notes" TEXT,
            "accepted_at" TIMESTAMPTZ,
            "accepted_by" INT,
            "accepted_by_name" VARCHAR(100),
            "missing_notes" TEXT,
            "missing_marked_at" TIMESTAMPTZ,
            "missing_marked_by" INT,
            "missing_marked_by_name" VARCHAR(100),
            "notes" TEXT,
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            CONSTRAINT "uq_rd_sys_archive_tenant_project_type"
                UNIQUE ("tenant_id", "project_id", "archive_type_code")
        );
        CREATE INDEX IF NOT EXISTS "idx_rd_sys_archive_tenant_project"
            ON "apps_kuaiplm_rd_project_system_archive_items" ("tenant_id", "project_id");
        CREATE INDEX IF NOT EXISTS "idx_rd_sys_archive_tenant_fill"
            ON "apps_kuaiplm_rd_project_system_archive_items" ("tenant_id", "fill_status");
        CREATE INDEX IF NOT EXISTS "idx_rd_sys_archive_tenant_accept"
            ON "apps_kuaiplm_rd_project_system_archive_items" ("tenant_id", "acceptance_status");

        INSERT INTO "apps_kuaiplm_rd_project_system_archive_items" (
            "tenant_id", "project_id", "archive_type_code", "archive_type_name", "sort_order"
        )
        SELECT p."tenant_id", p."id", v."archive_type_code", v."archive_type_name", v."sort_order"
        FROM "apps_kuaiplm_rd_projects" p
        CROSS JOIN (
            VALUES
                ('qms_materials', '体系资料', 1),
                ('product_tech_detail_sheet', '产品技术资料明细表', 2),
                ('design_task_plan', '任务计划书', 3),
                ('product_implementation_plan', '产品实现方案书', 4),
                ('sample_contact', '打样联系单', 5),
                ('prototype_build_sheet', '样机制作书', 6),
                ('test_report', '测试报告', 7),
                ('project_summary', '项目总结报告', 8)
        ) AS v("archive_type_code", "archive_type_name", "sort_order")
        WHERE p."deleted_at" IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM "apps_kuaiplm_rd_project_system_archive_items" i
              WHERE i."tenant_id" = p."tenant_id"
                AND i."project_id" = p."id"
                AND i."archive_type_code" = v."archive_type_code"
          );
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaiplm_rd_project_system_archive_items";
    """
