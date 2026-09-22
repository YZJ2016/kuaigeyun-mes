"""
登录地点回填：含台湾且未冠「中国」的记录统一加前缀。

第三方 IP 库常把台湾标成独立地区；规范写路径见 core.utils.ip_parser.normalize_login_location_label。
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
UPDATE "core_login_logs"
SET "login_location" = '中国 ' || TRIM("login_location")
WHERE "login_location" IS NOT NULL
  AND TRIM("login_location") <> ''
  AND "login_location" !~ '^中国'
  AND "login_location" !~* '^China([[:space:]]|$)'
  AND (
    "login_location" ~ '台湾'
    OR "login_location" ~ '台灣'
    OR "login_location" ~* 'Taiwan'
  );

UPDATE "core_login_logs"
SET "login_location" = '中国 ' || TRIM(SUBSTRING("login_location" FROM 6))
WHERE "login_location" IS NOT NULL
  AND "login_location" ~* '^China[[:space:]]'
  AND (
    "login_location" ~ '台湾'
    OR "login_location" ~ '台灣'
    OR "login_location" ~* 'Taiwan'
  );
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return "-- noop: taiwan login_location china-prefix backfill is irreversible"
