"""
设备故障维修服务模块

提供设备故障和维修记录的 CRUD 操作。

Author: Luigi Lu
Date: 2026-01-05
"""

from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q
from loguru import logger

from apps.kuaizhizao.models.equipment_fault import (
    EquipmentFault,
    EquipmentRepair,
    EquipmentRepairParticipant,
)
from apps.kuaizhizao.models.equipment import Equipment
from apps.kuaizhizao.schemas.equipment import EQUIPMENT_STATUS_PROTECTED
from apps.kuaizhizao.services.spare_part_service import SparePartService
from apps.kuaizhizao.schemas.equipment_fault import (
    EquipmentFaultArriveRequest,
    EquipmentFaultCreate,
    EquipmentFaultUpdate,
    EquipmentRepairAddCollaboratorRequest,
    EquipmentRepairCompleteRequest,
    EquipmentRepairCreate,
    EquipmentRepairParticipantResponse,
    EquipmentRepairReassignRequest,
    EquipmentRepairResponse,
    EquipmentRepairUpdate,
)
from apps.common.audit_actor import apply_create_audit, apply_update_audit
from core.services.business.code_generation_service import CodeGenerationService
from infra.exceptions.exceptions import NotFoundError, ValidationError
from infra.models.user import User
from core.utils.timezone_utils import resolve_business_datetime


async def _find_open_repair_for_fault(
    tenant_id: int,
    *,
    fault_id: Optional[int] = None,
    fault_uuid: Optional[str] = None,
) -> Optional[EquipmentRepair]:
    """同一故障仅允许一张进行中维修单：按故障 id / uuid 查找最新进行中记录。"""
    if not fault_id and not fault_uuid:
        return None
    clauses = []
    if fault_id:
        clauses.append(Q(equipment_fault_id=int(fault_id)))
    if fault_uuid:
        clauses.append(Q(equipment_fault_uuid=str(fault_uuid)))
    fault_q = clauses[0]
    for extra in clauses[1:]:
        fault_q |= extra
    return (
        await EquipmentRepair.filter(
            fault_q,
            tenant_id=tenant_id,
            status="进行中",
            deleted_at__isnull=True,
        )
        .order_by("-id")
        .first()
    )


async def _inherit_arrival_from_sibling_repair(
    tenant_id: int,
    repair: EquipmentRepair,
) -> bool:
    """历史重复单：完修前从同故障已签到维修单继承到场信息。"""
    if repair.arrival_at:
        return False
    fault_id = getattr(repair, "equipment_fault_id", None)
    fault_uuid = getattr(repair, "equipment_fault_uuid", None)
    if not fault_id and not fault_uuid:
        return False
    fault_clauses = []
    if fault_id:
        fault_clauses.append(Q(equipment_fault_id=int(fault_id)))
    if fault_uuid:
        fault_clauses.append(Q(equipment_fault_uuid=str(fault_uuid)))
    fault_q = fault_clauses[0]
    for extra in fault_clauses[1:]:
        fault_q |= extra
    sibling = (
        await EquipmentRepair.filter(
            fault_q,
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            arrival_at__isnull=False,
        )
        .exclude(id=repair.id)
        .order_by("-arrival_at", "-id")
        .first()
    )
    if not sibling or not sibling.arrival_at:
        return False
    repair.arrival_at = sibling.arrival_at
    repair.arrival_by_id = sibling.arrival_by_id
    repair.arrival_by_name = sibling.arrival_by_name
    return True

_OPEN_FAULT_STATUSES = ("待处理", "处理中")
DEFAULT_RESPONSE_MINUTES = 60
_ROLE_PRIMARY = "主责"
_ROLE_COLLAB = "协作"
_PART_ACTIVE = "进行中"
_PART_REASSIGNED = "已转派"
_PART_DONE = "已完成"
_PART_LEFT = "已退出"


async def _resolve_user_display(
    tenant_id: int, user_id: int
) -> tuple[User, str]:
    user = await User.filter(id=user_id, tenant_id=tenant_id).first()
    if not user:
        raise ValidationError(f"用户不存在: {user_id}")
    name = (user.full_name or user.username or "").strip() or f"用户{user_id}"
    return user, name


async def _list_repair_participants(
    tenant_id: int, repair_id: int
) -> list[EquipmentRepairParticipant]:
    return (
        await EquipmentRepairParticipant.filter(
            tenant_id=tenant_id,
            repair_id=repair_id,
            deleted_at__isnull=True,
        )
        .order_by("joined_at", "id")
        .all()
    )


async def serialize_equipment_repair(
    tenant_id: int, repair: EquipmentRepair
) -> EquipmentRepairResponse:
    parts = await _list_repair_participants(tenant_id, repair.id)
    base = EquipmentRepairResponse.model_validate(repair)
    return base.model_copy(
        update={
            "participants": [
                EquipmentRepairParticipantResponse.model_validate(p) for p in parts
            ]
        }
    )


async def _ensure_started_at(repair: EquipmentRepair, when: datetime) -> bool:
    if repair.started_at:
        return False
    repair.started_at = when
    return True


async def _ensure_primary_participant(
    tenant_id: int,
    repair: EquipmentRepair,
    *,
    user_id: Optional[int],
    user_name: Optional[str],
    joined_at: datetime,
    actor: Optional[User] = None,
) -> Optional[EquipmentRepairParticipant]:
    """接取/到场时确保主责参与人；已有进行中主责则不重复建。"""
    if not user_id:
        return None
    existing = await EquipmentRepairParticipant.filter(
        tenant_id=tenant_id,
        repair_id=repair.id,
        role=_ROLE_PRIMARY,
        status=_PART_ACTIVE,
        deleted_at__isnull=True,
    ).first()
    if existing:
        return existing
    name = (user_name or "").strip()
    if not name:
        _, name = await _resolve_user_display(tenant_id, int(user_id))
    row = EquipmentRepairParticipant(
        tenant_id=tenant_id,
        repair_id=repair.id,
        repair_uuid=repair.uuid,
        user_id=int(user_id),
        user_name=name,
        role=_ROLE_PRIMARY,
        status=_PART_ACTIVE,
        joined_at=joined_at,
    )
    apply_create_audit(row, actor)
    await row.save()
    return row


async def _finalize_active_participants(
    tenant_id: int,
    repair_id: int,
    *,
    left_at: datetime,
    actor: Optional[User] = None,
) -> None:
    rows = await EquipmentRepairParticipant.filter(
        tenant_id=tenant_id,
        repair_id=repair_id,
        status=_PART_ACTIVE,
        deleted_at__isnull=True,
    ).all()
    for row in rows:
        row.status = _PART_DONE
        row.left_at = left_at
        apply_update_audit(row, actor)
        await row.save()


async def _bootstrap_repair_participation(
    tenant_id: int,
    repair: EquipmentRepair,
    *,
    user_id: Optional[int],
    user_name: Optional[str],
    when: Optional[datetime] = None,
    actor: Optional[User] = None,
) -> None:
    """接取/创建维修：记录开始时间并确保主责参与人。"""
    now = when or resolve_business_datetime()
    changed = await _ensure_started_at(repair, now)
    if changed:
        await repair.save()
    await _ensure_primary_participant(
        tenant_id,
        repair,
        user_id=user_id,
        user_name=user_name,
        joined_at=now,
        actor=actor,
    )


async def sync_equipment_status_from_faults(
    tenant_id: int,
    equipment_id: int,
) -> Optional[str]:
    """
    按未闭环故障 / 进行中维修同步设备主数据状态（唯一真源）。

    规则：
    - 当前状态为停用/报废/校验中 → 不动
    - 存在进行中维修 → 维修中
    - 否则存在待处理/处理中故障 → 故障
    - 否则 → 正常
    """
    equipment = await Equipment.filter(
        tenant_id=tenant_id,
        id=equipment_id,
        deleted_at__isnull=True,
    ).first()
    if not equipment:
        return None
    current = str(equipment.status or "")
    if current in EQUIPMENT_STATUS_PROTECTED:
        return current

    has_active_repair = await EquipmentRepair.filter(
        tenant_id=tenant_id,
        equipment_id=equipment_id,
        status="进行中",
        deleted_at__isnull=True,
    ).exists()
    if has_active_repair:
        target = "维修中"
    else:
        has_open_fault = await EquipmentFault.filter(
            tenant_id=tenant_id,
            equipment_id=equipment_id,
            status__in=list(_OPEN_FAULT_STATUSES),
            deleted_at__isnull=True,
        ).exists()
        target = "故障" if has_open_fault else "正常"

    if current != target:
        equipment.status = target
        await equipment.save()
        logger.info(
            "equipment_status_synced_from_faults tenant_id={} equipment_id={} {} -> {}",
            tenant_id,
            equipment_id,
            current,
            target,
        )
    return target


class EquipmentFaultService:
    """
    设备故障记录服务类
    
    提供设备故障记录的 CRUD 操作。
    """
    
    @staticmethod
    async def create_equipment_fault(
        tenant_id: int,
        data: EquipmentFaultCreate,
        created_by: Optional[int] = None
    ) -> EquipmentFault:
        """
        创建设备故障记录
        
        Args:
            tenant_id: 组织ID
            data: 设备故障记录创建数据
            created_by: 创建人ID（可选）
            
        Returns:
            EquipmentFault: 创建设备故障记录对象
            
        Raises:
            ValidationError: 当设备不存在或故障记录编号已存在时抛出
        """
        try:
            # 验证设备是否存在
            equipment = await Equipment.filter(
                tenant_id=tenant_id,
                uuid=data.equipment_uuid,
                deleted_at__isnull=True
            ).first()
            
            if not equipment:
                raise ValidationError(f"设备不存在: {data.equipment_uuid}")
            if str(equipment.status or "") in EQUIPMENT_STATUS_PROTECTED:
                raise ValidationError(
                    f"设备当前为「{equipment.status}」，不能登记故障；请先通过状态变更/反报废恢复后再报修"
                )
            open_fault = await EquipmentFault.filter(
                tenant_id=tenant_id,
                equipment_id=equipment.id,
                status__in=list(_OPEN_FAULT_STATUSES),
                deleted_at__isnull=True,
            ).first()
            if open_fault:
                raise ValidationError(
                    f"设备已有未闭环报修单 {open_fault.fault_no}（{open_fault.status}），"
                    "请先完修或关闭后再新建"
                )

            # 如果没有提供故障记录编号，自动生成
            if not data.fault_no:
                try:
                    data.fault_no = await CodeGenerationService.generate_code(
                        tenant_id=tenant_id,
                        rule_code="equipment_fault_code",
                        context=None
                    )
                except ValidationError:
                    # 如果编码规则不存在，使用默认编码格式
                    timestamp = resolve_business_datetime().strftime("%Y%m%d%H%M%S")
                    data.fault_no = f"FT{timestamp}"

            reported_at = resolve_business_datetime()
            response_minutes = int(data.response_minutes or DEFAULT_RESPONSE_MINUTES)
            from apps.kuaizhizao.services.equipment_fault_reminder_service import (
                EquipmentFaultReminderService,
                compute_response_due_at,
            )

            response_due_at = compute_response_due_at(reported_at, response_minutes)
            
            fault = EquipmentFault(
                tenant_id=tenant_id,
                equipment_id=equipment.id,
                equipment_uuid=equipment.uuid,
                equipment_code=equipment.code,
                equipment_name=equipment.name,
                reported_at=reported_at,
                response_minutes=response_minutes,
                response_due_at=response_due_at,
                **data.model_dump(
                    exclude_none=True,
                    exclude={"equipment_uuid", "response_minutes", "fault_date"},
                ),
                fault_date=reported_at,
            )
            reporter = None
            if created_by:
                reporter = await User.filter(id=created_by, tenant_id=tenant_id).first()
            if reporter and not fault.reporter_id:
                fault.reporter_id = reporter.id
                fault.reporter_name = fault.reporter_name or reporter.full_name or reporter.username
            apply_create_audit(fault, reporter)
            await fault.save()

            if fault.status in _OPEN_FAULT_STATUSES and fault.repair_required:
                await EquipmentFaultReminderService.on_fault_reported(
                    tenant_id,
                    fault,
                    due_at=response_due_at,
                )

            from apps.kuaizhizao.services.equipment_mobile_notification import notify_equipment_fault_reported

            try:
                await notify_equipment_fault_reported(
                    tenant_id=tenant_id,
                    fault=fault,
                    reporter=reporter,
                )
            except Exception as exc:
                logger.warning("设备报修通知派发失败 tenant={}: {}", tenant_id, exc)

            await sync_equipment_status_from_faults(tenant_id, equipment.id)
            return fault
        except IntegrityError:
            raise ValidationError(f"设备故障记录编号 {data.fault_no} 已存在")

    @staticmethod
    async def arrive_at_fault(
        tenant_id: int,
        fault_uuid: str,
        data: EquipmentFaultArriveRequest,
        *,
        operator: Optional[User] = None,
    ) -> EquipmentRepair:
        """到场扫码签到：校验设备一致，写入到达人与时间，解除到场超时提醒。"""
        fault = await EquipmentFaultService.get_equipment_fault_by_uuid(tenant_id, fault_uuid)
        if fault.status in ("已修复", "已关闭"):
            raise ValidationError("故障已关闭，无法到场签到")
        scanned = (data.equipment_uuid or "").strip()
        if scanned != fault.equipment_uuid:
            raise ValidationError("扫码设备与故障设备不一致，请扫描本故障设备二维码")

        repair = await _find_open_repair_for_fault(
            tenant_id, fault_id=fault.id, fault_uuid=fault.uuid
        )
        now = resolve_business_datetime()
        operator_name = (
            (data.repairer_name or "").strip()
            or (operator.full_name if operator else None)
            or (operator.username if operator else None)
            or ""
        )
        if repair and repair.arrival_at:
            raise ValidationError("本故障已完成到场签到")

        if not operator or not operator.id:
            raise ValidationError("须登录后再到场签到")
        if not repair:
            create_data = EquipmentRepairCreate(
                equipment_uuid=fault.equipment_uuid,
                equipment_fault_uuid=fault.uuid,
                repair_date=now,
                repair_type=(data.repair_type or "现场维修").strip() or "现场维修",
                repair_description=fault.fault_description or "到场签到",
                repairer_id=int(operator.id),
                repairer_name=operator_name or None,
                status="进行中",
            )
            # 直接建单，避免走 create 内「复用进行中单」分支（此处本就没有）
            repair = await EquipmentRepairService.create_equipment_repair(
                tenant_id=tenant_id,
                data=create_data,
                created_by=operator.id if operator else None,
            )

        repair.arrival_at = now
        repair.arrival_by_id = operator.id if operator else None
        repair.arrival_by_name = operator_name or None
        if not repair.started_at:
            repair.started_at = now
        if operator and not repair.repairer_id:
            repair.repairer_id = operator.id
            repair.repairer_name = repair.repairer_name or operator_name
        apply_update_audit(repair, operator)
        await repair.save()
        if operator:
            await _ensure_primary_participant(
                tenant_id,
                repair,
                user_id=operator.id,
                user_name=operator_name or repair.repairer_name,
                joined_at=now,
                actor=operator,
            )

        from apps.kuaizhizao.services.equipment_fault_reminder_service import (
            EquipmentFaultReminderService,
        )

        await EquipmentFaultReminderService.stop_arrival_reminders(
            tenant_id,
            fault.id,
            reason="已到场签到",
        )
        if fault.status == "待处理":
            fault.status = "处理中"
            apply_update_audit(fault, operator)
            await fault.save()
        await sync_equipment_status_from_faults(tenant_id, fault.equipment_id)
        return repair
    
    @staticmethod
    async def get_equipment_fault_by_uuid(
        tenant_id: int,
        uuid: str
    ) -> EquipmentFault:
        """
        根据UUID获取设备故障记录
        
        Args:
            tenant_id: 组织ID
            uuid: 设备故障记录UUID
            
        Returns:
            EquipmentFault: 设备故障记录对象
            
        Raises:
            NotFoundError: 当设备故障记录不存在时抛出
        """
        fault = await EquipmentFault.filter(
            tenant_id=tenant_id,
            uuid=uuid,
            deleted_at__isnull=True
        ).first()
        
        if not fault:
            raise NotFoundError("设备故障记录不存在")
        
        return fault
    
    @staticmethod
    async def list_equipment_faults(
        tenant_id: int,
        skip: int = 0,
        limit: int = 100,
        equipment_uuid: Optional[str] = None,
        status: Optional[str] = None,
        fault_type: Optional[str] = None,
        search: Optional[str] = None,
        keyword: Optional[str] = None,
        order_by: Optional[str] = None,
        fault_start_date: Optional[str] = None,
        fault_end_date: Optional[str] = None,
        created_start_date: Optional[str] = None,
        created_end_date: Optional[str] = None,
        uuid: Optional[str] = None,
    ) -> tuple[List[EquipmentFault], int]:
        """
        获取设备故障记录列表
        
        Args:
            tenant_id: 组织ID
            skip: 跳过数量
            limit: 限制数量
            equipment_uuid: 设备UUID（可选）
            status: 故障状态（可选）
            fault_type: 故障类型（可选）
            search: 搜索关键词（可选，搜索故障记录编号）
            
        Returns:
            tuple[List[EquipmentFault], int]: 设备故障记录列表和总数量
        """
        query = EquipmentFault.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True
        )
        
        # 筛选条件
        if equipment_uuid:
            query = query.filter(equipment_uuid=equipment_uuid)
        if status:
            query = query.filter(status=status)
        if fault_type:
            query = query.filter(fault_type=fault_type)
        if uuid:
            query = query.filter(uuid=uuid.strip())

        from apps.kuaizhizao.services.equipment_list_core import (
            EQUIPMENT_FAULT_SORTABLE_FIELDS,
            apply_equipment_created_date_range,
            apply_equipment_document_date_range,
            apply_equipment_keyword_filter,
            pick_search_keyword,
            resolve_equipment_list_order_by,
        )

        query = apply_equipment_keyword_filter(
            query,
            pick_search_keyword(keyword, search),
            ["fault_no", "equipment_code", "equipment_name", "fault_description"],
        )
        query = apply_equipment_document_date_range(
            query,
            date_field="fault_date",
            start_date=fault_start_date,
            end_date=fault_end_date,
        )
        query = apply_equipment_created_date_range(
            query,
            start_date=created_start_date,
            end_date=created_end_date,
        )

        total = await query.count()
        order_clause = resolve_equipment_list_order_by(
            order_by,
            EQUIPMENT_FAULT_SORTABLE_FIELDS,
            "-fault_date",
        )
        faults = await query.offset(skip).limit(limit).order_by(order_clause)
        
        return faults, total
    
    @staticmethod
    async def update_equipment_fault(
        tenant_id: int,
        uuid: str,
        data: EquipmentFaultUpdate
    ) -> EquipmentFault:
        """
        更新设备故障记录
        
        Args:
            tenant_id: 组织ID
            uuid: 设备故障记录UUID
            data: 设备故障记录更新数据
            
        Returns:
            EquipmentFault: 更新后的设备故障记录对象
            
        Raises:
            NotFoundError: 当设备故障记录不存在时抛出
        """
        fault = await EquipmentFaultService.get_equipment_fault_by_uuid(tenant_id, uuid)
        
        update_data = data.model_dump(exclude_unset=True, exclude_none=True)
        
        # 更新字段
        for key, value in update_data.items():
            setattr(fault, key, value)
        
        await fault.save()
        if "status" in update_data:
            await sync_equipment_status_from_faults(tenant_id, fault.equipment_id)
        return fault
    
    @staticmethod
    async def delete_equipment_fault(
        tenant_id: int,
        uuid: str
    ) -> None:
        """
        删除设备故障记录（软删除）
        
        Args:
            tenant_id: 组织ID
            uuid: 设备故障记录UUID
            
        Raises:
            NotFoundError: 当设备故障记录不存在时抛出
        """
        fault = await EquipmentFaultService.get_equipment_fault_by_uuid(tenant_id, uuid)
        equipment_id = fault.equipment_id
        
        # 软删除
        fault.deleted_at = resolve_business_datetime()
        await fault.save()
        await sync_equipment_status_from_faults(tenant_id, equipment_id)


class EquipmentRepairService:
    """
    设备维修记录服务类
    
    提供设备维修记录的 CRUD 操作。
    """

    # 维修状态 → 关联故障单状态（列表「当前阶段」读故障 status）
    _REPAIR_TO_FAULT_STATUS = {
        "进行中": "处理中",
        "已完成": "已修复",
    }
    _FAULT_TERMINAL = frozenset({"已关闭"})

    @classmethod
    async def _sync_linked_fault_status(
        cls,
        *,
        tenant_id: int,
        equipment_fault: Optional[EquipmentFault],
        repair_status: Optional[str],
    ) -> None:
        """维修创建/更新后回写关联故障单阶段，避免列表仍显示「待处理」。"""
        if not equipment_fault or not repair_status:
            return
        target = cls._REPAIR_TO_FAULT_STATUS.get(repair_status)
        if not target:
            return
        if equipment_fault.status in cls._FAULT_TERMINAL:
            return
        if equipment_fault.status == target:
            return
        # 已修复后不因「进行中」回退
        if equipment_fault.status == "已修复" and target == "处理中":
            return
        equipment_fault.status = target
        if target == "已修复":
            equipment_fault.repair_required = False
        await equipment_fault.save()
        logger.info(
            "equipment_repair_synced_fault tenant_id={} fault_uuid={} repair_status={} fault_status={}",
            tenant_id,
            equipment_fault.uuid,
            repair_status,
            target,
        )
    
    @staticmethod
    async def create_equipment_repair(
        tenant_id: int,
        data: EquipmentRepairCreate,
        created_by: Optional[int] = None
    ) -> EquipmentRepair:
        """
        创建设备维修记录
        
        Args:
            tenant_id: 组织ID
            data: 设备维修记录创建数据
            created_by: 创建人ID（可选）
            
        Returns:
            EquipmentRepair: 创建设备维修记录对象
            
        Raises:
            ValidationError: 当设备不存在或维修记录编号已存在时抛出
        """
        try:
            # 验证设备是否存在
            equipment = await Equipment.filter(
                tenant_id=tenant_id,
                uuid=data.equipment_uuid,
                deleted_at__isnull=True
            ).first()
            
            if not equipment:
                raise ValidationError(f"设备不存在: {data.equipment_uuid}")
            
            # 如果关联了设备故障，验证设备故障是否存在
            equipment_fault = None
            if data.equipment_fault_uuid:
                equipment_fault = await EquipmentFault.filter(
                    tenant_id=tenant_id,
                    uuid=data.equipment_fault_uuid,
                    deleted_at__isnull=True
                ).first()
                
                if not equipment_fault:
                    raise ValidationError(f"设备故障记录不存在: {data.equipment_fault_uuid}")

            if equipment_fault:
                existing = await _find_open_repair_for_fault(
                    tenant_id,
                    fault_id=equipment_fault.id,
                    fault_uuid=equipment_fault.uuid,
                )
                if existing and existing.status == "进行中":
                    raise ValidationError(
                        "该故障已有进行中的维修单，请通过转派更换主维修人，勿重复指派"
                    )

            _, repairer_name = await _resolve_user_display(tenant_id, int(data.repairer_id))
            data.repairer_name = repairer_name
            
            # 如果没有提供维修记录编号，自动生成
            if not data.repair_no:
                try:
                    data.repair_no = await CodeGenerationService.generate_code(
                        tenant_id=tenant_id,
                        rule_code="equipment_repair_code",
                        context=None
                    )
                except ValidationError:
                    # 如果编码规则不存在，使用默认编码格式
                    timestamp = resolve_business_datetime().strftime("%Y%m%d%H%M%S")
                    data.repair_no = f"RP{timestamp}"
            
            repair = EquipmentRepair(
                tenant_id=tenant_id,
                equipment_id=equipment.id,
                equipment_uuid=equipment.uuid,
                equipment_name=equipment.name,
                equipment_fault_id=equipment_fault.id if equipment_fault else None,
                equipment_fault_uuid=equipment_fault.uuid if equipment_fault else None,
                **data.model_dump(exclude_none=True, exclude={'equipment_uuid', 'equipment_fault_uuid'})
            )
            actor = None
            if created_by is not None:
                actor = await User.filter(id=created_by).first()
                apply_create_audit(repair, actor)
            await repair.save()
            await _bootstrap_repair_participation(
                tenant_id,
                repair,
                user_id=repair.repairer_id or created_by,
                user_name=repair.repairer_name,
                actor=actor,
            )
            await EquipmentRepairService._sync_linked_fault_status(
                tenant_id=tenant_id,
                equipment_fault=equipment_fault,
                repair_status=repair.status,
            )
            # 故障状态未变时 _sync 会提前返回；创建维修后仍需按进行中维修刷新设备状态
            await sync_equipment_status_from_faults(tenant_id, equipment.id)
            if data.repair_parts:
                await SparePartService().apply_parts_usage(
                    tenant_id,
                    data.repair_parts,
                    rel_type="equipment_repair",
                    rel_id=repair.id,
                    operator_id=data.repairer_id or created_by,
                    operator_name=data.repairer_name,
                )
            if equipment_fault:
                from apps.kuaizhizao.services.equipment_mobile_notification import (
                    notify_equipment_fault_assigned,
                )

                try:
                    await notify_equipment_fault_assigned(
                        tenant_id=tenant_id,
                        fault=equipment_fault,
                        repairer_id=data.repairer_id,
                        repairer_name=data.repairer_name or "",
                    )
                except Exception as exc:
                    logger.warning("设备派工消息提醒失败 tenant={}: {}", tenant_id, exc)
            return repair
        except IntegrityError:
            raise ValidationError(f"设备维修记录编号 {data.repair_no} 已存在")
    
    @staticmethod
    async def get_equipment_repair_by_uuid(
        tenant_id: int,
        uuid: str
    ) -> EquipmentRepair:
        """
        根据UUID获取设备维修记录
        
        Args:
            tenant_id: 组织ID
            uuid: 设备维修记录UUID
            
        Returns:
            EquipmentRepair: 设备维修记录对象
            
        Raises:
            NotFoundError: 当设备维修记录不存在时抛出
        """
        repair = await EquipmentRepair.filter(
            tenant_id=tenant_id,
            uuid=uuid,
            deleted_at__isnull=True
        ).first()
        
        if not repair:
            raise NotFoundError("设备维修记录不存在")
        
        return repair
    
    @staticmethod
    async def list_equipment_repairs(
        tenant_id: int,
        skip: int = 0,
        limit: int = 100,
        equipment_uuid: Optional[str] = None,
        equipment_fault_uuid: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        keyword: Optional[str] = None,
        order_by: Optional[str] = None,
        repair_start_date: Optional[str] = None,
        repair_end_date: Optional[str] = None,
        created_start_date: Optional[str] = None,
        created_end_date: Optional[str] = None,
        mine_user_id: Optional[int] = None,
    ) -> tuple[List[EquipmentRepair], int]:
        """
        获取设备维修记录列表
        
        Args:
            tenant_id: 组织ID
            skip: 跳过数量
            limit: 限制数量
            equipment_uuid: 设备UUID（可选）
            equipment_fault_uuid: 设备故障UUID（可选）
            status: 维修状态（可选）
            search: 搜索关键词（可选，搜索维修记录编号）
            
        Returns:
            tuple[List[EquipmentRepair], int]: 设备维修记录列表和总数量
        """
        query = EquipmentRepair.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True
        )
        
        # 筛选条件
        if equipment_uuid:
            query = query.filter(equipment_uuid=equipment_uuid)
        if equipment_fault_uuid:
            query = query.filter(equipment_fault_uuid=equipment_fault_uuid)
        if status:
            query = query.filter(status=status)

        if mine_user_id is not None:
            participant_repair_ids = await EquipmentRepairParticipant.filter(
                tenant_id=tenant_id,
                user_id=mine_user_id,
                status=_PART_ACTIVE,
                deleted_at__isnull=True,
            ).values_list("repair_id", flat=True)
            participant_ids = list(participant_repair_ids)
            from tortoise.expressions import Q

            if participant_ids:
                query = query.filter(
                    Q(repairer_id=mine_user_id) | Q(id__in=participant_ids)
                )
            else:
                query = query.filter(repairer_id=mine_user_id)

        from apps.kuaizhizao.services.equipment_list_core import (
            EQUIPMENT_REPAIR_SORTABLE_FIELDS,
            apply_equipment_created_date_range,
            apply_equipment_document_date_range,
            apply_equipment_keyword_filter,
            pick_search_keyword,
            resolve_equipment_list_order_by,
        )

        query = apply_equipment_keyword_filter(
            query,
            pick_search_keyword(keyword, search),
            ["repair_no", "equipment_name", "repairer_name", "repair_description"],
        )
        query = apply_equipment_document_date_range(
            query,
            date_field="repair_date",
            start_date=repair_start_date,
            end_date=repair_end_date,
        )
        query = apply_equipment_created_date_range(
            query,
            start_date=created_start_date,
            end_date=created_end_date,
        )

        total = await query.count()
        order_clause = resolve_equipment_list_order_by(
            order_by,
            EQUIPMENT_REPAIR_SORTABLE_FIELDS,
            "-repair_date",
        )
        repairs = await query.offset(skip).limit(limit).order_by(order_clause)
        
        return repairs, total
    
    @staticmethod
    async def complete_equipment_repair(
        tenant_id: int,
        uuid: str,
        data: EquipmentRepairCompleteRequest,
        *,
        operator: Optional[User] = None,
    ) -> EquipmentRepair:
        repair = await EquipmentRepairService.get_equipment_repair_by_uuid(tenant_id, uuid)
        if repair.status == "已取消":
            raise ValidationError("已取消的维修单不可完工")
        if repair.status == "已完成":
            raise ValidationError("维修单已完工")
        inherited_arrival = await _inherit_arrival_from_sibling_repair(tenant_id, repair)
        if not repair.arrival_at:
            raise ValidationError("请先到场扫码签到后再完工")

        cause = (data.fault_cause or "").strip()
        content = (data.repair_content or "").strip()
        if not cause:
            raise ValidationError("请填写故障原因")
        if not content:
            raise ValidationError("请填写维修内容")

        now = resolve_business_datetime()
        repair.fault_cause = cause
        repair.repair_content = content
        repair.repair_description = content
        repair.repair_result = data.repair_result or "成功"
        if data.remark is not None:
            repair.remark = data.remark
        if data.attachments is not None:
            repair.attachments = data.attachments
        repair.status = "已完成"
        repair.completed_at = now
        if not repair.started_at:
            repair.started_at = repair.arrival_at or now
        apply_update_audit(repair, operator)
        await repair.save()
        await _finalize_active_participants(
            tenant_id,
            repair.id,
            left_at=now,
            actor=operator,
        )
        if inherited_arrival:
            logger.info(
                "equipment repair {} inherited arrival_at from sibling before complete",
                repair.uuid,
            )

        linked_fault = None
        if repair.equipment_fault_uuid:
            linked_fault = await EquipmentFault.filter(
                tenant_id=tenant_id,
                uuid=repair.equipment_fault_uuid,
                deleted_at__isnull=True,
            ).first()
            await EquipmentRepairService._sync_linked_fault_status(
                tenant_id=tenant_id,
                equipment_fault=linked_fault,
                repair_status=repair.status,
            )
            if linked_fault:
                from apps.kuaizhizao.services.equipment_fault_reminder_service import (
                    EquipmentFaultReminderService,
                )

                await EquipmentFaultReminderService.stop_arrival_reminders(
                    tenant_id,
                    linked_fault.id,
                    reason="维修已完工",
                )
                from apps.kuaizhizao.services.equipment_mobile_notification import (
                    notify_equipment_fault_resolved,
                )

                try:
                    await notify_equipment_fault_resolved(
                        tenant_id=tenant_id,
                        fault=linked_fault,
                        repairer_name=repair.repairer_name or repair.arrival_by_name or "",
                        repair_result=content or repair.repair_result or "已修复",
                    )
                except Exception as exc:
                    logger.warning("设备恢复消息提醒失败 tenant={}: {}", tenant_id, exc)

        await sync_equipment_status_from_faults(tenant_id, repair.equipment_id)
        return repair

    @staticmethod
    async def update_equipment_repair(
        tenant_id: int,
        uuid: str,
        data: EquipmentRepairUpdate
    ) -> EquipmentRepair:
        """
        更新设备维修记录
        
        Args:
            tenant_id: 组织ID
            uuid: 设备维修记录UUID
            data: 设备维修记录更新数据
            
        Returns:
            EquipmentRepair: 更新后的设备维修记录对象
            
        Raises:
            NotFoundError: 当设备维修记录不存在时抛出
        """
        repair = await EquipmentRepairService.get_equipment_repair_by_uuid(tenant_id, uuid)
        
        update_data = data.model_dump(exclude_unset=True, exclude_none=True)
        if update_data.get("status") == "已完成":
            await _inherit_arrival_from_sibling_repair(tenant_id, repair)
            if not repair.arrival_at and not update_data.get("arrival_at"):
                raise ValidationError("请先到场扫码签到后再完工")
            if repair.arrival_at and not update_data.get("arrival_at"):
                update_data["arrival_at"] = repair.arrival_at
                update_data.setdefault("arrival_by_id", repair.arrival_by_id)
                update_data.setdefault("arrival_by_name", repair.arrival_by_name)
            cause = (update_data.get("fault_cause") or repair.fault_cause or "").strip()
            content = (
                update_data.get("repair_content")
                or repair.repair_content
                or update_data.get("repair_description")
                or repair.repair_description
                or ""
            ).strip()
            if not cause:
                raise ValidationError("完工须填写故障原因")
            if not content:
                raise ValidationError("完工须填写维修内容")
            update_data["fault_cause"] = cause
            update_data["repair_content"] = content
            update_data.setdefault("completed_at", resolve_business_datetime())
        
        # 更新字段
        for key, value in update_data.items():
            setattr(repair, key, value)
        
        await repair.save()

        if update_data.get("status") == "已完成":
            done_at = repair.completed_at or resolve_business_datetime()
            if not repair.started_at:
                repair.started_at = repair.arrival_at or done_at
                await repair.save()
            await _finalize_active_participants(
                tenant_id,
                repair.id,
                left_at=done_at,
                actor=None,
            )

        if "status" in update_data:
            if repair.equipment_fault_uuid:
                linked_fault = await EquipmentFault.filter(
                    tenant_id=tenant_id,
                    uuid=repair.equipment_fault_uuid,
                    deleted_at__isnull=True,
                ).first()
                await EquipmentRepairService._sync_linked_fault_status(
                    tenant_id=tenant_id,
                    equipment_fault=linked_fault,
                    repair_status=repair.status,
                )
                if linked_fault and update_data.get("status") == "已完成":
                    from apps.kuaizhizao.services.equipment_fault_reminder_service import (
                        EquipmentFaultReminderService,
                    )

                    await EquipmentFaultReminderService.stop_arrival_reminders(
                        tenant_id,
                        linked_fault.id,
                        reason="维修已完工",
                    )
                    from apps.kuaizhizao.services.equipment_mobile_notification import (
                        notify_equipment_fault_resolved,
                    )

                    try:
                        await notify_equipment_fault_resolved(
                            tenant_id=tenant_id,
                            fault=linked_fault,
                            repairer_name=repair.repairer_name or "",
                            repair_result=repair.repair_content
                            or repair.repair_description
                            or repair.repair_result
                            or "已修复",
                        )
                    except Exception as exc:
                        logger.warning("设备恢复消息提醒失败 tenant={}: {}", tenant_id, exc)
            # 已取消等不映射故障状态的路径也需刷新设备状态
            await sync_equipment_status_from_faults(tenant_id, repair.equipment_id)
        return repair

    @staticmethod
    async def add_collaborator(
        tenant_id: int,
        uuid: str,
        data: EquipmentRepairAddCollaboratorRequest,
        *,
        operator: Optional[User] = None,
    ) -> EquipmentRepair:
        repair = await EquipmentRepairService.get_equipment_repair_by_uuid(tenant_id, uuid)
        if repair.status != "进行中":
            raise ValidationError("仅进行中的维修单可添加协作人")
        user, name = await _resolve_user_display(tenant_id, int(data.user_id))
        active_same = await EquipmentRepairParticipant.filter(
            tenant_id=tenant_id,
            repair_id=repair.id,
            user_id=user.id,
            status=_PART_ACTIVE,
            deleted_at__isnull=True,
        ).first()
        if active_same:
            raise ValidationError(f"{name} 已在本维修单进行中，勿重复添加")
        now = resolve_business_datetime()
        await _bootstrap_repair_participation(
            tenant_id,
            repair,
            user_id=repair.repairer_id or (operator.id if operator else None),
            user_name=repair.repairer_name,
            when=now,
            actor=operator,
        )
        row = EquipmentRepairParticipant(
            tenant_id=tenant_id,
            repair_id=repair.id,
            repair_uuid=repair.uuid,
            user_id=user.id,
            user_name=name,
            role=_ROLE_COLLAB,
            status=_PART_ACTIVE,
            joined_at=now,
            remark=(data.remark or "").strip() or None,
        )
        apply_create_audit(row, operator)
        await row.save()
        return repair

    @staticmethod
    async def reassign_primary(
        tenant_id: int,
        uuid: str,
        data: EquipmentRepairReassignRequest,
        *,
        operator: Optional[User] = None,
    ) -> EquipmentRepair:
        repair = await EquipmentRepairService.get_equipment_repair_by_uuid(tenant_id, uuid)
        if repair.status != "进行中":
            raise ValidationError("仅进行中的维修单可转派")
        to_user, to_name = await _resolve_user_display(tenant_id, int(data.to_user_id))
        now = resolve_business_datetime()
        await _bootstrap_repair_participation(
            tenant_id,
            repair,
            user_id=repair.repairer_id or (operator.id if operator else None),
            user_name=repair.repairer_name,
            when=now,
            actor=operator,
        )
        current_primary = await EquipmentRepairParticipant.filter(
            tenant_id=tenant_id,
            repair_id=repair.id,
            role=_ROLE_PRIMARY,
            status=_PART_ACTIVE,
            deleted_at__isnull=True,
        ).first()
        if current_primary and current_primary.user_id == to_user.id:
            raise ValidationError("转派目标已是当前主责人")
        if current_primary:
            current_primary.status = _PART_REASSIGNED
            current_primary.left_at = now
            current_primary.reassigned_to_id = to_user.id
            current_primary.reassigned_to_name = to_name
            if data.remark:
                current_primary.remark = (data.remark or "").strip() or current_primary.remark
            apply_update_audit(current_primary, operator)
            await current_primary.save()
        # 目标若已是协作进行中，结束协作段再升为主责
        active_target = await EquipmentRepairParticipant.filter(
            tenant_id=tenant_id,
            repair_id=repair.id,
            user_id=to_user.id,
            status=_PART_ACTIVE,
            deleted_at__isnull=True,
        ).first()
        if active_target:
            active_target.status = _PART_LEFT
            active_target.left_at = now
            apply_update_audit(active_target, operator)
            await active_target.save()
        new_primary = EquipmentRepairParticipant(
            tenant_id=tenant_id,
            repair_id=repair.id,
            repair_uuid=repair.uuid,
            user_id=to_user.id,
            user_name=to_name,
            role=_ROLE_PRIMARY,
            status=_PART_ACTIVE,
            joined_at=now,
            remark=(data.remark or "").strip() or None,
        )
        apply_create_audit(new_primary, operator)
        await new_primary.save()
        repair.repairer_id = to_user.id
        repair.repairer_name = to_name
        apply_update_audit(repair, operator)
        await repair.save()
        return repair
    
    @staticmethod
    async def delete_equipment_repair(
        tenant_id: int,
        uuid: str
    ) -> None:
        """
        删除设备维修记录（软删除）
        
        Args:
            tenant_id: 组织ID
            uuid: 设备维修记录UUID
            
        Raises:
            NotFoundError: 当设备维修记录不存在时抛出
        """
        repair = await EquipmentRepairService.get_equipment_repair_by_uuid(tenant_id, uuid)
        equipment_id = repair.equipment_id
        
        # 软删除
        repair.deleted_at = resolve_business_datetime()
        await repair.save()
        await sync_equipment_status_from_faults(tenant_id, equipment_id)

