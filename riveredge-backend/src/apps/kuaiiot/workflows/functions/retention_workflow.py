"""留存清理占位。能力延后在六步之后（spec154 留存清理），本函数为占位 no-op，保持已注册 cron 不报错。"""

from loguru import logger


async def run_kuaiiot_retention_cleanup() -> dict:
    """留存清理能力延后在六步之后（spec154 留存清理），占位 no-op，保持已注册 cron 不报错。"""
    logger.debug("kuaiiot retention cleanup skipped: not implemented")
    return {"skipped": True, "reason": "not_implemented"}
