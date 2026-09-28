"""定时订阅执行。调度器只认这个类的 execute_subscription。"""

from __future__ import annotations

import re
from typing import Any

from core.schemas.message_template import MessageAttachment, SendMessageRequest
from core.services.messaging.message_service import MessageService

INBOX_CHANNEL = "inbox"
INTERNAL_MESSAGE_TYPE = "internal"
TASK_TYPE = "kuaireport_report_subscription"

_PATH_RE = re.compile(r"([A-Za-z]:\\|/[\w.-]+/|\\\\)")
_SECRET_RE = re.compile(r"password|passwd|口令|secret|cipher|token|hash", re.IGNORECASE)


def public_error(message: str) -> str:
    """失败文案不带口令、哈希或内部路径。"""
    text = " ".join(str(message or "").split())
    if not text or _PATH_RE.search(text) or _SECRET_RE.search(text):
        return "订阅执行失败"
    return text[:200]


def _message_body(name: str, report_id: int, total: int) -> str:
    title = " ".join(str(name or "").split()) or "报表订阅"
    return f"报表订阅「{title}」已执行，报表 {int(report_id)}，共 {int(total)} 行。"


def _execute_payload(result: Any) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        return result.model_dump()
    return {
        "data": result.data,
        "total": result.total,
        "success": result.success,
        "summary": result.summary,
    }


class SubscriptionService:
    """已有任务类型 kuaireport_report_subscription 的执行入口。"""

    def __init__(self, store: Any = None) -> None:
        self.store = store

    def _store(self) -> Any:
        if self.store is not None:
            return self.store
        from apps.kuaireport.slices.s149_distribution import TortoiseDistributionStore

        return TortoiseDistributionStore()

    async def execute_subscription(self, tenant_id: int, subscription_id: int) -> dict[str, Any]:
        store = self._store()
        row = await store.get_subscription(int(tenant_id), int(subscription_id))
        if row is None:
            return {"success": False, "error": "订阅不存在", "excel_attached": False}
        try:
            return await self._run(store, int(tenant_id), row)
        except Exception as exc:
            safe = public_error(str(exc))
            await store.mark_run(int(tenant_id), int(row["id"]), "failed", safe)
            return {"success": False, "error": safe, "excel_attached": False}

    async def _run(self, store: Any, tenant_id: int, row: dict[str, Any]) -> dict[str, Any]:
        subscription_id = int(row["id"])
        if not row.get("is_active"):
            await store.mark_run(tenant_id, subscription_id, "failed", "订阅未启用")
            return {"success": False, "error": "订阅未启用", "excel_attached": False}
        if str(row.get("channel") or "") != INBOX_CHANNEL:
            await store.mark_run(tenant_id, subscription_id, "failed", "订阅渠道无法发送")
            return {"success": False, "error": "订阅渠道无法发送", "excel_attached": False}

        recipient_ids = _recipient_ids(row.get("recipient_user_ids"))
        if not recipient_ids:
            await store.mark_run(tenant_id, subscription_id, "failed", "没有接收人")
            return {"success": False, "error": "没有接收人", "excel_attached": False}

        found = await store.users_in_tenant(tenant_id, recipient_ids)
        if set(recipient_ids) != set(found):
            await store.mark_run(tenant_id, subscription_id, "failed", "接收人不是本组织用户")
            return {"success": False, "error": "接收人不是本组织用户", "excel_attached": False}

        from apps.kuaireport.services.execute_service import execute_report

        filters = row.get("filters") if isinstance(row.get("filters"), dict) else {}
        executed = await execute_report(tenant_id, int(row["report_id"]), filters)
        payload = _execute_payload(executed)
        if payload["success"] is False:
            await store.mark_run(tenant_id, subscription_id, "failed", "报表执行失败")
            return {"success": False, "error": "报表执行失败", "excel_attached": False}
        content = _message_body(
            str(row.get("name") or ""),
            int(row["report_id"]),
            int(payload["total"] or 0),
        )
        attachment = await _workbook_attachment(tenant_id, row, filters)

        # 站内信走已有 MessageService.send_message。inbox 映射为 internal。
        for user_id in recipient_ids:
            request_fields: dict[str, Any] = {
                "type": INTERNAL_MESSAGE_TYPE,
                "recipient": str(user_id),
                "subject": str(row.get("name") or "报表订阅")[:200],
                "content": content,
            }
            if attachment is not None:
                request_fields["attachment"] = attachment
            response = await MessageService.send_message(
                tenant_id=tenant_id,
                request=SendMessageRequest(**request_fields),
            )
            if not response.success:
                safe = public_error(response.error or "")
                await store.mark_run(tenant_id, subscription_id, "failed", safe)
                return {"success": False, "error": safe, "excel_attached": False}

        await store.mark_run(tenant_id, subscription_id, "success", None)
        return {"success": True, "excel_attached": attachment is not None}


async def _workbook_attachment(
    tenant_id: int,
    row: dict[str, Any],
    filters: dict[str, Any],
) -> MessageAttachment | None:
    """仅 attach_excel 为真时取 146 工作簿。为假则不传附件。"""
    if not row.get("attach_excel"):
        return None
    from apps.kuaireport.slices.s146_center import export_full_excel
    from infra.domain.tenant_context import with_tenant

    async with with_tenant(tenant_id, reason="报表订阅导出工作簿"):
        workbook, filename = await export_full_excel(int(row["report_id"]), filters)
    return MessageAttachment(filename=filename, content=workbook)


def _recipient_ids(raw: Any) -> list[int]:
    if not isinstance(raw, list):
        return []
    ids: list[int] = []
    for item in raw:
        ids.append(int(item))
    return ids
