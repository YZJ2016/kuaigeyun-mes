"""通用单据推送编排：任意 source_type + target_profile，不绑定具体业务页。

任意页面：
1. 业务适配组装 Model（DocumentPushPrepared）
2. 调用 DocumentPushPipeline.push
即可落到外部系统。关联回写由调用方注入（避免 core→apps 依赖）。

P2：按 prepared.connector_type 解析 Adapter（金蝶 / Webhook·OA/CRM）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional

from loguru import logger

from core.models.integration_config import IntegrationConfig
from core.services.integration.document_push_adapter import (
    DocumentPushAdapter,
    ensure_default_adapters_registered,
    get_push_adapter,
)
from infra.exceptions.exceptions import BusinessLogicError, ValidationError

PersistRelationFn = Callable[[Dict[str, Any]], Awaitable[None]]

# connector_type → category 缓存（来自 PRESET；目录存在 ≠ 可推）
_CONNECTOR_CATEGORY_CACHE: Optional[Dict[str, str]] = None


def category_for_connector_type(connector_type: str) -> Optional[str]:
    """connector_type → 品类；目录映射存在不等于可写回。"""
    global _CONNECTOR_CATEGORY_CACHE
    ctype = str(connector_type or "").strip()
    if not ctype:
        return None
    if _CONNECTOR_CATEGORY_CACHE is None:
        try:
            from core.api.connector_definitions.connector_definitions import (
                PRESET_APP_CONNECTORS,
            )

            _CONNECTOR_CATEGORY_CACHE = {
                str(item.get("type") or "").strip(): str(item.get("category") or "").strip()
                for item in PRESET_APP_CONNECTORS
                if str(item.get("type") or "").strip()
            }
        except Exception:
            _CONNECTOR_CATEGORY_CACHE = {}
    return _CONNECTOR_CATEGORY_CACHE.get(ctype) or "other"


@dataclass
class DocumentPushRequest:
    """通用推送请求（页面入口只传身份 + 可选连接覆盖）。"""

    source_type: str
    source_id: int
    target_profile: str
    source_code: Optional[str] = None
    source_name: Optional[str] = None
    connection_code: Optional[str] = None
    save_api_uuid: Optional[str] = None
    dry_run: bool = False


@dataclass
class DocumentPushPrepared:
    """业务适配层输出：已映射好的目标报文 + 元数据。"""

    form_id: str
    model: Dict[str, Any]
    target_type: str
    target_name: str = ""
    relation_desc: str = ""
    connector_type: str = "kingdee_galaxy"
    config: Dict[str, Any] = field(default_factory=dict)


class DocumentPushPipeline:
    """单据无关编排：选连接 → 调适配器 → 解析 →（可选）关联回写。"""

    def __init__(self) -> None:
        ensure_default_adapters_registered()

    async def push(
        self,
        *,
        tenant_id: int,
        acting_user_id: int,
        request: DocumentPushRequest,
        prepared: DocumentPushPrepared,
        persist_relation: Optional[PersistRelationFn] = None,
    ) -> Dict[str, Any]:
        source_type = str(request.source_type or "").strip()
        target_profile = str(request.target_profile or "").strip()
        if not source_type or int(request.source_id or 0) <= 0:
            raise ValidationError("推送缺少 source_type / source_id")
        if not target_profile:
            raise ValidationError("推送缺少 target_profile")

        config = dict(prepared.config or {})
        if request.connection_code:
            config["connection_code"] = str(request.connection_code).strip()
        if request.save_api_uuid:
            config["save_api_uuid"] = str(request.save_api_uuid).strip()

        form_id = str(prepared.form_id or "").strip()
        if not form_id:
            raise ValidationError("推送缺少 form_id")
        model = prepared.model
        if not isinstance(model, dict) or not model:
            raise ValidationError("推送 Model 为空")

        adapter = self._resolve_adapter(prepared.connector_type)
        body = adapter.wrap_save(form_id=form_id, model=model, cfg=config)

        logger.info(
            "document_push prepare tenant_id={} source={}/{} profile={} connector={} dry_run={} form_id={}",
            tenant_id,
            source_type,
            request.source_id,
            target_profile,
            prepared.connector_type,
            bool(request.dry_run),
            form_id,
        )

        if request.dry_run:
            return {
                "success": True,
                "dry_run": True,
                "source_type": source_type,
                "source_id": int(request.source_id),
                "target_profile": target_profile,
                "target_type": prepared.target_type,
                "connector_type": prepared.connector_type,
                "form_id": form_id,
                "model": model,
                "body": body,
                "message": "dry_run",
            }

        from core.utils.timezone_utils import resolve_business_datetime

        started_at = resolve_business_datetime()
        try:
            result = await self._execute_push(
                tenant_id=tenant_id,
                acting_user_id=acting_user_id,
                request=request,
                prepared=prepared,
                adapter=adapter,
                config=config,
                form_id=form_id,
                body=body,
                source_type=source_type,
                target_profile=target_profile,
                persist_relation=persist_relation,
            )
        except Exception as exc:
            await self._record_push_run_log(
                tenant_id=tenant_id,
                source_type=source_type,
                source_id=int(request.source_id),
                target_profile=target_profile,
                connector_type=prepared.connector_type,
                started_at=started_at,
                success=False,
                error=str(exc),
            )
            raise

        await self._record_push_run_log(
            tenant_id=tenant_id,
            source_type=source_type,
            source_id=int(request.source_id),
            target_profile=target_profile,
            connector_type=prepared.connector_type,
            started_at=started_at,
            success=True,
            bill_no=str(result.get("bill_no") or ""),
        )
        return result

    async def _execute_push(
        self,
        *,
        tenant_id: int,
        acting_user_id: int,
        request: DocumentPushRequest,
        prepared: DocumentPushPrepared,
        adapter: DocumentPushAdapter,
        config: Dict[str, Any],
        form_id: str,
        body: Dict[str, Any],
        source_type: str,
        target_profile: str,
        persist_relation: Optional[PersistRelationFn],
    ) -> Dict[str, Any]:
        timeout = float(config.get("timeout") or 30.0)
        # 硬上限：防止配置误写导致外部调用挂死拖垮 worker
        timeout = max(1.0, min(timeout, 120.0))
        save_api_uuid = str(config.get("save_api_uuid") or "").strip()
        connection = await self._resolve_connection(
            tenant_id,
            connector_type=prepared.connector_type,
            config=config,
        )
        operate_connection = await self._resolve_operate_connection(
            tenant_id,
            save_api_uuid=save_api_uuid,
            fallback=connection,
        )

        if save_api_uuid:
            response = await adapter.call_via_api_library(
                tenant_id=tenant_id,
                api_uuid=save_api_uuid,
                body=body,
                timeout=timeout,
            )
        else:
            save_path = str(config.get("save_path") or "").strip() or adapter.save_path
            response = await adapter.call_direct(
                connection,
                save_path,
                body,
                timeout=timeout,
            )

        ok, message = adapter.parse_status(response)
        if not ok:
            raise BusinessLogicError(message)

        fallback = str(request.source_code or request.source_id or "")
        target_id, bill_no = adapter.parse_bill_ref(response, fallback=fallback)

        connector_for_resolve = str(
            getattr(adapter, "connector_type", "") or prepared.connector_type or ""
        ).strip()
        if (
            connector_for_resolve == "kingdee_cosmic"
            and int(target_id or 0) <= 0
            and str(bill_no or "").strip()
        ):
            from core.services.integration.kingdee_cosmic_push_adapter import (
                resolve_kingdee_cosmic_bill_id_by_billno,
            )

            resolved = await resolve_kingdee_cosmic_bill_id_by_billno(
                operate_connection,
                form_id=form_id,
                bill_no=str(bill_no).strip(),
                timeout=timeout,
            )
            if resolved > 0:
                target_id = resolved

        result = {
            "success": True,
            "source_type": source_type,
            "source_id": int(request.source_id),
            "source_code": request.source_code,
            "source_name": request.source_name,
            "target_profile": target_profile,
            "target_type": prepared.target_type,
            "target_name": prepared.target_name or prepared.target_type,
            "connector_type": prepared.connector_type,
            "relation_desc": prepared.relation_desc
            or f"{source_type} → {target_profile}",
            "bill_id": target_id,
            "bill_no": bill_no,
            "message": message,
            "acting_user_id": acting_user_id,
        }

        # 保存已成功：即使后续提交/审核失败也先落关联，便于金蝶侧补字段后再次推送走补审。
        async def _persist_saved_relation() -> None:
            if persist_relation is None:
                return
            await persist_relation(result)

        try:
            workflow_message, submit_after, audit_after = await self._run_submit_audit_workflow(
                tenant_id=tenant_id,
                adapter=adapter,
                connection=operate_connection,
                connector_type=str(prepared.connector_type or "").strip(),
                config=config,
                form_id=form_id,
                bill_id=int(target_id or 0),
                bill_no=str(bill_no or ""),
                timeout=timeout,
            )
        except Exception as workflow_exc:
            await _persist_saved_relation()
            bill_hint = str(bill_no or target_id or "").strip()
            detail = str(workflow_exc).strip() or "金蝶提交/审核失败"
            if bill_hint and bill_hint not in detail:
                detail = f"{detail}（金蝶单号 {bill_hint} 已保存；补全必填后可再次推送以补提交/审核）"
            raise BusinessLogicError(detail) from workflow_exc

        result_message = message
        if workflow_message:
            base = (message or "保存成功").rstrip("。")
            result_message = f"{base}；{workflow_message}"
        elif (
            str(prepared.connector_type or "").strip() == "kingdee_cosmic"
            and (
                str(config.get("submit_path") or "").strip()
                or str(config.get("audit_path") or "").strip()
            )
            and not submit_after
            and not audit_after
        ):
            suffix = "（未执行提交/审核，金蝶侧可能仍为暂存；可在业务配置开启 submit_after_save / audit_after_save）"
            result_message = f"{(message or '保存成功').rstrip('。')}{suffix}"
        result["message"] = result_message

        await _persist_saved_relation()

        logger.info(
            "document_push ok tenant_id={} source={}/{} profile={} bill_no={}",
            tenant_id,
            source_type,
            request.source_id,
            target_profile,
            bill_no,
        )
        return result

    async def _record_push_run_log(
        self,
        *,
        tenant_id: int,
        source_type: str,
        source_id: int,
        target_profile: str,
        connector_type: str,
        started_at: Any,
        success: bool,
        error: Optional[str] = None,
        bill_no: str = "",
        action: Optional[str] = None,
    ) -> None:
        """外推/补提交审核/撤回 operate 写 core_sync_run_logs；失败不影响主流程。"""
        from core.models.sync_run_log import SyncRunLog
        from core.services.data.sync_trigger_kind import current_sync_trigger_kind
        from core.utils.timezone_utils import resolve_business_datetime

        now = resolve_business_datetime()
        duration_ms = 0
        if started_at is not None:
            try:
                duration_ms = int((now - started_at).total_seconds() * 1000)
            except Exception:
                duration_ms = 0
        category = category_for_connector_type(connector_type)
        action_label = str(action or "").strip()
        summary = (
            f"{source_type}/{source_id} → {target_profile} ({connector_type}/{category})"
            + (f" action={action_label}" if action_label else "")
            + (f" bill_no={bill_no}" if bill_no else "")
        )
        if error:
            summary = f"{summary}; {error}"[:2000]
        try:
            from core.services.integration.document_push_slo import document_push_slo

            document_push_slo.record(
                category=category or "other",
                connector_type=str(connector_type or "").strip() or "unknown",
                target_profile=str(target_profile or "").strip() or "unknown",
                success=success,
                duration_ms=duration_ms,
                dry_run=False,
            )
        except Exception:
            pass
        try:
            await SyncRunLog.create(
                tenant_id=tenant_id,
                binding_id=None,
                entity_type="document_push",
                mode="push",
                status="success" if success else "failed",
                created=1 if success else 0,
                updated=0,
                skipped=0,
                failed=0 if success else 1,
                fetched=0,
                truncated=False,
                duration_ms=duration_ms,
                error_summary=summary,
                started_at=started_at,
                finished_at=now,
                category=category,
                connector_type=str(connector_type or "").strip() or None,
                target_profile=str(target_profile or "").strip() or None,
                source_type=str(source_type or "").strip() or None,
                source_id=int(source_id) if source_id else None,
                trigger_kind=current_sync_trigger_kind(),
            )
        except Exception:
            logger.warning(
                "document_push sync_run_log failed tenant_id={} source={}/{} profile={}",
                tenant_id,
                source_type,
                source_id,
                target_profile,
                exc_info=True,
            )

    def _resolve_adapter(self, connector_type: str) -> DocumentPushAdapter:
        ensure_default_adapters_registered()
        return get_push_adapter(connector_type)

    async def _resolve_operate_connection(
        self,
        tenant_id: int,
        *,
        save_api_uuid: str,
        fallback: IntegrationConfig,
    ) -> IntegrationConfig:
        """Save 走接口库时，提交/审核 direct 调用须与 Save 同一连接器换票。"""
        api_uuid = str(save_api_uuid or "").strip()
        if not api_uuid:
            return fallback
        try:
            from uuid import UUID

            from core.models.api import API

            api = await API.filter(tenant_id=tenant_id, uuid=UUID(api_uuid)).first()
            conn_id = int(getattr(api, "integration_config_id", 0) or 0) if api else 0
            if conn_id <= 0:
                return fallback
            conn = await IntegrationConfig.filter(
                tenant_id=tenant_id,
                id=conn_id,
                is_active=True,
                deleted_at__isnull=True,
            ).first()
            return conn or fallback
        except Exception:
            return fallback

    async def _run_submit_audit_workflow(
        self,
        *,
        tenant_id: int,
        adapter: DocumentPushAdapter,
        connection: IntegrationConfig,
        connector_type: str,
        config: Dict[str, Any],
        form_id: str,
        bill_id: int,
        bill_no: str,
        timeout: float,
    ) -> tuple[str, bool, bool]:
        submit_path = str(
            config.get("submit_path") or getattr(adapter, "submit_path", "") or ""
        ).strip()
        audit_path = str(
            config.get("audit_path") or getattr(adapter, "audit_path", "") or ""
        ).strip()
        submit_after = False
        audit_after = False
        if not (adapter.supports_submit_audit() or submit_path or audit_path):
            return "", submit_after, audit_after

        from core.services.integration.kingdee_warehouse_document_push_config import (
            read_kingdee_push_workflow_bool,
        )

        workflow_default = bool(submit_path or audit_path)
        submit_after = read_kingdee_push_workflow_bool(
            config, "submit_after_save", default=workflow_default
        )
        audit_after = read_kingdee_push_workflow_bool(
            config, "audit_after_save", default=workflow_default
        )
        need_operate = submit_after or audit_after
        connector = str(connector_type or getattr(adapter, "connector_type", "") or "").strip()
        target_id = int(bill_id or 0)
        billno = str(bill_no or "").strip()
        if (
            need_operate
            and connector == "kingdee_cosmic"
            and target_id <= 0
            and not billno
        ):
            raise BusinessLogicError(
                "金蝶苍穹未返回单据内码或单号，无法自动提交/审核"
            )
        if need_operate and connector == "kingdee_cosmic" and target_id <= 0 and billno:
            from core.services.integration.kingdee_cosmic_push_adapter import (
                resolve_kingdee_cosmic_bill_id_by_billno,
            )

            resolved = await resolve_kingdee_cosmic_bill_id_by_billno(
                connection,
                form_id=form_id,
                bill_no=billno,
                timeout=timeout,
            )
            if resolved > 0:
                target_id = resolved

        steps: list[str] = []
        if submit_after and submit_path:
            try:
                _, submit_msg = await self._submit_or_audit(
                    tenant_id=tenant_id,
                    adapter=adapter,
                    connection=connection,
                    path=submit_path,
                    form_id=form_id,
                    bill_id=target_id,
                    bill_no=billno,
                    timeout=timeout,
                    config=config,
                    operate_api_uuid=str(config.get("submit_api_uuid") or "").strip() or None,
                )
                steps.append(f"已提交（{submit_msg or '成功'}）")
            except BusinessLogicError as exc:
                text = str(exc).replace(" ", "")
                if "只有暂存" in text and "提交" in text:
                    steps.append("已提交（单据已不在暂存，继续审核）")
                else:
                    raise
        if audit_after and audit_path:
            _, audit_msg = await self._submit_or_audit(
                tenant_id=tenant_id,
                adapter=adapter,
                connection=connection,
                path=audit_path,
                form_id=form_id,
                bill_id=target_id,
                bill_no=billno,
                timeout=timeout,
                config=config,
                operate_api_uuid=str(config.get("audit_api_uuid") or "").strip() or None,
            )
            steps.append(f"已审核（{audit_msg or '成功'}）")
        workflow_message = "金蝶" + "、".join(steps) if steps else ""
        return workflow_message, submit_after, audit_after

    async def cosmic_im_submit_audit_only(
        self,
        *,
        tenant_id: int,
        connector_type: str,
        config: Dict[str, Any],
        form_id: str,
        bill_id: int = 0,
        bill_no: str = "",
        source_type: Optional[str] = None,
        source_id: int = 0,
        target_profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        """已保存过的苍穹 im 单：仅 batchSubmit / batchAudit（补提交流程）。"""
        from core.utils.timezone_utils import resolve_business_datetime

        started_at = resolve_business_datetime()
        profile = str(target_profile or "").strip()
        st = str(source_type or "").strip()
        sid = int(source_id or 0)
        try:
            adapter = self._resolve_adapter(connector_type)
            save_api_uuid = str(config.get("save_api_uuid") or "").strip()
            connection = await self._resolve_connection(
                tenant_id,
                connector_type=connector_type,
                config=config,
            )
            operate_connection = await self._resolve_operate_connection(
                tenant_id,
                save_api_uuid=save_api_uuid,
                fallback=connection,
            )
            timeout = max(1.0, min(float(config.get("timeout") or 30.0), 120.0))
            workflow_message, _, _ = await self._run_submit_audit_workflow(
                tenant_id=tenant_id,
                adapter=adapter,
                connection=operate_connection,
                connector_type=connector_type,
                config=config,
                form_id=form_id,
                bill_id=int(bill_id or 0),
                bill_no=str(bill_no or "").strip(),
                timeout=timeout,
            )
            if not workflow_message:
                raise BusinessLogicError(
                    "未执行金蝶提交/审核（请确认 submit_after_save / audit_after_save 与 submit_path / audit_path）"
                )
            if st and sid > 0 and profile:
                await self._record_push_run_log(
                    tenant_id=tenant_id,
                    source_type=st,
                    source_id=sid,
                    target_profile=profile,
                    connector_type=connector_type,
                    started_at=started_at,
                    success=True,
                    bill_no=str(bill_no or "").strip(),
                    action="submit_audit",
                )
            return {
                "success": True,
                "message": workflow_message,
                "bill_id": bill_id,
                "bill_no": bill_no,
            }
        except Exception as exc:
            if st and sid > 0 and profile:
                await self._record_push_run_log(
                    tenant_id=tenant_id,
                    source_type=st,
                    source_id=sid,
                    target_profile=profile,
                    connector_type=connector_type,
                    started_at=started_at,
                    success=False,
                    error=str(exc),
                    bill_no=str(bill_no or "").strip(),
                    action="submit_audit",
                )
            raise

    async def cosmic_im_operate_only(
        self,
        *,
        tenant_id: int,
        connector_type: str,
        config: Dict[str, Any],
        form_id: str,
        path: str,
        bill_id: int = 0,
        bill_no: str = "",
        operate_api_uuid: Optional[str] = None,
        anchor_save_api_uuid: Optional[str] = None,
        operate_slot: Optional[str] = None,
        source_type: Optional[str] = None,
        source_id: int = 0,
        target_profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        """苍穹 im 单：单步 batchUnaudit / batchUnsubmit / batchDelete 等 operate。"""
        from core.utils.timezone_utils import resolve_business_datetime

        started_at = resolve_business_datetime()
        profile = str(target_profile or "").strip()
        st = str(source_type or "").strip()
        sid = int(source_id or 0)
        action = str(operate_slot or "operate").strip() or "operate"
        try:
            adapter = self._resolve_adapter(connector_type)
            operate_path = str(path or "").strip()
            if not operate_path:
                raise BusinessLogicError("金蝶苍穹 operate 缺少 path")
            connection = await self._resolve_connection(
                tenant_id,
                connector_type=connector_type,
                config=config,
            )
            save_uuid = str(
                anchor_save_api_uuid or config.get("save_api_uuid") or ""
            ).strip()
            operate_connection = await self._resolve_operate_connection(
                tenant_id,
                save_api_uuid=save_uuid,
                fallback=connection,
            )
            timeout = max(1.0, min(float(config.get("timeout") or 30.0), 120.0))
            target_id = int(bill_id or 0)
            billno = str(bill_no or "").strip()
            if (
                str(connector_type or "").strip() == "kingdee_cosmic"
                and target_id <= 0
                and not billno
            ):
                raise BusinessLogicError("金蝶苍穹未返回单据内码或单号，无法执行 operate")
            if (
                str(connector_type or "").strip() == "kingdee_cosmic"
                and target_id <= 0
                and billno
            ):
                from core.services.integration.kingdee_cosmic_push_adapter import (
                    resolve_kingdee_cosmic_bill_id_by_billno,
                )

                resolved = await resolve_kingdee_cosmic_bill_id_by_billno(
                    operate_connection,
                    form_id=form_id,
                    bill_no=billno,
                    timeout=timeout,
                )
                if resolved > 0:
                    target_id = resolved
            _, message = await self._submit_or_audit(
                tenant_id=tenant_id,
                adapter=adapter,
                connection=operate_connection,
                path=operate_path,
                form_id=form_id,
                bill_id=target_id,
                bill_no=billno,
                timeout=timeout,
                config=config,
                operate_api_uuid=operate_api_uuid,
                operate_slot=operate_slot,
            )
            if st and sid > 0 and profile:
                await self._record_push_run_log(
                    tenant_id=tenant_id,
                    source_type=st,
                    source_id=sid,
                    target_profile=profile,
                    connector_type=connector_type,
                    started_at=started_at,
                    success=True,
                    bill_no=billno,
                    action=action,
                )
            return {
                "success": True,
                "message": message or "成功",
                "bill_id": target_id,
                "bill_no": billno,
            }
        except Exception as exc:
            # 与仓储撤回链一致：开放平台未发布 batchUnsubmit 时 HTTP 404 会跳过继续本地撤回，
            # 同步记录再记失败只会刷屏，无参考价值。
            from core.services.integration.kingdee_cosmic_response_status import (
                is_cosmic_batch_unsubmit_http_404,
            )

            skip_sync_log = action == "unsubmit" and is_cosmic_batch_unsubmit_http_404(exc)
            if st and sid > 0 and profile and not skip_sync_log:
                await self._record_push_run_log(
                    tenant_id=tenant_id,
                    source_type=st,
                    source_id=sid,
                    target_profile=profile,
                    connector_type=connector_type,
                    started_at=started_at,
                    success=False,
                    error=str(exc),
                    bill_no=str(bill_no or "").strip(),
                    action=action,
                )
            raise

    async def _resolve_connection(
        self,
        tenant_id: int,
        *,
        connector_type: str,
        config: Dict[str, Any],
    ) -> IntegrationConfig:
        code = str(config.get("connection_code") or config.get("integration_code") or "").strip()
        kind = str(connector_type or "kingdee_galaxy").strip() or "kingdee_galaxy"
        query = IntegrationConfig.filter(
            tenant_id=tenant_id,
            type=kind,
            is_active=True,
            deleted_at__isnull=True,
        )
        connection = await query.filter(code=code).first() if code else await query.first()
        if not connection:
            raise ValidationError(f"未找到已启用的应用连接器（type={kind}）")
        return connection

    async def _submit_or_audit(
        self,
        *,
        tenant_id: int,
        adapter: DocumentPushAdapter,
        connection: IntegrationConfig,
        path: str,
        form_id: str,
        bill_id: int,
        bill_no: str,
        timeout: float,
        config: Optional[Dict[str, Any]] = None,
        operate_api_uuid: Optional[str] = None,
        operate_slot: Optional[str] = None,
    ) -> tuple[bool, str]:
        body = adapter.wrap_operate(
            form_id=form_id,
            bill_id=bill_id,
            bill_no=bill_no,
            cfg=config,
        )
        api_uuid = str(operate_api_uuid or "").strip()
        if api_uuid:
            response = await adapter.call_via_api_library(
                tenant_id=tenant_id,
                api_uuid=api_uuid,
                body=body,
                timeout=timeout,
            )
        else:
            response = await adapter.call_direct(connection, path, body, timeout=timeout)
        im_batch = False
        if str(getattr(adapter, "connector_type", "") or "").strip() == "kingdee_cosmic":
            from core.services.integration.kingdee_cosmic_response_status import (
                extract_cosmic_response_status,
                is_im_batch_operate_path,
                is_im_operate_idempotent_message,
            )

            im_batch = is_im_batch_operate_path(path)
            ok, message = extract_cosmic_response_status(
                response,
                im_batch_operate=im_batch,
            )
            if not ok:
                detail = str(message or "").strip() or "金蝶提交/审核失败"
                slot = str(operate_slot or "").strip()
                if im_batch and slot and is_im_operate_idempotent_message(detail, slot):
                    return True, detail
        else:
            ok, message = adapter.parse_status(response)
        if not ok:
            detail = str(message or "").strip() or "金蝶提交/审核失败"
            path_l = str(path or "").lower().replace("_", "")
            if "领用人" in detail and "otheroutbill" in path_l:
                base = detail.rstrip("。.;； ")
                detail = (
                    f"{base}。"
                    "MES 单据/外推报文可以已带领用人，但连枝横等环境的 "
                    "im_otheroutbill/batchAdd 若未在开放平台发布 pickeroperator_operatornumber，"
                    "该写参会被网关静默丢弃，金蝶落单后仍无领用人，提交即报此错"
                    "（销售出库/采购入库接口无此限制）。"
                    "请在苍穹开放平台为 batchAdd 发布该写参后删暂存重推；"
                    "或在金蝶打开已保存暂存单手工补领用人并保存，再在 MES 推送一次（走补提交/审核）。"
                )
            raise BusinessLogicError(detail)
        return ok, message
