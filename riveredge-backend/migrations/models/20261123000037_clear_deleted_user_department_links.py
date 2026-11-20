"""清除已删除用户残留的部门任职与负责人引用，避免空部门仍显示人数且无法删除。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        DELETE FROM "core_user_department_assignments" AS a
        USING "core_users" AS u
        WHERE a.user_id = u.id
          AND u.deleted_at IS NOT NULL;

        UPDATE "core_users"
        SET department_id = NULL
        WHERE deleted_at IS NOT NULL
          AND department_id IS NOT NULL;

        UPDATE "core_departments" AS d
        SET manager_id = NULL
        FROM "core_users" AS u
        WHERE d.manager_id = u.id
          AND u.deleted_at IS NOT NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- 历史任职与负责人引用无法无损回滚
        SELECT 1;
    """
