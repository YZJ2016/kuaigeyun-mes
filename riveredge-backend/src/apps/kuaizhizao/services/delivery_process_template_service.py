"""交付流程模板服务

契约：模板节点可挂预置子任务；创建交付项目时由 project service 派生为节点任务实例。
子任务负责人与成员可在模板预置（可选），未填时在项目工作台补全。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Any, Dict, List, Optional

from tortoise.transactions import in_transaction

from apps.common.audit_actor import apply_create_audit, apply_update_audit
from apps.common.base_service import AppBaseService
from apps.kuaizhizao.constants.delivery_project import DEFAULT_DELIVERY_PROCESS_NODES
from apps.kuaizhizao.models.delivery_project import (
    DeliveryProcessTemplate,
    DeliveryProcessTemplateNode,
    DeliveryProcessTemplateNodeTask,
)
from apps.kuaizhizao.schemas.delivery_project import (
    DeliveryMemberInput,
    DeliveryMemberResponse,
    DeliveryProcessTemplateCreate,
    DeliveryProcessTemplateListEnvelope,
    DeliveryProcessTemplateNodeCreate,
    DeliveryProcessTemplateNodeResponse,
    DeliveryProcessTemplateNodeTaskResponse,
    DeliveryProcessTemplateResponse,
    DeliveryProcessTemplateUpdate,
)
from core.utils.timezone_utils import resolve_business_datetime, today_site_str
from infra.exceptions.exceptions import NotFoundError, ValidationError
from infra.models.user import User


class DeliveryProcessTemplateService(AppBaseService[DeliveryProcessTemplate]):
    def __init__(self):
        super().__init__(DeliveryProcessTemplate)

    async def _generate_template_code(self, tenant_id: int) -> str:
        try:
            return await self.generate_code(
                tenant_id,
                "DELIVERY_PROCESS_TEMPLATE_CODE",
                prefix=f"DPT{today_site_str()}",
            )
        except Exception:
            import uuid

            return f"DPT{today_site_str()}{uuid.uuid4().hex[:4].upper()}"

    async def _get_or_404(self, tenant_id: int, template_id: int) -> DeliveryProcessTemplate:
        row = await DeliveryProcessTemplate.get_or_none(
            tenant_id=tenant_id, id=template_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError(f"流程模板不存在: {template_id}")
        return row

    async def _load_nodes(self, tenant_id: int, template_id: int) -> List[DeliveryProcessTemplateNode]:
        return await DeliveryProcessTemplateNode.filter(
            tenant_id=tenant_id, template_id=template_id
        ).order_by("sort_order", "id")

    @staticmethod
    def _serialize_template_task_members(
        members: Optional[List[DeliveryMemberInput]],
        owner_id: Optional[int] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        if not members:
            return None
        payload: List[Dict[str, Any]] = []
        seen: set[int] = set()
        for item in members:
            if not item.user_id or item.user_id in seen:
                continue
            if owner_id and item.user_id == owner_id:
                continue
            seen.add(item.user_id)
            payload.append(
                {
                    "user_id": item.user_id,
                    "user_name": (item.user_name or "").strip() or str(item.user_id),
                }
            )
        return payload or None

    @staticmethod
    def _parse_template_task_members(raw: Any) -> List[DeliveryMemberResponse]:
        if not isinstance(raw, list):
            return []
        members: List[DeliveryMemberResponse] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            user_id = item.get("user_id")
            if not user_id:
                continue
            members.append(
                DeliveryMemberResponse(
                    user_id=int(user_id),
                    user_name=str(item.get("user_name") or user_id),
                )
            )
        return members

    def _task_to_response(
        self, task: DeliveryProcessTemplateNodeTask
    ) -> DeliveryProcessTemplateNodeTaskResponse:
        return DeliveryProcessTemplateNodeTaskResponse(
            id=task.id,
            template_node_id=task.template_node_id,
            task_key=task.task_key,
            task_name=task.task_name,
            core_task=getattr(task, "core_task", None),
            sort_order=task.sort_order,
            default_owner_role=task.default_owner_role,
            owner_id=getattr(task, "owner_id", None),
            owner_name=getattr(task, "owner_name", None),
            members=self._parse_template_task_members(getattr(task, "members_json", None)),
            planned_duration_days=task.planned_duration_days,
            track_mode=getattr(task, "track_mode", None) or "progress",
            participant_mode=getattr(task, "participant_mode", None) or "solo",
        )

    async def _load_tasks_by_node(
        self, tenant_id: int, node_ids: List[int]
    ) -> Dict[int, List[DeliveryProcessTemplateNodeTask]]:
        if not node_ids:
            return {}
        rows = await DeliveryProcessTemplateNodeTask.filter(
            tenant_id=tenant_id, template_node_id__in=node_ids
        ).order_by("sort_order", "id")
        by_node: Dict[int, List[DeliveryProcessTemplateNodeTask]] = defaultdict(list)
        for row in rows:
            by_node[row.template_node_id].append(row)
        return by_node

    async def _replace_nodes(
        self,
        tenant_id: int,
        template_id: int,
        nodes: List[DeliveryProcessTemplateNodeCreate],
    ) -> None:
        existing_nodes = await DeliveryProcessTemplateNode.filter(
            tenant_id=tenant_id, template_id=template_id
        )
        existing_ids = [n.id for n in existing_nodes]
        if existing_ids:
            await DeliveryProcessTemplateNodeTask.filter(
                tenant_id=tenant_id, template_node_id__in=existing_ids
            ).delete()
        await DeliveryProcessTemplateNode.filter(
            tenant_id=tenant_id, template_id=template_id
        ).delete()
        for idx, node in enumerate(nodes):
            created = await DeliveryProcessTemplateNode.create(
                tenant_id=tenant_id,
                template_id=template_id,
                node_key=node.node_key,
                node_name=node.node_name,
                sort_order=node.sort_order if node.sort_order else idx + 1,
                default_owner_role=node.default_owner_role,
                planned_duration_days=node.planned_duration_days,
                schedule_group=(node.schedule_group or "").strip() or None,
                duration_rules=self._normalize_duration_rules(
                    getattr(node, "duration_rules", None)
                ),
                is_critical=node.is_critical,
                is_milestone=node.is_milestone,
            )
            for t_idx, task in enumerate(node.tasks or []):
                owner_id = getattr(task, "owner_id", None)
                owner_name = (getattr(task, "owner_name", None) or "").strip() or None
                members_json = self._serialize_template_task_members(
                    getattr(task, "members", None), owner_id=owner_id
                )
                await DeliveryProcessTemplateNodeTask.create(
                    tenant_id=tenant_id,
                    template_node_id=created.id,
                    task_key=task.task_key or f"task_{t_idx + 1}",
                    task_name=task.task_name,
                    core_task=(getattr(task, "core_task", None) or "").strip() or None,
                    sort_order=task.sort_order if task.sort_order else t_idx + 1,
                    default_owner_role=task.default_owner_role,
                    owner_id=owner_id,
                    owner_name=owner_name,
                    members_json=members_json,
                    planned_duration_days=task.planned_duration_days or 0,
                    track_mode=getattr(task, "track_mode", None) or "progress",
                    participant_mode=getattr(task, "participant_mode", None) or "solo",
                )

    async def _to_response(
        self, template: DeliveryProcessTemplate, nodes: Optional[List[DeliveryProcessTemplateNode]] = None
    ) -> DeliveryProcessTemplateResponse:
        if nodes is None:
            nodes = await self._load_nodes(template.tenant_id, template.id)
        tasks_by_node = await self._load_tasks_by_node(
            template.tenant_id, [n.id for n in nodes]
        )
        node_payloads: List[DeliveryProcessTemplateNodeResponse] = []
        for n in nodes:
            node_payloads.append(
                DeliveryProcessTemplateNodeResponse(
                    id=n.id,
                    template_id=n.template_id,
                    node_key=n.node_key,
                    node_name=n.node_name,
                    sort_order=n.sort_order,
                    default_owner_role=n.default_owner_role,
                    planned_duration_days=n.planned_duration_days,
                    schedule_group=getattr(n, "schedule_group", None),
                    duration_rules=getattr(n, "duration_rules", None),
                    is_critical=n.is_critical,
                    is_milestone=n.is_milestone,
                    tasks=[
                        self._task_to_response(t) for t in tasks_by_node.get(n.id, [])
                    ],
                )
            )
        return DeliveryProcessTemplateResponse(
            id=template.id,
            template_code=template.template_code,
            template_name=template.template_name,
            project_type=template.project_type,
            is_active=template.is_active,
            is_default=template.is_default,
            notes=template.notes,
            nodes=node_payloads,
            created_at=template.created_at,
            updated_at=template.updated_at,
        )

    async def ensure_default_template(self, tenant_id: int, current_user: User) -> DeliveryProcessTemplate:
        existing = await DeliveryProcessTemplate.filter(
            tenant_id=tenant_id, is_default=True, deleted_at__isnull=True
        ).first()
        if existing:
            return existing
        body = DeliveryProcessTemplateCreate(
            template_name="标准订单交机流程",
            project_type="ETO",
            is_active=True,
            nodes=[DeliveryProcessTemplateNodeCreate(**n) for n in DEFAULT_DELIVERY_PROCESS_NODES],
        )
        created = await self.create_template(tenant_id, body, current_user, set_default=True)
        return await self._get_or_404(tenant_id, created.id)

    async def create_template(
        self,
        tenant_id: int,
        body: DeliveryProcessTemplateCreate,
        current_user: User,
        *,
        set_default: bool = False,
    ) -> DeliveryProcessTemplateResponse:
        if not body.nodes:
            raise ValidationError("流程模板至少需要一个节点")
        async with in_transaction():
            code = await self._generate_template_code(tenant_id)
            row = DeliveryProcessTemplate(
                tenant_id=tenant_id,
                template_code=code,
                template_name=body.template_name.strip(),
                project_type=body.project_type,
                is_active=body.is_active,
                is_default=set_default,
                notes=body.notes,
            )
            apply_create_audit(row, current_user)
            await row.save()
            if set_default:
                await DeliveryProcessTemplate.filter(
                    tenant_id=tenant_id, deleted_at__isnull=True
                ).exclude(id=row.id).update(is_default=False)
            await self._replace_nodes(tenant_id, row.id, body.nodes)
        return await self._to_response(row)

    async def list_templates(
        self,
        tenant_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
        active_only: bool = False,
        keyword: Optional[str] = None,
    ) -> DeliveryProcessTemplateListEnvelope:
        qs = DeliveryProcessTemplate.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if active_only:
            qs = qs.filter(is_active=True)
        if keyword:
            qs = qs.filter(template_name__icontains=keyword.strip())
        total = await qs.count()
        rows = await qs.order_by("-is_default", "template_name").offset(skip).limit(limit)
        items = [await self._to_response(r) for r in rows]
        return DeliveryProcessTemplateListEnvelope(items=items, total=total)

    async def get_template(self, tenant_id: int, template_id: int) -> DeliveryProcessTemplateResponse:
        row = await self._get_or_404(tenant_id, template_id)
        return await self._to_response(row)

    async def update_template(
        self,
        tenant_id: int,
        template_id: int,
        body: DeliveryProcessTemplateUpdate,
        current_user: User,
    ) -> DeliveryProcessTemplateResponse:
        row = await self._get_or_404(tenant_id, template_id)
        async with in_transaction():
            if body.template_name is not None:
                row.template_name = body.template_name.strip()
            if body.project_type is not None:
                row.project_type = body.project_type
            if body.is_active is not None:
                row.is_active = body.is_active
            if body.notes is not None:
                row.notes = body.notes
            apply_update_audit(row, current_user)
            await row.save()
            if body.nodes is not None:
                if not body.nodes:
                    raise ValidationError("流程模板至少需要一个节点")
                await self._replace_nodes(tenant_id, template_id, body.nodes)
        return await self._to_response(row)

    async def delete_template(self, tenant_id: int, template_id: int, current_user: User) -> None:
        row = await self._get_or_404(tenant_id, template_id)
        if row.is_default:
            raise ValidationError("默认模板不可删除")
        row.deleted_at = resolve_business_datetime()
        apply_update_audit(row, current_user)
        await row.save()

    async def set_default(self, tenant_id: int, template_id: int, current_user: User) -> DeliveryProcessTemplateResponse:
        row = await self._get_or_404(tenant_id, template_id)
        async with in_transaction():
            await DeliveryProcessTemplate.filter(
                tenant_id=tenant_id, deleted_at__isnull=True
            ).update(is_default=False)
            row.is_default = True
            row.is_active = True
            apply_update_audit(row, current_user)
            await row.save()
        return await self._to_response(row)

    @staticmethod
    def _normalize_duration_rules(raw) -> Optional[dict]:
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ValidationError("节点 duration_rules 必须为对象")
        attr_key = raw.get("attr_key")
        days_by_value = raw.get("days_by_value")
        if not attr_key or not isinstance(attr_key, str) or not attr_key.strip():
            raise ValidationError("duration_rules.attr_key 必填")
        if not isinstance(days_by_value, dict) or not days_by_value:
            raise ValidationError("duration_rules.days_by_value 须为非空对象")
        normalized: Dict[str, int] = {}
        for key, days in days_by_value.items():
            k = str(key).strip()
            if not k:
                raise ValidationError("duration_rules.days_by_value 键不可为空")
            try:
                d = int(days)
            except (TypeError, ValueError) as exc:
                raise ValidationError(f"duration_rules 型号 {k} 工期无效") from exc
            if d < 0:
                raise ValidationError(f"duration_rules 型号 {k} 工期不可为负")
            normalized[k] = d
        return {"attr_key": attr_key.strip(), "days_by_value": normalized}

    @staticmethod
    def resolve_node_duration_days(node: DeliveryProcessTemplateNode, config_attrs=None) -> int:
        """按产品型号规则解析节点工期；无匹配则用 planned_duration_days。"""
        base = max(int(node.planned_duration_days or 0), 0)
        rules = getattr(node, "duration_rules", None)
        if not isinstance(rules, dict):
            return base
        attr_key = rules.get("attr_key")
        days_by_value = rules.get("days_by_value")
        if not attr_key or not isinstance(days_by_value, dict):
            return base
        attrs = config_attrs if isinstance(config_attrs, dict) else {}
        raw_val = attrs.get(attr_key)
        if raw_val is None or raw_val == "":
            return base
        product_model = str(raw_val).strip()
        if product_model not in days_by_value:
            raise ValidationError(
                f"节点 {node.node_key} 未配置产品型号 {product_model} 的工期，请补全 duration_rules 或修改项目配置"
            )
        return max(int(days_by_value[product_model]), 0)

    @staticmethod
    def _node_schedule_group(node: DeliveryProcessTemplateNode) -> str:
        return (getattr(node, "schedule_group", None) or "").strip()

    @staticmethod
    def compute_node_planned_dates(
        start_date,
        template_nodes: List[DeliveryProcessTemplateNode],
        config_attrs=None,
    ):
        """按模板工期排计划；同一 schedule_group 内节点并行（同起点，下游按组内最长工期推进）。"""
        ordered = sorted(template_nodes, key=lambda n: (n.sort_order or 0, n.id or 0))
        cursor = start_date
        result = []
        i = 0
        while i < len(ordered):
            node = ordered[i]
            group = DeliveryProcessTemplateService._node_schedule_group(node)
            if group:
                group_nodes = [node]
                j = i + 1
                while j < len(ordered):
                    if DeliveryProcessTemplateService._node_schedule_group(ordered[j]) != group:
                        break
                    group_nodes.append(ordered[j])
                    j += 1
                group_start = cursor
                group_max_end = group_start
                max_duration = 0
                for group_node in group_nodes:
                    duration = DeliveryProcessTemplateService.resolve_node_duration_days(
                        group_node, config_attrs
                    )
                    max_duration = max(max_duration, duration)
                    node_end = group_start + timedelta(days=duration) if duration else group_start
                    if node_end > group_max_end:
                        group_max_end = node_end
                    result.append((group_node, group_start, node_end))
                if max_duration > 0:
                    cursor = group_max_end + timedelta(days=1)
                else:
                    cursor = group_max_end
                i = j
                continue

            duration = DeliveryProcessTemplateService.resolve_node_duration_days(
                node, config_attrs
            )
            node_start = cursor
            node_end = node_start + timedelta(days=duration) if duration else node_start
            result.append((node, node_start, node_end))
            if duration > 0:
                cursor = node_end + timedelta(days=1)
            else:
                cursor = node_end
            i += 1
        return result
