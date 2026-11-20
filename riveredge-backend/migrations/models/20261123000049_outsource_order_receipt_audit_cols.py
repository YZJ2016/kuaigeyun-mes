"""工序委外收货批次表补齐 BaseModel 审计列。

1038 建表时未含 updated_by / updated_by_name；下达后详情查询 SELECT 会失败。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_outsource_order_receipts"
            ADD COLUMN IF NOT EXISTS "updated_by" INT,
            ADD COLUMN IF NOT EXISTS "updated_by_name" VARCHAR(100);
        COMMENT ON COLUMN "apps_kuaizhizao_outsource_order_receipts"."updated_by" IS '更新人ID';
        COMMENT ON COLUMN "apps_kuaizhizao_outsource_order_receipts"."updated_by_name" IS '更新人姓名';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_outsource_order_receipts"
            DROP COLUMN IF EXISTS "updated_by",
            DROP COLUMN IF EXISTS "updated_by_name";
    """
