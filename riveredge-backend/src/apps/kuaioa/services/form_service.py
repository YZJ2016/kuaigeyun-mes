"""审批表单服务。"""

from __future__ import annotations

from typing import Any, Optional

from apps.kuaioa.constants.general_signoff_business_types import (
    is_valid_general_signoff_business_type,
)
from apps.kuaioa.models.form_request import KuaioaFormRequest
from apps.kuaioa.models.form_request_issue import KuaioaFormRequestIssueGrant
from apps.kuaioa.models.form_template import KuaioaFormTemplate
from apps.kuaioa.schemas.forms import (
    FormRequestCreate,
    FormRequestUpdate,
    FormTemplateCreate,
    FormTemplateUpdate,
)
from apps.kuaioa.services.approval_helper import (
    AUDIT_NODE_FORM_REQUEST,
    cancel_approval,
    enrich_with_approval,
    is_audit_required,
    start_approval,
)
from apps.kuaioa.services.kuaioa_list_core import (
    build_keyword_q,
    generate_daily_code,
    model_to_dict,
    touch_updated,
)
from apps.kuaioa.services.form_schema_validator import normalize_fields_schema, validate_form_data
from apps.kuaioa.services.form_request_issue_service import (
    clear_form_request_issue,
    enrich_form_request_item,
    filter_visible_form_requests,
    grants_by_request_ids,
)
from apps.kuaioa.utils.form_request_issue_access import (
    load_user_role_ids,
    user_can_view_form_request_row,
)
from apps.kuaioa.utils.form_request_confirmation import (
    CONFIRMATION_KIND_COMPLETE_MACHINE,
    confirmation_kind_from_form_data,
    validate_confirmation_on_submit,
)
from apps.kuaioa.utils.form_request_material_issue import validate_material_issue_on_submit
from apps.kuaioa.utils.form_request_review_sheet import validate_review_sheet_on_submit
from apps.kuaioa.schemas.forms import FormRequestConfirmationReply
from apps.common.audit_actor import apply_create_audit
from core.services.system.menu_service import MenuService
from core.services.permission.user_permission_service import UserPermissionService
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError, ValidationError
from infra.models.user import User


def _normalize_business_type(raw: Optional[str]) -> Optional[str]:
    code = (raw or "").strip() or None
    if not is_valid_general_signoff_business_type(code):
        raise ValidationError(f"非法业务类型: {raw}")
    return code


class FormTemplateService:
    async def list_templates(
        self,
        tenant_id: int,
        *,
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        business_type: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> list[dict[str, Any]]:
        q = KuaioaFormTemplate.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if category:
            q = q.filter(category=category)
        if business_type is not None:
            bt = (business_type or "").strip()
            if bt:
                q = q.filter(business_type=bt)
            else:
                q = q.filter(business_type__isnull=True)
        if is_active is not None:
            q = q.filter(is_active=is_active)
        if keyword:
            q = q.filter(build_keyword_q(keyword, "template_code", "template_name"))
        rows = await q.order_by("-created_at", "-id")
        return [model_to_dict(row) for row in rows]

    async def get_template(self, tenant_id: int, template_id: int) -> dict[str, Any]:
        row = await KuaioaFormTemplate.get_or_none(
            id=template_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("表单模板不存在")
        return model_to_dict(row)

    async def create_template(
        self, tenant_id: int, data: FormTemplateCreate, user: User
    ) -> dict[str, Any]:
        exists = await KuaioaFormTemplate.filter(
            tenant_id=tenant_id, template_code=data.template_code, deleted_at__isnull=True
        ).exists()
        if exists:
            raise BusinessLogicError("模板编码已存在")
        create_payload: dict[str, Any] = {
            "tenant_id": tenant_id,
            "template_code": data.template_code.strip(),
            "template_name": data.template_name.strip(),
            "category": data.category,
            "business_type": _normalize_business_type(data.business_type),
            "description": data.description,
            "fields_schema": normalize_fields_schema(data.fields_schema),
            "is_active": data.is_active,
            "show_in_menu": data.show_in_menu,
        }
        apply_create_audit(create_payload, user)
        row = await KuaioaFormTemplate.create(**create_payload)
        if row.show_in_menu:
            await MenuService._clear_menu_cache(tenant_id)
        return model_to_dict(row)

    async def update_template(
        self, tenant_id: int, template_id: int, data: FormTemplateUpdate, user: User
    ) -> dict[str, Any]:
        row = await KuaioaFormTemplate.get_or_none(
            id=template_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("表单模板不存在")
        menu_affecting_before = (row.show_in_menu, row.is_active, row.template_name, row.template_code)
        payload = data.model_dump(exclude_unset=True)
        if "fields_schema" in payload:
            payload["fields_schema"] = normalize_fields_schema(payload["fields_schema"])
        if "business_type" in payload:
            payload["business_type"] = _normalize_business_type(payload.get("business_type"))
        for key, value in payload.items():
            setattr(row, key, value)
        await touch_updated(row, user)
        await row.save()
        menu_affecting_after = (row.show_in_menu, row.is_active, row.template_name, row.template_code)
        if menu_affecting_before != menu_affecting_after:
            await MenuService._clear_menu_cache(tenant_id)
        return model_to_dict(row)

    async def get_template_by_code(self, tenant_id: int, template_code: str) -> dict[str, Any]:
        code = str(template_code or "").strip()
        if not code:
            raise NotFoundError("表单模板不存在")
        row = await KuaioaFormTemplate.get_or_none(
            tenant_id=tenant_id,
            template_code=code,
            deleted_at__isnull=True,
        )
        if not row:
            raise NotFoundError("表单模板不存在")
        return model_to_dict(row)

    async def delete_template(self, tenant_id: int, template_id: int, user: User) -> None:
        row = await KuaioaFormTemplate.get_or_none(
            id=template_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("表单模板不存在")
        if row.show_in_menu:
            await MenuService._clear_menu_cache(tenant_id)
        row.deleted_at = resolve_business_datetime()
        await touch_updated(row, user)
        await row.save()


async def _resolve_active_template(
    tenant_id: int, template_id: Optional[int]
) -> Optional[KuaioaFormTemplate]:
    if not template_id:
        return None
    template = await KuaioaFormTemplate.get_or_none(
        id=template_id, tenant_id=tenant_id, deleted_at__isnull=True
    )
    if not template:
        raise NotFoundError("表单模板不存在")
    if not template.is_active:
        raise BusinessLogicError("表单模板已停用")
    return template


class FormRequestService:
    async def _permission_codes_for_user(self, tenant_id: int, user_id: Optional[int]) -> list[str]:
        if user_id is None:
            return []
        return sorted(
            await UserPermissionService.get_user_permissions(
                user_id=user_id,
                tenant_id=tenant_id,
            )
        )

    async def list_requests(
        self,
        tenant_id: int,
        *,
        keyword: Optional[str] = None,
        status: Optional[str] = None,
        template_id: Optional[int] = None,
        business_type: Optional[str] = None,
        current_user_id: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        q = KuaioaFormRequest.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if status:
            q = q.filter(status=status)
        if template_id:
            q = q.filter(template_id=template_id)
        if business_type is not None:
            bt = (business_type or "").strip()
            if bt:
                q = q.filter(business_type=bt)
            else:
                q = q.filter(business_type__isnull=True)
        if keyword:
            q = q.filter(build_keyword_q(keyword, "request_code", "title", "applicant_name"))
        rows = await q.order_by("-created_at", "-id")
        permission_codes = await self._permission_codes_for_user(tenant_id, current_user_id)
        visible_rows = await filter_visible_form_requests(
            rows,
            tenant_id=tenant_id,
            current_user_id=current_user_id,
            permission_codes=permission_codes,
        )
        role_ids: Optional[list[int]] = None
        department_id: Optional[int] = None
        if current_user_id is not None:
            role_ids = await load_user_role_ids(current_user_id)
            user_row = await User.get_or_none(id=current_user_id)
            department_id = getattr(user_row, "department_id", None) if user_row else None
        grant_map = await grants_by_request_ids(
            tenant_id, [int(r.id) for r in visible_rows if r.id is not None]
        )
        result = []
        for row in visible_rows:
            item = model_to_dict(row)
            await enrich_with_approval(item, tenant_id, "kuaioa_form_request")
            grants = grant_map.get(int(row.id), [])
            await enrich_form_request_item(
                item,
                row,
                grants=grants,
                current_user_id=current_user_id,
                permission_codes=permission_codes,
                role_ids=role_ids,
                department_id=department_id,
            )
            result.append(item)
        return result

    async def get_request(
        self,
        tenant_id: int,
        request_id: int,
        *,
        current_user_id: Optional[int] = None,
    ) -> dict[str, Any]:
        row = await KuaioaFormRequest.get_or_none(
            id=request_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("申请单不存在")
        permission_codes = await self._permission_codes_for_user(tenant_id, current_user_id)
        grants = await KuaioaFormRequestIssueGrant.filter(
            tenant_id=tenant_id,
            request_id=request_id,
            deleted_at__isnull=True,
        ).all()
        if not await user_can_view_form_request_row(
            row,
            user_id=current_user_id,
            permission_codes=permission_codes,
            grants=grants,
        ):
            raise NotFoundError("申请单不存在")
        item = model_to_dict(row)
        item = await enrich_with_approval(item, tenant_id, "kuaioa_form_request")
        role_ids = await load_user_role_ids(current_user_id) if current_user_id else None
        user_row = await User.get_or_none(id=current_user_id) if current_user_id else None
        department_id = getattr(user_row, "department_id", None) if user_row else None
        return await enrich_form_request_item(
            item,
            row,
            grants=grants,
            current_user_id=current_user_id,
            permission_codes=permission_codes,
            role_ids=role_ids,
            department_id=department_id,
            include_grants=True,
        )

    async def create_request(
        self, tenant_id: int, data: FormRequestCreate, user: User
    ) -> dict[str, Any]:
        template = await _resolve_active_template(tenant_id, data.template_id)
        if template:
            validate_form_data(template.fields_schema or [], data.form_data)
        request_code = await generate_daily_code(
            KuaioaFormRequest, tenant_id, "FR", code_field="request_code"
        )
        create_payload: dict[str, Any] = {
            "tenant_id": tenant_id,
            "request_code": request_code,
            "template_id": data.template_id,
            "template_code": template.template_code if template else data.template_code,
            "business_type": (template.business_type if template else None) or None,
            "title": data.title.strip(),
            "form_data": data.form_data,
            "department_name": data.department_name,
            "notes": data.notes,
            "applicant_id": user.id,
            "applicant_name": getattr(user, "name", None) or getattr(user, "username", None),
            "status": "draft",
        }
        apply_create_audit(create_payload, user)
        row = await KuaioaFormRequest.create(**create_payload)
        return model_to_dict(row)

    async def update_request(
        self, tenant_id: int, request_id: int, data: FormRequestUpdate, user: User
    ) -> dict[str, Any]:
        row = await KuaioaFormRequest.get_or_none(
            id=request_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("申请单不存在")
        if row.status not in {"draft", "rejected"}:
            raise BusinessLogicError("当前状态不可编辑")
        payload = data.model_dump(exclude_unset=True)
        if "form_data" in payload:
            template = await _resolve_active_template(tenant_id, row.template_id)
            if template:
                validate_form_data(template.fields_schema or [], payload.get("form_data"))
        for key, value in payload.items():
            setattr(row, key, value)
        await touch_updated(row, user)
        await row.save()
        return model_to_dict(row)

    async def delete_request(self, tenant_id: int, request_id: int, user: User) -> None:
        row = await KuaioaFormRequest.get_or_none(
            id=request_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("申请单不存在")
        if row.status not in {"draft", "cancelled"}:
            raise BusinessLogicError("仅草稿或已撤销状态可删除")
        row.deleted_at = resolve_business_datetime()
        await touch_updated(row, user)
        await row.save()

    async def submit_request(self, tenant_id: int, request_id: int, user_id: int) -> dict[str, Any]:
        user = await User.get_or_none(id=user_id)
        row = await KuaioaFormRequest.get_or_none(
            id=request_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("申请单不存在")
        if row.status not in {"draft", "rejected"}:
            raise BusinessLogicError("当前状态不可提交")
        template = await _resolve_active_template(tenant_id, row.template_id)
        if template:
            validate_form_data(template.fields_schema or [], row.form_data or {})
        if (row.business_type or "").strip().lower() == "confirmation":
            validate_confirmation_on_submit(row.form_data or {})
        if (row.business_type or "").strip().lower() == "review_sheet":
            validate_review_sheet_on_submit(row.form_data or {})
        if (row.business_type or "").strip().lower() == "material_issue":
            validate_material_issue_on_submit(row.form_data or {})
        row.status = "pending"
        row.submitted_at = resolve_business_datetime()
        await touch_updated(row, user or user_id)
        await row.save()
        approval_instance = None
        if await is_audit_required(tenant_id, AUDIT_NODE_FORM_REQUEST):
            approval_instance = await start_approval(
                tenant_id,
                node_key=AUDIT_NODE_FORM_REQUEST,
                entity_type="kuaioa_form_request",
                entity_id=int(row.id),
                entity_uuid=str(row.uuid),
                title=f"自定义申请: {row.title}",
                content=row.notes or row.title,
                submitter_id=user_id,
                business_type=row.business_type,
            )
        else:
            row.status = "approved"
            await touch_updated(row, user or user_id)
            await row.save()
        from core.services.approval.audit_flow_guard import approval_instance_finished_on_submit

        if approval_instance and approval_instance_finished_on_submit(approval_instance):
            await apply_form_request_decision(
                tenant_id, request_id, True, user_id, is_auto_approve=True
            )
        else:
            from apps.kuaioa.services.kuaioa_form_request_reminder_service import (
                KuaioaFormRequestReminderService,
            )

            row = await KuaioaFormRequest.get_or_none(
                id=request_id, tenant_id=tenant_id, deleted_at__isnull=True
            )
            if row:
                await KuaioaFormRequestReminderService.sync_after_submit(tenant_id, row)
        return await self.get_request(tenant_id, request_id, current_user_id=user_id)

    async def reply_confirmation(
        self,
        tenant_id: int,
        request_id: int,
        data: FormRequestConfirmationReply,
        user: User,
    ) -> dict[str, Any]:
        row = await KuaioaFormRequest.get_or_none(
            id=request_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("申请单不存在")
        if (row.business_type or "").strip().lower() != "confirmation":
            raise BusinessLogicError("仅确认书可销售回答")
        form_data = dict(row.form_data or {})
        if confirmation_kind_from_form_data(form_data) != CONFIRMATION_KIND_COMPLETE_MACHINE:
            raise BusinessLogicError("仅整机确认须销售回答")
        if (row.status or "").strip().lower() != "pending":
            raise BusinessLogicError("仅待审批状态可填写销售回答")
        result = str(data.confirmation_result or "").strip()
        if result not in {"agree", "reject", "conditional"}:
            raise ValidationError("确认结论无效")
        form_data["confirmation_result"] = result
        row.form_data = form_data
        await touch_updated(row, user)
        await row.save()
        return await self.get_request(tenant_id, request_id, current_user_id=user.id)

    async def revoke_request(self, tenant_id: int, request_id: int, user_id: int) -> dict[str, Any]:
        user = await User.get_or_none(id=user_id)
        row = await KuaioaFormRequest.get_or_none(
            id=request_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("申请单不存在")
        if row.status != "pending":
            raise BusinessLogicError("仅待审批状态可撤销")
        await cancel_approval(
            tenant_id,
            entity_type="kuaioa_form_request",
            entity_id=int(row.id),
            operator_id=user_id,
        )
        row.status = "cancelled"
        await touch_updated(row, user or user_id)
        await row.save()
        from apps.kuaioa.services.kuaioa_form_request_reminder_service import (
            KuaioaFormRequestReminderService,
        )

        await KuaioaFormRequestReminderService.sync_after_terminal(
            tenant_id, request_id, reason="已撤销"
        )
        return model_to_dict(row)


async def apply_form_request_decision(
    tenant_id: int,
    request_id: int,
    approved: bool,
    user_id: int,
    *,
    is_auto_approve: bool = False,
) -> None:
    from apps.kuaioa.services.approval_helper import assert_kuaioa_manual_approval_action

    row = await KuaioaFormRequest.get_or_none(
        id=request_id, tenant_id=tenant_id, deleted_at__isnull=True
    )
    if not row:
        return
    await assert_kuaioa_manual_approval_action(
        tenant_id,
        audit_node_key=AUDIT_NODE_FORM_REQUEST,
        entity_type="kuaioa_form_request",
        entity_id=request_id,
        doc_label="自定义申请",
        verb="审核" if approved else "驳回",
        is_auto_approve=is_auto_approve,
    )
    row.status = "approved" if approved else "rejected"
    await touch_updated(row, user_id)
    await row.save()
    if not approved:
        await clear_form_request_issue(tenant_id, request_id)
    from apps.kuaioa.services.kuaioa_form_request_reminder_service import (
        KuaioaFormRequestReminderService,
    )

    await KuaioaFormRequestReminderService.sync_after_terminal(
        tenant_id,
        request_id,
        reason="审核通过" if approved else "已驳回",
    )
