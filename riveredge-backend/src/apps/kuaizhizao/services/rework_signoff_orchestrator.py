"""会签返工编排（唯一流转真源）。

销售提交后按 A-A / A-B 固化节点顺序推进。
不复用 MES 下达/报工，也不按 form_sections 自由保存冒充办结。
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from loguru import logger

from apps.kuaizhizao.constants import DocumentStatus
from apps.kuaizhizao.constants.rework_business_types import is_signoff_rework_business
from apps.kuaizhizao.constants.rework_signoff_chain import (
    SIGNOFF_CHAIN_VERSION_V2,
    SIGNOFF_FLOW_KEY,
    chain_for_order,
    chain_version_from_flow,
    node_label,
)
from apps.kuaizhizao.constants.rework_signoff_sections import (
    POSITION_REVIEW_SUB_SECTIONS,
    REWORK_EXEC_SUB_SECTIONS,
)
from apps.kuaizhizao.models.rework_order_signoff import ReworkOrderSignoff
from core.utils.timezone_utils import resolve_business_datetime, today_site_str
from infra.exceptions.exceptions import BusinessLogicError, ValidationError


class ReworkSignoffOrchestrator:
    def __init__(self, service: Any) -> None:
        self.service = service

    def _payload(self, order: Any) -> dict:
        raw = getattr(order, "extension_payload", None) or {}
        return dict(raw) if isinstance(raw, dict) else {}

    def _flow(self, order: Any) -> dict:
        flow = self._payload(order).get(SIGNOFF_FLOW_KEY) or {}
        return dict(flow) if isinstance(flow, dict) else {}

    def _path(self, order: Any) -> str:
        payload = self._payload(order)
        path = str(payload.get("rework_path_type") or self._flow(order).get("path") or "aa").strip().lower()
        return "ab" if path == "ab" else "aa"

    def _chain(self, order: Any) -> list[tuple[str, str]]:
        flow = self._flow(order)
        return chain_for_order(self._path(order), flow)

    def _chain_version(self, order: Any) -> int:
        return chain_version_from_flow(self._flow(order))

    def _section_done(self, order: Any) -> dict:
        flow = self._flow(order)
        raw = flow.get("section_done") or {}
        return dict(raw) if isinstance(raw, dict) else {}

    def _assert_multi_sections_done(self, order: Any, node: str, required_keys: tuple[str, ...]) -> None:
        done_map = self._section_done(order).get(node) or {}
        if not isinstance(done_map, dict):
            done_map = {}
        missing = [k for k in required_keys if not done_map.get(k)]
        if missing:
            raise ValidationError(f"节点「{node}」须完成全部分区填报后再办结")

    async def start(self, tenant_id: int, order: Any, actor_id: int) -> None:
        """销售提交：签掉销售节点，当前节点落到下一部门，并通知办理人。"""
        if not is_signoff_rework_business(getattr(order, "business_type", None)):
            raise BusinessLogicError("仅会签型返工单走部门链")
        if not str(getattr(order, "product_line_code", None) or "").strip():
            raise ValidationError("会签型返工单须填写产品线码以生成 FR 单号")
        if not str(getattr(order, "rework_reason", None) or "").strip():
            raise ValidationError("提交前须填写返工原因")
        path = self._path(order)
        flow_seed: dict = {"chain_version": SIGNOFF_CHAIN_VERSION_V2}
        chain = chain_for_order(path, flow_seed)
        if len(chain) < 2:
            raise ValidationError("会签节点链未配置")
        user = await self.service.get_user_info(actor_id)
        now = resolve_business_datetime()
        await ReworkOrderSignoff.filter(
            tenant_id=tenant_id,
            rework_order_id=order.id,
        ).delete()
        for idx, (code, name) in enumerate(chain):
            signed = code == "sales"
            await ReworkOrderSignoff.create(
                tenant_id=tenant_id,
                uuid=str(uuid.uuid4()),
                rework_order_id=order.id,
                dept_code=code,
                dept_name=name,
                sort_order=idx,
                status="signed" if signed else "pending",
                result="agree" if signed else None,
                signer_id=actor_id if signed else None,
                signer_name=user["name"] if signed else None,
                signed_at=now if signed else None,
                created_by=actor_id,
                created_by_name=user["name"],
                updated_by=actor_id,
                updated_by_name=user["name"],
            )
        nxt = chain[1]
        payload = self._payload(order)
        payload["rework_path_type"] = path
        payload[SIGNOFF_FLOW_KEY] = {
            "path": path,
            "chain_version": SIGNOFF_CHAIN_VERSION_V2,
            "current_node_key": nxt[0],
            "current_node_name": nxt[1],
            "node_entered_at": today_site_str(),
            "assignees": {},
            "section_done": {},
        }
        order.extension_payload = payload
        order.review_status = DocumentStatus.SUBMITTED.value
        order.updated_by = actor_id
        order.updated_by_name = user["name"]
        await order.save()
        await self._notify(tenant_id, order, nxt[0], nxt[1], actor_id)

    async def assign(self, tenant_id: int, order: Any, dept_code: str, user_id: int, actor_id: int) -> None:
        flow = self._flow(order)
        if not flow:
            raise BusinessLogicError("请先提交返工单，再指定节点办理人")
        code = str(dept_code or "").strip()
        if code not in {c for c, _ in self._chain(order)}:
            raise ValidationError("未知会签节点")
        assignees = dict(flow.get("assignees") or {})
        assignees[code] = int(user_id)
        flow["assignees"] = assignees
        payload = self._payload(order)
        payload[SIGNOFF_FLOW_KEY] = flow
        order.extension_payload = payload
        user = await self.service.get_user_info(actor_id)
        order.updated_by = actor_id
        order.updated_by_name = user["name"]
        await order.save()
        ver = self._chain_version(order)
        if flow.get("current_node_key") == code:
            await self._notify(
                tenant_id,
                order,
                code,
                node_label(self._path(order), code, chain_version=ver),
                actor_id,
            )

    async def mark_section_done(
        self,
        tenant_id: int,
        order: Any,
        node_key: str,
        sub_section_key: str,
        actor_id: int,
    ) -> None:
        """标记某节点下分区已填报（保存本分区时调用，不推进链）。"""
        flow = self._flow(order)
        current = str(flow.get("current_node_key") or "").strip()
        node = str(node_key or "").strip()
        sub = str(sub_section_key or "").strip()
        if not node or not sub:
            raise ValidationError("须指定节点与分区")
        if node != current:
            raise BusinessLogicError("仅当前节点可保存本分区的会签进度")
        section_done = dict(flow.get("section_done") or {})
        node_done = dict(section_done.get(node) or {})
        node_done[sub] = True
        section_done[node] = node_done
        flow["section_done"] = section_done
        payload = self._payload(order)
        payload[SIGNOFF_FLOW_KEY] = flow
        order.extension_payload = payload
        user = await self.service.get_user_info(actor_id)
        order.updated_by = actor_id
        order.updated_by_name = user["name"]
        await order.save()

    async def complete(self, tenant_id: int, order: Any, actor_id: int, notes: Optional[str] = None) -> None:
        flow = self._flow(order)
        current = str(flow.get("current_node_key") or "").strip()
        if not current:
            raise BusinessLogicError("返工单尚未进入部门链，请先提交")
        chain = self._chain(order)
        keys = [c for c, _ in chain]
        if current not in keys:
            raise ValidationError("当前节点不在会签链上")
        await self._assert_node_ready(tenant_id, order, current)
        gated = await self.service.try_gate_signoff_node_approval(
            tenant_id, order, current, actor_id, notes=notes
        )
        if gated:
            return
        await self._advance_after_node_signed(tenant_id, order, current, actor_id, notes)

    async def advance_after_signoff_approval(
        self,
        tenant_id: int,
        order: Any,
        dept_code: str,
        actor_id: int,
        notes: Optional[str] = None,
    ) -> None:
        """审批通过后自动办结会签节点并推进链。"""
        flow = self._flow(order)
        pending = str(flow.get("approval_pending_node") or "").strip()
        code = str(dept_code or "").strip()
        current = str(flow.get("current_node_key") or "").strip()
        if pending and pending != code:
            raise BusinessLogicError("审批节点与会签当前节点不一致")
        if current != code:
            raise BusinessLogicError("仅当前会签节点可在审批通过后推进")
        flow.pop("approval_pending_node", None)
        payload = self._payload(order)
        payload[SIGNOFF_FLOW_KEY] = flow
        order.extension_payload = payload
        await order.save()
        await self._advance_after_node_signed(tenant_id, order, code, actor_id, notes)

    async def _advance_after_node_signed(
        self,
        tenant_id: int,
        order: Any,
        current: str,
        actor_id: int,
        notes: Optional[str] = None,
    ) -> None:
        chain = self._chain(order)
        keys = [c for c, _ in chain]
        await self._mark_signed(tenant_id, order.id, current, actor_id, notes)
        idx = keys.index(current)
        user = await self.service.get_user_info(actor_id)
        flow = self._flow(order)
        if idx + 1 >= len(keys):
            order.status = "closed"
            flow["current_node_key"] = "closed"
            flow["current_node_name"] = "已关闭"
        else:
            nxt_key, nxt_name = chain[idx + 1]
            flow["current_node_key"] = nxt_key
            flow["current_node_name"] = nxt_name
            flow["node_entered_at"] = today_site_str()
        payload = self._payload(order)
        payload[SIGNOFF_FLOW_KEY] = flow
        order.extension_payload = payload
        order.updated_by = actor_id
        order.updated_by_name = user["name"]
        from apps.kuaizhizao.constants import DocumentStatus

        order.review_status = DocumentStatus.SUBMITTED.value
        await order.save()
        if flow.get("current_node_key") not in {"", "closed"}:
            await self._notify(
                tenant_id,
                order,
                str(flow["current_node_key"]),
                str(flow["current_node_name"]),
                actor_id,
            )

    async def return_node(self, tenant_id: int, order: Any, actor_id: int, notes: Optional[str] = None) -> None:
        flow = self._flow(order)
        current = str(flow.get("current_node_key") or "").strip()
        chain = self._chain(order)
        keys = [c for c, _ in chain]
        if current not in keys:
            raise BusinessLogicError("当前节点不可退回")
        idx = keys.index(current)
        if idx <= 0:
            raise BusinessLogicError("销售发起节点不可退回")
        prev_key, prev_name = chain[idx - 1]
        if not str(notes or "").strip():
            raise ValidationError("退回须填写原因")
        now = resolve_business_datetime()
        user = await self.service.get_user_info(actor_id)
        await ReworkOrderSignoff.filter(
            tenant_id=tenant_id,
            rework_order_id=order.id,
            dept_code=prev_key,
            deleted_at__isnull=True,
        ).update(status="pending", result=None, notes=notes, updated_at=now, updated_by=actor_id, updated_by_name=user["name"])
        flow["current_node_key"] = prev_key
        flow["current_node_name"] = prev_name
        flow["node_entered_at"] = today_site_str()
        flow["last_return_notes"] = notes
        payload = self._payload(order)
        payload[SIGNOFF_FLOW_KEY] = flow
        order.extension_payload = payload
        order.updated_by = actor_id
        order.updated_by_name = user["name"]
        await order.save()
        await self._notify(tenant_id, order, prev_key, prev_name, actor_id)

    async def _assert_node_ready(self, tenant_id: int, order: Any, node: str) -> None:
        payload = self._payload(order)
        ver = self._chain_version(order)

        if node == "rd":
            blank = [k for k in ("target_product_code", "rd_material_diff") if not str(payload.get(k) or "").strip()]
            if blank:
                raise ValidationError("研发节点须填写目标型号与型号差异说明")
        if node == "quality" and not str(payload.get("quality_requirements_text") or "").strip():
            raise ValidationError("质量节点须填写返工要求")

        if node == "ie_engineering" and ver >= SIGNOFF_CHAIN_VERSION_V2:
            await self.service.validate_ie_position_scrap_readiness(tenant_id, order.id, order)

        if node == "position_review" and ver >= SIGNOFF_CHAIN_VERSION_V2:
            self._assert_multi_sections_done(order, "position_review", POSITION_REVIEW_SUB_SECTIONS)
            for key in (
                "prod_mgr_signoff_notes",
                "quality_mgr_signoff_notes",
                "pqc_signoff_notes",
            ):
                if not str(payload.get(key) or "").strip():
                    raise ValidationError("返工排位审核须填写生产、质量经理与 PQC 会签意见")

        if node == "manufacturing" and ver < SIGNOFF_CHAIN_VERSION_V2:
            if not str(payload.get("manufacturing_process_notes") or "").strip():
                raise ValidationError("生产节点须填写返工工序")
            await self.service.validate_ie_position_scrap_readiness(tenant_id, order.id, order)

        if node == "purchasing":
            await self.service.validate_material_req_required_at(tenant_id, order.id)

        if node == "planning" and not str(payload.get("plan_schedule_notes") or "").strip():
            raise ValidationError("计划节点须填写排产计划说明")

        if node == "rework_exec" and ver >= SIGNOFF_CHAIN_VERSION_V2:
            self._assert_multi_sections_done(order, "rework_exec", REWORK_EXEC_SUB_SECTIONS)
            if not str(payload.get("warehouse_confirm_notes") or "").strip():
                raise ValidationError("返工执行须填写仓库确认说明")
            if not str(payload.get("production_exec_notes") or "").strip():
                raise ValidationError("返工执行须填写生产主管执行说明")
            if not str(payload.get("quality_pqc_exec_notes") or "").strip():
                raise ValidationError("返工执行须填写质量 PQC 执行说明")

        if node == "warehouse" and ver < SIGNOFF_CHAIN_VERSION_V2:
            if not str(payload.get("warehouse_confirm_notes") or "").strip():
                raise ValidationError("仓库节点须填写确认说明")

        if node == "manufacturing_exec" and getattr(order, "need_warehouse_in", None) is None:
            raise ValidationError("完工入库节点须确认是否入库")

    async def _mark_signed(
        self, tenant_id: int, order_id: int, dept_code: str, actor_id: int, notes: Optional[str]
    ) -> None:
        user = await self.service.get_user_info(actor_id)
        now = resolve_business_datetime()
        updated = await ReworkOrderSignoff.filter(
            tenant_id=tenant_id,
            rework_order_id=order_id,
            dept_code=dept_code,
            deleted_at__isnull=True,
        ).update(
            status="signed",
            result="agree",
            signer_id=actor_id,
            signer_name=user["name"],
            signed_at=now,
            notes=notes,
            updated_at=now,
            updated_by=actor_id,
            updated_by_name=user["name"],
        )
        if not updated:
            raise ValidationError("当前会签节点不存在")

    async def _notify(
        self, tenant_id: int, order: Any, node_key: str, node_name: str, actor_id: int
    ) -> None:
        flow = self._flow(order)
        assignee = (flow.get("assignees") or {}).get(node_key)
        if not assignee:
            return
        try:
            from core.schemas.message_template import SendMessageRequest
            from core.services.messaging.message_service import MessageService

            code = getattr(order, "code", None) or order.id
            await MessageService.send_message(
                tenant_id,
                SendMessageRequest(
                    type="internal",
                    recipient=str(int(assignee)),
                    subject=f"返工单待评审 {code}",
                    content=f"返工单 {code} 已到达「{node_name}」，请于当日完成评审。",
                    variables={
                        "message_category": "process",
                        "trigger_document": "rework_order",
                        "detail_path": f"/apps/funide-oa/production-execution/rework-orders/{order.id}",
                    },
                ),
            )
        except Exception as exc:
            logger.error("返工单节点提醒发送失败 order={} node={}: {}", order.id, node_key, exc)