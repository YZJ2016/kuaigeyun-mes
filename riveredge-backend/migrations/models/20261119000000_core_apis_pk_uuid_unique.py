"""core_apis：消重撞号/撞 uuid、清软删幽灵、补 PRIMARY KEY / UNIQUE(uuid)、校准序列。

根因：建表无主键 + 序列落后于 max(id)，导致同 id 多行；ORM 按 id 更新/refresh 会
MultipleObjectsReturned 或误改兄弟行。产品删除已是硬删，软删行仅占号干扰。

生产曾仅有同 id 消重，CREATE UNIQUE INDEX uk_core_apis_uuid 因同 uuid 多行失败；
本迁移在建唯一索引前删除同 uuid / 同 (tenant_id, code) 的多余行（保留最新）。
"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- 1) 硬清软删幽灵（产品路径已硬删，残留只占号）
        DELETE FROM "core_apis" WHERE "deleted_at" IS NOT NULL;

        -- 2) 同 id 多行：保留 ctid 最小一行，其余改到新 id（从当前 max+1 起）
        WITH dups AS (
            SELECT ctid,
                   ROW_NUMBER() OVER (PARTITION BY id ORDER BY ctid) AS rn
            FROM "core_apis"
        ),
        need AS (
            SELECT ctid,
                   ROW_NUMBER() OVER (ORDER BY ctid) AS n
            FROM dups
            WHERE rn > 1
        ),
        base AS (
            SELECT COALESCE(MAX(id), 0) AS m FROM "core_apis"
        )
        UPDATE "core_apis" AS a
        SET id = base.m + need.n
        FROM need, base
        WHERE a.ctid = need.ctid;

        -- 3) 同 uuid 多行：保留 updated_at 最新（同则 id 小），其余硬删
        --    同步绑定按 uuid 指向保留行，删多余行不改绑定目标。
        DELETE FROM "core_apis" AS a
        USING (
            SELECT ctid,
                   ROW_NUMBER() OVER (
                       PARTITION BY "uuid"
                       ORDER BY "updated_at" DESC NULLS LAST, "id" ASC, ctid ASC
                   ) AS rn
            FROM "core_apis"
        ) AS d
        WHERE a.ctid = d.ctid AND d.rn > 1;

        -- 4) 同 (tenant_id, code) 多行：同样保留最新
        DELETE FROM "core_apis" AS a
        USING (
            SELECT ctid,
                   ROW_NUMBER() OVER (
                       PARTITION BY "tenant_id", "code"
                       ORDER BY "updated_at" DESC NULLS LAST, "id" ASC, ctid ASC
                   ) AS rn
            FROM "core_apis"
        ) AS d
        WHERE a.ctid = d.ctid AND d.rn > 1;

        -- 5) 主键（可重跑）
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'pk_core_apis'
            ) THEN
                ALTER TABLE "core_apis" ADD CONSTRAINT "pk_core_apis" PRIMARY KEY ("id");
            END IF;
        END $$;

        -- 6) uuid 全局唯一（同步绑定真源）
        DROP INDEX IF EXISTS "idx_core_apis_uuid";
        DROP INDEX IF EXISTS "uk_core_apis_uuid";
        CREATE UNIQUE INDEX "uk_core_apis_uuid" ON "core_apis" ("uuid");

        -- 7) (tenant_id, code) 全量唯一（已无软删行，去掉部分索引）
        DROP INDEX IF EXISTS "uk_core_apis_tenant_code";
        CREATE UNIQUE INDEX "uk_core_apis_tenant_code" ON "core_apis" ("tenant_id", "code");

        -- 8) 序列对齐
        SELECT setval(
            pg_get_serial_sequence('core_apis', 'id'),
            GREATEST((SELECT COALESCE(MAX(id), 1) FROM "core_apis"), 1),
            true
        );
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "core_apis" DROP CONSTRAINT IF EXISTS "pk_core_apis";
        DROP INDEX IF EXISTS "uk_core_apis_uuid";
        CREATE INDEX IF NOT EXISTS "idx_core_apis_uuid" ON "core_apis" ("uuid");
        DROP INDEX IF EXISTS "uk_core_apis_tenant_code";
        CREATE UNIQUE INDEX "uk_core_apis_tenant_code"
            ON "core_apis" ("tenant_id", "code")
            WHERE ("deleted_at" IS NULL);
    """
