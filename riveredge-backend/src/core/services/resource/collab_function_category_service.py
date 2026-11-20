"""
协同配置三页：按功能域预置 ResourceCategory，并为资源挂靠分类。
"""

from __future__ import annotations

from typing import Dict, Optional, Type

from tortoise.models import Model

from core.config.collab_function_categories import (
    all_function_category_defs,
    resolve_function_category_for_approval_process,
    resolve_function_category_for_message_template,
    resolve_function_category_for_print_template,
)
from core.models.approval_process import ApprovalProcess
from core.models.message_template import MessageTemplate
from core.models.print_template import PrintTemplate
from core.models.resource_category import (
    RESOURCE_TYPE_APPROVAL_PROCESS,
    RESOURCE_TYPE_MESSAGE_TEMPLATE,
    RESOURCE_TYPE_PRINT_TEMPLATE,
    ResourceCategory,
)
from core.services.resource.resource_category_service import ResourceCategoryService
from infra.exceptions.exceptions import ValidationError


class CollabFunctionCategoryService:
    """审批 / 消息 / 打印模板功能域分类预置与回填。"""

    @staticmethod
    def _assert_collab_resource_type(resource_type: str) -> str:
        allowed = {
            RESOURCE_TYPE_APPROVAL_PROCESS,
            RESOURCE_TYPE_MESSAGE_TEMPLATE,
            RESOURCE_TYPE_PRINT_TEMPLATE,
        }
        normalized = str(resource_type or "").strip()
        if normalized not in allowed:
            raise ValidationError(
                f"仅支持 {sorted(allowed)} 的功能域分类预置，收到: {resource_type!r}"
            )
        return normalized

    @staticmethod
    def _model_for(resource_type: str) -> Type[Model]:
        if resource_type == RESOURCE_TYPE_APPROVAL_PROCESS:
            return ApprovalProcess
        if resource_type == RESOURCE_TYPE_MESSAGE_TEMPLATE:
            return MessageTemplate
        return PrintTemplate

    async def ensure_function_categories(
        self,
        tenant_id: int,
        resource_type: str,
    ) -> int:
        """创建缺失的功能域分类，返回本次新建数量。"""
        resource_type = self._assert_collab_resource_type(resource_type)
        svc = ResourceCategoryService()
        created = 0
        for item in all_function_category_defs():
            before = await ResourceCategory.filter(
                tenant_id=tenant_id,
                resource_type=resource_type,
                code=item.code,
                deleted_at__isnull=True,
            ).exists()
            if before:
                continue
            await svc.ensure_category_by_code(
                tenant_id,
                resource_type,
                code=item.code,
                name=item.name,
                description=item.description,
                sort_order=item.sort_order,
            )
            created += 1
        return created

    async def _category_id_map(
        self,
        tenant_id: int,
        resource_type: str,
    ) -> Dict[str, int]:
        await self.ensure_function_categories(tenant_id, resource_type)
        rows = await ResourceCategory.filter(
            tenant_id=tenant_id,
            resource_type=resource_type,
            deleted_at__isnull=True,
        ).all()
        return {row.code: row.id for row in rows}

    async def resolve_category_id_for_approval(
        self,
        tenant_id: int,
        process_code: Optional[str],
    ) -> Optional[int]:
        code = resolve_function_category_for_approval_process(process_code)
        id_map = await self._category_id_map(tenant_id, RESOURCE_TYPE_APPROVAL_PROCESS)
        return id_map.get(code)

    async def resolve_category_id_for_message(
        self,
        tenant_id: int,
        template_code: Optional[str],
    ) -> Optional[int]:
        code = resolve_function_category_for_message_template(template_code)
        id_map = await self._category_id_map(tenant_id, RESOURCE_TYPE_MESSAGE_TEMPLATE)
        return id_map.get(code)

    async def resolve_category_id_for_print(
        self,
        tenant_id: int,
        *,
        document_type: Optional[str],
        template_code: Optional[str] = None,
    ) -> Optional[int]:
        code = resolve_function_category_for_print_template(
            document_type=document_type,
            code=template_code,
        )
        id_map = await self._category_id_map(tenant_id, RESOURCE_TYPE_PRINT_TEMPLATE)
        return id_map.get(code)

    async def backfill_resource_categories(
        self,
        tenant_id: int,
        resource_type: str,
    ) -> int:
        """为未分类条目按功能域规则写入 category_id。"""
        resource_type = self._assert_collab_resource_type(resource_type)
        id_map = await self._category_id_map(tenant_id, resource_type)
        model = self._model_for(resource_type)
        rows = await model.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            category_id__isnull=True,
        ).all()
        updated = 0
        for row in rows:
            category_code: Optional[str] = None
            if resource_type == RESOURCE_TYPE_APPROVAL_PROCESS:
                category_code = resolve_function_category_for_approval_process(
                    getattr(row, "code", None)
                )
            elif resource_type == RESOURCE_TYPE_MESSAGE_TEMPLATE:
                category_code = resolve_function_category_for_message_template(
                    getattr(row, "code", None)
                )
            else:
                config = getattr(row, "config", None) or {}
                doc_type = config.get("document_type") if isinstance(config, dict) else None
                category_code = resolve_function_category_for_print_template(
                    document_type=doc_type,
                    code=getattr(row, "code", None),
                )
            category_id = id_map.get(category_code or "common")
            if category_id is None:
                continue
            row.category_id = category_id
            await row.save(update_fields=["category_id", "updated_at"])
            updated += 1
        return updated

    async def load_function_presets(
        self,
        tenant_id: int,
        resource_type: str,
    ) -> Dict[str, int]:
        """预置功能域分类并回填未分类条目。"""
        resource_type = self._assert_collab_resource_type(resource_type)
        categories_created = await self.ensure_function_categories(tenant_id, resource_type)
        items_categorized = await self.backfill_resource_categories(tenant_id, resource_type)
        return {
            "categories_created": categories_created,
            "items_categorized": items_categorized,
        }
