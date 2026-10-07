"""继电器自动报工：读 zscl 快照 → 匹配工序 → 正式报工。"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from loguru import logger

from apps.ind_relay.models.auto_report import (
    MODE_PLAN_OFFLINE,
    MODE_REALTIME,
    ZSCL_TAG_KEY,
    RelayAutoReportBinding,
    RelayAutoReportConfig,
    RelayAutoReportLog,
)
from apps.ind_relay.services.auto_report_math import (
    allocate_increment,
    candidate_bind_sort_key,
    candidate_fill_sort_key,
    compute_zscl_increment,
    equipment_in_default_ids,
    should_changeover,
)
from apps.kuaizhizao.models.equipment import Equipment
from apps.kuaizhizao.models.work_order import WorkOrder
from apps.kuaizhizao.models.work_order_operation import WorkOrderOperation
from apps.kuaizhizao.schemas.reporting_record import ReportingRecordCreate
from apps.kuaizhizao.services.reporting_service import ReportingService
from apps.kuaizhizao.services.work_order_service import WORK_ORDER_IN_PROGRESS_STATUS
from apps.kuaiiot.models.iot import IotDevice, IotTagSnapshot

try:
    from apps.kuaiiot.models.iot import IotDiscoveredMqttDevice
except ImportError:  # 快数采私有仓未合入现场设备名录模型时仍可报工
    IotDiscoveredMqttDevice = None  # type: ignore[misc, assignment]
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError, ValidationError
from infra.models.user import User

ZERO = Decimal("0")
_IN_PROGRESS_WO = {
    "in_progress",
    "生产中",
    "进行中",
    "执行中",
    "IN_PROGRESS",
}


class AutoReportService:
    @staticmethod
    async def get_or_create_config(tenant_id: int) -> RelayAutoReportConfig:
        from tortoise.exceptions import OperationalError

        try:
            row = await RelayAutoReportConfig.get_or_none(
                tenant_id=tenant_id, deleted_at__isnull=True
            )
            if row:
                return row
            return await RelayAutoReportConfig.create(
                tenant_id=tenant_id,
                is_enabled=False,
                match_by_device=False,
                interval_minutes=5,
                report_mode=MODE_REALTIME,
                offline_threshold_seconds=180,
            )
        except OperationalError as exc:
            raise ValidationError(
                "自动报工数据表尚未就绪，请在 riveredge-backend 执行 aerich upgrade（迁移 828）后重启服务"
            ) from exc

    @staticmethod
    async def update_config(
        tenant_id: int,
        *,
        user_id: Optional[int],
        data: dict[str, Any],
    ) -> RelayAutoReportConfig:
        row = await AutoReportService.get_or_create_config(tenant_id)
        if "is_enabled" in data and data["is_enabled"] is not None:
            row.is_enabled = bool(data["is_enabled"])
        if "interval_minutes" in data and data["interval_minutes"] is not None:
            minutes = int(data["interval_minutes"])
            if minutes < 1:
                raise ValidationError("自动报工间隔至少 1 分钟")
            row.interval_minutes = minutes
        if "report_mode" in data and data["report_mode"] is not None:
            mode = str(data["report_mode"]).strip()
            if mode not in {MODE_REALTIME, MODE_PLAN_OFFLINE}:
                raise ValidationError("无效的自动报工模式")
            row.report_mode = mode
        if "offline_threshold_seconds" in data and data["offline_threshold_seconds"] is not None:
            seconds = int(data["offline_threshold_seconds"])
            if seconds < 30:
                raise ValidationError("离线兜底阈值至少 30 秒")
            row.offline_threshold_seconds = seconds
        if "reporter_user_id" in data:
            reporter_id = data["reporter_user_id"]
            if reporter_id is None:
                row.reporter_user_id = None
                row.reporter_user_name = None
            else:
                user = await User.get_or_none(id=int(reporter_id), tenant_id=tenant_id)
                if not user or not user.is_active:
                    raise ValidationError("报工创建人不存在或已停用")
                row.reporter_user_id = int(user.id)
                row.reporter_user_name = (
                    (user.full_name or user.username or "").strip() or str(user.id)
                )
        if "remarks" in data:
            row.remarks = data["remarks"]
        if user_id is not None:
            row.updated_by = int(user_id)
        await row.save()
        return row

    @staticmethod
    async def list_bindings(tenant_id: int) -> list[RelayAutoReportBinding]:
        return (
            await RelayAutoReportBinding.filter(tenant_id=tenant_id, deleted_at__isnull=True)
            .order_by("-id")
            .all()
        )

    @staticmethod
    async def upsert_binding(
        tenant_id: int,
        *,
        user_id: Optional[int],
        iot_device_id: int,
        is_enabled: bool = True,
        remarks: Optional[str] = None,
    ) -> RelayAutoReportBinding:
        device = await IotDevice.get_or_none(
            tenant_id=tenant_id, id=int(iot_device_id), deleted_at__isnull=True
        )
        if not device:
            raise NotFoundError("快数采设备不存在")
        if not device.equipment_uuid:
            raise ValidationError("请先在「设备连接」绑定 MES 设备")
        equipment = await Equipment.get_or_none(
            tenant_id=tenant_id,
            uuid=device.equipment_uuid,
            deleted_at__isnull=True,
        )
        if not equipment:
            raise ValidationError("绑定的 MES 设备不存在，请重新在设备连接中选择")

        existing = await RelayAutoReportBinding.get_or_none(
            tenant_id=tenant_id,
            iot_device_id=int(device.id),
            deleted_at__isnull=True,
        )
        if existing:
            row = existing
        else:
            row = RelayAutoReportBinding(
                tenant_id=tenant_id,
                iot_device_id=int(device.id),
                baseline_aligned=False,
                pending_quantity=ZERO,
            )
        row.iot_device_uuid = device.uuid
        row.iot_device_code = device.code
        row.iot_device_name = device.name
        row.external_device_id = device.external_device_id
        row.equipment_uuid = equipment.uuid
        row.equipment_id = int(equipment.id)
        row.equipment_code = equipment.code
        row.equipment_name = equipment.name
        line_id, line_code, line_name = await AutoReportService._resolve_production_line(
            tenant_id, device=device, equipment=equipment
        )
        row.production_line_id = line_id
        row.production_line_code = line_code
        row.production_line_name = line_name
        row.is_enabled = bool(is_enabled)
        if remarks is not None:
            row.remarks = remarks
        if user_id is not None:
            row.updated_by = int(user_id)
            if not existing:
                row.created_by = int(user_id)
        await row.save()
        return row

    @staticmethod
    async def set_binding_enabled(
        tenant_id: int,
        binding_id: int,
        *,
        is_enabled: bool,
        user_id: Optional[int] = None,
    ) -> RelayAutoReportBinding:
        row = await RelayAutoReportBinding.get_or_none(
            tenant_id=tenant_id, id=binding_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("绑定不存在")
        row.is_enabled = bool(is_enabled)
        if user_id is not None:
            row.updated_by = int(user_id)
        await row.save()
        return row

    @staticmethod
    async def delete_binding(
        tenant_id: int,
        binding_id: int,
        *,
        user_id: Optional[int] = None,
    ) -> None:
        row = await RelayAutoReportBinding.get_or_none(
            tenant_id=tenant_id, id=binding_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("绑定不存在")
        row.deleted_at = resolve_business_datetime()
        if user_id is not None:
            row.updated_by = int(user_id)
        await row.save(update_fields=["deleted_at", "updated_by", "updated_at"])

    @staticmethod
    async def list_logs(
        tenant_id: int,
        *,
        binding_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[RelayAutoReportLog], int]:
        q = RelayAutoReportLog.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if binding_id is not None:
            q = q.filter(binding_id=binding_id)
        total = await q.count()
        rows = await q.order_by("-id").offset(skip).limit(limit)
        return rows, total

    @staticmethod
    async def list_bound_iot_device_options(tenant_id: int) -> list[dict[str, Any]]:
        devices = await IotDevice.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            equipment_uuid__isnull=False,
        ).exclude(equipment_uuid="").order_by("name").limit(500)
        uuids = [d.equipment_uuid for d in devices if d.equipment_uuid]
        eq_map: dict[str, Equipment] = {}
        if uuids:
            for eq in await Equipment.filter(
                tenant_id=tenant_id, uuid__in=uuids, deleted_at__isnull=True
            ):
                eq_map[eq.uuid] = eq
        result = []
        for d in devices:
            eq = eq_map.get(d.equipment_uuid or "")
            if not eq:
                continue
            result.append(
                {
                    "iot_device_id": int(d.id),
                    "iot_device_uuid": d.uuid,
                    "iot_device_code": d.code,
                    "iot_device_name": d.name,
                    "external_device_id": d.external_device_id,
                    "equipment_uuid": eq.uuid,
                    "equipment_id": int(eq.id),
                    "equipment_code": eq.code,
                    "equipment_name": eq.name,
                    "production_line_id": eq.production_line_id,
                    "production_line_code": eq.production_line_code,
                    "production_line_name": eq.production_line_name,
                    "is_online": bool(d.is_online),
                    "last_seen_at": d.last_seen_at,
                    "label": (
                        f"{d.name} → {eq.name}/{eq.code}"
                        + (
                            f" ({eq.production_line_name})"
                            if eq.production_line_name
                            else ""
                        )
                    ),
                }
            )
        return result

    @staticmethod
    async def _append_log(
        tenant_id: int,
        *,
        binding: Optional[RelayAutoReportBinding],
        level: str,
        event: str,
        message: str,
        zscl: Optional[Decimal] = None,
        increment_qty: Optional[Decimal] = None,
        work_order_id: Optional[int] = None,
        work_order_code: Optional[str] = None,
        operation_id: Optional[int] = None,
        reporting_record_id: Optional[int] = None,
        extra: Optional[dict] = None,
    ) -> None:
        await RelayAutoReportLog.create(
            tenant_id=tenant_id,
            binding_id=int(binding.id) if binding else None,
            iot_device_id=int(binding.iot_device_id) if binding else None,
            level=level,
            event=event,
            message=message[:2000] if message else None,
            zscl=zscl,
            increment_qty=increment_qty,
            work_order_id=work_order_id,
            work_order_code=work_order_code,
            operation_id=operation_id,
            reporting_record_id=reporting_record_id,
            extra=extra,
        )

    @staticmethod
    async def _read_zscl(tenant_id: int, iot_device_id: int) -> tuple[Optional[Decimal], Optional[Any]]:
        snap = await IotTagSnapshot.get_or_none(
            tenant_id=tenant_id,
            device_id=iot_device_id,
            tag_key=ZSCL_TAG_KEY,
            deleted_at__isnull=True,
        )
        if not snap:
            return None, None
        if snap.value_number is not None:
            return Decimal(str(snap.value_number)), snap.sampled_at
        if snap.value_text:
            try:
                return Decimal(str(snap.value_text).strip()), snap.sampled_at
            except (InvalidOperation, ValueError):
                return None, snap.sampled_at
        return None, snap.sampled_at

    @staticmethod
    def _wo_in_progress(wo: WorkOrder) -> bool:
        return (wo.status or "") in _IN_PROGRESS_WO

    @staticmethod
    def _planned_start(wo: WorkOrder, op: WorkOrderOperation):
        return op.planned_start_date or wo.planned_start_date

    @staticmethod
    def _apply_bind(binding: RelayAutoReportBinding, wo: WorkOrder, op: WorkOrderOperation) -> None:
        binding.bound_work_order_id = int(wo.id)
        binding.bound_work_order_code = wo.code
        binding.bound_operation_id = int(op.operation_id) if op.operation_id else None
        binding.bound_operation_name = op.operation_name
        binding.bound_product_id = int(wo.product_id) if wo.product_id else None

    @staticmethod
    async def _resolve_production_line(
        tenant_id: int,
        *,
        device: IotDevice,
        equipment: Equipment,
    ) -> tuple[Optional[int], Optional[str], Optional[str]]:
        line_id = equipment.production_line_id
        line_code = (equipment.production_line_code or "").strip() or None
        line_name = (equipment.production_line_name or "").strip() or None
        if (
            IotDiscoveredMqttDevice is not None
            and (not line_code and not line_name)
            and device.external_device_id
        ):
            disc = (
                await IotDiscoveredMqttDevice.filter(
                    tenant_id=tenant_id,
                    external_device_id=device.external_device_id,
                    deleted_at__isnull=True,
                )
                .order_by("-last_seen_at")
                .first()
            )
            if disc:
                line_code = (disc.line_code or "").strip() or line_code
                line_name = (disc.line_name or "").strip() or line_name
        return line_id, line_code, line_name

    @staticmethod
    def _equipment_ids_from_json(raw: object) -> list[int]:
        if not isinstance(raw, (list, tuple)):
            return []
        out: list[int] = []
        for item in raw:
            try:
                out.append(int(item))
            except (TypeError, ValueError):
                continue
        return out

    @staticmethod
    async def list_process_operations_for_equipment(
        tenant_id: int,
        equipment_id: int,
    ) -> list[dict[str, Any]]:
        from apps.master_data.models.process import Operation

        rows = await Operation.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
        ).order_by("code")
        result: list[dict[str, Any]] = []
        for op in rows:
            if not equipment_in_default_ids(op.default_equipment_ids, equipment_id):
                continue
            result.append(
                {
                    "id": int(op.id),
                    "uuid": op.uuid,
                    "code": op.code,
                    "name": op.name,
                    "is_active": bool(op.is_active),
                    "reporting_type": op.reporting_type,
                    "default_equipment_ids": AutoReportService._equipment_ids_from_json(
                        op.default_equipment_ids
                    ),
                }
            )
        return result

    @staticmethod
    async def list_binding_process_operations(
        tenant_id: int,
        binding_id: int,
    ) -> dict[str, Any]:
        row = await RelayAutoReportBinding.get_or_none(
            tenant_id=tenant_id, id=binding_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError("绑定不存在")
        if not row.equipment_id:
            raise ValidationError("绑定缺少 MES 设备")
        items = await AutoReportService.list_process_operations_for_equipment(
            tenant_id, int(row.equipment_id)
        )
        return {
            "binding_id": int(row.id),
            "equipment_id": int(row.equipment_id),
            "equipment_code": row.equipment_code,
            "equipment_name": row.equipment_name,
            "items": items,
        }

    @staticmethod
    async def process_operation_counts_by_equipment(tenant_id: int) -> dict[int, int]:
        from apps.master_data.models.process import Operation

        counts: dict[int, int] = {}
        rows = await Operation.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        for op in rows:
            for eid in AutoReportService._equipment_ids_from_json(op.default_equipment_ids):
                counts[eid] = counts.get(eid, 0) + 1
        return counts

    @staticmethod
    async def _master_operation_ids_for_equipment(
        tenant_id: int,
        equipment_id: int,
    ) -> set[int]:
        ops = await AutoReportService.list_process_operations_for_equipment(
            tenant_id, equipment_id
        )
        return {int(op["id"]) for op in ops}

    @staticmethod
    def _op_has_equipment(op: WorkOrderOperation, equipment_id: int) -> bool:
        if op.assigned_equipment_id and int(op.assigned_equipment_id) == equipment_id:
            return True
        ids = op.assigned_equipment_ids or []
        if isinstance(ids, list):
            for raw in ids:
                try:
                    if int(raw) == equipment_id:
                        return True
                except (TypeError, ValueError):
                    continue
        return False

    @staticmethod
    async def _find_candidate_ops(
        tenant_id: int,
        *,
        equipment_id: int,
        bound_operation_ids: set[int],
    ) -> list[tuple[WorkOrder, WorkOrderOperation]]:
        if not bound_operation_ids:
            return []
        work_orders = await WorkOrder.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            status__in=list(WORK_ORDER_IN_PROGRESS_STATUS),
            is_frozen=False,
        ).exclude(status="split").all()
        if not work_orders:
            return []
        wo_map = {int(w.id): w for w in work_orders}
        ops = await WorkOrderOperation.filter(
            tenant_id=tenant_id,
            work_order_id__in=list(wo_map.keys()),
            deleted_at__isnull=True,
        ).all()
        ops_by_wo: dict[int, list[WorkOrderOperation]] = {}
        for op in ops:
            if (op.status or "") in {"completed", "cancelled", "paused"}:
                continue
            ops_by_wo.setdefault(int(op.work_order_id), []).append(op)

        candidates: list[tuple[WorkOrder, WorkOrderOperation, int]] = []
        for wo_id, wo_ops in ops_by_wo.items():
            wo = wo_map.get(wo_id)
            if not wo:
                continue
            matched = [
                op
                for op in wo_ops
                if op.operation_id
                and int(op.operation_id) in bound_operation_ids
                and AutoReportService._op_has_equipment(op, equipment_id)
            ]
            for op in matched:
                if not op.assigned_worker_id and not getattr(op, "assigned_team_id", None):
                    continue
                status_rank = 0 if AutoReportService._wo_in_progress(wo) else 1
                candidates.append((wo, op, status_rank))

        candidates.sort(
            key=lambda item: candidate_bind_sort_key(
                item[2],
                AutoReportService._planned_start(item[0], item[1]),
                int(item[0].id or 0),
            )
        )
        return [(wo, op) for wo, op, _ in candidates]

    @staticmethod
    async def _remaining_for_op(tenant_id: int, wo: WorkOrder, op: WorkOrderOperation) -> Decimal:
        from apps.kuaizhizao.services.reporting_service import _compute_operation_reportable_remaining

        try:
            rem = await _compute_operation_reportable_remaining(tenant_id, wo, op)
            return rem if rem > ZERO else ZERO
        except Exception as exc:  # noqa: BLE001
            logger.warning("auto_report remaining failed wo={} op={}: {}", wo.id, op.id, exc)
            plan = Decimal(str(wo.quantity or 0))
            done = Decimal(str(op.completed_quantity or 0))
            rem = plan - done
            return rem if rem > ZERO else ZERO

    @staticmethod
    async def _create_reporting(
        tenant_id: int,
        *,
        config: RelayAutoReportConfig,
        wo: WorkOrder,
        op: WorkOrderOperation,
        qty: Decimal,
        binding: RelayAutoReportBinding,
    ) -> tuple[Optional[int], Decimal, Decimal]:
        """
        创建正式报工。报工时同步计算本道可报量（含超报规则），按可报量截断。

        返回 (record_id, 实际报工量, 截断前请求量)。无可报量时 (None, 0, requested)。
        """
        requested = qty if qty > ZERO else ZERO
        if requested <= ZERO:
            return None, ZERO, ZERO
        # 与正式报工同一套 remaining：计划量、已完成、工序超报规则一并计入
        remaining = await AutoReportService._remaining_for_op(tenant_id, wo, op)
        actual = requested if requested <= remaining else remaining
        if actual <= ZERO:
            return None, ZERO, requested
        reporter_id = config.reporter_user_id
        if not reporter_id:
            raise ValidationError("请先配置报工创建人")
        worker_id = op.assigned_worker_id
        if not worker_id:
            raw_ids = getattr(op, "assigned_worker_ids", None) or []
            if isinstance(raw_ids, list) and raw_ids:
                try:
                    worker_id = int(raw_ids[0])
                except (TypeError, ValueError):
                    worker_id = None
        team_id = getattr(op, "assigned_team_id", None)
        worker_name = (op.assigned_worker_name or "").strip() or None
        team_name = (getattr(op, "assigned_team_name", None) or "").strip() or None
        payload: dict[str, Any] = {
            "work_order_id": int(wo.id),
            "work_order_code": wo.code or str(wo.id),
            "work_order_name": wo.name or wo.code or str(wo.id),
            "operation_id": int(op.operation_id),
            "operation_code": op.operation_code or "",
            "operation_name": op.operation_name or "",
            "reported_quantity": actual,
            "qualified_quantity": actual,
            "unqualified_quantity": ZERO,
            "work_hours": ZERO,
            "status": "pending",
            "reported_at": resolve_business_datetime(),
            "remarks": (
                f"自动报工 iot={binding.iot_device_code or binding.iot_device_id}"
                + (f"；请求{requested}按可报量截断为{actual}" if actual < requested else "")
            ),
            "origin": "auto",
            "production_line_id": binding.production_line_id,
            "production_line_code": binding.production_line_code,
            "production_line_name": binding.production_line_name,
            "device_info": {
                "source": "ind_relay_auto_report",
                "origin": "auto",
                "iot_device_id": binding.iot_device_id,
                "equipment_uuid": binding.equipment_uuid,
                "equipment_code": binding.equipment_code,
                "production_line_id": binding.production_line_id,
                "production_line_code": binding.production_line_code,
                "production_line_name": binding.production_line_name,
                "requested_qty": str(requested),
                "reportable_remaining": str(remaining),
                "reported_qty": str(actual),
            },
            "idempotency_key": (
                f"ind-relay-ar-{binding.id}-{wo.id}-{op.operation_id}-"
                f"{actual}-{int(resolve_business_datetime().timestamp())}"
            ),
        }
        if team_id:
            payload["team_id"] = int(team_id)
            payload["team_name"] = team_name or f"team-{team_id}"
            payload["worker_name"] = team_name or payload["team_name"]
        elif worker_id:
            payload["worker_id"] = int(worker_id)
            payload["worker_name"] = worker_name or f"user-{worker_id}"
        else:
            raise ValidationError("工序未派工，无法自动报工")

        create_data = ReportingRecordCreate.model_validate(payload)
        record = await ReportingService().create_reporting_record(
            tenant_id=tenant_id,
            reporting_data=create_data,
            reported_by=int(reporter_id),
            entry_mode="auto",
            client_channel="auto",
        )
        return int(record.id), actual, requested

    @staticmethod
    async def _report_pairs(
        tenant_id: int,
        *,
        config: RelayAutoReportConfig,
        binding: RelayAutoReportBinding,
        pairs: list[tuple[WorkOrder, WorkOrderOperation, Decimal]],
        current: Optional[Decimal],
        reason: str,
        event: str = "report",
    ) -> tuple[list[int], Decimal, Optional[tuple[WorkOrder, WorkOrderOperation]]]:
        reported_ids: list[int] = []
        reported_qty = ZERO
        last_ok: Optional[tuple[WorkOrder, WorkOrderOperation]] = None
        for wo, op, qty in pairs:
            if qty <= ZERO:
                continue
            try:
                # 创建时同步算可报量/是否超限并截断，不依赖分摊阶段单独判断
                rid, actual, requested = await AutoReportService._create_reporting(
                    tenant_id,
                    config=config,
                    wo=wo,
                    op=op,
                    qty=qty,
                    binding=binding,
                )
            except (ValidationError, BusinessLogicError, NotFoundError) as exc:
                await AutoReportService._append_log(
                    tenant_id,
                    binding=binding,
                    level="error",
                    event="error",
                    message=str(exc),
                    zscl=current,
                    increment_qty=qty,
                    work_order_id=int(wo.id),
                    work_order_code=wo.code,
                    operation_id=int(op.operation_id) if op.operation_id else None,
                    extra={"reason": reason},
                )
                break
            except Exception as exc:  # noqa: BLE001
                logger.exception("ind_relay auto report failed: {}", exc)
                await AutoReportService._append_log(
                    tenant_id,
                    binding=binding,
                    level="error",
                    event="error",
                    message=f"报工异常: {exc}",
                    zscl=current,
                    increment_qty=qty,
                    work_order_id=int(wo.id),
                    work_order_code=wo.code,
                    extra={"reason": reason},
                )
                break
            if not rid or actual <= ZERO:
                await AutoReportService._append_log(
                    tenant_id,
                    binding=binding,
                    level="info",
                    event="skip",
                    message="报工时计算可报量为 0，跳过该工单继续分摊",
                    zscl=current,
                    increment_qty=requested if requested > ZERO else qty,
                    work_order_id=int(wo.id),
                    work_order_code=wo.code,
                    operation_id=int(op.operation_id) if op.operation_id else None,
                    extra={"reason": reason, "requested": str(requested or qty)},
                )
                continue
            reported_ids.append(rid)
            reported_qty += actual
            last_ok = (wo, op)
            msg = "自动报工成功"
            if actual < requested:
                msg = f"自动报工成功（请求 {requested}，按可报量截断为 {actual}）"
            await AutoReportService._append_log(
                tenant_id,
                binding=binding,
                level="info",
                event=event,
                message=msg,
                zscl=current,
                increment_qty=actual,
                work_order_id=int(wo.id),
                work_order_code=wo.code,
                operation_id=int(op.operation_id) if op.operation_id else None,
                reporting_record_id=rid,
                extra={
                    "reason": reason,
                    "requested": str(requested),
                    "reported": str(actual),
                },
            )
        return reported_ids, reported_qty, last_ok

    @staticmethod
    async def settle_binding(
        tenant_id: int,
        binding: RelayAutoReportBinding,
        config: RelayAutoReportConfig,
        *,
        force_flush: bool = False,
        reason: str = "tick",
    ) -> dict[str, Any]:
        if not binding.is_enabled:
            return {"skipped": True, "reason": "binding_disabled"}
        if not binding.equipment_id:
            await AutoReportService._append_log(
                tenant_id,
                binding=binding,
                level="warning",
                event="skip",
                message="绑定缺少 MES 设备 ID",
            )
            return {"skipped": True, "reason": "no_equipment"}

        equipment = await Equipment.get_or_none(
            tenant_id=tenant_id, id=int(binding.equipment_id), deleted_at__isnull=True
        )
        if equipment:
            device = await IotDevice.get_or_none(
                tenant_id=tenant_id, id=int(binding.iot_device_id), deleted_at__isnull=True
            )
            if device:
                line_id, line_code, line_name = await AutoReportService._resolve_production_line(
                    tenant_id, device=device, equipment=equipment
                )
                binding.production_line_id = line_id
                binding.production_line_code = line_code
                binding.production_line_name = line_name

        current, sampled_at = await AutoReportService._read_zscl(tenant_id, int(binding.iot_device_id))
        if sampled_at:
            binding.last_seen_at = sampled_at
            if binding.offline_flushed:
                binding.offline_flushed = False

        kind, increment = compute_zscl_increment(current, binding.last_zscl)
        if kind == "missing":
            await AutoReportService._append_log(
                tenant_id,
                binding=binding,
                level="info",
                event="skip",
                message="无 zscl 点位快照",
                extra={"reason": reason},
            )
            await binding.save()
            return {"skipped": True, "reason": "no_zscl"}

        if kind == "baseline" or not binding.baseline_aligned:
            binding.last_zscl = current
            binding.baseline_aligned = True
            binding.last_settle_at = resolve_business_datetime()
            await binding.save()
            await AutoReportService._append_log(
                tenant_id,
                binding=binding,
                level="info",
                event="baseline",
                message="首次对齐 zscl 基线，不报工",
                zscl=current,
                extra={"reason": reason},
            )
            return {"baseline": True, "zscl": str(current)}

        if kind == "zero" and not force_flush:
            binding.last_settle_at = resolve_business_datetime()
            await binding.save()
            return {"skipped": True, "reason": "zero_increment"}

        pending = Decimal(str(binding.pending_quantity or 0))
        if increment > ZERO:
            pending += increment
            binding.last_zscl = current

        bound_operation_ids = await AutoReportService._master_operation_ids_for_equipment(
            tenant_id, int(binding.equipment_id)
        )
        if not bound_operation_ids:
            binding.pending_quantity = pending
            binding.last_settle_at = resolve_business_datetime()
            await binding.save()
            await AutoReportService._append_log(
                tenant_id,
                binding=binding,
                level="info",
                event="skip",
                message="MES 设备未在工序主数据中设为默认设备，请先在工序档案绑定该设备",
                zscl=current,
                increment_qty=increment if increment > ZERO else None,
                extra={"pending": str(pending), "reason": reason},
            )
            return {"skipped": True, "reason": "no_master_ops", "pending": str(pending)}

        candidates = await AutoReportService._find_candidate_ops(
            tenant_id,
            equipment_id=int(binding.equipment_id),
            bound_operation_ids=bound_operation_ids,
        )
        if not candidates:
            binding.pending_quantity = pending
            binding.last_settle_at = resolve_business_datetime()
            await binding.save()
            await AutoReportService._append_log(
                tenant_id,
                binding=binding,
                level="info",
                event="skip",
                message="工序已绑定该设备，但进行中工单未派给该设备或未派工人",
                zscl=current,
                increment_qty=increment if increment > ZERO else None,
                extra={
                    "pending": str(pending),
                    "reason": reason,
                    "masterOperationCount": len(bound_operation_ids),
                },
            )
            return {"skipped": True, "reason": "no_task", "pending": str(pending)}

        best_wo, best_op = candidates[0]
        in_progress_hits = [
            (wo, op) for wo, op in candidates if AutoReportService._wo_in_progress(wo)
        ]
        if len(in_progress_hits) > 1:
            await AutoReportService._append_log(
                tenant_id,
                binding=binding,
                level="info",
                event="BIND",
                message=(
                    "当前设备命中多条生产中任务，已按计划开始时间自动选择，"
                    f"candidateCount={len(in_progress_hits)}"
                ),
                work_order_id=int(best_wo.id),
                work_order_code=best_wo.code,
                operation_id=int(best_op.operation_id) if best_op.operation_id else None,
                extra={
                    "candidateCount": len(in_progress_hits),
                    "selected": best_wo.code,
                },
            )

        bound_wo_id = binding.bound_work_order_id
        bound_pair = next(
            ((wo, op) for wo, op in candidates if bound_wo_id and int(wo.id) == int(bound_wo_id)),
            None,
        )
        changeover = should_changeover(
            has_bound=bool(bound_wo_id),
            bound_still_candidate=bound_pair is not None,
            bound_in_progress=bool(bound_pair and AutoReportService._wo_in_progress(bound_pair[0])),
            bound_product_id=(
                int(bound_pair[0].product_id)
                if bound_pair and bound_pair[0].product_id
                else binding.bound_product_id
            ),
            best_in_progress=AutoReportService._wo_in_progress(best_wo),
            best_wo_id=int(best_wo.id),
            best_product_id=int(best_wo.product_id) if best_wo.product_id else None,
            bound_wo_id=int(bound_wo_id or 0),
        )

        if changeover:
            reported_ids: list[int] = []
            reported_qty = ZERO
            abandoned = ZERO
            if bound_pair and pending > ZERO:
                old_wo, old_op = bound_pair
                rem = await AutoReportService._remaining_for_op(tenant_id, old_wo, old_op)
                take = rem if rem < pending else pending
                if take > ZERO:
                    reported_ids, reported_qty, _ = await AutoReportService._report_pairs(
                        tenant_id,
                        config=config,
                        binding=binding,
                        pairs=[(old_wo, old_op, take)],
                        current=current,
                        reason=reason,
                        event="changeover",
                    )
                abandoned = pending - reported_qty
                if abandoned > ZERO:
                    await AutoReportService._append_log(
                        tenant_id,
                        binding=binding,
                        level="info",
                        event="changeover",
                        message=(
                            f"切单：旧单按可报量结 {reported_qty}，"
                            f"剩余 {abandoned} 不转入新工单"
                        ),
                        zscl=current,
                        increment_qty=abandoned,
                        work_order_id=int(old_wo.id),
                        work_order_code=old_wo.code,
                        operation_id=int(old_op.operation_id) if old_op.operation_id else None,
                        extra={"reason": reason, "abandoned": str(abandoned)},
                    )
            elif bound_wo_id and pending > ZERO and bound_pair is None:
                abandoned = pending
                await AutoReportService._append_log(
                    tenant_id,
                    binding=binding,
                    level="info",
                    event="changeover",
                    message="旧任务已不在可报工集合，增量不转入新工单，仅对齐新任务基线",
                    zscl=current,
                    increment_qty=pending,
                    extra={"old_work_order_id": bound_wo_id, "reason": reason},
                )
            AutoReportService._apply_bind(binding, best_wo, best_op)
            binding.last_zscl = current
            # 切单不把旧产品剩余带给新任务
            binding.pending_quantity = ZERO
            binding.last_settle_at = resolve_business_datetime()
            if force_flush and reason.startswith("offline"):
                binding.offline_flushed = True
            await binding.save()
            await AutoReportService._append_log(
                tenant_id,
                binding=binding,
                level="info",
                event="BIND",
                message=f"切单后绑定新任务 {best_wo.code}，基线已对齐",
                zscl=current,
                work_order_id=int(best_wo.id),
                work_order_code=best_wo.code,
                operation_id=int(best_op.operation_id) if best_op.operation_id else None,
                extra={"reason": reason, "abandoned": str(abandoned)},
            )
            return {
                "changeover": True,
                "reported": len(reported_ids),
                "qty": str(reported_qty),
                "pending": "0",
                "abandoned": str(abandoned),
                "record_ids": reported_ids,
            }

        target_wo, target_op = bound_pair if bound_pair else (best_wo, best_op)
        AutoReportService._apply_bind(binding, target_wo, target_op)

        product_id = int(target_wo.product_id) if target_wo.product_id else None
        target_operation_id = int(target_op.operation_id) if target_op.operation_id else None
        same_product = [
            (wo, op)
            for wo, op in candidates
            if product_id is not None
            and wo.product_id
            and int(wo.product_id) == product_id
            and int(wo.id) != int(target_wo.id)
            and target_operation_id is not None
            and op.operation_id
            and int(op.operation_id) == target_operation_id
        ]
        same_product.sort(
            key=lambda item: candidate_fill_sort_key(
                AutoReportService._planned_start(item[0], item[1]),
                int(item[0].id or 0),
            )
        )
        queue = [(target_wo, target_op), *same_product]

        should_report = force_flush or config.report_mode == MODE_REALTIME
        if not should_report and config.report_mode == MODE_PLAN_OFFLINE:
            rem = await AutoReportService._remaining_for_op(tenant_id, target_wo, target_op)
            if pending >= rem > ZERO:
                should_report = True

        if not should_report:
            binding.pending_quantity = pending
            binding.last_settle_at = resolve_business_datetime()
            await binding.save()
            await AutoReportService._append_log(
                tenant_id,
                binding=binding,
                level="info",
                event="accumulate",
                message="计划量/断链模式：仅累计待报数量",
                zscl=current,
                increment_qty=increment if increment > ZERO else None,
                work_order_id=int(target_wo.id),
                work_order_code=target_wo.code,
                operation_id=int(target_op.operation_id) if target_op.operation_id else None,
                extra={"pending": str(pending), "reason": reason},
            )
            return {"accumulated": True, "pending": str(pending)}

        if pending <= ZERO:
            binding.last_settle_at = resolve_business_datetime()
            await binding.save()
            return {"skipped": True, "reason": "no_pending"}

        remainings: list[Decimal] = []
        for wo, op in queue:
            rem = await AutoReportService._remaining_for_op(tenant_id, wo, op)
            remainings.append(rem)
        # 不强制超报：每张只报到可报量，剩余挂 pending 等下一张同条件工单
        allocs = allocate_increment(pending, remainings, last_takes_overflow=False)
        pairs = [
            (wo, op, qty) for (wo, op), qty in zip(queue, allocs) if qty > ZERO
        ]
        planned_alloc = sum(allocs, ZERO)
        if planned_alloc > ZERO:
            await AutoReportService._append_log(
                tenant_id,
                binding=binding,
                level="info",
                event="allocate",
                message=(
                    f"按计划量分摊：待报 {pending}，"
                    f"本次分配 {planned_alloc} 到 {len(pairs)} 张工单，"
                    f"剩余 {pending - planned_alloc}"
                ),
                zscl=current,
                increment_qty=planned_alloc,
                work_order_id=int(target_wo.id),
                work_order_code=target_wo.code,
                operation_id=target_operation_id,
                extra={
                    "reason": reason,
                    "queueSize": len(queue),
                    "allocs": [str(a) for a in allocs],
                    "remainings": [str(r) for r in remainings],
                },
            )

        if not pairs:
            binding.pending_quantity = pending
            binding.last_settle_at = resolve_business_datetime()
            await binding.save()
            await AutoReportService._append_log(
                tenant_id,
                binding=binding,
                level="info",
                event="accumulate",
                message="候选工单本道工序已无可报量，待报数量继续挂起",
                zscl=current,
                increment_qty=pending,
                work_order_id=int(target_wo.id),
                work_order_code=target_wo.code,
                operation_id=target_operation_id,
                extra={"pending": str(pending), "reason": reason},
            )
            return {"accumulated": True, "pending": str(pending), "reason": "no_remaining"}

        reported_ids, reported_qty, last_ok = await AutoReportService._report_pairs(
            tenant_id,
            config=config,
            binding=binding,
            pairs=pairs,
            current=current,
            reason=reason,
        )
        if last_ok:
            AutoReportService._apply_bind(binding, last_ok[0], last_ok[1])

        leftover = pending - reported_qty
        binding.pending_quantity = leftover if leftover > ZERO else ZERO
        binding.last_settle_at = resolve_business_datetime()
        if force_flush and reason.startswith("offline"):
            binding.offline_flushed = True
        await binding.save()
        if leftover > ZERO:
            await AutoReportService._append_log(
                tenant_id,
                binding=binding,
                level="info",
                event="accumulate",
                message=(
                    f"已按可报量报工 {reported_qty}，剩余 {leftover} 挂待报；"
                    "有同产品同工序进行中工单时下轮继续顺延"
                ),
                zscl=current,
                increment_qty=leftover,
                work_order_id=int(binding.bound_work_order_id)
                if binding.bound_work_order_id
                else None,
                work_order_code=binding.bound_work_order_code,
                operation_id=binding.bound_operation_id,
                extra={"pending": str(leftover), "reported": str(reported_qty), "reason": reason},
            )
        return {
            "reported": len(reported_ids),
            "qty": str(reported_qty),
            "pending": str(binding.pending_quantity),
            "record_ids": reported_ids,
        }

    @staticmethod
    async def settle_tenant(tenant_id: int, *, force: bool = False) -> dict[str, Any]:
        config = await AutoReportService.get_or_create_config(tenant_id)
        if not config.is_enabled and not force:
            return {"tenant_id": tenant_id, "skipped": True, "reason": "disabled"}
        if not config.reporter_user_id:
            return {"tenant_id": tenant_id, "skipped": True, "reason": "no_reporter"}

        bindings = await RelayAutoReportBinding.filter(
            tenant_id=tenant_id, deleted_at__isnull=True, is_enabled=True
        ).all()
        if not bindings:
            return {"tenant_id": tenant_id, "skipped": True, "reason": "no_bindings"}

        now = resolve_business_datetime()
        interval = max(1, int(config.interval_minutes or 5))
        iot_map = {
            int(d.id): d
            for d in await IotDevice.filter(
                tenant_id=tenant_id,
                id__in=[int(b.iot_device_id) for b in bindings],
                deleted_at__isnull=True,
            )
        }
        results = []
        for binding in bindings:
            due = True
            if binding.last_settle_at and not force:
                due = binding.last_settle_at <= now - timedelta(minutes=interval)
            offline_force = False
            if config.report_mode == MODE_PLAN_OFFLINE:
                iot = iot_map.get(int(binding.iot_device_id))
                last_seen = (iot.last_seen_at if iot else None) or binding.last_seen_at
                threshold = max(30, int(config.offline_threshold_seconds or 180))
                stale = bool(last_seen and last_seen <= now - timedelta(seconds=threshold))
                device_offline = bool(iot and not iot.is_online and last_seen)
                if (
                    (stale or device_offline)
                    and not binding.offline_flushed
                    and Decimal(str(binding.pending_quantity or 0)) > ZERO
                ):
                    offline_force = True
                    due = True
            if not due:
                continue
            try:
                outcome = await AutoReportService.settle_binding(
                    tenant_id,
                    binding,
                    config,
                    force_flush=offline_force or force,
                    reason="offline" if offline_force else ("force" if force else "tick"),
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("ind_relay settle binding {} failed: {}", binding.id, exc)
                outcome = {"error": str(exc)}
            results.append({"binding_id": binding.id, **outcome})
        return {"tenant_id": tenant_id, "bindings": len(bindings), "results": results}

    @staticmethod
    async def settle_all_tenants() -> dict[str, Any]:
        from core.models.application import Application

        tenant_ids = (
            await Application.filter(
                code="ind-relay",
                is_installed=True,
                is_active=True,
                deleted_at__isnull=True,
            )
            .distinct()
            .values_list("tenant_id", flat=True)
        )
        summaries = []
        for tid in tenant_ids:
            try:
                summaries.append(await AutoReportService.settle_tenant(int(tid)))
            except Exception as exc:  # noqa: BLE001
                logger.exception("ind_relay auto report tenant {} failed: {}", tid, exc)
                summaries.append({"tenant_id": int(tid), "error": str(exc)})
        return {"tenants": len(tenant_ids), "items": summaries}
