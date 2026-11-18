"""金蝶AI苍穹 OpenAPI 推送适配器：换票 / 组信封 / 结果解析，不感知业务单据类型。"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from core.models.integration_config import IntegrationConfig
from core.services.integration.connector_request import resolve_connector_request
from core.services.integration.kingdee_cosmic_api_presets import IM_PURINBILL_ADD_PATH
from core.services.integration.kingdee_cosmic_paths import prepare_kingdee_cosmic_outbound
from core.services.integration.kingdee_cosmic_response_status import (
    _cosmic_batch_first_result,
    extract_cosmic_response_status,
)
from core.services.integration.kingdee_cosmic_service import (
    apply_kingdee_cosmic_session_headers,
    is_kingdee_cosmic_access_token_rejected,
    login_kingdee_cosmic_session,
    invalidate_kingdee_cosmic_token_cache,
)
from infra.exceptions.exceptions import BusinessLogicError
from infra.infrastructure.http import get_http_client

__all__ = [
    "KingdeeCosmicPushAdapter",
    "extract_cosmic_response_status",
    "extract_cosmic_saved_bill_ref",
]

def extract_cosmic_saved_bill_ref(payload: Any, fallback: str = "") -> Tuple[int, str]:
    if not isinstance(payload, dict):
        return 0, str(fallback or "")
    data = _cosmic_batch_first_result(payload)
    if not isinstance(data, dict):
        data = payload
    raw_id = data.get("id") or data.get("Id") or data.get("billid") or data.get("billId") or 0
    try:
        target_id = int(raw_id)
    except (TypeError, ValueError):
        target_id = 0
    keys = data.get("keys") if isinstance(data.get("keys"), dict) else {}
    number = str(
        data.get("billno")
        or data.get("billNo")
        or data.get("number")
        or data.get("Number")
        or (keys.get("billno") if keys else "")
        or fallback
        or ""
    ).strip()
    return target_id, number


class KingdeeCosmicPushAdapter:
    """按 IntegrationConfig.type=kingdee_cosmic 调用 OpenAPI 写入。"""

    connector_type = "kingdee_cosmic"
    # 默认采购入库；业务适配可通过 config.save_path 覆盖
    save_path = IM_PURINBILL_ADD_PATH
    submit_path = ""
    audit_path = ""

    def supports_submit_audit(self) -> bool:
        # 苍穹提交/审核为独立 path，按业务配置另调；默认不在 Pipeline 内 Submit/Audit
        return False

    def wrap_save(
        self, *, form_id: str, model: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        config = cfg or {}
        wrap = str(config.get("body_wrap") or "data").strip().lower()
        if wrap in {"", "none", "flat"}:
            return dict(model)
        # batchAdd 等接口：data 为单据数组
        if wrap in {"data_list", "data_array", "list"}:
            return {"data": [dict(model)]}
        # 默认与开放平台 / 制造链路写入一致：业务字段放在 data 内
        return {"data": dict(model)}

    def wrap_operate(
        self,
        *,
        form_id: str,
        bill_id: int = 0,
        bill_no: str = "",
    ) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if int(bill_id or 0) > 0:
            data["id"] = int(bill_id)
        if bill_no:
            data["billno"] = str(bill_no)
        return {"data": data}

    async def call_direct(
        self,
        connection: IntegrationConfig,
        path: str,
        body: Dict[str, Any],
        *,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        cfg = connection.get_config()
        url, headers = resolve_connector_request(
            connection, endpoint=path, headers={"Content-Type": "application/json"}
        )
        method, url, params, body_out = prepare_kingdee_cosmic_outbound(
            cfg, url, "POST", None, body
        )
        session = await login_kingdee_cosmic_session(cfg)
        headers = apply_kingdee_cosmic_session_headers(
            headers,
            config=cfg,
            access_token=str(session.get("access_token") or ""),
        )
        client = get_http_client()
        resp = await client.request(
            method or "POST",
            url,
            json=body_out,
            params=params or None,
            headers=headers,
            timeout=timeout,
        )
        payload = _safe_json(resp)
        if is_kingdee_cosmic_access_token_rejected(payload, http_status=resp.status_code):
            await invalidate_kingdee_cosmic_token_cache(cfg)
            session = await login_kingdee_cosmic_session(cfg, force_refresh=True)
            headers = apply_kingdee_cosmic_session_headers(
                headers,
                config=cfg,
                access_token=str(session.get("access_token") or ""),
            )
            resp = await client.request(
                method or "POST",
                url,
                json=body_out,
                params=params or None,
                headers=headers,
                timeout=timeout,
            )
            payload = _safe_json(resp)
        if resp.status_code >= 400:
            raise BusinessLogicError(f"金蝶苍穹接口返回 HTTP {resp.status_code}")
        if not isinstance(payload, dict):
            raise BusinessLogicError(f"金蝶苍穹接口返回非 JSON：{(resp.text or '')[:200]}")
        return payload

    async def call_via_api_library(
        self,
        *,
        tenant_id: int,
        api_uuid: str,
        body: Dict[str, Any],
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        from uuid import UUID

        from core.schemas.api import APITestRequest
        from core.services.application.api_service import APIService

        result = await APIService().test_api(
            tenant_id,
            UUID(str(api_uuid)),
            APITestRequest(body=body),
            timeout=timeout,
        )
        status_code = int(result.get("status_code") or 0)
        payload = result.get("body")
        if status_code >= 400:
            raise BusinessLogicError(f"金蝶苍穹接口返回 HTTP {status_code}")
        if status_code == 0 and isinstance(payload, dict) and payload.get("error"):
            raise BusinessLogicError(str(payload.get("error"))[:500])
        if not isinstance(payload, dict):
            raise BusinessLogicError("金蝶苍穹接口返回非 JSON 对象")
        return payload

    def parse_status(self, payload: Any) -> Tuple[bool, str]:
        return extract_cosmic_response_status(payload)

    def parse_bill_ref(self, payload: Any, fallback: str = "") -> Tuple[int, str]:
        return extract_cosmic_saved_bill_ref(payload, fallback=fallback)


def _safe_json(resp: Any) -> Any:
    try:
        return resp.json()
    except Exception:
        return None
