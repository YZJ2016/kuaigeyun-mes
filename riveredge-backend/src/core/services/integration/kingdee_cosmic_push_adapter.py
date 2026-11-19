"""金蝶AI苍穹 OpenAPI 推送适配器：换票 / 组信封 / 结果解析，不感知业务单据类型。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.models.integration_config import IntegrationConfig
from core.services.integration.connector_request import resolve_connector_request
from core.services.integration.kingdee_cosmic_api_presets import IM_PURINBILL_ADD_PATH
from core.services.integration.kingdee_cosmic_paths import prepare_kingdee_cosmic_outbound
from core.services.integration.kingdee_cosmic_response_status import (
    extract_cosmic_response_status,
    is_im_batch_operate_path,
    is_im_operate_idempotent_message,
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


def _format_kingdee_cosmic_http_error(
    status_code: int,
    *,
    path: str = "",
    api_name: str = "",
) -> str:
    label = str(api_name or "").strip()
    path_s = str(path or "").strip()
    head = f"金蝶苍穹接口返回 HTTP {status_code}"
    if label or path_s:
        head = f"{head}（{label + ' ' if label else ''}{path_s}）".rstrip()
    if int(status_code or 0) != 404:
        return head
    return (
        f"{head}。"
        "常见原因：开放平台未发布或未对第三方应用授权该 API；"
        "或数据互通误绑了新增 add/add2 接口而非 batchUnaudit/batchUnSubmit/batchDelete。"
        "请在接口库加载对应批量 operate 预设，在苍穹发布后在接口管理测试通过，再重试撤回。"
    )


def _cosmic_batch_first_result(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    from core.services.integration.kingdee_cosmic_response_status import (
        _cosmic_batch_first_result as _first,
    )

    return _first(payload)


def extract_cosmic_saved_bill_ref(payload: Any, fallback: str = "") -> Tuple[int, str]:
    if not isinstance(payload, dict):
        return 0, str(fallback or "")
    data = _cosmic_batch_first_result(payload)
    if not isinstance(data, dict):
        data = payload
    # batchAdd 等接口常把内码放在 result[].keys.id，顶层 id 为空；只读顶层会导致
    # 后续 batchSubmit/batchAudit 仅带 billno，提交能过、审核空转，单据停在「已提交」。
    keys = data.get("keys") if isinstance(data.get("keys"), dict) else {}
    raw_id = (
        data.get("id")
        or data.get("Id")
        or data.get("billid")
        or data.get("billId")
        or (keys.get("id") if keys else None)
        or (keys.get("Id") if keys else None)
        or (keys.get("billid") if keys else None)
        or (keys.get("billId") if keys else None)
        or 0
    )
    try:
        target_id = int(str(raw_id).strip())
    except (TypeError, ValueError):
        target_id = 0
    number = str(
        data.get("billno")
        or data.get("billNo")
        or data.get("number")
        or data.get("Number")
        or (keys.get("billno") if keys else "")
        or (keys.get("billNo") if keys else "")
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
        cfg: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        config = cfg or {}
        row: Dict[str, Any] = {}
        if int(bill_id or 0) > 0:
            # 苍穹开放平台 batchSubmit/batchAudit 样例以字符串内码为主；id 与 ids 同传
            # （部分环境只认 ids），避免雪花 id 在网关按 Number 丢精度。
            sid = str(int(bill_id))
            row["id"] = sid
            row["ids"] = sid
        if bill_no:
            row["billno"] = str(bill_no)
        # 苍穹 im_*/batchSubmit、batchAudit：data 须为 Map（单对象），传 JSONArray 会报
        # JSONArray cannot be cast to Map。batchAdd 保存可用 data_list，提交/审核勿跟着用数组。
        wrap = str(config.get("operate_body_wrap") or "data").strip().lower()
        if wrap in {"data_list", "data_array", "list"}:
            return {"data": [row] if row else []}
        return {"data": row}

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
            raise BusinessLogicError(
                _format_kingdee_cosmic_http_error(resp.status_code, path=path)
            )
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

        api_path = ""
        api_name = ""
        try:
            from core.models.api import API

            api_row = await API.filter(tenant_id=tenant_id, uuid=UUID(str(api_uuid))).first()
            if api_row:
                api_path = str(api_row.path or "").strip()
                api_name = str(api_row.name or api_row.code or "").strip()
        except Exception:
            pass
        result = await APIService().test_api(
            tenant_id,
            UUID(str(api_uuid)),
            APITestRequest(body=body),
            timeout=timeout,
        )
        status_code = int(result.get("status_code") or 0)
        payload = result.get("body")
        if status_code >= 400:
            raise BusinessLogicError(
                _format_kingdee_cosmic_http_error(
                    status_code,
                    path=api_path,
                    api_name=api_name,
                )
            )
        if status_code == 0 and isinstance(payload, dict) and payload.get("error"):
            raise BusinessLogicError(str(payload.get("error"))[:500])
        if not isinstance(payload, dict):
            raise BusinessLogicError("金蝶苍穹接口返回非 JSON 对象")
        return payload

    def parse_status(self, payload: Any) -> Tuple[bool, str]:
        return extract_cosmic_response_status(payload)

    def parse_bill_ref(self, payload: Any, fallback: str = "") -> Tuple[int, str]:
        return extract_cosmic_saved_bill_ref(payload, fallback=fallback)


_IM_BILL_QUERY_PATH: Dict[str, str] = {
    "im_purinbill": "kapi/v2/im/im_purinbill/query",
    "im_saloutbill": "kapi/v2/im/im_saloutbill/query",
    "im_otheroutbill": "kapi/v2/im/im_otheroutbill/query",
    "im_otherinbill": "kapi/v2/im/im_otherinbill/query",
    "im_surplusbill": "kapi/v2/im/im_surplusbill/query",
    "im_deficitbill": "kapi/v2/im/im_deficitbill/query",
}


def _first_query_row(response: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(response, dict):
        return None
    data = response.get("data")
    if not isinstance(data, dict):
        return None
    rows = data.get("rows")
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return rows[0]
    # 部分环境详情 query 直接回单对象
    if data.get("id") is not None or data.get("billno") is not None:
        return data
    return None


def normalize_kingdee_im_billstatus(raw: Any) -> str:
    """开放平台 billstatus：A 暂存 / B 已提交 / C 已审核。"""
    text = str(raw or "").strip().upper()
    if text in {"A", "B", "C"}:
        return text
    return ""


async def query_kingdee_cosmic_bill_by_billno(
    connection: IntegrationConfig,
    *,
    form_id: str,
    bill_no: str,
    timeout: float = 30.0,
) -> Optional[Dict[str, Any]]:
    """按 billno 查仓穹库存单：返回首行（含 id / billstatus / billentry）。无单返回 None。"""
    path = _IM_BILL_QUERY_PATH.get(str(form_id or "").strip())
    bill = str(bill_no or "").strip()
    if not path or not bill:
        return None
    adapter = KingdeeCosmicPushAdapter()
    response = await adapter.call_direct(
        connection,
        path,
        {"data": {"billno": bill}},
        timeout=timeout,
    )
    ok, _ = extract_cosmic_response_status(response)
    if not ok:
        return None
    return _first_query_row(response)


async def resolve_kingdee_cosmic_bill_id_by_billno(
    connection: IntegrationConfig,
    *,
    form_id: str,
    bill_no: str,
    timeout: float = 30.0,
) -> int:
    """Save 未回内码时，用开放平台 query 按 billno 取 id，供 batchSubmit/batchAudit。"""
    row = await query_kingdee_cosmic_bill_by_billno(
        connection, form_id=form_id, bill_no=bill_no, timeout=timeout
    )
    if not row:
        return 0
    raw_id = row.get("id")
    try:
        return int(str(raw_id).strip())
    except (TypeError, ValueError):
        return 0


def kingdee_im_revoke_slots_for_billstatus(
    billstatus: str,
    *,
    include_delete: bool,
) -> List[str]:
    """按 billstatus 编排反审/撤销/删除；未知状态走全链以防漏步。"""
    status = normalize_kingdee_im_billstatus(billstatus)
    slots: List[str] = []
    if status == "A":
        pass
    elif status == "B":
        slots.append("unsubmit")
    else:
        # C 或未知：全链
        slots.extend(["withdraw", "unsubmit"])
    if include_delete:
        slots.append("delete")
    return slots


def _safe_json(resp: Any) -> Any:
    try:
        return resp.json()
    except Exception:
        return None
