"""AI 请求审计中间件。"""

from __future__ import annotations

import time
from typing import Callable, Optional

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.models.ai_audit_log import AiAuditLog

_AI_PATH_PREFIX = "/api/v1/core/ai"
_LEGACY_AI_PATHS = (
    "/api/v1/core/site-settings/integrations/deepseek/completions",
)


class AiAuditMiddleware(BaseHTTPMiddleware):
    """记录 AI 网关请求的 tenant/user/route/latency。"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if not self._is_ai_path(path):
            return await call_next(request)

        started = time.perf_counter()
        response = await call_next(request)
        latency_ms = int((time.perf_counter() - started) * 1000)

        tenant_id, user_id = self._extract_identity(request)
        capability = self._parse_capability(path)
        await self._persist_audit(
            tenant_id=tenant_id,
            user_id=user_id,
            route=path,
            capability=capability,
            latency_ms=latency_ms,
            status_code=response.status_code,
        )
        return response

    @staticmethod
    def _is_ai_path(path: str) -> bool:
        if path.startswith(_AI_PATH_PREFIX):
            return True
        return path in _LEGACY_AI_PATHS

    @staticmethod
    def _parse_capability(path: str) -> Optional[str]:
        if "/chat/completions" in path:
            return "chat"
        if "/draft/structure" in path:
            return "draft"
        if "/agent/run" in path:
            return "agent"
        if "/jobs" in path:
            return "jobs"
        if "/status" in path:
            return "status"
        return None

    @staticmethod
    def _extract_identity(request: Request) -> tuple[Optional[int], Optional[int]]:
        """审计归属只认已认证身份。

        红线：禁止信 ``X-Tenant-ID`` 等客户端租户头（可伪造归属）。
        优先取 get_current_user 处理期写入的 ``request.state.tenant_id``
        /``user_id``（JWT 解析结果）；state 缺失时回退直接解析
        Authorization JWT（与 OperationLogMiddleware 同款）。
        """
        state = getattr(request, "state", None)
        if state is not None:
            cached_tenant_id = getattr(state, "tenant_id", None)
            cached_user_id = getattr(state, "user_id", None)
            if cached_user_id is not None:
                try:
                    tenant_id = (
                        int(cached_tenant_id) if cached_tenant_id is not None else None
                    )
                    return tenant_id, int(cached_user_id)
                except (ValueError, TypeError):
                    pass

        authorization = request.headers.get("Authorization")
        if not authorization or not authorization.startswith("Bearer "):
            return None, None
        try:
            from infra.domain.security.security import get_token_payload

            payload = get_token_payload(authorization[7:])
            if not payload:
                return None, None
            tenant_id = payload.get("tenant_id")
            sub = payload.get("sub")
            tenant_id_int = int(tenant_id) if tenant_id is not None else None
            user_id_int = int(sub) if sub is not None else None
            return tenant_id_int, user_id_int
        except (ValueError, TypeError):
            return None, None
        except Exception:  # noqa: BLE001
            return None, None

    @staticmethod
    async def _persist_audit(
        *,
        tenant_id: Optional[int],
        user_id: Optional[int],
        route: str,
        capability: Optional[str],
        latency_ms: int,
        status_code: int,
        model: Optional[str] = None,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> None:
        if tenant_id is None:
            return
        try:
            await AiAuditLog.create(
                tenant_id=tenant_id,
                user_id=user_id,
                route=route,
                capability=capability,
                model=model,
                latency_ms=latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                status_code=status_code,
                error_message=error_message,
            )
        except Exception as exc:
            logger.warning("AI 审计写入失败 route={} error={}", route, exc)
