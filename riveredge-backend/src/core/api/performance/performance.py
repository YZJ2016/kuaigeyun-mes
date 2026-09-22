"""
API 性能监控 API 模块

进程内聚合已迁移至 Prometheus；本模块保留缓存统计与指标入口说明。
"""

from fastapi import APIRouter, Depends, Query
from loguru import logger

from core.metrics.http_metrics import SLOW_API_THRESHOLD_MS
from infra.infrastructure.cache.cache_manager import cache_manager
from infra.api.deps.deps import get_current_user
from core.api.deps.deps import get_current_tenant
from infra.models.user import User

router = APIRouter(prefix="/performance", tags=["Core - Performance"])


@router.get("/stats", summary="Get performance statistics")
async def get_performance_stats(
    limit: int = Query(10, ge=1, le=100, description="保留参数，兼容旧客户端"),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> dict:
    """
    获取性能相关概览。

    API 延迟直方图与慢请求计数请从各实例 scrape ``/metrics``（Prometheus 格式）。
    """
    try:
        cache_stats = cache_manager.get_stats()
        return {
            "metrics_endpoint": "/metrics",
            "slow_api_threshold_ms": SLOW_API_THRESHOLD_MS,
            "cache_stats": cache_stats,
            "note": (
                "API 延迟与 QPS 已导出为 Prometheus 指标 riveredge_http_*；"
                "多实例部署请对每个后端实例抓取 /metrics 后聚合。"
            ),
        }
    except Exception as e:
        logger.error("获取性能统计信息失败: {}", e)
        raise


@router.get("/slow-apis", summary="List slow APIs")
async def get_slow_apis(
    limit: int = Query(10, ge=1, le=100, description="保留参数，兼容旧客户端"),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> dict:
    """
    慢 API 列表已迁移至 Prometheus。

    查询示例：``rate(riveredge_http_slow_requests_total[5m])`` 或
    ``histogram_quantile(0.95, sum(rate(riveredge_http_request_duration_seconds_bucket[5m])) by (le, path))``。
    """
    return {
        "metrics_endpoint": "/metrics",
        "threshold_ms": SLOW_API_THRESHOLD_MS,
        "prometheus_queries": {
            "slow_request_rate": "sum(rate(riveredge_http_slow_requests_total[5m])) by (method, path)",
            "p95_latency": (
                "histogram_quantile(0.95, sum(rate(riveredge_http_request_duration_seconds_bucket[5m])) by (le, method, path))"
            ),
        },
        "note": "进程内慢 API 排行已移除；请使用 Prometheus/Grafana 按实例聚合。",
    }


@router.post("/reset-stats", summary="Reset performance statistics")
async def reset_performance_stats(
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> dict:
    """
    Prometheus 指标为累计计数，不支持在应用内重置。

    如需清空，请重启进程或在 Prometheus 侧调整 retention。
    """
    return {
        "success": False,
        "message": "性能指标已迁移至 Prometheus（/metrics），不支持在应用内重置。",
        "metrics_endpoint": "/metrics",
    }
