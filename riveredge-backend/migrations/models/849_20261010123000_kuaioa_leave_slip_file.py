"""轻办公请假出差：请假条附件 UUID。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaioa_leave_requests"
    ADD COLUMN IF NOT EXISTS "leave_slip_file_uuid" VARCHAR(36);
COMMENT ON COLUMN "apps_kuaioa_leave_requests"."leave_slip_file_uuid"
    IS '请假条附件 file UUID';
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaioa_leave_requests"
    DROP COLUMN IF EXISTS "leave_slip_file_uuid";
"""
