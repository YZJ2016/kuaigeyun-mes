"""客商表补主键并对齐 id 序列，消除同 id 多行导致的 MultipleObjectsReturned。

根因：apps_master_data_suppliers / customers 建表后无 PRIMARY KEY，且
id 序列落后于 max(id)。同步/新建会插入已占用的 id，ORM 按 id 取供应商时抛
「Multiple objects returned」（采购申请转采购订单校验供应商即命中）。

策略（与 core_apis 997 同构）：
1. 同 id 多行：保留 created_at 最早一行，其余改到 max(id)+n 新号；
2. 补 PRIMARY KEY(id)（可重跑）；
3. setval 序列到当前 max(id)。

单据上的 supplier_id / customer_id 仍指向保留行；被改号的行成为独立客商，
需按编码核对后手工重绑业务引用（撞号期间引用本就不唯一）。
"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


def _dedupe_and_pk_sql(table: str, pk_name: str, seq_name: str) -> str:
    return f"""
        -- 同 id 多行：保留最早创建，其余改到新 id
        WITH dups AS (
            SELECT ctid,
                   ROW_NUMBER() OVER (
                       PARTITION BY id
                       ORDER BY created_at ASC NULLS LAST, ctid ASC
                   ) AS rn
            FROM "{table}"
        ),
        need AS (
            SELECT ctid,
                   ROW_NUMBER() OVER (ORDER BY ctid) AS n
            FROM dups
            WHERE rn > 1
        ),
        base AS (
            SELECT COALESCE(MAX(id), 0) AS m FROM "{table}"
        )
        UPDATE "{table}" AS a
        SET id = base.m + need.n
        FROM need, base
        WHERE a.ctid = need.ctid;

        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = '{pk_name}'
            ) THEN
                ALTER TABLE "{table}" ADD CONSTRAINT "{pk_name}" PRIMARY KEY ("id");
            END IF;
        END $$;

        SELECT setval(
            '{seq_name}',
            GREATEST((SELECT COALESCE(MAX(id), 1) FROM "{table}"), 1),
            true
        );
    """


async def upgrade(db: BaseDBAsyncClient) -> str:
    return (
        _dedupe_and_pk_sql(
            "apps_master_data_suppliers",
            "pk_apps_master_data_suppliers",
            "apps_master_data_suppliers_id_seq",
        )
        + _dedupe_and_pk_sql(
            "apps_master_data_customers",
            "pk_apps_master_data_customers",
            "apps_master_data_customers_id_seq",
        )
    )


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_suppliers"
            DROP CONSTRAINT IF EXISTS "pk_apps_master_data_suppliers";
        ALTER TABLE "apps_master_data_customers"
            DROP CONSTRAINT IF EXISTS "pk_apps_master_data_customers";
    """
