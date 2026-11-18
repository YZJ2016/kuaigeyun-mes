from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_payment_applications"
        ADD COLUMN IF NOT EXISTS "department_id" INT;
        ALTER TABLE "apps_kuaizhizao_payment_applications"
        ADD COLUMN IF NOT EXISTS "department_name" VARCHAR(200);
        COMMENT ON COLUMN "apps_kuaizhizao_payment_applications"."department_id" IS '申请部门ID';
        COMMENT ON COLUMN "apps_kuaizhizao_payment_applications"."department_name" IS '申请部门名称';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_payment_applications" DROP COLUMN IF EXISTS "department_name";
        ALTER TABLE "apps_kuaizhizao_payment_applications" DROP COLUMN IF EXISTS "department_id";
    """
