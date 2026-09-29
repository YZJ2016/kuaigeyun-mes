"""连接健康检查占位。能力延后在六步之后（KIO-D6），本函数为占位 no-op，保持已注册 cron 不报错。"""

from loguru import logger


async def run_kuaiiot_connection_health_check() -> dict:
    """连接健康检查能力延后在六步之后（KIO-D6），占位 no-op，保持已注册 cron 不报错。"""
    logger.debug("kuaiiot connection health check skipped: not implemented")
    return {"skipped": True, "reason": "not_implemented"}
