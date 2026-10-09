"""
登录地点回填：修复误去「州」后缀导致的单字市名（如「中国 广东 广」→「中国 广东 广州」）。

写路径修复见 core.utils.ip_parser._strip_admin_suffix；本迁移仅改历史 core_login_logs。
"""

from __future__ import annotations

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    from core.utils.ip_parser import repair_truncated_zhou_city_login_location

    rows = await db.execute_query_dict(
        """
        SELECT "id", "login_location"
        FROM "core_login_logs"
        WHERE "login_location" IS NOT NULL
          AND TRIM("login_location") <> ''
        """
    )
    updates: list[tuple[str, int]] = []
    for row in rows:
        row_id = int(row["id"])
        old = str(row["login_location"] or "").strip()
        if not old:
            continue
        new = repair_truncated_zhou_city_login_location(old)
        if new and new != old:
            updates.append((new, row_id))

    for new_label, row_id in updates:
        await db.execute_query(
            """
            UPDATE "core_login_logs"
            SET "login_location" = $1
            WHERE "id" = $2
            """,
            [new_label, row_id],
        )

    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    return "SELECT 1;"
