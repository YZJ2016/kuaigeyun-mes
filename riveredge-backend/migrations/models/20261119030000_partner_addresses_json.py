"""客户/供应商地址明细：addresses JSONB，并从既有地址字段回填。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_customers"
            ADD COLUMN IF NOT EXISTS "addresses" JSONB NOT NULL DEFAULT '[]';
        COMMENT ON COLUMN "apps_master_data_customers"."addresses" IS '地址明细 JSON 数组';

        ALTER TABLE "apps_master_data_suppliers"
            ADD COLUMN IF NOT EXISTS "addresses" JSONB NOT NULL DEFAULT '[]';
        COMMENT ON COLUMN "apps_master_data_suppliers"."addresses" IS '地址明细 JSON 数组';

        UPDATE "apps_master_data_customers"
           SET "addresses" = jsonb_build_array(
                 jsonb_strip_nulls(
                   jsonb_build_object(
                     'address_type', 'registered',
                     'address', TRIM("address"),
                     'is_default', true
                   )
                 )
               )
         WHERE "deleted_at" IS NULL
           AND COALESCE(jsonb_array_length("addresses"), 0) = 0
           AND NULLIF(TRIM(COALESCE("address", '')), '') IS NOT NULL;

        UPDATE "apps_master_data_customers"
           SET "addresses" = "addresses" || jsonb_build_array(
                 jsonb_strip_nulls(
                   jsonb_build_object(
                     'address_type', 'delivery',
                     'address', TRIM("delivery_address"),
                     'contact_name', NULLIF(TRIM(COALESCE("delivery_contact_name", '')), ''),
                     'contact_phone', NULLIF(TRIM(COALESCE("delivery_contact_phone", '')), '')
                   )
                 )
               )
         WHERE "deleted_at" IS NULL
           AND NULLIF(TRIM(COALESCE("delivery_address", '')), '') IS NOT NULL
           AND NOT EXISTS (
             SELECT 1
               FROM jsonb_array_elements("addresses") AS elem
              WHERE elem->>'address_type' = 'delivery'
           );

        UPDATE "apps_master_data_customers"
           SET "addresses" = "addresses" || jsonb_build_array(
                 jsonb_strip_nulls(
                   jsonb_build_object(
                     'address_type', 'invoice',
                     'address', TRIM("invoice_address")
                   )
                 )
               )
         WHERE "deleted_at" IS NULL
           AND NULLIF(TRIM(COALESCE("invoice_address", '')), '') IS NOT NULL
           AND NOT EXISTS (
             SELECT 1
               FROM jsonb_array_elements("addresses") AS elem
              WHERE elem->>'address_type' = 'invoice'
           );

        UPDATE "apps_master_data_suppliers"
           SET "addresses" = jsonb_build_array(
                 jsonb_strip_nulls(
                   jsonb_build_object(
                     'address_type', 'registered',
                     'address', TRIM("address"),
                     'is_default', true
                   )
                 )
               )
         WHERE "deleted_at" IS NULL
           AND COALESCE(jsonb_array_length("addresses"), 0) = 0
           AND NULLIF(TRIM(COALESCE("address", '')), '') IS NOT NULL;

        UPDATE "apps_master_data_suppliers"
           SET "addresses" = "addresses" || jsonb_build_array(
                 jsonb_strip_nulls(
                   jsonb_build_object(
                     'address_type', 'delivery',
                     'address', TRIM("delivery_address"),
                     'contact_name', NULLIF(TRIM(COALESCE("delivery_contact_name", '')), ''),
                     'contact_phone', NULLIF(TRIM(COALESCE("delivery_contact_phone", '')), '')
                   )
                 )
               )
         WHERE "deleted_at" IS NULL
           AND NULLIF(TRIM(COALESCE("delivery_address", '')), '') IS NOT NULL
           AND NOT EXISTS (
             SELECT 1
               FROM jsonb_array_elements("addresses") AS elem
              WHERE elem->>'address_type' = 'delivery'
           );

        UPDATE "apps_master_data_suppliers"
           SET "addresses" = "addresses" || jsonb_build_array(
                 jsonb_strip_nulls(
                   jsonb_build_object(
                     'address_type', 'invoice',
                     'address', TRIM("invoice_address")
                   )
                 )
               )
         WHERE "deleted_at" IS NULL
           AND NULLIF(TRIM(COALESCE("invoice_address", '')), '') IS NOT NULL
           AND NOT EXISTS (
             SELECT 1
               FROM jsonb_array_elements("addresses") AS elem
              WHERE elem->>'address_type' = 'invoice'
           );
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_customers" DROP COLUMN IF EXISTS "addresses";
        ALTER TABLE "apps_master_data_suppliers" DROP COLUMN IF EXISTS "addresses";
    """
