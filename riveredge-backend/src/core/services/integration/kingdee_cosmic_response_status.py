"""金蝶苍穹 OpenAPI 响应解析（无连接器依赖，便于单测）。"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


def _cosmic_batch_first_result(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, dict):
        result = data.get("result")
        if isinstance(result, list) and result and isinstance(result[0], dict):
            return result[0]
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return None


def is_im_batch_operate_path(path: str) -> bool:
    hay = str(path or "").lower().replace("_", "")
    return any(
        token in hay
        for token in (
            "batchunaudit",
            "batchunsubmit",
            "batchdelete",
            "batchsubmit",
            "batchaudit",
            "billbatchaudit",
        )
    )


def is_im_operate_idempotent_message(message: str, operate_slot: str) -> bool:
    """重复撤回/单据已在目标状态时，允许继续本地撤回。"""
    text = str(message or "").strip()
    if not text:
        return False
    compact = text.replace(" ", "")
    slot = str(operate_slot or "").strip()
    if slot == "withdraw":
        if any(
            phrase in compact
            for phrase in (
                "未审核",
                "不是已审核",
                "非已审核",
                "非审核态",
                "无需反审核",
                "当前状态不允许反审核",
            )
        ):
            return True
        # 苍穹已反审核、MES 未撤回时重试：「单据非审核态，不能反审核」
        if "不能反审核" in compact and (
            "非审核" in compact or "未审核" in compact
        ):
            return True
        return False
    if slot == "unsubmit":
        return any(
            phrase in compact
            for phrase in (
                "未提交",
                "不是已提交",
                "非已提交",
                "无需撤销",
                "无需反提交",
                "暂存",
                "当前状态不允许撤销提交",
            )
        )
    if slot == "delete":
        return any(
            phrase in compact
            for phrase in (
                "已删除",
                "不存在",
                "找不到",
                "无需删除",
            )
        )
    return False


def is_cosmic_batch_unsubmit_http_404(exc: BaseException) -> bool:
    text = str(exc or "").lower().replace("_", "")
    return "http404" in text.replace(" ", "") and "batchunsubmit" in text


def extract_cosmic_response_status(
    payload: Any,
    *,
    im_batch_operate: bool = False,
) -> Tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, "金蝶苍穹返回非 JSON 对象"
    error_code = str(payload.get("errorCode") or payload.get("error_code") or "").strip()
    status = payload.get("status")
    message = str(payload.get("message") or payload.get("msg") or "").strip()
    status_ok = status is True or str(status).lower() == "true" or error_code in {
        "0",
        "success",
        "SUCCESS",
    }
    ok = status_ok
    data = payload.get("data")
    if isinstance(data, dict):
        fail_count = str(data.get("failCount") or "").strip()
        success_count = str(data.get("successCount") or "").strip()
        if fail_count and fail_count not in {"0", "0.0"}:
            ok = False
        elif not im_batch_operate and success_count == "0" and fail_count in {"0", "0.0", ""}:
            total = str(data.get("totalCount") or "").strip()
            if total and total not in {"0", "0.0"}:
                ok = False
        elif im_batch_operate and status_ok and fail_count in {"0", "0.0", ""}:
            ok = True
        if not ok and not message:
            filt = str(data.get("filter") or "").strip()
            if filt:
                message = filt[:500]
    first = _cosmic_batch_first_result(payload)
    if isinstance(first, dict):
        bill_status = first.get("billStatus")
        if not im_batch_operate and (
            bill_status is False or str(bill_status).lower() == "false"
        ):
            ok = False
            row_msgs = first.get("errors") or first.get("rowMsg") or []
            if isinstance(row_msgs, list) and row_msgs:
                chunks: list[str] = []
                for item in row_msgs:
                    if isinstance(item, dict):
                        nested = item.get("rowMsg") or item.get("message")
                        if isinstance(nested, list):
                            chunks.extend(str(x) for x in nested if x)
                        elif nested:
                            chunks.append(str(nested))
                    elif item:
                        chunks.append(str(item))
                if chunks:
                    message = "；".join(chunks)[:500]
    if ok:
        return True, (message or "成功")[:500]
    if message:
        return False, message[:500]
    if error_code:
        return False, f"金蝶苍穹调用失败 errorCode={error_code}"[:500]
    return False, "金蝶苍穹调用失败"[:500]
