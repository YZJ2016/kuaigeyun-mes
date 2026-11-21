"""发货通知单增加审核状态。历史待审核/已驳回迁出业务 status；已通知或已出库记审核通过。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_shipment_notices"
            ADD COLUMN "review_status" VARCHAR(20) NOT NULL DEFAULT '草稿';
        UPDATE "apps_kuaizhizao_shipment_notices"
            SET "review_status" = '审核通过'
            WHERE "deleted_at" IS NULL
              AND "status" IN ('已通知', '已出库');
        UPDATE "apps_kuaizhizao_shipment_notices"
            SET "review_status" = '待审核',
                "status" = '待发货'
            WHERE "deleted_at" IS NULL
              AND "status" = '待审核';
        UPDATE "apps_kuaizhizao_shipment_notices"
            SET "review_status" = '审核驳回',
                "status" = '待发货'
            WHERE "deleted_at" IS NULL
              AND "status" = '已驳回';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "apps_kuaizhizao_shipment_notices"
            SET "status" = '待审核'
            WHERE "deleted_at" IS NULL
              AND "status" = '待发货'
              AND "review_status" = '待审核';
        UPDATE "apps_kuaizhizao_shipment_notices"
            SET "status" = '已驳回'
            WHERE "deleted_at" IS NULL
              AND "status" = '待发货'
              AND "review_status" IN ('审核驳回', '已驳回');
        ALTER TABLE "apps_kuaizhizao_shipment_notices"
            DROP COLUMN "review_status";
    """
