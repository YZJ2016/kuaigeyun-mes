"""
质检执行公共 helpers（来料/过程/成品/委外/巡检/OQC 共用）。

分类型 Service 类体在独立文件；本模块禁止再挂 Incoming/Process/Finished 类定义。
旧入口 `quality_service` 再导出本模块符号以保持 import 兼容。
"""

from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
import json
from tortoise.transactions import in_transaction
from tortoise.expressions import Q
from loguru import logger

from apps.kuaizhizao.models.incoming_inspection import IncomingInspection
from apps.kuaizhizao.models.process_inspection import ProcessInspection
from apps.kuaizhizao.models.finished_goods_inspection import FinishedGoodsInspection

from apps.kuaizhizao.schemas.quality import (
    # 来料检验单
    IncomingInspectionCreate,
    IncomingInspectionUpdate,
    IncomingInspectionResponse,
    IncomingInspectionListResponse,
    EnsureIqcForPurchaseReceiptResponse,
    EnsureIqcForPurchaseReceiptLineSummary,
    EnsureIqcForCustomerMaterialRegistrationResponse,
    EnsureFqcForFinishedGoodsReceiptResponse,
    EnsureFqcForFinishedGoodsReceiptLineSummary,
    # 过程检验单
    ProcessInspectionCreate, ProcessInspectionUpdate, ProcessInspectionResponse, ProcessInspectionListResponse,
    # 成品检验单
    FinishedGoodsInspectionCreate, FinishedGoodsInspectionUpdate, FinishedGoodsInspectionResponse, FinishedGoodsInspectionListResponse,
)

from apps.common.base_service import AppBaseService
from apps.kuaizhizao.services.inspection_policy_service import (
    iqc_inspection_passed_for_inbound,
    fqc_inspection_passed_for_inbound,
    resolve_iqc_plan_label_for_material,
    resolve_fqc_plan_label_for_material,
    InspectionStage,
    get_quality_effective_config,
    get_quality_inspection_stage_toggles,
    resolve_inspection_policy,
    build_material_policy_cache,
    stage_plan_type,
)
from core.utils.timezone_utils import (
    resolve_business_datetime,
    to_api_isoformat,
    to_site_date,
    today_site_str,
)
from infra.exceptions.exceptions import NotFoundError, ValidationError, BusinessLogicError

from datetime import date, time as dt_time

INCOMING_INSPECTION_SORTABLE_FIELDS = frozenset({
    "inspection_code", "material_code", "material_name", "supplier_name",
    "purchase_receipt_code", "customer_material_registration_code",
    "inspection_quantity", "qualified_quantity", "unqualified_quantity",
    "inspector_name", "inspection_result", "quality_status", "status",
    "inspection_time", "created_at", "updated_at",
})
PROCESS_INSPECTION_SORTABLE_FIELDS = frozenset({
    "inspection_code", "work_order_code", "operation_name", "material_code",
    "material_name", "inspection_quantity", "qualified_quantity",
    "unqualified_quantity", "inspector_name", "inspection_result",
    "quality_status", "status", "inspection_time", "created_at", "updated_at",
})
FINISHED_GOODS_INSPECTION_SORTABLE_FIELDS = frozenset({
    "inspection_code", "work_order_code", "material_code", "material_name",
    "inspection_quantity", "qualified_quantity", "unqualified_quantity",
    "inspector_name", "inspection_result", "quality_status", "status",
    "inspection_time", "created_at", "updated_at",
})
OQC_INSPECTION_SORTABLE_FIELDS = frozenset({
    "inspection_code", "customer_name", "material_code", "material_name",
    "shipment_notice_code", "sales_delivery_code", "inspection_quantity",
    "qualified_quantity", "unqualified_quantity", "inspector_name",
    "inspection_result", "quality_status", "status", "release_decision",
    "inspection_time", "created_at", "updated_at",
})
NONCONFORMING_LEDGER_SORTABLE_FIELDS = frozenset({
    "code", "work_order_code", "operation_name", "product_code", "product_name",
    "defect_quantity", "defect_type", "defect_reason", "disposition", "status",
    "created_at", "updated_at",
})
EIGHT_D_REPORT_SORTABLE_FIELDS = frozenset({
    "report_code", "title", "severity", "owner_name", "status",
    "due_date", "created_at", "updated_at",
})


def _resolve_quality_list_order_by(
    order_by: Optional[str],
    allowed: frozenset,
    default: str,
    *,
    field_aliases: Optional[Dict[str, str]] = None,
) -> str:
    if not order_by:
        return default
    descending = str(order_by).startswith("-")
    field = str(order_by).lstrip("-")
    if field_aliases and field in field_aliases:
        field = field_aliases[field]
    if field not in allowed:
        return default
    return f"-{field}" if descending else field


def _parse_optional_api_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def apply_quality_inspection_doc_status_filter(query, status: Optional[str]) -> Any:
    """
    钉住 Tab / 列表 status 筛选：「已检验」按 inspection_result 真源，包含已审核/待审核等单据状态。
    """
    from tortoise.expressions import Q

    raw = str(status or "").strip()
    if not raw:
        return query
    if raw == "待检验":
        return query.filter(Q(status="待检验") | Q(inspection_result="待检验"))
    if raw == "已检验":
        return query.filter(inspection_result="已检验")
    return query.filter(status=raw)


def _apply_quality_inspection_list_filters(
    query,
    filters: Dict[str, Any],
    *,
    keyword_fields: List[str],
    time_field: str = "inspection_time",
) -> Any:
    kw = (filters.get("keyword") or "").strip()
    if kw:
        q = Q()
        for field in keyword_fields:
            q |= Q(**{f"{field}__icontains": kw})
        query = query.filter(q)
    inspection_start = _parse_optional_api_date(filters.get("inspection_start_date"))
    inspection_end = _parse_optional_api_date(filters.get("inspection_end_date"))
    if inspection_start is not None:
        query = query.filter(**{f"{time_field}__gte": datetime.combine(inspection_start, dt_time.min)})
    if inspection_end is not None:
        query = query.filter(**{f"{time_field}__lte": datetime.combine(inspection_end, dt_time.max)})
    created_start = _parse_optional_api_date(filters.get("created_start_date"))
    created_end = _parse_optional_api_date(filters.get("created_end_date"))
    if created_start is not None:
        query = query.filter(created_at__gte=datetime.combine(created_start, dt_time.min))
    if created_end is not None:
        query = query.filter(created_at__lte=datetime.combine(created_end, dt_time.max))
    return query


def _customer_material_line_item_id(item: Any) -> int:
    raw_id = getattr(item, "id", None)
    if raw_id is not None and int(raw_id) > 0:
        return int(raw_id)
    line_id = getattr(item, "line_id", None)
    if line_id is not None:
        return int(line_id)
    mid = getattr(item, "material_id", None)
    if mid is not None:
        return int(mid)
    return 0


def _filter_items_by_selected_item_ids(
    items: List[Any],
    selected_item_ids: Optional[List[int]],
    *,
    id_getter,
) -> List[Any]:
    if selected_item_ids is None:
        return items
    selected = {int(i) for i in selected_item_ids if i is not None}
    if not selected:
        raise BusinessLogicError("请至少选择一条明细")
    filtered = [item for item in items if id_getter(item) in selected]
    if not filtered:
        raise BusinessLogicError("所选明细均不可加载，请重新选择")
    return filtered


from datetime import timedelta
from decimal import Decimal

from apps.kuaizhizao.services.inspection_quantity_utils import assert_inspection_quantities_balanced


async def _get_quantity_decimal_places(tenant_id: int) -> int:
    from infra.services.business_config_service import BusinessConfigService

    return await BusinessConfigService().get_quantity_decimal_places(tenant_id)


async def _get_quality_policy_flags(tenant_id: int) -> tuple[bool, bool]:
    """读取质量策略开关（来料检验、过程检验）。"""
    from infra.services.business_config_service import BusinessConfigService

    cfg = await BusinessConfigService().get_business_config(tenant_id)
    quality = cfg.get("parameters", {}).get("quality", {})
    return bool(quality.get("incoming_inspection", False)), bool(quality.get("process_inspection", False))


async def _is_finished_inspection_enabled(tenant_id: int) -> bool:
    """读取成品检验开关。"""
    from infra.services.business_config_service import BusinessConfigService

    cfg = await BusinessConfigService().get_business_config(tenant_id)
    quality = cfg.get("parameters", {}).get("quality", {})
    return bool(quality.get("finished_inspection", False))


async def _is_quality_audit_required(tenant_id: int, stage_code: str) -> bool:
    """
    质检审核开关：优先读取分阶段开关，未配置时回退到总开关 quality_inspection。
    """
    from infra.services.business_config_service import BusinessConfigService

    config_service = BusinessConfigService()
    return await config_service.check_audit_required(tenant_id, stage_code)


async def _quality_inspection_initial_review_fields(
    tenant_id: int, stage_code: str
) -> Dict[str, Any]:
    """创建检验单时清空审核态（覆盖模型默认「待审核」）。

    与系统审核规范一致：关闭人工审核 = 自动通过，但通过时机对齐「提交/生效」——
    检验单对应「执行检验」(conduct)，创建时不预置已通过。
    """
    _ = tenant_id, stage_code
    return {"review_status": ""}


async def _quality_inspection_conduct_finalize_fields(
    tenant_id: int,
    stage_code: str,
    *,
    quality_status: str,
    inspected_by: int,
    inspector_name: str,
) -> Dict[str, Any]:
    """执行检验后的审核字段（系统规范）。

    - 开启人工审核：进入待审核，由人审/驳
    - 未开启人工审核：自动通过审核（非跳过）；合格件业务态落「已审核」，
      不合格件业务态保持「已检验」以便缺陷/退货，审核列仍为已通过
    """
    from apps.kuaizhizao.constants import ReviewStatus

    fields: Dict[str, Any] = {"status": "已检验"}
    if await _is_quality_audit_required(tenant_id, stage_code):
        fields["review_status"] = ReviewStatus.PENDING.value
        return fields

    # 关闭人工审核：执行检验后自动通过
    fields.update(
        {
            "review_status": ReviewStatus.APPROVED,
            "reviewer_id": inspected_by,
            "reviewer_name": inspector_name,
            "review_time": resolve_business_datetime(),
        }
    )
    if quality_status == "合格":
        fields["status"] = "已审核"
    return fields


async def _start_quality_inspection_approval_after_conduct(
    *,
    tenant_id: int,
    user_id: int,
    stage_code: str,
    inspection: Any,
    doc_label: str,
) -> Any | None:
    """开审时执行检验进入待审后必须创建审批实例。

    返回审批实例；空审批人 auto_pass 等可能导致提交瞬间已通过，
    调用方须据此同步落业务审核（与销售订单 submit 契约一致）。
    """
    if not await _is_quality_audit_required(tenant_id, stage_code):
        return None
    from core.services.approval.audit_flow_guard import start_document_approval_or_raise

    code = getattr(inspection, "inspection_code", None) or str(inspection.id)
    return await start_document_approval_or_raise(
        tenant_id=tenant_id,
        user_id=user_id,
        node_key=stage_code,
        entity_type=stage_code,
        entity_id=int(inspection.id),
        entity_uuid=str(inspection.uuid),
        title=f"{doc_label}审批: {code}",
        content=f"检验单: {code}",
        doc_label=doc_label,
    )


async def _assert_quality_inspection_pending_approval(
    *,
    tenant_id: int,
    stage_code: str,
    inspection_id: int,
    doc_label: str,
    verb: str,
    is_auto_approve: bool = False,
) -> None:
    """审核已开时须有进行中流程；auto_pass 完成写回或补齐已通过实例时放行。"""
    if is_auto_approve:
        return
    audit_required = await _is_quality_audit_required(tenant_id, stage_code)
    if not audit_required:
        return
    from core.services.approval.audit_flow_guard import (
        assert_manual_approval_action_allowed,
        get_approval_gate_status,
    )

    gate = await get_approval_gate_status(
        tenant_id=tenant_id,
        entity_type=stage_code,
        entity_id=inspection_id,
    )
    assert_manual_approval_action_allowed(
        gate,
        doc_label=doc_label,
        verb=verb,
        is_auto_approve=is_auto_approve,
    )


async def _require_iqc_stage_enabled(tenant_id: int) -> None:
    """组织级 IQC 总开关（TenantConfig）；关闭时禁止创建/下推来料检。"""
    t = await get_quality_inspection_stage_toggles(tenant_id)
    if not t.get("iqc_enabled", True):
        raise BusinessLogicError("当前组织已关闭来料检验（IQC）环节，禁止创建或下推来料检验单")


_PURCHASE_RECEIPT_IQC_ELIGIBLE_STATUSES = frozenset({
    "待入库", "已入库", "草稿", "draft", "DRAFT",
})


def _purchase_receipt_allows_iqc_creation(receipt: Any) -> bool:
    return str(getattr(receipt, "status", "") or "").strip() in _PURCHASE_RECEIPT_IQC_ELIGIBLE_STATUSES


_CUSTOMER_MATERIAL_IQC_ELIGIBLE_STATUSES = frozenset({"pending", "processed"})


def _customer_material_allows_iqc_creation(registration: Any) -> bool:
    return str(getattr(registration, "status", "") or "").strip() in _CUSTOMER_MATERIAL_IQC_ELIGIBLE_STATUSES


_FINISHED_GOODS_RECEIPT_FQC_ELIGIBLE_STATUSES = frozenset({
    "待入库", "已入库", "草稿", "draft", "DRAFT",
})


def _finished_goods_receipt_allows_fqc_creation(receipt: Any) -> bool:
    return str(getattr(receipt, "status", "") or "").strip() in _FINISHED_GOODS_RECEIPT_FQC_ELIGIBLE_STATUSES


def _semi_finished_goods_receipt_allows_fqc_creation(receipt: Any) -> bool:
    return _finished_goods_receipt_allows_fqc_creation(receipt)


async def _collect_fqc_required_material_ids(tenant_id: int, lines: List[Any]) -> List[int]:
    """成品入库明细中 fqc 策略≠none 且数量>0 的物料 ID（去重保序）。"""
    candidate_mids: List[int] = []
    for item in lines:
        mid = getattr(item, "material_id", None)
        if not mid:
            continue
        qty = getattr(item, "receipt_quantity", None) or getattr(item, "qualified_quantity", None) or 0
        try:
            if float(qty) <= 0:
                continue
        except (TypeError, ValueError):
            continue
        candidate_mids.append(int(mid))
    policy_cache = await build_material_policy_cache(tenant_id, candidate_mids, "fqc")

    needs_qc_mids: List[int] = []
    seen: set[int] = set()
    for item in lines:
        mid = getattr(item, "material_id", None)
        if not mid:
            continue
        qty = getattr(item, "receipt_quantity", None) or getattr(item, "qualified_quantity", None) or 0
        try:
            if float(qty) <= 0:
                continue
        except (TypeError, ValueError):
            continue
        mid_int = int(mid)
        if mid_int in seen:
            continue
        if policy_cache.get(mid_int, ("none", None, ""))[0] == "none":
            continue
        seen.add(mid_int)
        needs_qc_mids.append(mid_int)
    return needs_qc_mids


async def _ensure_fqc_for_work_order(
    tenant_id: int,
    work_order_id: int,
    created_by: int,
) -> Optional[FinishedGoodsInspectionResponse]:
    """补齐工单成品检验单（已有则返回，缺失则创建）。"""
    existing = await FinishedGoodsInspection.filter(
        tenant_id=tenant_id,
        work_order_id=work_order_id,
        deleted_at__isnull=True,
    ).order_by("-id").first()
    if existing:
        return FinishedGoodsInspectionResponse.model_validate(existing)

    from apps.kuaizhizao.services.finished_goods_inspection_service import (
        FinishedGoodsInspectionService,
    )
    svc = FinishedGoodsInspectionService()
    try:
        return await svc.create_inspection_from_work_order(
            tenant_id=tenant_id,
            work_order_id=work_order_id,
            created_by=created_by,
        )
    except BusinessLogicError as e:
        msg = str(e)
        if "pull_from_work_order.no_remaining" in msg or "already_pulled" in msg:
            pending = await FinishedGoodsInspection.filter(
                tenant_id=tenant_id,
                work_order_id=work_order_id,
                deleted_at__isnull=True,
            ).exclude(status="已取消").order_by("-id").first()
            if pending:
                return FinishedGoodsInspectionResponse.model_validate(pending)
        if "无质检" in msg or "无需下推" in msg or "no_inspection_required" in msg:
            return None
        raise


async def _collect_iqc_required_material_ids(tenant_id: int, lines: List[Any]) -> List[int]:
    """采购入库明细中 iqc 策略≠none 且数量>0 的物料 ID（去重保序）。"""
    candidate_mids: List[int] = []
    for item in lines:
        mid = getattr(item, "material_id", None)
        if not mid:
            continue
        qty = getattr(item, "receipt_quantity", None) or getattr(item, "quantity", None) or 0
        try:
            if float(qty) <= 0:
                continue
        except (TypeError, ValueError):
            continue
        candidate_mids.append(int(mid))
    policy_cache = await build_material_policy_cache(tenant_id, candidate_mids, "iqc")

    needs_qc_mids: List[int] = []
    seen: set[int] = set()
    for item in lines:
        mid = getattr(item, "material_id", None)
        if not mid:
            continue
        qty = getattr(item, "receipt_quantity", None) or getattr(item, "quantity", None) or 0
        try:
            if float(qty) <= 0:
                continue
        except (TypeError, ValueError):
            continue
        mid_int = int(mid)
        if mid_int in seen:
            continue
        if policy_cache.get(mid_int, ("none", None, ""))[0] == "none":
            continue
        seen.add(mid_int)
        needs_qc_mids.append(mid_int)
    return needs_qc_mids


async def _require_ipqc_stage_enabled(tenant_id: int) -> None:
    """组织级 IPQC 总开关。"""
    t = await get_quality_inspection_stage_toggles(tenant_id)
    if not t.get("ipqc_enabled", True):
        raise BusinessLogicError("当前组织已关闭过程检验（IPQC）环节，禁止创建或下推过程检验单")


async def _require_fqc_stage_enabled(tenant_id: int) -> None:
    """组织级 FQC 总开关。"""
    t = await get_quality_inspection_stage_toggles(tenant_id)
    if not t.get("fqc_enabled", True):
        raise BusinessLogicError("当前组织已关闭成品检验（FQC）环节，禁止创建或下推成品检验单")


def _work_order_product_fields(work_order: Any) -> Dict[str, Any]:
    """工单产品物料字段（product_* 与历史 material_* 兼容）。"""
    from apps.kuaizhizao.services.work_order_tracking_service import WorkOrderTrackingService

    mid = getattr(work_order, "product_id", None) or getattr(work_order, "material_id", None)
    code = getattr(work_order, "product_code", None) or getattr(work_order, "material_code", None)
    name = getattr(work_order, "product_name", None) or getattr(work_order, "material_name", None)
    spec = getattr(work_order, "material_spec", None) or getattr(work_order, "product_spec", None)
    batch = WorkOrderTrackingService.effective_batch_no(work_order)
    serial = WorkOrderTrackingService.effective_serial_no(work_order)
    qty = getattr(work_order, "quantity", None) or getattr(work_order, "planned_quantity", None)
    return {
        "material_id": mid,
        "material_code": code,
        "material_name": name,
        "material_spec": spec,
        "batch_number": batch,
        "serial_number": serial,
        "planned_qty": qty,
    }


async def _resolve_material_base_unit(tenant_id: int, material_id: Any) -> str:
    """检验数量存储单位：物料基础单位名称（禁止落编码）。"""
    try:
        mid = int(material_id)
    except (TypeError, ValueError):
        return "个"
    if mid <= 0:
        return "个"
    from apps.master_data.models.material import Material
    from apps.master_data.services.sync_association_service import material_snapshot_unit_name

    mat = await Material.get_or_none(
        tenant_id=tenant_id,
        id=mid,
        deleted_at__isnull=True,
    )
    return await material_snapshot_unit_name(tenant_id, mat)


async def _ensure_inspection_material_unit(
    tenant_id: int,
    payload: Dict[str, Any],
) -> None:
    """建单/开展前补齐 material_unit（基础单位名称）。"""
    from apps.master_data.services.sync_association_service import canonicalize_business_unit_name

    unit = str(payload.get("material_unit") or "").strip()
    if unit:
        payload["material_unit"] = await canonicalize_business_unit_name(tenant_id, unit)
        return
    mid = payload.get("material_id")
    payload["material_unit"] = await _resolve_material_base_unit(tenant_id, mid)


async def _ensure_inspection_material_spec_model(
    tenant_id: int,
    payload: Dict[str, Any],
) -> None:
    """建单前补齐物料规格/型号快照（仅填空，不覆盖已有值）。"""
    mid = payload.get("material_id")
    if not mid:
        return
    need_spec = not str(payload.get("material_spec") or "").strip()
    need_model = not str(payload.get("material_model") or "").strip()
    if not need_spec and not need_model:
        return
    from apps.master_data.models.material import Material

    mat = await Material.get_or_none(tenant_id=tenant_id, id=int(mid))
    if not mat:
        return
    if need_spec:
        payload["material_spec"] = getattr(mat, "specification", None)
    if need_model:
        payload["material_model"] = getattr(mat, "model", None)


def _summarize_pull_preview_items(preview_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """加载候选：明细行数、可加载行数、物料摘要（供取单弹窗展示）。"""
    pushable_count = sum(
        1 for row in preview_items if float(row.get("max_push_quantity") or 0) > 0
    )
    needs_temporary_plan = any(
        float(row.get("max_push_quantity") or 0) > 0 and bool(row.get("needs_temporary_plan"))
        for row in preview_items
    )
    material_labels: List[str] = []
    seen: set[str] = set()
    for row in preview_items:
        label = str(row.get("material_name") or row.get("material_code") or "").strip()
        if not label or label in seen:
            continue
        seen.add(label)
        material_labels.append(label)
    summary = "、".join(material_labels[:3])
    if len(material_labels) > 3:
        summary = f"{summary} 等{len(material_labels)}种"
    return {
        "line_count": len(preview_items),
        "pushable_line_count": pushable_count,
        "material_summary": summary or None,
        "needs_temporary_plan": needs_temporary_plan,
    }


def _apply_material_snapshots_to_preview_items(
    preview_items: List[Dict[str, Any]],
    material_snaps: Dict[int, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """用主数据物料快照补齐 preview 行上的编码/名称（兼容明细未冗余快照）。"""
    enriched: List[Dict[str, Any]] = []
    for row in preview_items:
        mid = row.get("material_id")
        code = str(row.get("material_code") or "").strip()
        name = str(row.get("material_name") or "").strip()
        if mid:
            snap = material_snaps.get(int(mid)) or {}
            code = code or str(snap.get("material_code") or "").strip()
            name = name or str(snap.get("material_name") or "").strip()
        enriched.append({**row, "material_code": code, "material_name": name})
    return enriched


async def _resolve_fqc_customer_snapshot(
    tenant_id: int,
    *,
    sales_order_id: Optional[int],
    customer_id: Optional[int] = None,
    customer_name: Optional[str] = None,
) -> Tuple[Optional[int], Optional[str]]:
    """成品检验客户快照：工单无客户字段，须从关联销售订单写入。"""
    name = str(customer_name or "").strip()
    if name:
        return customer_id, name
    if not sales_order_id:
        return customer_id, None
    from apps.kuaizhizao.models.sales_order import SalesOrder

    so = await SalesOrder.get_or_none(
        id=int(sales_order_id),
        tenant_id=tenant_id,
        deleted_at__isnull=True,
    )
    if not so:
        return customer_id, None
    resolved_name = str(so.customer_name or "").strip()
    return (int(so.customer_id), resolved_name or None) if resolved_name else (so.customer_id, None)


async def _resolve_customer_material_pull_customer_name_map(
    tenant_id: int,
    registrations: List[Any],
) -> Dict[int, str]:
    customer_ids = [
        int(r.customer_id)
        for r in registrations
        if getattr(r, "customer_id", None) and not str(getattr(r, "customer_name", "") or "").strip()
    ]
    if not customer_ids:
        return {}
    from apps.master_data.models.customer import Customer

    customers = await Customer.filter(
        tenant_id=tenant_id,
        id__in=list(set(customer_ids)),
        deleted_at__isnull=True,
    ).all()
    return {int(c.id): str(c.name or "").strip() for c in customers if c.name}


async def _load_material_snapshot_map(
    tenant_id: int,
    material_ids: List[int],
) -> Dict[int, Dict[str, Any]]:
    from apps.kuaizhizao.services.customer_material_registration_service import (
        CustomerMaterialRegistrationService,
    )

    return await CustomerMaterialRegistrationService._material_snapshot_map(
        tenant_id, material_ids
    )


def _resolve_work_order_pull_product_display(
    work_order: Any,
    wf: Dict[str, Any],
    material_snaps: Dict[int, Dict[str, Any]],
) -> Dict[str, Optional[str]]:
    """工单加载候选：补齐产品名称/编码（兼容工单未冗余物料快照）。"""
    mid = wf.get("material_id")
    code = str(wf.get("material_code") or "").strip()
    name = str(wf.get("material_name") or "").strip()
    if not name:
        name = str(
            getattr(work_order, "product_name", None)
            or getattr(work_order, "name", None)
            or ""
        ).strip()
    if mid:
        snap = material_snaps.get(int(mid)) or {}
        code = code or str(snap.get("material_code") or "").strip()
        name = name or str(snap.get("material_name") or "").strip()
    return {
        "product_name": name or None,
        "material_code": code or None,
    }


async def _resolve_inspection_template_fields(
    tenant_id: int,
    material_id: Optional[int],
    stage: InspectionStage,
    operation_id: Optional[int] = None,
    explicit_plan_id: Optional[int] = None,
    use_quality_characteristics: bool = False,
    work_order_operation: Any = None,
    force_simple_when_unset: bool = False,
) -> Dict[str, Any]:
    """按场景解析 mode/plan_id 并填充检验项模板。

    force_simple_when_unset：造数等场景——无质检或方案模式但无可用方案时，按简易质检生成模板。
    """
    from apps.kuaizhizao.models.inspection_plan import InspectionPlan, InspectionPlanStep
    from apps.kuaizhizao.models.quality_standard import QualityStandard
    from apps.kuaizhizao.services.inspection_step_spec import plan_step_to_snapshot_item
    from infra.exceptions.exceptions import ConflictError

    if not material_id:
        return {}

    plan_type = stage_plan_type(stage)
    mode, resolved_plan_id, _ = await resolve_inspection_policy(
        tenant_id,
        stage,
        material_id=material_id,
        operation_id=operation_id,
        work_order_operation=work_order_operation,
    )
    # 临时指定方案（如已入库补检）：物料未配置 IQC 时仍可按所选方案生成检验项
    if mode == "none":
        if force_simple_when_unset:
            mode = "simple"
        elif not explicit_plan_id:
            return {}
        else:
            mode = "plan"

    def _items_field(items_payload: dict) -> Dict[str, Any]:
        if use_quality_characteristics:
            return {"quality_characteristics": items_payload}
        return {"other_checks": items_payload}

    plan_id = explicit_plan_id or resolved_plan_id

    if mode == "plan":
        plan = None
        if plan_id:
            plan = await InspectionPlan.filter(
                tenant_id=tenant_id, id=plan_id, deleted_at__isnull=True, is_active=True
            ).first()
            if plan and str(plan.plan_type) != plan_type:
                from apps.kuaizhizao.services.inspection_policy_service import (
                    plan_type_display_label,
                    stage_display_label,
                )

                hint = (
                    "请在工序主数据或工艺路线上改选过程检验方案。"
                    if stage == "ipqc"
                    else "请在物料主数据上改选与当前检验环节类型一致的方案。"
                )
                raise ConflictError(
                    f"质检方案 {plan.plan_code} 类型为{plan_type_display_label(plan.plan_type)}，"
                    f"与当前{stage_display_label(stage)}所需{plan_type_display_label(plan_type)}不一致。"
                    f"{hint}"
                )
        if not plan:
            plan = await InspectionPlan.filter(
                tenant_id=tenant_id,
                material_id=material_id,
                plan_type=plan_type,
                deleted_at__isnull=True,
                is_active=True,
            ).order_by("-created_at").first()
        if plan:
            steps = await InspectionPlanStep.filter(plan_id=plan.id).order_by("sequence").all()
            items: List[Dict[str, Any]] = []
            for step in steps:
                item: Dict[str, Any] = plan_step_to_snapshot_item(step)
                if step.quality_standard_id:
                    std = await QualityStandard.get_or_none(
                        tenant_id=tenant_id, id=step.quality_standard_id, deleted_at__isnull=True
                    )
                    if std:
                        item["standard"] = {
                            "standard_code": std.standard_code,
                            "inspection_items": std.inspection_items,
                            "acceptance_criteria": std.acceptance_criteria,
                        }
                items.append(item)
            payload = {
                "plan_id": plan.id,
                "plan_code": plan.plan_code,
                "plan_name": plan.plan_name,
                "plan_version": plan.version,
                "items": items,
            }
            return {
                "inspection_standard": f"{plan.plan_name} ({plan.plan_code})",
                **_items_field(payload),
            }
        if force_simple_when_unset:
            mode = "simple"

    if mode == "simple":
        std = await QualityStandard.filter(
            tenant_id=tenant_id,
            material_id=material_id,
            standard_type=plan_type,
            is_active=True,
            deleted_at__isnull=True,
        ).order_by("-created_at").first()
        if not std:
            std = await QualityStandard.filter(
                tenant_id=tenant_id,
                material_id__isnull=True,
                standard_type=plan_type,
                is_active=True,
                deleted_at__isnull=True,
            ).order_by("-created_at").first()
        if std:
            from apps.kuaizhizao.services.inspection_step_spec import quality_standard_to_template_items

            structured = quality_standard_to_template_items(std)
            if structured:
                payload = {"standard_id": std.id, "items": structured}
                return {
                    "inspection_standard": f"{std.standard_name} ({std.standard_code})",
                    **_items_field(payload),
                }
            methods = std.inspection_methods
            first_method = methods[0] if isinstance(methods, list) and methods else None
            payload = {
                "standard_id": std.id,
                "inspection_items": std.inspection_items,
                "inspection_methods": std.inspection_methods,
                "acceptance_criteria": std.acceptance_criteria,
            }
            return {
                "inspection_standard": f"{std.standard_name} ({std.standard_code})",
                "inspection_method": first_method,
                **_items_field(payload),
            }
    return {}


async def _apply_explicit_inspection_plan_to_inspection_row(
    tenant_id: int,
    row: Any,
    inspection_plan_id: int,
    stage: InspectionStage,
    *,
    updated_by: int,
    updated_by_name: str,
) -> None:
    """待检验单据按指定方案重建检验项快照。"""
    from apps.kuaizhizao.services.document_action_policy.types import CAPABILITY_REASON_MESSAGES

    material_id = getattr(row, "material_id", None)
    if not material_id:
        raise BusinessLogicError("检验单缺少物料，无法切换检验方案")
    use_qc = stage == "ipqc"
    operation_id = getattr(row, "operation_id", None) if use_qc else None
    template = await _resolve_inspection_template_fields(
        tenant_id,
        int(material_id),
        stage,
        operation_id=operation_id,
        explicit_plan_id=int(inspection_plan_id),
        use_quality_characteristics=use_qc,
    )
    if not template:
        raise BusinessLogicError(
            CAPABILITY_REASON_MESSAGES["quality_inspection.apply_plan.invalid"],
        )
    if template.get("inspection_standard") is not None:
        row.inspection_standard = template["inspection_standard"]
    if "inspection_method" in template:
        row.inspection_method = template.get("inspection_method")
    if template.get("other_checks") is not None:
        row.other_checks = template["other_checks"]
    if template.get("quality_characteristics") is not None:
        row.quality_characteristics = template["quality_characteristics"]
        snap = template["quality_characteristics"]
        if isinstance(snap, dict) and snap.get("plan_id"):
            row.inspection_plan_id = int(snap["plan_id"])
    row.updated_by = updated_by
    row.updated_by_name = updated_by_name
    await row.save()


async def _enrich_inspection_template_sampling_fields(
    tenant_id: int,
    inspection_row: Any,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    from apps.kuaizhizao.services.inspection_sampling_transfer_service import (
        enrich_template_payload_resolved_sampling,
    )

    material_id = getattr(inspection_row, "material_id", None)
    lot_qty = getattr(inspection_row, "inspection_quantity", None)
    out = dict(payload)
    if out.get("other_checks") is not None:
        out["other_checks"] = await enrich_template_payload_resolved_sampling(
            tenant_id, material_id, out["other_checks"], lot_qty
        )
    if out.get("quality_characteristics") is not None:
        out["quality_characteristics"] = await enrich_template_payload_resolved_sampling(
            tenant_id, material_id, out["quality_characteristics"], lot_qty
        )
    return out


async def _apply_sampling_transfer_after_conduct(
    tenant_id: int,
    inspection_row: Any,
    *,
    lot_accepted: bool,
    template_attr: str,
) -> None:
    from apps.kuaizhizao.services.inspection_sampling_transfer_service import (
        apply_sampling_transfers_for_template,
    )

    template = getattr(inspection_row, template_attr, None)
    await apply_sampling_transfers_for_template(
        tenant_id,
        getattr(inspection_row, "material_id", None),
        template,
        lot_accepted=lot_accepted,
    )


def _validate_inspection_template_conduct(
    template_json: Any,
    conduct_data: Dict[str, Any],
    *,
    require_step_photo: bool = True,
) -> None:
    from apps.kuaizhizao.services.inspection_step_spec import validate_inspection_template_conduct

    validate_inspection_template_conduct(
        template_json, conduct_data, require_step_photo=require_step_photo
    )


def _assert_unqualified_qty_when_steps_fail(
    inspection: Any,
    template_attr: str,
    inspection_data: Dict[str, Any],
    unqualified_quantity: Any,
) -> None:
    from apps.kuaizhizao.services.inspection_step_spec import assert_unqualified_qty_when_steps_fail

    assert_unqualified_qty_when_steps_fail(
        getattr(inspection, template_attr, None),
        inspection_data,
        unqualified_quantity,
    )


async def _resolve_conduct_inspector_id(
    tenant_id: int,
    inspection_data: Dict[str, Any],
    inspected_by: int,
) -> int:
    """开展检验：优先表单检验人员（id 或 uuid），缺省为当前操作人。"""
    raw = inspection_data.get("inspector_id")
    if raw is not None and raw != "":
        try:
            inspector_id = int(raw)
        except (TypeError, ValueError):
            inspector_id = 0
        if inspector_id > 0:
            return inspector_id
    raw_uuid = inspection_data.get("inspector_uuid")
    if raw_uuid not in (None, ""):
        from infra.models.user import User

        user = await User.get_or_none(tenant_id=tenant_id, uuid=str(raw_uuid).strip())
        if user and user.id:
            return int(user.id)
    return inspected_by


_CONDUCT_PAYLOAD_SKIP_KEYS = frozenset({
    "item_results",
    "conduct_step_results",
    "qualified_quantity",
    "unqualified_quantity",
    "inspector_id",
    "inspector_name",
    "inspector_uuid",
    # C-03：IQC/IPQC/FQC 的 inspection_result 为过程态「已检验」，判定走 quality_status；
    # 禁止请求体覆盖服务端权威字段（OQC 另有专用 conduct，不走本 SKIP）
    "inspection_result",
    "quality_status",
    "status",
    # 仅当模型有 measurement_data 字段时由下方 build 写入；禁止请求体直接落入 ORM
    "measurement_data",
    "qualified_qty_with_unit",
    "unqualified_qty_with_unit",
    # 业务时刻仅由服务端 resolve_business_datetime 写入，禁止请求体覆盖
    "inspection_time",
    "review_time",
    "created_at",
    "updated_at",
})


def _apply_template_conduct_to_payload(
    inspection: Any,
    template_attr: str,
    inspection_data: dict,
    *,
    require_step_photo: bool = True,
) -> dict:
    """校验方案项并返回可写入 ORM 的 conduct 附加字段。"""
    from apps.kuaizhizao.services.inspection_step_spec import (
        apply_derived_step_results,
        build_measurement_data_from_conduct,
        merge_template_conduct_results,
    )

    template = getattr(inspection, template_attr, None)
    conduct_input = apply_derived_step_results(template, dict(inspection_data))
    _validate_inspection_template_conduct(
        template, conduct_input, require_step_photo=require_step_photo
    )
    payload = {
        k: v
        for k, v in conduct_input.items()
        if k not in _CONDUCT_PAYLOAD_SKIP_KEYS and v is not None
    }
    merged_measurement = build_measurement_data_from_conduct(template, conduct_input)
    if merged_measurement and hasattr(inspection, "measurement_data"):
        payload["measurement_data"] = merged_measurement
    if template and (
        conduct_input.get("item_results")
        or conduct_input.get("conduct_step_results")
        or conduct_input.get("measurement_data")
    ):
        payload[template_attr] = merge_template_conduct_results(template, conduct_input)
    elif "item_results" in payload:
        payload.pop("item_results", None)
    # 来料等无 measurement_data 列的模型：请求体杂项不得进入 filter().update(**payload)
    fields_map = getattr(getattr(inspection, "_meta", None), "fields_map", None)
    if isinstance(fields_map, dict) and fields_map:
        payload = {k: v for k, v in payload.items() if k in fields_map}
    return payload


def _merge_template_conduct_results(
    template_json: Any,
    conduct_data: Dict[str, Any],
) -> Any:
    from apps.kuaizhizao.services.inspection_step_spec import merge_template_conduct_results

    return merge_template_conduct_results(template_json, conduct_data)


async def _maybe_create_quality_exception_from_inspection(
    tenant_id: int,
    source_type: str,
    source_id: int,
    inspected_by: int,
    problem_description: Optional[str] = None,
    severity: str = "major",
) -> None:
    """检验不合格时自动创建质量异常（幂等真源在 ExceptionService.create_from_inspection）。"""
    from apps.kuaizhizao.services.exception_service import ExceptionService

    await ExceptionService().create_from_inspection(
        tenant_id=tenant_id,
        source_type=source_type,
        source_id=source_id,
        created_by=inspected_by,
        problem_description=problem_description,
        severity=severity,
    )


async def _maybe_record_spc_samples_from_inspection(
    tenant_id: int,
    inspection: Any,
    template_attr: str,
    inspection_data: dict,
    user_id: int,
    source_type: str,
) -> None:
    """检验含数值步骤时写入 SPC 样本（按 step_key + 物料）。"""
    from apps.kuaizhizao.schemas.quality_improvement import SPCSampleCreate
    from apps.kuaizhizao.services.inspection_step_spec import build_spc_sample_payloads
    from apps.kuaizhizao.services.quality_improvement_service import SPCService

    template = getattr(inspection, template_attr, None)
    payloads = build_spc_sample_payloads(
        template,
        inspection_data,
        material_id=getattr(inspection, "material_id", None),
        material_code=getattr(inspection, "material_code", None),
        source_type=source_type,
        source_id=getattr(inspection, "id", None),
        source_code=getattr(inspection, "inspection_code", None),
    )
    if not payloads:
        return

    spc_svc = SPCService()
    sample_time = resolve_business_datetime()
    for row in payloads:
        await spc_svc.create_sample(
            tenant_id=tenant_id,
            user_id=user_id,
            payload=SPCSampleCreate(
                characteristic_name=row["characteristic_name"],
                sample_time=sample_time,
                sample_value=row["sample_value"],
                sample_group=row.get("sample_group"),
                source_type=row.get("source_type"),
                source_id=row.get("source_id"),
                source_code=row.get("source_code"),
                remarks=row.get("remarks"),
            ),
        )

__all__ = [n for n in list(globals()) if not n.startswith("__")]
