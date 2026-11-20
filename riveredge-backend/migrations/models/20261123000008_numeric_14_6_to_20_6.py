"""补齐迁移 888 遗留：NUMERIC(14,6) → 平台标准 DECIMAL(20,6)。

888 对原 (12,4) 做了 precision+2 → (14,6)，整数位仍约 8，写入可用库存等大数时
会触发 numeric field overflow。配置中心与 decimal_limits 已约定 (20,6)。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        DO $$
        DECLARE
            r RECORD;
        BEGIN
            FOR r IN
                SELECT
                    c.table_name,
                    c.column_name
                FROM information_schema.columns c
                WHERE c.table_schema = 'public'
                  AND c.data_type = 'numeric'
                  AND COALESCE(c.numeric_precision, 0) = 14
                  AND COALESCE(c.numeric_scale, 0) = 6
                  AND (
                    c.table_name LIKE 'apps\\_%' ESCAPE '\\'
                    OR c.table_name LIKE 'haoligo\\_%' ESCAPE '\\'
                  )
                  AND (
                    c.column_name ~* '(quantity|qty|amount|price|cost|balance|debit|credit|fee|interest)'
                    OR c.column_name IN (
                      'opening_debit', 'opening_credit', 'period_debit', 'period_credit',
                      'year_debit', 'year_credit', 'ending_debit', 'ending_credit',
                      'threshold_value', 'current_quantity', 'suggested_quantity',
                      'planned_receipt', 'planned_release', 'planned_production',
                      'planned_procurement', 'net_requirement', 'gross_requirement',
                      'safety_stock', 'reorder_point', 'available_inventory',
                      'reference_cost', 'credit_limit', 'landing_cost',
                      'suggested_work_order_quantity', 'suggested_purchase_order_quantity',
                      'quantity_per_base'
                    )
                  )
            LOOP
                EXECUTE format(
                    'ALTER TABLE %I ALTER COLUMN %I TYPE NUMERIC(20, 6) USING %I::NUMERIC',
                    r.table_name,
                    r.column_name,
                    r.column_name
                );
            END LOOP;
        END $$;
        """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- 降级不自动缩 precision；若已写入超过 NUMERIC(14,6) 的值请先手工处理
        SELECT 1;
        """
