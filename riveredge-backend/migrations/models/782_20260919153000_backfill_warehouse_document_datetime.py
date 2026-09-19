"""
出入库 Hub 制单日期 / 操作人历史回填。

根因：取单建单路径未写入业务日（picking_time / delivery_time / receipt_time 等），
Hub 列表「制单日期」读业务字段为空。委外发/收/退创建时已写 issued_at / received_at，
无需本迁移。

策略：仅填空值；业务日回填为 created_at（建单时刻 UTC）；操作人回填为 created_by / created_by_name。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- 1) 制单/业务日期（仅 NULL）
        UPDATE "apps_kuaizhizao_production_pickings"
        SET "picking_time" = "created_at"
        WHERE "deleted_at" IS NULL AND "picking_time" IS NULL;

        UPDATE "apps_kuaizhizao_sales_deliveries"
        SET "delivery_time" = "created_at"
        WHERE "deleted_at" IS NULL AND "delivery_time" IS NULL;

        UPDATE "apps_kuaizhizao_purchase_receipts"
        SET "receipt_time" = "created_at"
        WHERE "deleted_at" IS NULL AND "receipt_time" IS NULL;

        UPDATE "apps_kuaizhizao_production_returns"
        SET "return_time" = "created_at"
        WHERE "deleted_at" IS NULL AND "return_time" IS NULL;

        UPDATE "apps_kuaizhizao_sales_returns"
        SET "return_time" = "created_at"
        WHERE "deleted_at" IS NULL AND "return_time" IS NULL;

        UPDATE "apps_kuaizhizao_other_inbounds"
        SET "receipt_time" = "created_at"
        WHERE "deleted_at" IS NULL AND "receipt_time" IS NULL;

        UPDATE "apps_kuaizhizao_other_outbounds"
        SET "delivery_time" = "created_at"
        WHERE "deleted_at" IS NULL AND "delivery_time" IS NULL;

        UPDATE "apps_kuaizhizao_finished_goods_receipts"
        SET "receipt_time" = "created_at"
        WHERE "deleted_at" IS NULL AND "receipt_time" IS NULL;

        UPDATE "apps_kuaizhizao_material_borrows"
        SET "borrow_time" = "created_at"
        WHERE "deleted_at" IS NULL AND "borrow_time" IS NULL;

        -- 2) 操作人（仅 ID/姓名为空）
        UPDATE "apps_kuaizhizao_production_pickings"
        SET
            "picker_id" = COALESCE("picker_id", "created_by"),
            "picker_name" = COALESCE(NULLIF(BTRIM("picker_name"), ''), NULLIF(BTRIM("created_by_name"), ''))
        WHERE "deleted_at" IS NULL
          AND (
              "picker_id" IS NULL
              OR BTRIM(COALESCE("picker_name", '')) = ''
          );

        UPDATE "apps_kuaizhizao_sales_deliveries"
        SET
            "deliverer_id" = COALESCE("deliverer_id", "created_by"),
            "deliverer_name" = COALESCE(NULLIF(BTRIM("deliverer_name"), ''), NULLIF(BTRIM("created_by_name"), ''))
        WHERE "deleted_at" IS NULL
          AND (
              "deliverer_id" IS NULL
              OR BTRIM(COALESCE("deliverer_name", '')) = ''
          );

        UPDATE "apps_kuaizhizao_purchase_receipts"
        SET
            "receiver_id" = COALESCE("receiver_id", "created_by"),
            "receiver_name" = COALESCE(NULLIF(BTRIM("receiver_name"), ''), NULLIF(BTRIM("created_by_name"), ''))
        WHERE "deleted_at" IS NULL
          AND (
              "receiver_id" IS NULL
              OR BTRIM(COALESCE("receiver_name", '')) = ''
          );

        UPDATE "apps_kuaizhizao_production_returns"
        SET
            "returner_id" = COALESCE("returner_id", "created_by"),
            "returner_name" = COALESCE(NULLIF(BTRIM("returner_name"), ''), NULLIF(BTRIM("created_by_name"), ''))
        WHERE "deleted_at" IS NULL
          AND (
              "returner_id" IS NULL
              OR BTRIM(COALESCE("returner_name", '')) = ''
          );

        UPDATE "apps_kuaizhizao_sales_returns"
        SET
            "returner_id" = COALESCE("returner_id", "created_by"),
            "returner_name" = COALESCE(NULLIF(BTRIM("returner_name"), ''), NULLIF(BTRIM("created_by_name"), ''))
        WHERE "deleted_at" IS NULL
          AND (
              "returner_id" IS NULL
              OR BTRIM(COALESCE("returner_name", '')) = ''
          );

        UPDATE "apps_kuaizhizao_other_inbounds"
        SET
            "receiver_id" = COALESCE("receiver_id", "created_by"),
            "receiver_name" = COALESCE(NULLIF(BTRIM("receiver_name"), ''), NULLIF(BTRIM("created_by_name"), ''))
        WHERE "deleted_at" IS NULL
          AND (
              "receiver_id" IS NULL
              OR BTRIM(COALESCE("receiver_name", '')) = ''
          );

        UPDATE "apps_kuaizhizao_other_outbounds"
        SET
            "deliverer_id" = COALESCE("deliverer_id", "created_by"),
            "deliverer_name" = COALESCE(NULLIF(BTRIM("deliverer_name"), ''), NULLIF(BTRIM("created_by_name"), ''))
        WHERE "deleted_at" IS NULL
          AND (
              "deliverer_id" IS NULL
              OR BTRIM(COALESCE("deliverer_name", '')) = ''
          );

        UPDATE "apps_kuaizhizao_finished_goods_receipts"
        SET
            "receiver_id" = COALESCE("receiver_id", "created_by"),
            "receiver_name" = COALESCE(NULLIF(BTRIM("receiver_name"), ''), NULLIF(BTRIM("created_by_name"), ''))
        WHERE "deleted_at" IS NULL
          AND (
              "receiver_id" IS NULL
              OR BTRIM(COALESCE("receiver_name", '')) = ''
          );

        UPDATE "apps_kuaizhizao_material_borrows"
        SET
            "borrower_id" = COALESCE("borrower_id", "created_by"),
            "borrower_name" = COALESCE(NULLIF(BTRIM("borrower_name"), ''), NULLIF(BTRIM("created_by_name"), ''))
        WHERE "deleted_at" IS NULL
          AND (
              "borrower_id" IS NULL
              OR BTRIM(COALESCE("borrower_name", '')) = ''
          );
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return "-- noop: warehouse document datetime backfill is irreversible"
