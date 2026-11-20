"""接口表增加出站字段映射（本地字段 → 对方字段）。

上游同步：988_20261103150000_api_outbound_field_mappings
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "core_apis"
    ADD COLUMN IF NOT EXISTS "outbound_field_mappings" JSONB NULL;
COMMENT ON COLUMN "core_apis"."outbound_field_mappings" IS '出站字段映射：[{enabled,level,local_field,remote_field,default_value}]，push 时按行组装报文';
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "core_apis"
    DROP COLUMN IF EXISTS "outbound_field_mappings";
"""
