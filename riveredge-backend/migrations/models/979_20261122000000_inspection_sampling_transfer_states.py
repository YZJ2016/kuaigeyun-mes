"""国标抽检严格度转移状态表"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_inspection_sampling_transfer_states" (
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT,
            "created_at" TIMESTAMPTZ NOT NULL,
            "updated_at" TIMESTAMPTZ NOT NULL,
            "id" SERIAL NOT NULL PRIMARY KEY,
            "material_id" INT NOT NULL,
            "plan_id" INT NOT NULL,
            "step_key" VARCHAR(36) NOT NULL,
            "strictness" VARCHAR(20) NOT NULL DEFAULT 'normal',
            "recent_lot_verdicts" JSONB NOT NULL DEFAULT '[]',
            "consecutive_accept" INT NOT NULL DEFAULT 0,
            "consecutive_reject" INT NOT NULL DEFAULT 0,
            CONSTRAINT "uid_kz_sampling_transfer_t_m_p_s"
                UNIQUE ("tenant_id", "material_id", "plan_id", "step_key")
        );
        CREATE INDEX IF NOT EXISTS "idx_kz_sampling_transfer_tenant_material"
            ON "apps_kuaizhizao_inspection_sampling_transfer_states" ("tenant_id", "material_id");
        CREATE INDEX IF NOT EXISTS "idx_kz_sampling_transfer_tenant_plan"
            ON "apps_kuaizhizao_inspection_sampling_transfer_states" ("tenant_id", "plan_id");
        COMMENT ON TABLE "apps_kuaizhizao_inspection_sampling_transfer_states"
            IS '快格轻制造 - 国标抽检严格度转移状态';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaizhizao_inspection_sampling_transfer_states";
    """
