"""将仍为旧默认 100MB 的图纸上传上限回填为 200MB（与当前产品默认一致）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "infra_tenants"
        SET "settings" = jsonb_set(
            COALESCE("settings", '{}'::jsonb),
            '{business_config,parameters,master_data,drawing_max_upload_size_mb}',
            '200'::jsonb,
            true
        )
        WHERE COALESCE(
            ("settings" -> 'business_config' -> 'parameters' -> 'master_data' ->> 'drawing_max_upload_size_mb')::int,
            -1
        ) = 100;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- 无法区分「旧默认 100」与「有意设为 100」，不自动回滚
        SELECT 1;
    """
