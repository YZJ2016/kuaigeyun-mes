"""为有主部门但无任职行的用户回填 is_primary 任职记录。"""
from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        INSERT INTO core_user_department_assignments (
            uuid,
            tenant_id,
            user_id,
            department_id,
            is_primary,
            created_at,
            updated_at
        )
        SELECT
            gen_random_uuid(),
            u.tenant_id,
            u.id,
            u.department_id,
            TRUE,
            NOW() AT TIME ZONE 'UTC',
            NOW() AT TIME ZONE 'UTC'
        FROM core_users u
        WHERE u.deleted_at IS NULL
          AND u.department_id IS NOT NULL
          AND u.department_id > 0
          AND NOT EXISTS (
              SELECT 1
                FROM core_user_department_assignments a
               WHERE a.tenant_id = u.tenant_id
                 AND a.user_id = u.id
                 AND a.department_id = u.department_id
          );
    """
