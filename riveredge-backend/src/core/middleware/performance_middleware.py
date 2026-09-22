"""
API 性能监控中间件

通过 Prometheus 指标聚合请求延迟（多实例可 scrape /metrics），
并保留 X-Response-Time 响应头与慢 API 日志。
"""

import time
from typing import Callable

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.metrics.http_metrics import (
    HTTP_REQUEST_DURATION,
    HTTP_REQUESTS_TOTAL,
    HTTP_SLOW_REQUESTS_TOTAL,
    SLOW_API_THRESHOLD_MS,
)


class PerformanceMiddleware(BaseHTTPMiddleware):
    """记录 /api 请求延迟到 Prometheus，并输出慢 API 警告。"""

    SLOW_API_THRESHOLD = SLOW_API_THRESHOLD_MS

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self._should_monitor(request):
            return await call_next(request)

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._record_metrics(request, elapsed_ms, status_code=500, success=False)
            raise

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self._record_metrics(request, elapsed_ms, status_code=response.status_code, success=True)
        response.headers["X-Response-Time"] = f"{elapsed_ms:.2f}ms"

        if elapsed_ms > self.SLOW_API_THRESHOLD:
            logger.warning(
                "⚠️ 慢API检测: {} {} - 响应时间: {:.2f}ms",
                request.method,
                self._metric_path(request),
                elapsed_ms,
            )

        return response

    def _should_monitor(self, request: Request) -> bool:
        return request.url.path.startswith("/api/")

    @staticmethod
    def _metric_path(request: Request) -> str:
        route = request.scope.get("route")
        if route is not None:
            return route.path
        return request.url.path

    def _record_metrics(
        self,
        request: Request,
        elapsed_ms: float,
        *,
        status_code: int,
        success: bool,
    ) -> None:
        path = self._metric_path(request)
        method = request.method
        elapsed_sec = elapsed_ms / 1000.0

        HTTP_REQUEST_DURATION.labels(method=method, path=path).observe(elapsed_sec)
        HTTP_REQUESTS_TOTAL.labels(
            method=method,
            path=path,
            status=str(status_code),
        ).inc()

        if elapsed_ms > self.SLOW_API_THRESHOLD:
            HTTP_SLOW_REQUESTS_TOTAL.labels(method=method, path=path).inc()

        if not success:
            logger.debug(
                "API 请求失败: {} {} status={} {:.2f}ms",
                method,
                path,
                status_code,
                elapsed_ms,
            )
