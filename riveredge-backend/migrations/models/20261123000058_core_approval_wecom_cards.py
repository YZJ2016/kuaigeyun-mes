"""审批企微可更新卡片追踪表 core_approval_wecom_cards（上游 992 迁移的时间戳 remap 落位）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "core_approval_wecom_cards" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL UNIQUE,
            "tenant_id" INT,
            "approval_instance_id" INT NOT NULL,
            "recipient_user_id" INT NOT NULL,
            "wecom_userid" VARCHAR(64) NOT NULL,
            "msgid" VARCHAR(128),
            "response_code" VARCHAR(128),
            "card_kind" VARCHAR(32) NOT NULL DEFAULT 'template_card',
            "status" VARCHAR(20) NOT NULL DEFAULT 'active',
            "subject" VARCHAR(200),
            "content" TEXT,
            "document_url" VARCHAR(2048),
            "task_id" VARCHAR(128),
            "invalidate_label" VARCHAR(64),
            "deleted_at" TIMESTAMPTZ,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS "idx_approval_wecom_cards_tenant_instance_status"
            ON "core_approval_wecom_cards" ("tenant_id", "approval_instance_id", "status");
        CREATE INDEX IF NOT EXISTS "idx_approval_wecom_cards_tenant_instance_user"
            ON "core_approval_wecom_cards" ("tenant_id", "approval_instance_id", "recipient_user_id");
        CREATE INDEX IF NOT EXISTS "idx_approval_wecom_cards_tenant_status"
            ON "core_approval_wecom_cards" ("tenant_id", "status");
        COMMENT ON TABLE "core_approval_wecom_cards" IS '审批待办企微可更新卡片';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "core_approval_wecom_cards";
    """
