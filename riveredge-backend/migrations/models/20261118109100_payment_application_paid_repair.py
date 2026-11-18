"""回填：付款单删除后未冲回的付款申请已付金额/状态。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "apps_kuaizhizao_payment_application_lines" AS l
        SET "paid_amount" = 0
        FROM "apps_kuaizhizao_payment_applications" AS a
        WHERE l."application_id" = a."id"
          AND l."tenant_id" = a."tenant_id"
          AND a."deleted_at" IS NULL
          AND (
            COALESCE(a."paid_amount", 0) > 0
            OR a."status" IN ('已付款', '部分付款')
          )
          AND NOT EXISTS (
            SELECT 1
            FROM "apps_kuaizhizao_document_relations" AS r
            INNER JOIN "apps_kuaicaiwu_payments" AS p
              ON p."id" = r."target_id"
             AND p."tenant_id" = r."tenant_id"
             AND p."deleted_at" IS NULL
             AND p."status" = 'Confirmed'
            WHERE r."tenant_id" = a."tenant_id"
              AND r."source_type" = 'payment_application'
              AND r."source_id" = a."id"
              AND r."target_type" = 'payment'
          );

        UPDATE "apps_kuaizhizao_payment_applications" AS a
        SET "paid_amount" = 0,
            "remaining_amount" = COALESCE(a."total_request_amount", 0),
            "status" = '已批准'
        WHERE a."deleted_at" IS NULL
          AND (
            COALESCE(a."paid_amount", 0) > 0
            OR a."status" IN ('已付款', '部分付款')
          )
          AND NOT EXISTS (
            SELECT 1
            FROM "apps_kuaizhizao_document_relations" AS r
            INNER JOIN "apps_kuaicaiwu_payments" AS p
              ON p."id" = r."target_id"
             AND p."tenant_id" = r."tenant_id"
             AND p."deleted_at" IS NULL
             AND p."status" = 'Confirmed'
            WHERE r."tenant_id" = a."tenant_id"
              AND r."source_type" = 'payment_application'
              AND r."source_id" = a."id"
              AND r."target_type" = 'payment'
          );
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- 不可逆回填，downgrade 为空
    """
