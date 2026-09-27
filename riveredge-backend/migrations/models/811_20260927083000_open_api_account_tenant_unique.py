"""开放 API 账套：同一租户仅保留一条有效记录，并加部分唯一索引。"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        WITH ranked AS (
            SELECT id, tenant_id,
                   ROW_NUMBER() OVER (PARTITION BY tenant_id ORDER BY id) AS rn
            FROM core_open_api_accounts
            WHERE deleted_at IS NULL AND tenant_id IS NOT NULL
        ),
        dups AS (
            SELECT r.id AS dup_id, k.id AS keep_id
            FROM ranked r
            INNER JOIN ranked k ON k.tenant_id = r.tenant_id AND k.rn = 1
            WHERE r.rn > 1
        )
        UPDATE core_open_api_apps AS a
        SET account_id = d.keep_id,
            updated_at = CURRENT_TIMESTAMP
        FROM dups AS d
        WHERE a.account_id = d.dup_id
          AND a.deleted_at IS NULL;

        WITH ranked AS (
            SELECT id, tenant_id,
                   ROW_NUMBER() OVER (PARTITION BY tenant_id ORDER BY id) AS rn
            FROM core_open_api_accounts
            WHERE deleted_at IS NULL AND tenant_id IS NOT NULL
        ),
        dups AS (
            SELECT r.id AS dup_id
            FROM ranked r
            WHERE r.rn > 1
        )
        UPDATE core_open_api_accounts AS a
        SET deleted_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        FROM dups AS d
        WHERE a.id = d.dup_id;

        CREATE UNIQUE INDEX IF NOT EXISTS "uq_open_api_accounts_tenant_active"
            ON "core_open_api_accounts" ("tenant_id")
            WHERE "deleted_at" IS NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "uq_open_api_accounts_tenant_active";
    """
