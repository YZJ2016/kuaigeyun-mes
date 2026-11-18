"""回填：由要求上传凭证的付款申请生成的付款单，补写 require_payment_voucher。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "apps_kuaicaiwu_payments" AS p
        SET "require_payment_voucher" = TRUE
        FROM "apps_kuaizhizao_document_relations" AS r
        INNER JOIN "apps_kuaizhizao_payment_applications" AS a
            ON a."id" = r."source_id"
            AND a."tenant_id" = r."tenant_id"
            AND a."deleted_at" IS NULL
        WHERE r."target_type" = 'payment'
          AND r."target_id" = p."id"
          AND r."source_type" = 'payment_application'
          AND r."tenant_id" = p."tenant_id"
          AND a."require_payment_voucher" IS TRUE
          AND p."deleted_at" IS NULL
          AND p."require_payment_voucher" IS NOT TRUE;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- 不可逆回填，downgrade 为空
    """
