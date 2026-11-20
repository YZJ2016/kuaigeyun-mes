"""
审批流程 / 消息模板 / 打印模板 分类外键。
"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "core_approval_processes"
            ADD COLUMN IF NOT EXISTS "category_id" INT;
        CREATE INDEX IF NOT EXISTS "idx_core_approval_processes_category_id"
            ON "core_approval_processes" ("category_id");
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_core_approval_processes_category_id'
            ) THEN
                ALTER TABLE "core_approval_processes"
                    ADD CONSTRAINT "fk_core_approval_processes_category_id"
                    FOREIGN KEY ("category_id")
                    REFERENCES "core_resource_categories" ("id")
                    ON DELETE SET NULL;
            END IF;
        END $$;

        ALTER TABLE "core_message_templates"
            ADD COLUMN IF NOT EXISTS "category_id" INT;
        CREATE INDEX IF NOT EXISTS "idx_core_message_templates_category_id"
            ON "core_message_templates" ("category_id");
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_core_message_templates_category_id'
            ) THEN
                ALTER TABLE "core_message_templates"
                    ADD CONSTRAINT "fk_core_message_templates_category_id"
                    FOREIGN KEY ("category_id")
                    REFERENCES "core_resource_categories" ("id")
                    ON DELETE SET NULL;
            END IF;
        END $$;

        ALTER TABLE "core_print_templates"
            ADD COLUMN IF NOT EXISTS "category_id" INT;
        CREATE INDEX IF NOT EXISTS "idx_core_print_templates_category_id"
            ON "core_print_templates" ("category_id");
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_core_print_templates_category_id'
            ) THEN
                ALTER TABLE "core_print_templates"
                    ADD CONSTRAINT "fk_core_print_templates_category_id"
                    FOREIGN KEY ("category_id")
                    REFERENCES "core_resource_categories" ("id")
                    ON DELETE SET NULL;
            END IF;
        END $$;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "core_print_templates" DROP CONSTRAINT IF EXISTS "fk_core_print_templates_category_id";
        DROP INDEX IF EXISTS "idx_core_print_templates_category_id";
        ALTER TABLE "core_print_templates" DROP COLUMN IF EXISTS "category_id";

        ALTER TABLE "core_message_templates" DROP CONSTRAINT IF EXISTS "fk_core_message_templates_category_id";
        DROP INDEX IF EXISTS "idx_core_message_templates_category_id";
        ALTER TABLE "core_message_templates" DROP COLUMN IF EXISTS "category_id";

        ALTER TABLE "core_approval_processes" DROP CONSTRAINT IF EXISTS "fk_core_approval_processes_category_id";
        DROP INDEX IF EXISTS "idx_core_approval_processes_category_id";
        ALTER TABLE "core_approval_processes" DROP COLUMN IF EXISTS "category_id";
    """
