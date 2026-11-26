"""回填：采购订单进项发票 → 入库应付 单据关联（全链路 PI→PY→PK）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        INSERT INTO "apps_kuaizhizao_document_relations" (
            "uuid",
            "tenant_id",
            "source_type",
            "source_id",
            "source_code",
            "target_type",
            "target_id",
            "target_code",
            "relation_type",
            "relation_mode",
            "relation_desc",
            "created_at",
            "updated_at"
        )
        SELECT
            gen_random_uuid(),
            pi."tenant_id",
            'purchase_invoice',
            pi."id",
            pi."invoice_code",
            'payable',
            py."id",
            py."payable_code",
            'source',
            'push',
            '采购订单进项发票关联入库应付',
            NOW(),
            NOW()
        FROM "apps_kuaicaiwu_purchase_invoices" pi
        INNER JOIN "apps_kuaizhizao_purchase_receipts" pr
            ON pr."tenant_id" = pi."tenant_id"
            AND pr."purchase_order_id" = pi."purchase_order_id"
            AND pr."deleted_at" IS NULL
        INNER JOIN "apps_kuaicaiwu_payables" py
            ON py."tenant_id" = pi."tenant_id"
            AND py."source_id" = pr."id"
            AND py."deleted_at" IS NULL
            AND py."source_type" IN ('采购入库', 'purchase_receipt', 'PurchaseReceipt')
        WHERE pi."deleted_at" IS NULL
            AND pi."purchase_order_id" IS NOT NULL
            AND pi."status" NOT IN ('已作废', '已红冲')
            AND NOT EXISTS (
                SELECT 1 FROM "apps_kuaizhizao_document_relations" r
                WHERE r."tenant_id" = pi."tenant_id"
                    AND r."source_type" = 'purchase_invoice'
                    AND r."source_id" = pi."id"
                    AND r."target_type" = 'payable'
                    AND r."target_id" = py."id"
            );
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DELETE FROM "apps_kuaizhizao_document_relations"
        WHERE "relation_desc" = '采购订单进项发票关联入库应付'
            AND "source_type" = 'purchase_invoice'
            AND "target_type" = 'payable';
    """
