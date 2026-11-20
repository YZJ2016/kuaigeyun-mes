"""
采购申请服务

提供采购申请相关的业务逻辑处理。

Author: RiverEdge Team
Date: 2025-02-01
"""

from datetime import datetime, date, time
from typing import List, Optional, Dict, Any, Tuple, NamedTuple

from tortoise.expressions import Q
from decimal import Decimal
from tortoise.functions import Count

from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction
from apps.kuaizhizao.constants import (
    DocumentStatus, ReviewStatus, normalize_status, 
    is_draft_status, is_pending_review_status, LEGACY_AUDITED_VALUES
)

from apps.common.base_service import AppBaseService
from infra.exceptions.exceptions import NotFoundError, ValidationError, BusinessLogicError
from infra.services.business_config_service import BusinessConfigService
from loguru import logger

from apps.kuaizhizao.models import PurchaseRequisition, PurchaseRequisitionItem, PurchaseOrder, PurchaseOrderItem
from apps.master_data.models import Supplier
from apps.master_data.models.material import Material
from apps.kuaizhizao.schemas.purchase_requisition import (
    PurchaseRequisitionCreate, PurchaseRequisitionUpdate, PurchaseRequisitionResponse,
    PurchaseRequisitionListResponse, PurchaseRequisitionItemResponse,
    ConvertToPurchaseOrderRequest,
)
from apps.kuaizhizao.schemas.purchase import PurchaseOrderCreate, PurchaseOrderItemCreate
from apps.kuaizhizao.services.purchase_service import PurchaseService
from apps.kuaizhizao.utils.document_source_types import is_purchase_requisition_source_type
from apps.kuaizhizao.utils.pull_open_line_quantity import (
    build_partial_push_qty_triplet,
    requisition_material_group_key,
)
from apps.kuaizhizao.utils.document_line_material_snapshot import (
    partner_snapshot_fields_from_source_line,
)
from apps.kuaizhizao.utils.material_source_helper import (
    SOURCE_TYPE_BUY,
    resolve_material_purchase_line_unit_price,
)
from apps.kuaizhizao.services.document_action_policy.enricher import (
    enrich_purchase_requisition_detail_capabilities,
    enrich_purchase_requisition_list_capabilities,
    purchase_requisition_has_linked_purchase_order,
)
from core.utils.timezone_utils import resolve_business_datetime, today_site_str, to_site_date
from apps.kuaizhizao.services.document_action_policy.purchase_requisition import (
    REQUISITION_DOWNSTREAM_PUSH_STATUS_VALUES,
    assert_purchase_requisition_capability,
    requisition_open_line_can_push,
)

def _default_requisition_name(requisition_code: str) -> str:
    code = (requisition_code or "").strip()
    return f"采购申请-{code}" if code else "采购申请"


def _supplier_header_contact_fields(sup: Optional[Supplier]) -> Dict[str, str]:
    """转采购订单草稿头：供应商联系人/电话（contacts 明细首条）。"""
    if not sup:
        return {}
    from apps.master_data.services.supply_chain_service import _partner_contacts_for_response

    rows = _partner_contacts_for_response(sup)
    if not rows:
        return {}
    first = rows[0]
    out: Dict[str, str] = {}
    contact = str(first.get("contact_person") or "").strip()
    phone = str(first.get("phone") or "").strip()
    if contact:
        out["supplier_contact"] = contact[:100]
    if phone:
        out["supplier_phone"] = phone[:20]
    return out


_DEFAULT_PURCHASE_TAX_RATE_PERCENT = Decimal("13")


class _RequisitionPushLinePricing(NamedTuple):
    """申请下推采购订单行。录入单价只计算一次，价类与该单价一致。"""

    stored_unit_price: Decimal
    stored_line_excl_total: Decimal
    tax_rate_percent: Decimal
    display_gross_incl: Decimal
    display_unit_price: Decimal
    price_type: str


PURCHASE_REQUISITION_SORTABLE_FIELDS = frozenset({
    "requisition_code",
    "requisition_name",
    "source_type",
    "source_code",
    "requisition_date",
    "required_date",
    "status",
    "review_status",
    "applicant_name",
    "created_at",
    "updated_at",
})


class PurchaseRequisitionService(AppBaseService[PurchaseRequisition]):
    """采购申请服务"""

    def __init__(self):
        super().__init__(PurchaseRequisition)
        self.purchase_service = PurchaseService()
        self.business_config_service = BusinessConfigService()

    async def _generate_requisition_code(self, tenant_id: int) -> str:
        """生成采购申请编码"""
        return await self.generate_code(tenant_id, "PURCHASE_REQUISITION_CODE", prefix="CGSQ")

    async def _po_items_by_requisition_item_ids(
        self, tenant_id: int, req_item_ids: List[int]
    ) -> Dict[int, PurchaseOrderItem]:
        """按申请行 id 反查采购订单明细（认 purchase_requisition / PurchaseRequisition）。"""
        if not req_item_ids:
            return {}
        po_items = await PurchaseOrderItem.filter(
            tenant_id=tenant_id,
            source_id__in=req_item_ids,
        ).all()
        po_item_by_source: Dict[int, PurchaseOrderItem] = {}
        for pi in po_items:
            if not is_purchase_requisition_source_type(getattr(pi, "source_type", None)):
                continue
            sid = int(pi.source_id or 0)
            if sid <= 0:
                continue
            existing = po_item_by_source.get(sid)
            if existing is None or pi.id > existing.id:
                po_item_by_source[sid] = pi
        return po_item_by_source

    async def _heal_requisition_links_from_downstream(
        self,
        tenant_id: int,
        requisition_id: int,
        all_items: List[PurchaseRequisitionItem],
    ) -> Dict[int, PurchaseOrderItem]:
        """
        自愈申请行 ↔ 采购订单行：
        1) POI.source_id = 申请行 id
        2) 头 source / 仍缺链时，按同单物料对齐未挂链行（修复编辑 PO 丢 source 的历史数据）
        """
        req_item_ids = [int(i.id) for i in all_items]
        po_item_by_source = await self._po_items_by_requisition_item_ids(
            tenant_id, req_item_ids
        )

        for it in all_items:
            target = po_item_by_source.get(int(it.id))
            if target and (
                not it.purchase_order_id
                or int(it.purchase_order_item_id or 0) != int(target.id)
            ):
                await it.update_from_dict({
                    "purchase_order_id": target.order_id,
                    "purchase_order_item_id": target.id,
                }).save()
                it.purchase_order_id = target.order_id
                it.purchase_order_item_id = target.id

        # 未挂链，或头链仍在但 purchase_order_item_id 已随 PO 删建失效
        needs_material_heal: List[PurchaseRequisitionItem] = []
        for it in all_items:
            if not it.purchase_order_id:
                needs_material_heal.append(it)
                continue
            poi_id = int(it.purchase_order_item_id or 0)
            if poi_id <= 0:
                needs_material_heal.append(it)
                continue
            if not await PurchaseOrderItem.exists(tenant_id=tenant_id, id=poi_id):
                needs_material_heal.append(it)

        if not needs_material_heal:
            return po_item_by_source

        pos = await PurchaseOrder.filter(
            tenant_id=tenant_id,
            source_id=requisition_id,
            deleted_at__isnull=True,
        ).all()
        linked_pos = [
            po for po in pos
            if is_purchase_requisition_source_type(getattr(po, "source_type", None))
        ]
        if not linked_pos:
            return po_item_by_source

        from collections import defaultdict

        used_poi_ids = {int(pi.id) for pi in po_item_by_source.values()}
        poi_pool: Dict[int, List[PurchaseOrderItem]] = defaultdict(list)
        for po in linked_pos:
            for poi in await PurchaseOrderItem.filter(
                tenant_id=tenant_id, order_id=po.id
            ).all():
                if int(poi.id) in used_poi_ids:
                    continue
                # 已挂其它申请行来源的明细不可被物料对齐抢走
                if is_purchase_requisition_source_type(
                    getattr(poi, "source_type", None)
                ) and int(poi.source_id or 0) > 0:
                    continue
                poi_pool[int(poi.material_id or 0)].append(poi)

        for it in needs_material_heal:
            bucket = poi_pool.get(int(it.material_id or 0)) or []
            # 优先在已挂的采购单上找同行物料
            if it.purchase_order_id:
                preferred = [
                    p for p in bucket if int(p.order_id) == int(it.purchase_order_id)
                ]
                if preferred:
                    target = preferred[0]
                    bucket.remove(target)
                elif bucket:
                    target = bucket.pop(0)
                else:
                    continue
            else:
                if not bucket:
                    continue
                target = bucket.pop(0)
            await it.update_from_dict({
                "purchase_order_id": target.order_id,
                "purchase_order_item_id": target.id,
            }).save()
            it.purchase_order_id = target.order_id
            it.purchase_order_item_id = target.id
            # 回写行源，避免下次编辑/自愈再丢
            if not target.source_id or not is_purchase_requisition_source_type(
                getattr(target, "source_type", None)
            ):
                await target.update_from_dict({
                    "source_type": "purchase_requisition",
                    "source_id": int(it.id),
                }).save()
            po_item_by_source[int(it.id)] = target

        return po_item_by_source

    async def _create_requisition_in_tx(
        self,
        tenant_id: int,
        data: PurchaseRequisitionCreate,
        created_by: int,
    ) -> int:
        """写事务内只做插入（发号在事务外，避免 generate_code 嵌套挂起）。"""
        async with in_transaction():
            req_date = data.requisition_date or date.today()
            user_info = await self.get_user_info(created_by)
            applicant_id = int(data.applicant_id) if data.applicant_id else created_by
            if data.applicant_name and str(data.applicant_name).strip():
                applicant_name = str(data.applicant_name).strip()
            elif applicant_id == created_by:
                applicant_name = user_info["name"]
            else:
                applicant_name = (await self.get_user_info(applicant_id))["name"]
            custom_name = (data.requisition_name or "").strip()
            req = await PurchaseRequisition.create(
                tenant_id=tenant_id,
                requisition_code=data.requisition_code,
                order_type=getattr(data, "order_type", None) or "标准采购",
                requisition_name=custom_name or _default_requisition_name(data.requisition_code),
                status="草稿",
                review_status=ReviewStatus.DRAFT.value,
                requisition_date=req_date,
                applicant_id=applicant_id,
                applicant_name=applicant_name,
                department_id=getattr(data, "department_id", None),
                department_name=getattr(data, "department_name", None),
                required_date=data.required_date,
                source_type=data.source_type,
                source_id=data.source_id,
                source_code=data.source_code,
                notes=data.notes,
                attachments=data.attachments,
                created_by=created_by,
                created_by_name=user_info["name"],
                updated_by=created_by,
                updated_by_name=user_info["name"],
            )

            for item_data in data.items:
                await PurchaseRequisitionItem.create(
                    tenant_id=tenant_id,
                    requisition_id=req.id,
                    material_id=item_data.material_id,
                    material_code=item_data.material_code,
                    material_name=item_data.material_name,
                    material_spec=item_data.material_spec,
                    unit=item_data.unit or "件",
                    quantity=item_data.quantity,
                    suggested_unit_price=item_data.suggested_unit_price or Decimal(0),
                    required_date=item_data.required_date or data.required_date,
                    demand_computation_item_id=item_data.demand_computation_item_id,
                    work_order_id=item_data.work_order_id,
                    work_order_code=item_data.work_order_code,
                    supplier_id=item_data.supplier_id,
                    notes=item_data.notes,
                    attachments=item_data.attachments,
                )
            return int(req.id)

    @staticmethod
    def _is_requisition_code_integrity_conflict(exc: IntegrityError) -> bool:
        msg = str(exc).lower()
        return (
            "requisition_code" in msg
            or "uidx_purchase_requisitions_tenant_req_code_active" in msg
        )

    async def create_requisition(
        self,
        tenant_id: int,
        data: PurchaseRequisitionCreate,
        created_by: int,
    ) -> PurchaseRequisitionResponse:
        """创建采购申请"""
        # 0. 检查模块是否启用
        is_enabled = await self.business_config_service.check_node_enabled(tenant_id, "purchase_request")
        if not is_enabled:
            raise BusinessLogicError("采购申请模块未启用，无法创建")
        if not data.items:
            raise BusinessLogicError("采购申请须包含至少一条明细")

        from apps.kuaizhizao.constants.purchase_order_type import (
            load_and_assert_purchase_order_type_materials,
            normalize_purchase_order_type,
        )

        order_type = normalize_purchase_order_type(getattr(data, "order_type", None))
        await load_and_assert_purchase_order_type_materials(
            tenant_id,
            order_type,
            [int(it.material_id) for it in data.items],
            document_label="采购申请",
        )
        data.order_type = order_type

        last_error: Exception | None = None
        req_id: int | None = None
        for attempt in range(5):
            code = str(data.requisition_code or "").strip()
            if not code or attempt > 0:
                data.requisition_code = await self._generate_requisition_code(tenant_id)
            try:
                req_id = await self._create_requisition_in_tx(
                    tenant_id, data, created_by
                )
                break
            except IntegrityError as exc:
                if not self._is_requisition_code_integrity_conflict(exc):
                    raise
                last_error = exc
                logger.warning(
                    "采购申请编号冲突，重试占号 attempt={} code={} err={}",
                    attempt + 1,
                    data.requisition_code,
                    exc,
                )
                data.requisition_code = ""
        if req_id is None:
            raise ValidationError(
                "采购申请编号已存在，请关闭弹窗后重新新建"
            ) from last_error

        response = await self.get_requisition_by_id(tenant_id, req_id)
        await self._finalize_document_flow_after_create(
            tenant_id=tenant_id,
            requisition_data=data,
            requisition_id=int(response.id),
            requisition_code=response.requisition_code,
            requisition_name=response.requisition_name,
            created_by=created_by,
        )
        source_type = (getattr(data, "document_flow_source_type", None) or "").strip()
        if not source_type:
            from apps.kuaizhizao.services.manual_create_auto_lifecycle import (
                apply_manual_create_auto_submit,
            )

            applied = await apply_manual_create_auto_submit(
                tenant_id=tenant_id,
                node_key="purchase_request",
                entity_id=int(response.id),
                operator_id=created_by,
            )
            if applied:
                return await self.get_requisition_by_id(tenant_id, int(response.id))
        return response

    async def _finalize_document_flow_after_create(
        self,
        tenant_id: int,
        requisition_data: "PurchaseRequisitionCreate",
        requisition_id: int,
        requisition_code: str,
        requisition_name: Optional[str],
        created_by: int,
    ) -> None:
        source_type = (getattr(requisition_data, "document_flow_source_type", None) or "").strip()
        if source_type == "demand_computation_items":
            computation_ids = getattr(requisition_data, "document_flow_demand_computation_ids", None) or []
            if not computation_ids:
                return
            from apps.kuaizhizao.services.document_push_pull_service import DocumentPushPullService

            await DocumentPushPullService().finalize_demand_computation_after_requisition_created(
                tenant_id=tenant_id,
                computation_ids=[int(v) for v in computation_ids],
                requisition_id=requisition_id,
                requisition_code=requisition_code,
                requisition_name=requisition_name,
                created_by=created_by,
            )
            return
        if source_type == "replenishment_suggestion_items":
            suggestion_ids = (
                getattr(requisition_data, "document_flow_replenishment_suggestion_ids", None) or []
            )
            if not suggestion_ids:
                return
            from apps.kuaizhizao.services.replenishment_suggestion_service import (
                ReplenishmentSuggestionService,
            )

            await ReplenishmentSuggestionService().finalize_replenishment_after_requisition_created(
                tenant_id=tenant_id,
                suggestion_ids=[int(v) for v in suggestion_ids],
                requisition_id=requisition_id,
                requisition_code=requisition_code,
                requisition_name=requisition_name,
                created_by=created_by,
            )
            return
        if source_type == "sales_order_buy_push":
            sales_order_id = getattr(requisition_data, "document_flow_sales_order_id", None)
            if not sales_order_id:
                return
            from apps.kuaizhizao.services.sales_order_purchase_push import (
                finalize_sales_order_after_requisition_created,
            )

            await finalize_sales_order_after_requisition_created(
                tenant_id=tenant_id,
                sales_order_id=int(sales_order_id),
                requisition_id=requisition_id,
                requisition_code=requisition_code,
                requisition_name=requisition_name,
                created_by=created_by,
            )

    async def get_requisition_by_id(
        self,
        tenant_id: int,
        requisition_id: int,
        *,
        viewer_id: Optional[int] = None,
    ) -> PurchaseRequisitionResponse:
        """获取采购申请详情"""
        req = await PurchaseRequisition.get_or_none(
            tenant_id=tenant_id, id=requisition_id, deleted_at__isnull=True
        )
        if not req:
            raise NotFoundError(f"采购申请不存在: {requisition_id}")

        items = await PurchaseRequisitionItem.filter(
            tenant_id=tenant_id, requisition_id=requisition_id
        ).all()

        material_ids = sorted(
            {
                int(i.material_id)
                for i in items
                if getattr(i, "material_id", None) is not None
            }
        )
        material_rows = (
            await Material.filter(tenant_id=tenant_id, id__in=material_ids).all()
            if material_ids
            else []
        )
        material_by_id: Dict[int, Material] = {m.id: m for m in material_rows}



        async def _build_item_resps(items_list, clear_orphan: bool = False):
            resps = []
            cleared = False
            for i in items_list:
                d = {k: getattr(i, k) for k in i._meta.fields_map if hasattr(i, k)}
                material = material_by_id.get(int(i.material_id)) if getattr(i, "material_id", None) is not None else None
                repaired_fields: Dict[str, Any] = {}
                if material:
                    if not str(d.get("material_code") or "").strip():
                        candidate_code = (
                            getattr(material, "main_code", None)
                            or getattr(material, "code", None)
                            or ""
                        )
                        if candidate_code:
                            repaired_fields["material_code"] = str(candidate_code)
                    if not str(d.get("material_name") or "").strip() and getattr(material, "name", None):
                        repaired_fields["material_name"] = str(material.name)
                    if not str(d.get("material_spec") or "").strip() and getattr(material, "specification", None):
                        repaired_fields["material_spec"] = str(material.specification)
                    if not str(d.get("unit") or "").strip() and getattr(material, "base_unit", None):
                        repaired_fields["unit"] = str(material.base_unit)
                if repaired_fields:
                    d.update(repaired_fields)
                    await i.update_from_dict(repaired_fields).save()
                d["converted_quantity_draft"] = Decimal(0)
                d["converted_quantity_confirmed"] = Decimal(0)
                if i.purchase_order_id and i.purchase_order_item_id:
                    po = await PurchaseOrder.get_or_none(tenant_id=tenant_id, id=i.purchase_order_id)
                    po_item = (
                        await PurchaseOrderItem.get_or_none(
                            tenant_id=tenant_id, id=i.purchase_order_item_id
                        )
                        if po
                        else None
                    )
                    if po and po_item:
                        qty = po_item.ordered_quantity or Decimal(0)
                        if is_draft_status(po.status):
                            d["converted_quantity_draft"] = qty
                        elif po.status in LEGACY_AUDITED_VALUES:
                            d["converted_quantity_confirmed"] = qty
                    elif clear_orphan:
                        await i.update_from_dict({
                            "purchase_order_id": None,
                            "purchase_order_item_id": None,
                            "supplier_id": None,
                        }).save()
                        d["purchase_order_id"] = None
                        d["purchase_order_item_id"] = None
                        d["supplier_id"] = None
                        cleared = True
                resps.append(PurchaseRequisitionItemResponse.model_validate(d))
            return resps, cleared

        # 第一遍：用现有 purchase_order_id 链接做正常计算 + 清理孤儿
        item_resps, cleared_orphan = await _build_item_resps(items, clear_orphan=True)
        if cleared_orphan:
            await self.merge_split_requisition_items(tenant_id, requisition_id)
            items = await PurchaseRequisitionItem.filter(
                tenant_id=tenant_id, requisition_id=requisition_id
            ).all()

        # 重新加载明细（可能因清孤儿/合并已变化）
        all_items = await PurchaseRequisitionItem.filter(
            tenant_id=tenant_id, requisition_id=requisition_id
        ).all()
        before_links = {
            int(it.id): (it.purchase_order_id, it.purchase_order_item_id) for it in all_items
        }
        po_item_by_source = await self._heal_requisition_links_from_downstream(
            tenant_id, requisition_id, all_items
        )
        healed = any(
            before_links.get(int(it.id)) != (it.purchase_order_id, it.purchase_order_item_id)
            for it in all_items
        )

        # 若有自愈，重建明细响应
        if healed:
            items = await PurchaseRequisitionItem.filter(
                tenant_id=tenant_id, requisition_id=requisition_id
            ).all()
            item_resps, _ = await _build_item_resps(items, clear_orphan=False)
            all_items = items
        elif cleared_orphan:
            item_resps, _ = await _build_item_resps(all_items, clear_orphan=False)

        # 转单状态判定：以 items.purchase_order_id 与下游 PO 反查的并集为准
        converted_req_item_ids = {it.id for it in all_items if it.purchase_order_id} | set(po_item_by_source.keys())
        has_any = len(converted_req_item_ids) > 0
        all_converted = len(all_items) > 0 and len(converted_req_item_ids) >= len(all_items)

        current_norm = normalize_status(req.status)
        new_status = req.status
        if all_converted:
            new_status = DocumentStatus.FULL_CONVERTED.value
        elif has_any:
            new_status = DocumentStatus.PARTIAL_CONVERTED.value
        elif current_norm in (
            DocumentStatus.AUDITED.value,
            DocumentStatus.APPROVED.value,
            DocumentStatus.CONFIRMED.value,
            DocumentStatus.PARTIAL_CONVERTED.value,
            DocumentStatus.FULL_CONVERTED.value,
        ):
            # 仅在已通过/转单语义区间回落为已通过，避免覆盖草稿/待审核/驳回
            new_status = "已通过"

        if req.status != new_status:
            req.status = new_status
            await req.save()

        req_dict = {k: getattr(req, k) for k in req._meta.fields_map if hasattr(req, k)}
        req_dict.pop("items", None)
        resp = PurchaseRequisitionResponse.model_construct(**req_dict)
        resp.items = item_resps
        from apps.kuaizhizao.services.document_lifecycle_service import get_purchase_requisition_lifecycle
        audit_required = await self.business_config_service.check_audit_required(tenant_id, "purchase_request")
        resp.lifecycle = get_purchase_requisition_lifecycle(req, audit_required=audit_required)
        from core.services.approval.audit_record_enricher import enrich_record

        resp = await enrich_purchase_requisition_detail_capabilities(tenant_id, req, resp)
        return await enrich_record(
            tenant_id,
            "purchase_request",
            resp,
            viewer_id=viewer_id,
        )

    async def _batch_requisition_items_count(
        self, tenant_id: int, requisition_ids: List[int]
    ) -> Dict[int, int]:
        """批量统计采购申请明细行数（列表用，避免 N+1 count）。"""
        if not requisition_ids:
            return {}
        rows = (
            await PurchaseRequisitionItem.filter(
                tenant_id=tenant_id,
                requisition_id__in=requisition_ids,
            )
            .group_by("requisition_id")
            .annotate(cnt=Count("id"))
            .values("requisition_id", "cnt")
        )
        return {int(row["requisition_id"]): int(row["cnt"]) for row in rows}

    async def _batch_requisition_item_totals(
        self, tenant_id: int, requisition_ids: List[int]
    ) -> Dict[int, Dict[str, Decimal]]:
        """批量统计采购申请总数量与总金额（列表用，避免逐单查询）。"""
        if not requisition_ids:
            return {}
        rows = await PurchaseRequisitionItem.filter(
            tenant_id=tenant_id,
            requisition_id__in=requisition_ids,
        ).values("requisition_id", "quantity", "suggested_unit_price")
        from apps.kuaizhizao.utils.document_amount_write import line_total_qty_unit_price

        totals: Dict[int, Dict[str, Decimal]] = {}
        for row in rows:
            req_id = int(row["requisition_id"])
            quantity = Decimal(str(row.get("quantity") or 0))
            unit_price = Decimal(str(row.get("suggested_unit_price") or 0))
            bucket = totals.setdefault(
                req_id,
                {"total_quantity": Decimal("0"), "total_amount": Decimal("0")},
            )
            bucket["total_quantity"] += quantity
            bucket["total_amount"] += line_total_qty_unit_price(quantity, unit_price)
        return totals

    async def _filter_requisitions_by_lifecycle_stage(
        self,
        tenant_id: int,
        reqs: List[PurchaseRequisition],
        lifecycle_stage: str,
        *,
        audit_required: bool,
    ) -> List[PurchaseRequisition]:
        """按 lifecycle 钉住 Tab 筛选（Mode A 草稿/驳回走 status，勿比对「—」）。"""
        from apps.kuaizhizao.services.document_lifecycle_service import (
            match_purchase_requisition_lifecycle_filter,
        )

        if not reqs:
            return []

        return [
            req
            for req in reqs
            if match_purchase_requisition_lifecycle_filter(
                req,
                lifecycle_stage,
                audit_required=audit_required,
            )
        ]

    @staticmethod
    def _resolve_list_order_by(order_by: Optional[str]) -> tuple[str, str]:
        if order_by:
            field = order_by.lstrip("-")
            if field in PURCHASE_REQUISITION_SORTABLE_FIELDS:
                descending = order_by.startswith("-")
                primary = f"-{field}" if descending else field
                secondary = "-id" if descending else "id"
                return primary, secondary
        return "-created_at", "-id"

    @staticmethod
    def _sort_requisitions_in_memory(
        reqs: List[PurchaseRequisition],
        primary: str,
        secondary: str,
    ) -> List[PurchaseRequisition]:
        def field_key(field_name: str, req: PurchaseRequisition):
            val = getattr(req, field_name.lstrip("-"), None)
            if val is None:
                return (1, "")
            return (0, val)

        def sort_key(req: PurchaseRequisition):
            p_field = primary.lstrip("-")
            s_field = secondary.lstrip("-")
            return (field_key(p_field, req), field_key(s_field, req))

        reverse = primary.startswith("-")
        return sorted(reqs, key=sort_key, reverse=reverse)

    async def list_requisitions(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None,
        lifecycle_stage: Optional[str] = None,
        source_type: Optional[str] = None,
        keyword: Optional[str] = None,
        requisition_code: Optional[str] = None,
        requisition_name: Optional[str] = None,
        required_date_from: Optional[date] = None,
        required_date_to: Optional[date] = None,
        created_start_date: Optional[date] = None,
        created_end_date: Optional[date] = None,
        order_by: Optional[str] = None,
        include_items: bool = False,
        viewer_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """列表查询，返回 { data, total, success }"""
        from apps.kuaizhizao.utils.list_item_material_keyword import (
            header_ids_matching_item_material,
        )

        query = PurchaseRequisition.filter(
            tenant_id=tenant_id, deleted_at__isnull=True
        )
        lifecycle_filter = (lifecycle_stage or "").strip()
        if lifecycle_filter == "待我审核":
            from core.services.approval.pending_my_approval import (
                entity_ids_pending_my_approval,
            )

            mine_ids = await entity_ids_pending_my_approval(
                tenant_id, "purchase_request", viewer_id
            )
            if not mine_ids:
                return {"data": [], "total": 0, "success": True}
            query = query.filter(id__in=mine_ids)
            lifecycle_filter = ""
        elif lifecycle_filter == "待审核":
            query = query.filter(status=DocumentStatus.PENDING_REVIEW.value)
            lifecycle_filter = ""
        if status and not lifecycle_filter and (lifecycle_stage or "").strip() not in (
            "待审核",
            "待我审核",
        ):
            query = query.filter(status=status)
        if source_type:
            query = query.filter(source_type=source_type)
        kw = (keyword or "").strip()
        if kw:
            material_req_ids = await header_ids_matching_item_material(
                tenant_id,
                PurchaseRequisitionItem,
                "requisition_id",
                kw,
            )
            query = query.filter(
                Q(requisition_code__icontains=kw)
                | Q(requisition_name__icontains=kw)
                | Q(source_code__icontains=kw)
                | Q(applicant_name__icontains=kw)
                | Q(id__in=material_req_ids)
            )
        rc = (requisition_code or "").strip()
        if rc:
            query = query.filter(requisition_code__icontains=rc)
        rn = (requisition_name or "").strip()
        if rn:
            query = query.filter(requisition_name__icontains=rn)
        if required_date_from is not None:
            query = query.filter(
                required_date__isnull=False, required_date__gte=required_date_from
            )
        if required_date_to is not None:
            query = query.filter(
                required_date__isnull=False, required_date__lte=required_date_to
            )
        if created_start_date is not None:
            query = query.filter(
                created_at__gte=datetime.combine(created_start_date, time.min)
            )
        if created_end_date is not None:
            query = query.filter(
                created_at__lte=datetime.combine(created_end_date, time(23, 59, 59))
            )

        audit_required = await self.business_config_service.check_audit_required(
            tenant_id, "purchase_request"
        )

        primary_order, secondary_order = self._resolve_list_order_by(order_by)

        if lifecycle_filter:
            candidate_reqs = await query.order_by(primary_order, secondary_order).all()
            matched_reqs = await self._filter_requisitions_by_lifecycle_stage(
                tenant_id,
                candidate_reqs,
                lifecycle_filter,
                audit_required=audit_required,
            )
            sorted_reqs = self._sort_requisitions_in_memory(
                matched_reqs, primary_order, secondary_order
            )
            total = len(sorted_reqs)
            reqs = sorted_reqs[skip : skip + limit]
        else:
            total = await query.count()
            reqs = await query.offset(skip).limit(limit).order_by(primary_order, secondary_order)

        req_ids = [req.id for req in reqs if req.id is not None]

        items_by_req: Dict[int, List[PurchaseRequisitionItemResponse]] = {}
        if include_items and req_ids:
            all_items = (
                await PurchaseRequisitionItem.filter(
                    tenant_id=tenant_id, requisition_id__in=req_ids
                )
                .order_by("requisition_id", "id")
                .all()
            )
            for it in all_items:
                rid = int(it.requisition_id)
                items_by_req.setdefault(rid, []).append(
                    PurchaseRequisitionItemResponse.model_validate(it)
                )

        items_count_map = await self._batch_requisition_items_count(tenant_id, req_ids)
        item_totals_map = await self._batch_requisition_item_totals(tenant_id, req_ids)
        from apps.kuaizhizao.services.document_lifecycle_service import (
            get_purchase_requisition_lifecycle,
        )

        result = []
        for req in reqs:
            req_dict = {k: getattr(req, k) for k in req._meta.fields_map if hasattr(req, k)}
            req_dict.pop("items", None)
            resp = PurchaseRequisitionListResponse.model_construct(**req_dict)
            resp.items_count = items_count_map.get(req.id, 0)
            totals = item_totals_map.get(req.id, None)
            if totals:
                resp.total_quantity = totals["total_quantity"]
                resp.total_amount = totals["total_amount"]
            else:
                resp.total_quantity = Decimal("0")
                resp.total_amount = Decimal("0")
            # 列表仅按当前 status 计算生命周期；转单状态自愈在详情/转单/修正接口执行
            resp.lifecycle = get_purchase_requisition_lifecycle(
                req, milestones=None, audit_required=audit_required
            )
            if include_items:
                resp.items = items_by_req.get(int(req.id), [])
            result.append(resp)

        enriched = await enrich_purchase_requisition_list_capabilities(tenant_id, reqs, result)
        from core.services.approval.audit_record_enricher import enrich_data_payload
        from loguru import logger

        payload = {
            "data": [item.model_dump() for item in enriched],
            "total": total,
            "success": True,
        }
        try:
            return await enrich_data_payload(
                tenant_id,
                "purchase_request",
                payload,
                viewer_id=viewer_id,
            )
        except Exception as exc:
            # 审批概况/选边校验失败时仍返回业务行，避免列表整页 422→前端空表
            logger.warning(
                "purchase_requisition list audit enrich failed — returning rows without viewer gates: {}",
                exc,
            )
            return payload

    async def _recalc_conversion_status(
        self, tenant_id: int, req: PurchaseRequisition
    ) -> None:
        """重新计算并保存采购申请的转单状态：
        - 自愈断开的链接（PurchaseOrderItem.source_id 反查）
        - 按下游 PO 占用数量判定 PARTIAL/FULL（挂链但占用未满仍算未转完）
        - 在「已通过/已确认/已审核/转单」语义区间内回写 PARTIAL_CONVERTED/FULL_CONVERTED
        草稿/待审核/驳回 等状态保持不变。
        """
        all_items = await PurchaseRequisitionItem.filter(
            tenant_id=tenant_id, requisition_id=req.id
        ).all()
        po_item_by_source = await self._heal_requisition_links_from_downstream(
            tenant_id, int(req.id), all_items
        )

        item_ids = [int(it.id) for it in all_items if it.id is not None]
        occupied_map = await self._occupied_purchase_order_qty_by_requisition_item_ids(
            tenant_id, item_ids
        )
        for sid in po_item_by_source.keys():
            occupied_map.setdefault(int(sid), Decimal("0"))

        has_any = False
        all_converted = len(all_items) > 0
        for it in all_items:
            iid = int(it.id) if it.id is not None else 0
            qty = Decimal(str(it.quantity or 0))
            occ = occupied_map.get(iid, Decimal("0"))
            if occ <= 0 and it.purchase_order_id:
                # 仅有挂链、尚无占用快照时，按行量视为已占用（自愈前瞬时）
                occ = qty
            if occ > 0:
                has_any = True
            if qty <= 0 or occ + Decimal("0.0000001") < qty:
                all_converted = False
        if not all_items:
            all_converted = False

        current_norm = normalize_status(req.status)
        new_status = req.status
        if all_converted:
            new_status = DocumentStatus.FULL_CONVERTED.value
        elif has_any:
            new_status = DocumentStatus.PARTIAL_CONVERTED.value
        elif current_norm in (
            DocumentStatus.AUDITED.value,
            DocumentStatus.APPROVED.value,
            DocumentStatus.CONFIRMED.value,
            DocumentStatus.PARTIAL_CONVERTED.value,
            DocumentStatus.FULL_CONVERTED.value,
        ):
            new_status = "已通过"
        if req.status != new_status:
            req.status = new_status
            await req.save()

    async def merge_split_requisition_items(
        self, tenant_id: int, requisition_id: int
    ) -> None:
        """
        合并因部分下推而拆分的申请明细行。
        当同一物料存在多行且均未转单时，合并为一行（数量相加）。
        """
        items = await PurchaseRequisitionItem.filter(
            tenant_id=tenant_id,
            requisition_id=requisition_id,
            purchase_order_id__isnull=True,
        ).all()
        if len(items) < 2:
            return

        by_material: Dict[int, List] = {}
        for i in items:
            mid = i.material_id
            if mid not in by_material:
                by_material[mid] = []
            by_material[mid].append(i)

        for mid, group in by_material.items():
            if len(group) < 2:
                continue
            total_qty = sum(Decimal(str(x.quantity or 0)) for x in group)
            keeper = group[0]
            to_delete = group[1:]
            await keeper.update_from_dict({"quantity": total_qty}).save()
            for d in to_delete:
                await d.delete()

    async def fix_requisition_status(
        self, tenant_id: int, requisition_id: int
    ) -> PurchaseRequisitionResponse:
        """
        修正采购申请状态：若状态为「全部转单」但存在未转单明细，则改为「部分转单」。
        同时清除指向已删除采购单的引用（purchase_order_id 指向不存在的 PO 时清空）。
        """
        req = await PurchaseRequisition.get_or_none(
            tenant_id=tenant_id, id=requisition_id, deleted_at__isnull=True
        )
        if not req:
            raise NotFoundError(f"采购申请不存在: {requisition_id}")


        all_items = await PurchaseRequisitionItem.filter(
            tenant_id=tenant_id, requisition_id=requisition_id
        ).all()

        # 清除指向已删除采购单的引用
        cleared_any = False
        for i in all_items:
            if i.purchase_order_id:
                po = await PurchaseOrder.get_or_none(
                    tenant_id=tenant_id, id=i.purchase_order_id
                )
                if not po:
                    await i.update_from_dict({
                        "purchase_order_id": None,
                        "purchase_order_item_id": None,
                        "supplier_id": None,
                    }).save()
                    cleared_any = True

        if cleared_any:
            await self.merge_split_requisition_items(tenant_id, requisition_id)

        # 复用统一的状态自愈逻辑（含 PurchaseOrderItem.source_id 反查）
        await self._recalc_conversion_status(tenant_id, req)
        return await self.get_requisition_by_id(tenant_id, requisition_id)

    async def delete_requisition(self, tenant_id: int, requisition_id: int) -> bool:
        """删除采购申请（软删除，仅草稿可删）"""
        req = await PurchaseRequisition.get_or_none(
            tenant_id=tenant_id, id=requisition_id, deleted_at__isnull=True
        )
        if not req:
            raise NotFoundError(f"采购申请不存在: {requisition_id}")
        logger.info("kuaizhizao_purchase_requisition_delete attempt: tenant_id={} req_id={} status={}", tenant_id, requisition_id, req.status)
        from apps.kuaizhizao.services.document_action_policy.enricher import (
            purchase_requisition_has_linked_purchase_order,
        )

        has_linked_po = await purchase_requisition_has_linked_purchase_order(
            tenant_id, requisition_id
        )
        from apps.kuaizhizao.services.document_action_policy.enricher import (
            resolve_review_submitted_for_document,
        )

        review_submitted = await resolve_review_submitted_for_document(
            tenant_id, "purchase_request", req
        )
        assert_purchase_requisition_capability(
            req,
            "delete",
            has_linked_purchase_order=has_linked_po,
            review_submitted=review_submitted,
        )
        await PurchaseRequisition.filter(tenant_id=tenant_id, id=requisition_id).update(
            deleted_at=resolve_business_datetime()
        )
        return True

    async def update_requisition(
        self,
        tenant_id: int,
        requisition_id: int,
        data: PurchaseRequisitionUpdate,
        updated_by: int,
        approval_edit_context: Optional[Dict[str, Any]] = None,
        approval_edit_comment: Optional[str] = None,
    ) -> PurchaseRequisitionResponse:
        """更新采购申请（草稿可改；审核中须当前审批人且节点开启改单）"""
        req = await PurchaseRequisition.get_or_none(
            tenant_id=tenant_id, id=requisition_id, deleted_at__isnull=True
        )
        if not req:
            raise NotFoundError(f"采购申请不存在: {requisition_id}")
        is_draft = is_draft_status(req.status)
        is_pending = is_pending_review_status(req.status)
        if not is_draft:
            if not (is_pending and approval_edit_context):
                if is_pending and not approval_edit_context:
                    from core.services.approval.approval_edit_guard import ApprovalEditGuard

                    edit_ctx = await ApprovalEditGuard.get_pending_edit_context(
                        tenant_id, "purchase_request", requisition_id, updated_by
                    )
                    if not edit_ctx:
                        raise BusinessLogicError("单据审核中，仅已开启改单权限的当前审批人可修改")
                    approval_edit_context = edit_ctx
                else:
                    assert_purchase_requisition_capability(req, "update")

        if approval_edit_context:
            from core.config.audit_editable_fields import is_field_editable

            node_editable = approval_edit_context.get("editable_fields")
            preview = data.model_dump(exclude_unset=True, exclude={"items"})
            for field in preview:
                if field in ("updated_by",):
                    continue
                if not is_field_editable("purchase_request", field, node_editable):
                    raise ValidationError(f"字段「{field}」不允许在审核中修改")
            if data.items is not None and not is_field_editable("purchase_request", "items", node_editable):
                raise ValidationError("字段「申请明细」不允许在审核中修改")

        update_data = data.model_dump(exclude_unset=True, exclude={"items"})
        from apps.kuaizhizao.constants.purchase_order_type import (
            load_and_assert_purchase_order_type_materials,
            normalize_purchase_order_type,
        )

        effective_order_type = normalize_purchase_order_type(
            update_data.get("order_type")
            if "order_type" in update_data
            else getattr(req, "order_type", None)
        )
        if "order_type" in update_data:
            update_data["order_type"] = effective_order_type
        line_material_ids = (
            [int(it.material_id) for it in data.items]
            if data.items is not None
            else await PurchaseRequisitionItem.filter(
                tenant_id=tenant_id, requisition_id=requisition_id
            ).values_list("material_id", flat=True)
        )
        await load_and_assert_purchase_order_type_materials(
            tenant_id,
            effective_order_type,
            line_material_ids,
            document_label="采购申请",
        )
        if update_data:
            from core.services.document_code_service import pop_and_apply_code_change_from_update_dict

            await pop_and_apply_code_change_from_update_dict(
                tenant_id,
                "kuaizhizao-purchase-requisition",
                req,
                update_data,
                "requisition_code",
            )
            if "requisition_name" in update_data:
                raw_name = update_data.get("requisition_name")
                trimmed = (raw_name or "").strip() if raw_name is not None else ""
                if trimmed:
                    update_data["requisition_name"] = trimmed
                else:
                    final_code = (update_data.get("requisition_code") or req.requisition_code or "").strip()
                    update_data["requisition_name"] = _default_requisition_name(final_code)
            user_info = await self.get_user_info(updated_by)
            if update_data:
                await req.update_from_dict({
                    **update_data,
                    "updated_by": updated_by,
                    "updated_by_name": user_info["name"],
                }).save()

        if data.items is not None:
            await PurchaseRequisitionItem.filter(
                tenant_id=tenant_id, requisition_id=requisition_id
            ).delete()
            for item_data in data.items:
                await PurchaseRequisitionItem.create(
                    tenant_id=tenant_id,
                    requisition_id=requisition_id,
                    material_id=item_data.material_id,
                    material_code=item_data.material_code,
                    material_name=item_data.material_name,
                    material_spec=item_data.material_spec,
                    unit=item_data.unit or "件",
                    quantity=item_data.quantity,
                    suggested_unit_price=item_data.suggested_unit_price or Decimal(0),
                    required_date=item_data.required_date,
                    demand_computation_item_id=item_data.demand_computation_item_id,
                    work_order_id=item_data.work_order_id,
                    work_order_code=item_data.work_order_code,
                    supplier_id=item_data.supplier_id,
                    notes=item_data.notes,
                    attachments=item_data.attachments,
                )

        return await self.get_requisition_by_id(tenant_id, requisition_id)

    async def submit_requisition(
        self,
        tenant_id: int,
        requisition_id: int,
        submitted_by: int,
        *,
        selected_approver_user_ids: Optional[List[int]] = None,
        selected_approver_by_node: Optional[Dict[str, List[int]]] = None,
    ) -> PurchaseRequisitionResponse:
        """提交采购申请（启动审批或直接通过）"""
        req = await PurchaseRequisition.get_or_none(
            tenant_id=tenant_id, id=requisition_id, deleted_at__isnull=True
        )
        if not req:
            raise NotFoundError(f"采购申请不存在: {requisition_id}")


        assert_purchase_requisition_capability(req, "submit")

        # 检查是否需要审核
        audit_required = await self.business_config_service.check_audit_required(tenant_id, "purchase_request")
        
        if audit_required:
            from core.services.approval.audit_flow_guard import (
                approval_instance_finished_on_submit,
                start_document_approval_or_raise,
            )

            instance = await start_document_approval_or_raise(
                tenant_id=tenant_id,
                user_id=submitted_by,
                node_key="purchase_request",
                entity_type="purchase_request",
                entity_id=int(req.id),
                entity_uuid=str(req.uuid),
                title=f"采购申请审批: {req.requisition_code}",
                content=f"申请人: {req.applicant_name or '—'}",
                doc_label="采购申请",
                selected_approver_user_ids=selected_approver_user_ids,
                selected_approver_by_node=selected_approver_by_node,
            )
            req.status = DocumentStatus.PENDING_REVIEW.value
            req.review_status = ReviewStatus.PENDING.value
            user_info = await self.get_user_info(submitted_by)
            req.updated_by = submitted_by
            req.updated_by_name = user_info["name"]
            await req.save()
            if approval_instance_finished_on_submit(instance):
                return await self.approve_requisition(
                    tenant_id,
                    requisition_id,
                    approved=True,
                    approved_by=submitted_by,
                    is_auto_approve=True,
                )
            return await self.get_requisition_by_id(tenant_id, requisition_id)
        req.status = DocumentStatus.CONFIRMED.value
        req.review_status = ReviewStatus.APPROVED.value
        user_info = await self.get_user_info(submitted_by)
        req.updated_by = submitted_by
        req.updated_by_name = user_info["name"]
        await req.save()
        return await self.get_requisition_by_id(tenant_id, requisition_id)

    async def approve_requisition(
        self,
        tenant_id: int,
        requisition_id: int,
        approved: bool,
        review_remarks: Optional[str] = None,
        approved_by: int = None,
        *,
        is_auto_approve: bool = False,
        instance_data_patch: Optional[Dict[str, Any]] = None,
    ) -> PurchaseRequisitionResponse:
        """审核采购申请（通过或驳回）"""
        from apps.kuaizhizao.constants import DocumentStatus, ReviewStatus, normalize_status

        req = await PurchaseRequisition.get_or_none(
            tenant_id=tenant_id, id=requisition_id, deleted_at__isnull=True
        )
        if not req:
            raise NotFoundError(f"采购申请不存在: {requisition_id}")

        assert_purchase_requisition_capability(req, "approve")

        audit_required = await self.business_config_service.check_audit_required(
            tenant_id, "purchase_request"
        )
        if not is_auto_approve:
            from core.services.approval.audit_flow_guard import assert_pending_approval_instance

            await assert_pending_approval_instance(
                tenant_id=tenant_id,
                entity_type="purchase_request",
                entity_id=requisition_id,
                audit_required=audit_required,
                doc_label="采购申请",
                verb="审核" if approved else "驳回",
            )

        from core.services.approval.uni_audit_service import UniAuditService

        async def _do_decide() -> PurchaseRequisitionResponse:
            row = await PurchaseRequisition.get_or_none(
                tenant_id=tenant_id, id=requisition_id, deleted_at__isnull=True
            )
            if not row:
                raise NotFoundError(f"采购申请不存在: {requisition_id}")
            user_info = await self.get_user_info(approved_by) if approved_by else None
            reviewer_name = user_info["name"] if user_info else None
            if approved:
                row.status = "已通过"  # 采购申请业务用语
                row.review_status = ReviewStatus.APPROVED.value
            else:
                row.status = "已驳回"
                row.review_status = ReviewStatus.REJECTED.value

            row.reviewer_id = approved_by
            row.reviewer_name = reviewer_name
            row.review_time = resolve_business_datetime()
            row.review_remarks = review_remarks
            if approved_by:
                row.updated_by = approved_by
                row.updated_by_name = user_info["name"]
            await row.save()
            return await self.get_requisition_by_id(tenant_id, requisition_id)

        sync_after_flow = False
        if audit_required and approved_by and not is_auto_approve:
            from core.services.approval.audit_flow_guard import (
                get_approval_gate_status,
                should_sync_doc_after_flow_completed,
            )

            gate = await get_approval_gate_status(
                tenant_id=tenant_id,
                entity_type="purchase_request",
                entity_id=requisition_id,
            )
            sync_after_flow = should_sync_doc_after_flow_completed(gate, approve=approved)

        if is_auto_approve or not approved_by or sync_after_flow:
            return await _do_decide()

        if approved:
            result = await UniAuditService.approve_with_flow_fallback(
                tenant_id=tenant_id,
                entity_type="purchase_request",
                entity_id=requisition_id,
                approver_id=approved_by,
                flow_approve=_do_decide,
                instance_data_patch=instance_data_patch,
            )
        else:
            result = await UniAuditService.reject_with_flow_fallback(
                tenant_id=tenant_id,
                entity_type="purchase_request",
                entity_id=requisition_id,
                approver_id=approved_by,
                reason=review_remarks,
                flow_reject=lambda _reason: _do_decide(),
            )
        return result if result is not None else await self.get_requisition_by_id(tenant_id, requisition_id)

    async def withdraw_requisition(
        self,
        tenant_id: int,
        requisition_id: int,
        withdrawn_by: int,
    ) -> PurchaseRequisitionResponse:
        """撤回提交：待审核 → 草稿（提交人撤回，非反审核）"""
        req = await PurchaseRequisition.get_or_none(
            tenant_id=tenant_id, id=requisition_id, deleted_at__isnull=True
        )
        if not req:
            raise NotFoundError(f"采购申请不存在: {requisition_id}")
        if not is_pending_review_status(req.status):
            raise BusinessLogicError("只有待审核状态的采购申请可撤回提交")

        try:
            from core.services.approval.approval_instance_service import ApprovalInstanceService

            await ApprovalInstanceService.cancel_approval(
                tenant_id=tenant_id,
                entity_type="purchase_request",
                entity_id=requisition_id,
                operator_id=withdrawn_by,
            )
        except Exception as e:
            logger.warning("取消采购申请审批流程失败或无需取消: {}", e)

        req.status = DocumentStatus.DRAFT.value
        req.review_status = ReviewStatus.PENDING.value
        req.reviewer_id = None
        req.reviewer_name = None
        req.review_time = None
        req.review_remarks = None
        user_info = await self.get_user_info(withdrawn_by)
        req.updated_by = withdrawn_by
        req.updated_by_name = user_info["name"]
        await req.save()

        return await self.get_requisition_by_id(tenant_id, requisition_id)

    async def withdraw_approval(
        self,
        tenant_id: int,
        requisition_id: int,
        operator_id: Optional[int] = None,
    ) -> PurchaseRequisitionResponse:
        """撤销审核：有流程则重开终审节点待再审；否则回草稿须重提。"""
        from apps.kuaizhizao.constants import DocumentStatus, ReviewStatus
        from core.services.approval.audit_transition import (
            resolve_revoke_to_draft_landing_phase,
        )
        from core.services.approval.uni_audit_service import UniAuditService

        req = await PurchaseRequisition.get_or_none(
            tenant_id=tenant_id, id=requisition_id, deleted_at__isnull=True
        )
        if not req:
            raise NotFoundError(f"采购申请不存在: {requisition_id}")

        has_linked_po = await purchase_requisition_has_linked_purchase_order(
            tenant_id, requisition_id
        )
        assert_purchase_requisition_capability(
            req,
            "revoke_approval",
            has_linked_purchase_order=has_linked_po,
        )

        audit_required = await self.business_config_service.check_audit_required(
            tenant_id, "purchase_request"
        )
        op_id = int(operator_id) if operator_id else 0

        async def _do_revoke(*, reopened: bool = False) -> PurchaseRequisitionResponse:
            landing = resolve_revoke_to_draft_landing_phase(
                manual_audit_enabled=audit_required,
                flow_reopened=reopened,
            )
            row = await PurchaseRequisition.get_or_none(
                tenant_id=tenant_id, id=requisition_id, deleted_at__isnull=True
            )
            if not row:
                raise NotFoundError(f"采购申请不存在: {requisition_id}")
            if landing == "pending":
                row.status = DocumentStatus.PENDING_REVIEW.value
            else:
                row.status = DocumentStatus.DRAFT.value
            row.review_status = ReviewStatus.PENDING.value
            row.reviewer_id = None
            row.reviewer_name = None
            row.review_time = None
            row.review_remarks = None
            if op_id:
                user_info = await self.get_user_info(op_id)
                row.updated_by = op_id
                row.updated_by_name = user_info["name"]
            await row.save()
            return await self.get_requisition_by_id(tenant_id, requisition_id)

        return await UniAuditService.revoke_with_flow_fallback(
            tenant_id=tenant_id,
            entity_type="purchase_request",
            entity_id=requisition_id,
            operator_id=op_id,
            flow_revoke=_do_revoke,
        )

    @staticmethod
    def _resolve_line_supplier_id(item: PurchaseRequisitionItem, data: ConvertToPurchaseOrderRequest) -> Optional[int]:
        """申请行实际使用的供应商：item_suppliers 映射 > 行上 supplier_id > 请求头 supplier_id"""
        if data.item_suppliers and item.id is not None:
            iid = int(item.id)
            for k, v in data.item_suppliers.items():
                if int(k) == iid:
                    return int(v)
        if item.supplier_id:
            return int(item.supplier_id)
        if data.supplier_id:
            return int(data.supplier_id)
        return None

    @staticmethod
    def _resolve_purchase_order_unit_price(
        item: PurchaseRequisitionItem,
        material_by_id: Dict[int, Material],
        price_override: Optional[Decimal] = None,
    ) -> Decimal:
        if price_override is not None:
            return price_override
        unit_price = item.suggested_unit_price or Decimal(0)
        if unit_price > 0:
            return unit_price
        mid = int(item.material_id) if item.material_id is not None else None
        material = material_by_id.get(mid) if mid is not None else None
        return resolve_material_purchase_line_unit_price(material=material)

    @staticmethod
    async def _resolve_purchase_order_unit_price_async(
        tenant_id: int,
        item: PurchaseRequisitionItem,
        material_by_id: Dict[int, Material],
        supplier_id: Optional[int],
        price_override: Optional[Decimal] = None,
    ) -> Decimal:
        if price_override is not None:
            return price_override
        unit_price = item.suggested_unit_price or Decimal(0)
        if unit_price > 0:
            return unit_price
        mid = int(item.material_id) if item.material_id is not None else None
        material = material_by_id.get(mid) if mid is not None else None
        from apps.kuaizhizao.utils.material_source_helper import (
            resolve_material_purchase_line_unit_price_async,
        )

        return await resolve_material_purchase_line_unit_price_async(
            tenant_id=tenant_id,
            material=material,
            supplier_id=int(supplier_id) if supplier_id and int(supplier_id) > 0 else None,
            quantity=item.quantity,
        )

    @staticmethod
    def _resolve_requisition_item_required_date(
        item: PurchaseRequisitionItem,
        requisition_header_required: Optional[date],
        fallback: date,
    ) -> date:
        """行到货日 → 采购申请表头到货日 → 转单基准日（与申请建单继承逻辑一致）。"""
        if item.required_date is not None:
            return item.required_date
        if requisition_header_required is not None:
            return requisition_header_required
        return fallback

    async def _resolve_requisition_line_tax_rate_percent(
        self,
        tenant_id: int,
        *,
        material_id: Optional[int],
        material_by_id: Dict[int, Material],
        supplier_id: int,
        quantity: Decimal,
    ) -> Decimal:
        """行税率：供应商价本 → 物料默认 → 13%（百分比）。"""
        from apps.kuaicaiwu.services.purchase_settlement import (
            normalize_po_tax_rate_to_percent,
        )
        from apps.master_data.services.partner_material_price_defaults import (
            material_default_tax_rate,
        )
        from apps.master_data.services.partner_material_price_resolver import (
            PartnerMaterialPriceResolver,
        )

        pct = Decimal("0")
        mid = int(material_id) if material_id is not None else 0
        sid = int(supplier_id) if supplier_id else 0
        if sid > 0 and mid > 0:
            resolved = await PartnerMaterialPriceResolver.resolve(
                tenant_id,
                "purchase",
                sid,
                mid,
                quantity=quantity,
            )
            if resolved.tax_rate is not None and Decimal(str(resolved.tax_rate)) > 0:
                pct = normalize_po_tax_rate_to_percent(resolved.tax_rate)
        if pct <= 0 and mid > 0:
            material = material_by_id.get(mid)
            if material is not None:
                mat_pct = material_default_tax_rate(material.defaults or {})
                if mat_pct > 0:
                    pct = normalize_po_tax_rate_to_percent(mat_pct)
        if pct <= 0:
            pct = _DEFAULT_PURCHASE_TAX_RATE_PERCENT
        return pct

    async def _build_requisition_push_line_pricing(
        self,
        tenant_id: int,
        *,
        item: PurchaseRequisitionItem,
        material_by_id: Dict[int, Material],
        supplier_id: int,
        quantity: Decimal,
        price_override: Optional[Decimal] = None,
    ) -> _RequisitionPushLinePricing:
        """建议价与转单改价按含税录入；价本回落价按未税录入。单价不反算。"""
        from apps.kuaizhizao.constants.price_type import DEFAULT_PURCHASE_PRICE_TYPE
        from apps.kuaizhizao.utils.purchase_order_line_amounts import (
            load_price_amount_places,
            split_purchase_entered_line,
        )

        qty = quantity if quantity > 0 else Decimal("0")
        tax_pct = await self._resolve_requisition_line_tax_rate_percent(
            tenant_id,
            material_id=int(item.material_id) if item.material_id is not None else None,
            material_by_id=material_by_id,
            supplier_id=supplier_id,
            quantity=qty,
        )
        price_places, amount_places = await load_price_amount_places(tenant_id)

        if price_override is not None:
            entered = price_override
            price_type = DEFAULT_PURCHASE_PRICE_TYPE
        elif (item.suggested_unit_price or Decimal(0)) > 0:
            entered = item.suggested_unit_price
            price_type = DEFAULT_PURCHASE_PRICE_TYPE
        else:
            entered = await self._resolve_purchase_order_unit_price_async(
                tenant_id,
                item,
                material_by_id,
                supplier_id,
                price_override=None,
            )
            price_type = "tax_exclusive"

        if qty <= 0 or Decimal(str(entered or 0)) <= 0:
            return _RequisitionPushLinePricing(
                stored_unit_price=Decimal("0"),
                stored_line_excl_total=Decimal("0"),
                tax_rate_percent=tax_pct,
                display_gross_incl=Decimal("0"),
                display_unit_price=Decimal("0"),
                price_type=price_type,
            )
        unit, excl, _tax, incl = split_purchase_entered_line(
            qty,
            entered,
            tax_pct,
            price_type,
            price_places=price_places,
            amount_places=amount_places,
        )
        return _RequisitionPushLinePricing(
            stored_unit_price=unit,
            stored_line_excl_total=excl,
            tax_rate_percent=tax_pct,
            display_gross_incl=incl,
            display_unit_price=unit,
            price_type=price_type,
        )

    async def _persist_buy_default_supplier(
        self,
        tenant_id: int,
        material_id: int,
        supplier_id: int,
        supplier_name: str,
    ) -> bool:
        """将默认供应商写回采购件物料的 source_config（仅 Buy）"""
        m = await Material.get_or_none(tenant_id=tenant_id, id=material_id, deleted_at__isnull=True)
        if not m or (m.source_type or "") != SOURCE_TYPE_BUY:
            return False
        cfg = dict(m.source_config or {})
        inner = dict(cfg.get("source_config") or {})
        inner["default_supplier_id"] = supplier_id
        inner["default_supplier_name"] = supplier_name or inner.get("default_supplier_name") or ""
        cfg["source_config"] = inner
        m.source_config = cfg
        await m.save()
        return True

    async def preview_push_to_purchase_order(
        self,
        tenant_id: int,
        requisition_id: int,
    ) -> Dict[str, Any]:
        """下推采购订单预览：返回可转单明细及数量门禁，不实际创建。"""
        req = await PurchaseRequisition.get_or_none(
            tenant_id=tenant_id, id=requisition_id, deleted_at__isnull=True
        )
        if not req:
            raise NotFoundError(f"采购申请不存在: {requisition_id}")
        assert_purchase_requisition_capability(req, "push_purchase_order")

        detail = await self.get_requisition_by_id(tenant_id, requisition_id)
        open_items = [
            item
            for item in (detail.items or [])
            if item.id is not None and float(item.quantity or 0) > 0
        ]
        occupied_po = await self._occupied_purchase_order_qty_by_requisition_item_ids(
            tenant_id, [int(item.id) for item in open_items]
        )
        preview_items: List[Dict[str, Any]] = []
        for item in open_items:
            qty = float(item.quantity or 0)
            pushed = min(qty, float(occupied_po.get(int(item.id), Decimal("0"))))
            max_push = max(0.0, qty - pushed)
            if max_push <= 0:
                continue
            preview_items.append(
                {
                    "item_id": int(item.id),
                    "material_id": item.material_id,
                    "material_code": item.material_code,
                    "material_name": item.material_name,
                    "material_spec": item.material_spec,
                    "unit": item.unit,
                    "quantity": qty,
                    "pushed_quantity": pushed,
                    "max_push_quantity": max_push,
                    "suggested_unit_price": float(item.suggested_unit_price or 0),
                    "supplier_id": item.supplier_id,
                    "required_date": str(item.required_date) if item.required_date else None,
                }
            )

        pushable_count = len(preview_items)
        has_blocking = pushable_count == 0
        blocking_reason = (
            "purchase_requisition.push_purchase_order.no_lines" if has_blocking else None
        )
        return {
            "target_type": "purchase_order",
            "requisition_id": requisition_id,
            "requisition_code": detail.requisition_code,
            "summary": (
                f"请选择本次要下推的采购申请明细（{pushable_count} 行可下推）"
                if not has_blocking
                else "当前采购申请无可下推明细"
            ),
            "items": preview_items,
            "has_blocking_issues": has_blocking,
            "blocking_reason": blocking_reason,
            "tip": "系统将按所选明细与数量生成采购订单；所选明细合并为一张采购订单，供应商不一致时表头为待定供应商。",
        }

    async def preview_push_to_inquiry(
        self,
        tenant_id: int,
        requisition_id: int,
    ) -> Dict[str, Any]:
        """下推询价单预览：返回可询价明细及数量门禁，不实际创建。"""
        req = await PurchaseRequisition.get_or_none(
            tenant_id=tenant_id, id=requisition_id, deleted_at__isnull=True
        )
        if not req:
            raise NotFoundError(f"采购申请不存在: {requisition_id}")
        assert_purchase_requisition_capability(req, "push_inquiry")

        detail = await self.get_requisition_by_id(tenant_id, requisition_id)
        candidate_items = [
            i for i in (detail.items or []) if not i.purchase_order_id and float(i.quantity or 0) > 0
        ]
        candidate_ids = [int(i.id) for i in candidate_items if i.id is not None]
        blocked_ids: set[int] = set()
        if candidate_ids:
            from apps.kuaizhizao.models.purchase_inquiry import PurchaseInquiry, PurchaseInquiryItem
            from apps.kuaizhizao.constants.purchase_inquiry import INQUIRY_ACTIVE_STATUSES

            active_items = await PurchaseInquiryItem.filter(
                tenant_id=tenant_id,
                source_requisition_item_id__in=candidate_ids,
                purchase_order_id__isnull=True,
            ).all()
            inquiry_ids = {a.inquiry_id for a in active_items}
            active_inquiries = (
                await PurchaseInquiry.filter(
                    tenant_id=tenant_id,
                    id__in=list(inquiry_ids),
                    deleted_at__isnull=True,
                    status__in=list(INQUIRY_ACTIVE_STATUSES),
                ).all()
                if inquiry_ids
                else []
            )
            active_inquiry_ids = {a.id for a in active_inquiries}
            blocked_ids = {
                int(a.source_requisition_item_id)
                for a in active_items
                if a.inquiry_id in active_inquiry_ids and a.source_requisition_item_id
            }

        preview_items: List[Dict[str, Any]] = []
        for item in candidate_items:
            if item.id is None:
                continue
            qty = float(item.quantity or 0)
            in_active_inquiry = int(item.id) in blocked_ids
            max_push = 0.0 if in_active_inquiry else qty
            preview_items.append(
                {
                    "item_id": int(item.id),
                    "material_id": item.material_id,
                    "material_code": item.material_code,
                    "material_name": item.material_name,
                    "material_spec": item.material_spec,
                    "unit": item.unit,
                    "quantity": qty,
                    "pushed_quantity": qty if in_active_inquiry else 0.0,
                    "max_push_quantity": max_push,
                    "required_date": str(item.required_date) if item.required_date else None,
                    "in_active_inquiry": in_active_inquiry,
                }
            )

        pushable_count = sum(1 for row in preview_items if float(row["max_push_quantity"]) > 0)
        has_blocking = pushable_count == 0
        blocking_reason = (
            "purchase_requisition.push_inquiry.no_lines" if has_blocking else None
        )
        return {
            "target_type": "purchase_inquiry",
            "requisition_id": requisition_id,
            "requisition_code": detail.requisition_code,
            "summary": (
                f"请选择本次要询价的采购申请明细（{pushable_count}/{len(preview_items)} 行可询价）"
                if not has_blocking
                else "当前采购申请无可询价明细"
            ),
            "items": preview_items,
            "has_blocking_issues": has_blocking,
            "blocking_reason": blocking_reason,
            "tip": "系统将按所选明细创建询价单，并推荐供应商参与报价。",
        }

    async def convert_to_purchase_order(
        self,
        tenant_id: int,
        requisition_id: int,
        data: ConvertToPurchaseOrderRequest,
        created_by: int,
    ) -> Dict[str, Any]:
        """将采购申请行转为采购订单；所选明细合并一张（与 draft/plan 同口径），可选回写物料默认供应商。"""
        req = await PurchaseRequisition.get_or_none(
            tenant_id=tenant_id, id=requisition_id, deleted_at__isnull=True
        )
        if not req:
            raise NotFoundError(f"采购申请不存在: {requisition_id}")

        assert_purchase_requisition_capability(req, "push_purchase_order")

        selected_ids = [int(v) for v in (data.item_ids or []) if v is not None]
        if not selected_ids:
            raise BusinessLogicError("请至少选择一条可下推采购申请明细")

        owned = await PurchaseRequisitionItem.filter(
            tenant_id=tenant_id,
            requisition_id=requisition_id,
            id__in=selected_ids,
        ).values_list("id", flat=True)
        owned_set = {int(v) for v in owned}
        candidate_ids = [iid for iid in selected_ids if iid in owned_set]
        if not candidate_ids:
            raise BusinessLogicError("所选申请行不属于本单或不存在")
        occupied_po = await self._occupied_purchase_order_qty_by_requisition_item_ids(
            tenant_id, candidate_ids
        )
        owned_items = await PurchaseRequisitionItem.filter(
            tenant_id=tenant_id, id__in=candidate_ids,
        ).all()
        by_id = {int(i.id): i for i in owned_items if i.id is not None}
        ordered_ids = [
            iid for iid in candidate_ids
            if iid in by_id
            and Decimal(str(by_id[iid].quantity or 0)) > occupied_po.get(iid, Decimal("0"))
        ]
        if not ordered_ids:
            raise BusinessLogicError("没有可转单的申请行或所选行已无可下推数量")

        convert_data = ConvertToPurchaseOrderRequest(
            item_ids=ordered_ids,
            supplier_id=data.supplier_id,
            supplier_name=data.supplier_name,
            item_quantities=data.item_quantities,
            item_unit_prices=data.item_unit_prices,
            item_suppliers=data.item_suppliers,
            persist_default_supplier_to_material=data.persist_default_supplier_to_material,
        )
        result = await self.convert_selected_items_to_purchase_orders(
            tenant_id=tenant_id,
            item_ids=ordered_ids,
            created_by=created_by,
            convert_data=convert_data,
        )
        if data.persist_default_supplier_to_material:
            result = {
                **result,
                "persisted_material_ids": result.get("persisted_material_ids") or [],
            }
        else:
            result = {**result, "persisted_material_ids": []}
        return result

    async def _occupied_purchase_order_qty_by_requisition_item_ids(
        self,
        tenant_id: int,
        item_ids: List[int],
    ) -> Dict[int, Decimal]:
        """按申请行汇总下游采购订单占用数量（含草稿；删除的 PO 不计）。"""
        if not item_ids:
            return {}
        from apps.kuaizhizao.models.purchase_order import PurchaseOrder, PurchaseOrderItem

        pois = await PurchaseOrderItem.filter(
            tenant_id=tenant_id,
            source_id__in=item_ids,
            deleted_at__isnull=True,
        ).all()
        if not pois:
            return {}
        order_ids = {int(pi.order_id) for pi in pois if pi.order_id}
        live_order_ids = set(
            await PurchaseOrder.filter(
                tenant_id=tenant_id,
                id__in=list(order_ids),
                deleted_at__isnull=True,
            ).values_list("id", flat=True)
        )
        occupied: Dict[int, Decimal] = {}
        for pi in pois:
            if int(pi.order_id or 0) not in live_order_ids:
                continue
            if not is_purchase_requisition_source_type(getattr(pi, "source_type", None)):
                continue
            sid = int(pi.source_id or 0)
            if sid <= 0:
                continue
            occupied[sid] = occupied.get(sid, Decimal("0")) + Decimal(
                str(pi.ordered_quantity or 0)
            )
        return occupied

    async def _occupied_inquiry_qty_by_requisition_item_ids(
        self,
        tenant_id: int,
        item_ids: List[int],
    ) -> Dict[int, Decimal]:
        """按申请行汇总下游询价占用数量（含草稿；删除的询价不计）。"""
        if not item_ids:
            return {}
        from apps.kuaizhizao.models.purchase_inquiry import PurchaseInquiry, PurchaseInquiryItem

        rows = await PurchaseInquiryItem.filter(
            tenant_id=tenant_id,
            source_requisition_item_id__in=item_ids,
        ).all()
        if not rows:
            return {}
        inquiry_ids = {int(r.inquiry_id) for r in rows if r.inquiry_id}
        live_inquiry_ids = set(
            await PurchaseInquiry.filter(
                tenant_id=tenant_id,
                id__in=list(inquiry_ids),
                deleted_at__isnull=True,
            ).values_list("id", flat=True)
        )
        occupied: Dict[int, Decimal] = {}
        for row in rows:
            if int(row.inquiry_id or 0) not in live_inquiry_ids:
                continue
            sid = int(row.source_requisition_item_id or 0)
            if sid <= 0:
                continue
            occupied[sid] = occupied.get(sid, Decimal("0")) + Decimal(str(row.quantity or 0))
        return occupied

    async def list_purchase_order_pull_lines(
        self,
        tenant_id: int,
        *,
        skip: int = 0,
        limit: int = 20,
        keyword: Optional[str] = None,
        requisition_id: Optional[int] = None,
        pullable_only: bool = True,
    ) -> Dict[str, Any]:
        """开口申请行：可转采购订单的剩余明细。"""
        return await self._list_requisition_open_lines(
            tenant_id,
            skip=skip,
            limit=limit,
            keyword=keyword,
            requisition_id=requisition_id,
            pullable_only=pullable_only,
            target="purchase_order",
        )

    async def list_purchase_inquiry_pull_lines(
        self,
        tenant_id: int,
        *,
        skip: int = 0,
        limit: int = 20,
        keyword: Optional[str] = None,
        requisition_id: Optional[int] = None,
        pullable_only: bool = True,
    ) -> Dict[str, Any]:
        """开口申请行：可转询价的剩余明细。"""
        return await self._list_requisition_open_lines(
            tenant_id,
            skip=skip,
            limit=limit,
            keyword=keyword,
            requisition_id=requisition_id,
            pullable_only=pullable_only,
            target="inquiry",
        )

    async def _list_requisition_open_lines(
        self,
        tenant_id: int,
        *,
        skip: int,
        limit: int,
        keyword: Optional[str],
        requisition_id: Optional[int],
        pullable_only: bool,
        target: str,
    ) -> Dict[str, Any]:
        req_query = PurchaseRequisition.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if requisition_id is not None:
            req_query = req_query.filter(id=int(requisition_id))
        if pullable_only:
            req_query = req_query.filter(status__in=REQUISITION_DOWNSTREAM_PUSH_STATUS_VALUES)
        requisitions = await req_query.only(
            "id",
            "requisition_code",
            "status",
            "review_status",
            "requisition_date",
            "applicant_name",
            "department_id",
            "department_name",
        )
        req_by_id = {int(r.id): r for r in requisitions}
        if not req_by_id:
            return {"data": [], "total": 0}

        items = await PurchaseRequisitionItem.filter(
            tenant_id=tenant_id,
            requisition_id__in=list(req_by_id.keys()),
        ).all()

        item_ids = [int(i.id) for i in items if i.id is not None]
        occupied_po = (
            await self._occupied_purchase_order_qty_by_requisition_item_ids(tenant_id, item_ids)
            if target == "purchase_order"
            else {}
        )
        occupied_inquiry = (
            await self._occupied_inquiry_qty_by_requisition_item_ids(tenant_id, item_ids)
            if target == "inquiry"
            else {}
        )

        items_by_material_group: Dict[Tuple[int, int], List] = {}
        for item in items:
            key = requisition_material_group_key(
                item.requisition_id, item.material_id, fallback_item_id=item.id,
            )
            items_by_material_group.setdefault(key, []).append(item)
        occupied_map = occupied_po if target == "purchase_order" else occupied_inquiry
        kw = (keyword or "").strip().lower()
        lines: List[Dict[str, Any]] = []
        for item in items:
            req = req_by_id.get(int(item.requisition_id))
            if not req:
                continue
            can_push = requisition_open_line_can_push(req, target=target)
            qty = float(item.quantity or 0)
            if qty <= 0:
                continue
            item_id = int(item.id) if item.id is not None else 0
            key = requisition_material_group_key(
                item.requisition_id, item.material_id, fallback_item_id=item_id or None,
            )
            group_items = items_by_material_group[key]
            group_suggested = sum(Decimal(str(i.quantity or 0)) for i in group_items)
            group_occupied = sum(
                (occupied_map.get(int(i.id), Decimal("0")) for i in group_items if i.id is not None),
                Decimal("0"),
            )
            suggested, pushed, remaining = build_partial_push_qty_triplet(
                group_suggested, group_occupied,
            )
            is_open_carrier = qty > float(occupied_map.get(item_id, Decimal("0")))
            group_ids = [int(i.id) for i in group_items if i.id is not None]
            is_closed_group_rep = (
                not is_open_carrier and remaining <= 0
                and bool(group_ids) and item_id == max(group_ids)
            )
            if pullable_only and not is_open_carrier:
                continue
            if not pullable_only and not is_open_carrier and not is_closed_group_rep:
                continue
            material_code = str(item.material_code or "").strip()
            material_name = str(item.material_name or "").strip()
            material_spec = str(item.material_spec or "").strip()
            department_name = str(getattr(req, "department_name", None) or "").strip()
            if kw:
                haystack = " ".join(
                    [material_code, material_name, material_spec, department_name]
                ).lower()
                if kw not in haystack:
                    continue
            requisition_date = req.requisition_date.isoformat() if req.requisition_date else None
            lines.append(
                {
                    "id": int(item.id),
                    "requisition_id": int(item.requisition_id),
                    "requisition_code": req.requisition_code,
                    "requisition_status": req.status,
                    "can_push": can_push,
                    "document_date": requisition_date,
                    "requisition_date": requisition_date,
                    "applicant_name": (str(req.applicant_name or "").strip() or None),
                    "department_id": getattr(req, "department_id", None),
                    "department_name": department_name or None,
                    "material_id": item.material_id,
                    "material_code": material_code,
                    "material_name": material_name,
                    "material_spec": material_spec or None,
                    "unit": item.unit or "件",
                    "suggested_quantity": suggested,
                    "pushed_quantity": pushed,
                    "remaining_quantity": remaining,
                    "required_date": str(item.required_date) if item.required_date else None,
                    "supplier_id": item.supplier_id,
                }
            )

        # 单据日期倒序（最新在前），同日按申请/行 id 倒序
        lines.sort(
            key=lambda r: (
                str(r.get("document_date") or ""),
                int(r.get("requisition_id") or 0),
                int(r.get("id") or 0),
            )
        )
        total = len(lines)
        return {"data": lines[skip : skip + limit], "total": total}

    class _RequisitionPoPlan(NamedTuple):
        po_create: PurchaseOrderCreate
        supplier_id: int
        conversions: List[Tuple[PurchaseRequisitionItem, Decimal]]
        requisition_ids: List[int]

    def _resolve_convert_quantity(
        self, item: PurchaseRequisitionItem, data: ConvertToPurchaseOrderRequest
    ) -> Decimal:
        full_qty = item.quantity
        if data.item_quantities:
            override = data.item_quantities.get(item.id) or data.item_quantities.get(str(item.id))
            if override is not None:
                return Decimal(str(override))
        return full_qty

    async def plan_purchase_orders_from_requisition_convert(
        self,
        tenant_id: int,
        data: ConvertToPurchaseOrderRequest,
        *,
        assert_push_capability: bool = True,
    ) -> List["_RequisitionPoPlan"]:
        """按转单请求规划采购订单 create 载荷（不写库、不拆申请行）。

        所选明细合并为一张采购订单（与销售订单/需求计算/补货建议直推一致）。
        行供应商不一致或缺失时表头为待定供应商；禁止按供应商或价类拆成多张导致新建页只见一行。
        明细顺序与 item_ids 勾选序一致。
        """
        from apps.kuaizhizao.constants.price_type import DEFAULT_PURCHASE_PRICE_TYPE
        from apps.kuaizhizao.constants.purchase_order_type import normalize_purchase_order_type

        selected_ids = [int(v) for v in data.item_ids if v is not None]
        if not selected_ids:
            raise BusinessLogicError("请至少选择一条可下推采购申请明细")

        items = await PurchaseRequisitionItem.filter(
            tenant_id=tenant_id,
            id__in=selected_ids,
        ).all()
        if not items:
            raise BusinessLogicError("没有可转单的申请行或所选行不存在")

        item_by_id = {int(i.id): i for i in items if i.id is not None}
        ordered_items = [item_by_id[iid] for iid in selected_ids if iid in item_by_id]
        if not ordered_items:
            raise BusinessLogicError("没有可转单的申请行或所选行不存在")
        occupied_po = await self._occupied_purchase_order_qty_by_requisition_item_ids(
            tenant_id, [int(i.id) for i in ordered_items if i.id is not None]
        )

        requisition_ids = sorted({int(i.requisition_id) for i in ordered_items})
        requisitions = await PurchaseRequisition.filter(
            tenant_id=tenant_id,
            id__in=requisition_ids,
            deleted_at__isnull=True,
        ).all()
        req_by_id = {int(r.id): r for r in requisitions}
        req_header_required_by_id = {int(r.id): r.required_date for r in requisitions}
        if len(req_by_id) != len(requisition_ids):
            raise NotFoundError("采购申请不存在")
        if assert_push_capability:
            for req in requisitions:
                assert_purchase_requisition_capability(req, "push_purchase_order")

        from apps.kuaizhizao.services.purchase_inquiry_service import PurchaseInquiryService

        await PurchaseInquiryService._assert_requisition_items_not_in_active_inquiry(
            tenant_id, [i.id for i in ordered_items]
        )

        line_supplier_ids: List[int] = []
        for item in ordered_items:
            sid = self._resolve_line_supplier_id(item, data)
            line_supplier_ids.append(int(sid) if sid else 0)

        unique_positive = {sid for sid in line_supplier_ids if sid > 0}
        supplier_rows = (
            await Supplier.filter(tenant_id=tenant_id, id__in=list(unique_positive)).all()
            if unique_positive
            else []
        )
        supplier_by_id = {s.id: s for s in supplier_rows}
        for sid in unique_positive:
            if sid not in supplier_by_id:
                raise NotFoundError(f"供应商不存在: {sid}")

        if len(unique_positive) == 1:
            supplier_id = next(iter(unique_positive))
            sup = supplier_by_id.get(supplier_id)
            supplier_name = (sup.name if sup else None) or data.supplier_name or "待定供应商"
        else:
            supplier_id = 0
            sup = None
            supplier_name = data.supplier_name or "待定供应商"

        material_ids = sorted(
            {int(i.material_id) for i in ordered_items if i.material_id is not None}
        )
        material_rows = (
            await Material.filter(tenant_id=tenant_id, id__in=material_ids).all()
            if material_ids
            else []
        )
        material_by_id = {int(m.id): m for m in material_rows}
        today = to_site_date(resolve_business_datetime())
        source_req_ids = sorted({int(i.requisition_id) for i in ordered_items})
        primary = req_by_id[source_req_ids[0]]
        source_codes = " ".join(req_by_id[rid].requisition_code for rid in source_req_ids)
        po_items: List[PurchaseOrderItemCreate] = []
        conversions: List[Tuple[PurchaseRequisitionItem, Decimal]] = []
        po_line_required_dates: List[date] = []

        for item in ordered_items:
            item_id = int(item.id) if item.id is not None else 0
            remaining = Decimal(str(item.quantity or 0)) - occupied_po.get(item_id, Decimal("0"))
            if remaining <= 0:
                raise BusinessLogicError(f"物料 {item.material_code or item_id} 已无可下推数量")
            qty = self._resolve_convert_quantity(item, data)
            if qty <= 0:
                continue
            if qty > remaining:
                raise BusinessLogicError(
                    f"物料 {item.material_code or item_id} 下推数量 {qty} 超过可取数量 {remaining}"
                )
            header_required = req_header_required_by_id.get(int(item.requisition_id))
            line_required = self._resolve_requisition_item_required_date(
                item, header_required, today
            )
            po_line_required_dates.append(line_required)
            price_override = None
            if data.item_unit_prices:
                price_override = data.item_unit_prices.get(item.id) or data.item_unit_prices.get(
                    str(item.id)
                )
                if price_override is not None:
                    price_override = Decimal(str(price_override))
            line_supplier_id = self._resolve_line_supplier_id(item, data)
            line_pricing = await self._build_requisition_push_line_pricing(
                tenant_id,
                item=item,
                material_by_id=material_by_id,
                supplier_id=line_supplier_id,
                quantity=qty,
                price_override=price_override,
            )
            conversions.append((item, qty))
            po_items.append(
                PurchaseOrderItemCreate(
                    material_id=item.material_id,
                    material_code=item.material_code,
                    material_name=item.material_name,
                    material_spec=item.material_spec,
                    ordered_quantity=qty,
                    unit=item.unit or "件",
                    unit_price=line_pricing.stored_unit_price,
                    display_unit_price=line_pricing.display_unit_price,
                    total_price=line_pricing.stored_line_excl_total,
                    tax_rate=line_pricing.tax_rate_percent,
                    received_quantity=Decimal(0),
                    outstanding_quantity=qty,
                    required_date=line_required,
                    source_type="purchase_requisition",
                    source_id=item.id,
                    demand_computation_item_id=item.demand_computation_item_id,
                    work_order_id=item.work_order_id,
                    work_order_code=item.work_order_code,
                    notes=item.notes,
                    **partner_snapshot_fields_from_source_line(item),
                )
            )

        if not po_items:
            raise BusinessLogicError("所选明细的本次下推数量均为 0，无法生成采购订单")

        delivery_date = max(po_line_required_dates, default=today)
        po_create = PurchaseOrderCreate(
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            order_date=today,
            delivery_date=delivery_date,
            order_type=normalize_purchase_order_type(getattr(primary, "order_type", None)),
            price_type=DEFAULT_PURCHASE_PRICE_TYPE,
            status=DocumentStatus.DRAFT.value,
            source_type="purchase_requisition",
            source_id=primary.id,
            department_id=getattr(primary, "department_id", None),
            department_name=getattr(primary, "department_name", None),
            notes=f"由采购申请{source_codes}转单生成",
            items=po_items,
            **_supplier_header_contact_fields(sup),
        )
        return [
            self._RequisitionPoPlan(
                po_create=po_create,
                supplier_id=supplier_id,
                conversions=conversions,
                requisition_ids=source_req_ids,
            )
        ]

    async def draft_purchase_orders_from_requisition_convert(
        self,
        tenant_id: int,
        data: ConvertToPurchaseOrderRequest,
    ) -> Dict[str, Any]:
        """供前端 handoff：返回每张规划采购单的 create 载荷与 document_flow。"""
        plans = await self.plan_purchase_orders_from_requisition_convert(tenant_id, data)
        drafts: List[Dict[str, Any]] = []
        for plan in plans:
            item_ids = [int(it.id) for it, _qty in plan.conversions if it.id is not None]
            qty_map = {int(it.id): float(qty) for it, qty in plan.conversions if it.id is not None}
            price_map: Dict[int, float] = {}
            if data.item_unit_prices:
                for it, _qty in plan.conversions:
                    if it.id is None:
                        continue
                    p = data.item_unit_prices.get(it.id) or data.item_unit_prices.get(str(it.id))
                    if p is not None:
                        price_map[int(it.id)] = float(p)
            supplier_map: Dict[int, int] = {}
            if data.item_suppliers:
                for it, _qty in plan.conversions:
                    if it.id is None:
                        continue
                    s = data.item_suppliers.get(it.id) or data.item_suppliers.get(str(it.id))
                    if s is not None:
                        supplier_map[int(it.id)] = int(s)
            payload = plan.po_create.model_dump(by_alias=True, mode="json")
            drafts.append(
                {
                    "create_payload": payload,
                    "document_flow": {
                        "documentFlowSourceType": "purchase_requisition_items",
                        "documentFlowRequisitionItemIds": item_ids,
                        "documentFlowItemQuantities": qty_map or None,
                        "documentFlowItemUnitPrices": price_map or None,
                        "documentFlowItemSuppliers": supplier_map or None,
                        "documentFlowPersistDefaultSupplier": data.persist_default_supplier_to_material,
                    },
                    "supplier_id": plan.supplier_id,
                    "requisition_ids": plan.requisition_ids,
                }
            )
        return {
            "target_type": "purchase_order",
            "source_type": "purchase_requisition",
            "drafts": drafts,
        }

    async def _maybe_split_requisition_item_for_qty(
        self,
        tenant_id: int,
        item: PurchaseRequisitionItem,
        qty: Decimal,
        requisition_id: int,
    ) -> PurchaseRequisitionItem:
        full_qty = item.quantity
        if qty >= full_qty:
            return item
        remaining = full_qty - qty
        await PurchaseRequisitionItem.create(
            tenant_id=tenant_id,
            requisition_id=requisition_id,
            material_id=item.material_id,
            material_code=item.material_code,
            material_name=item.material_name,
            material_spec=item.material_spec,
            unit=item.unit or "件",
            quantity=remaining,
            suggested_unit_price=item.suggested_unit_price,
            required_date=item.required_date,
            demand_computation_item_id=item.demand_computation_item_id,
            work_order_id=item.work_order_id,
            work_order_code=item.work_order_code,
            supplier_id=item.supplier_id,
            notes=item.notes,
        )
        await item.update_from_dict({"quantity": qty}).save()
        return item

    async def sync_requisition_item_to_po_occupation(
        self, tenant_id: int, requisition_item_id: int
    ) -> None:
        """按下游采购订单占用回写申请行数量：
        - 占用少于行量：拆出未转行（无 purchase_order_id），便于再次取单
        - 占用多于行量：从同物料未转行吸收数量
        - 占用为 0：清除挂链
        """
        item = await PurchaseRequisitionItem.get_or_none(
            tenant_id=tenant_id, id=requisition_item_id
        )
        if not item or item.id is None:
            return
        occupied_map = await self._occupied_purchase_order_qty_by_requisition_item_ids(
            tenant_id, [int(item.id)]
        )
        occupied = occupied_map.get(int(item.id), Decimal("0"))
        full_qty = Decimal(str(item.quantity or 0))
        if occupied <= 0:
            if item.purchase_order_id or item.purchase_order_item_id:
                await item.update_from_dict(
                    {"purchase_order_id": None, "purchase_order_item_id": None}
                ).save()
            return
        if full_qty <= 0:
            await item.update_from_dict({"quantity": occupied}).save()
            return

        if occupied + Decimal("0.0000001") >= full_qty and occupied <= full_qty:
            # 已占满（含浮点容差）；数量与占用一致即可
            if occupied != full_qty:
                await item.update_from_dict({"quantity": occupied}).save()
            return

        if occupied < full_qty:
            remaining = full_qty - occupied
            await PurchaseRequisitionItem.create(
                tenant_id=tenant_id,
                requisition_id=int(item.requisition_id),
                material_id=item.material_id,
                material_code=item.material_code,
                material_name=item.material_name,
                material_spec=item.material_spec,
                unit=item.unit or "件",
                quantity=remaining,
                suggested_unit_price=item.suggested_unit_price,
                required_date=item.required_date,
                demand_computation_item_id=item.demand_computation_item_id,
                work_order_id=item.work_order_id,
                work_order_code=item.work_order_code,
                supplier_id=item.supplier_id,
                notes=item.notes,
                **partner_snapshot_fields_from_source_line(item),
            )
            await item.update_from_dict({"quantity": occupied}).save()
            return

        # occupied > full_qty：从同物料未转行吸收
        need = occupied - full_qty
        frees = await PurchaseRequisitionItem.filter(
            tenant_id=tenant_id,
            requisition_id=int(item.requisition_id),
            material_id=item.material_id,
            purchase_order_id__isnull=True,
        ).exclude(id=int(item.id)).all()
        for free in frees:
            if need <= 0:
                break
            fq = Decimal(str(free.quantity or 0))
            if fq <= 0:
                await free.delete()
                continue
            if fq <= need:
                need -= fq
                await free.delete()
            else:
                await free.update_from_dict({"quantity": fq - need}).save()
                need = Decimal("0")
        await item.update_from_dict({"quantity": occupied}).save()

    async def finalize_requisition_items_after_purchase_order_created(
        self,
        tenant_id: int,
        purchase_order_id: int,
        purchase_order_code: str,
        po_items: List[PurchaseOrderItem],
        created_by: int,
        requisition_item_ids: List[int],
        convert_data: ConvertToPurchaseOrderRequest,
    ) -> List[int]:
        """采购订单保存后回写申请行、关联与申请头状态。返回已回写默认供应商的物料 id。"""
        from apps.kuaizhizao.services.document_relation_new_service import DocumentRelationNewService
        from apps.kuaizhizao.schemas.document_relation import DocumentRelationCreate

        items = await PurchaseRequisitionItem.filter(
            tenant_id=tenant_id,
            id__in=requisition_item_ids,
        ).all()
        item_by_id = {int(i.id): i for i in items}
        rel_svc = DocumentRelationNewService()
        persisted_material_ids: List[int] = []
        supplier_id = int((await PurchaseOrder.get(id=purchase_order_id)).supplier_id or 0)
        supplier_name = ""
        if supplier_id > 0:
            sup = await Supplier.get_or_none(tenant_id=tenant_id, id=supplier_id)
            supplier_name = (sup.name if sup else "") or ""

        po_item_by_source = {
            int(pi.source_id): pi
            for pi in po_items
            if pi.source_id is not None and is_purchase_requisition_source_type(pi.source_type)
        }
        # 前端若未注册 source_id，落库行可能没有来源。按 handoff 申请行与同物料未挂链 PO 行补齐。
        linked_poi_ids = {int(pi.id) for pi in po_item_by_source.values() if pi.id is not None}
        unlinked_by_material: Dict[int, List[PurchaseOrderItem]] = {}
        for pi in po_items:
            if pi.id is None or int(pi.id) in linked_poi_ids:
                continue
            if pi.source_id is not None and is_purchase_requisition_source_type(pi.source_type):
                continue
            mid = int(pi.material_id or 0)
            if mid <= 0:
                continue
            unlinked_by_material.setdefault(mid, []).append(pi)

        requisition_ids: set[int] = set()
        # 只回写「本单实际落库的 PO 行」对应的申请行：数量以 PO 行为真源；
        # 表单删行/改量后不得按 handoff 全量 item_ids 误占未转出的申请行。
        for rid in requisition_item_ids:
            raw = item_by_id.get(int(rid))
            if not raw:
                continue
            po_item = po_item_by_source.get(int(rid))
            if not po_item or not po_item.id:
                bucket = unlinked_by_material.get(int(raw.material_id or 0)) or []
                if not bucket:
                    continue
                po_item = bucket.pop(0)
                await po_item.update_from_dict(
                    {
                        "source_type": "purchase_requisition",
                        "source_id": int(rid),
                    }
                ).save()
                po_item_by_source[int(rid)] = po_item
            qty = Decimal(str(po_item.ordered_quantity or 0))
            if qty <= 0:
                qty = self._resolve_convert_quantity(raw, convert_data)
            if qty <= 0:
                continue
            item = await self._maybe_split_requisition_item_for_qty(
                tenant_id, raw, qty, int(raw.requisition_id)
            )
            po_item_id = int(po_item.id) if po_item and po_item.id else None
            await item.update_from_dict(
                {
                    "purchase_order_id": purchase_order_id,
                    "purchase_order_item_id": po_item_id,
                    "supplier_id": supplier_id if supplier_id > 0 else None,
                }
            ).save()
            requisition_ids.add(int(item.requisition_id))

            if convert_data.persist_default_supplier_to_material and supplier_id > 0:
                ok = await self._persist_buy_default_supplier(
                    tenant_id, item.material_id, supplier_id, supplier_name
                )
                if ok and item.material_id and item.material_id not in persisted_material_ids:
                    persisted_material_ids.append(item.material_id)

        req_by_id = {
            int(r.id): r
            for r in await PurchaseRequisition.filter(
                tenant_id=tenant_id, id__in=list(requisition_ids), deleted_at__isnull=True
            ).all()
        }
        for rid in requisition_ids:
            req = req_by_id.get(rid)
            if not req:
                continue
            await rel_svc.create_relation(
                tenant_id=tenant_id,
                relation_data=DocumentRelationCreate(
                    source_type="purchase_requisition",
                    source_id=rid,
                    source_code=req.requisition_code,
                    source_name=req.requisition_name or req.requisition_code,
                    target_type="purchase_order",
                    target_id=purchase_order_id,
                    target_code=purchase_order_code,
                    target_name=purchase_order_code,
                    relation_type="source",
                    relation_mode="push",
                    relation_desc="采购申请转采购订单",
                ),
                created_by=created_by,
            )

        for rid in requisition_ids:
            req = req_by_id[rid]
            await self._recalc_conversion_status(tenant_id, req)

        # 头表来源：取单创建时若前端未带回 source，按本批申请回写，便于后续自愈
        if requisition_ids:
            primary_req_id = next(iter(sorted(requisition_ids)))
            po_header = await PurchaseOrder.get_or_none(tenant_id=tenant_id, id=purchase_order_id)
            if po_header and (
                not po_header.source_id
                or not is_purchase_requisition_source_type(getattr(po_header, "source_type", None))
            ):
                await po_header.update_from_dict(
                    {
                        "source_type": "purchase_requisition",
                        "source_id": primary_req_id,
                    }
                ).save()

        push_mode = await BusinessConfigService().get_push_default_mode(tenant_id)
        if push_mode == "confirm":
            try:
                await self.purchase_service.submit_purchase_order(
                    tenant_id=tenant_id,
                    order_id=purchase_order_id,
                    submitted_by=created_by,
                )
            except Exception as e:
                logger.warning(
                    "采购申请 handoff 转单后自动提交采购订单失败: po_id={} err={}",
                    purchase_order_id,
                    e,
                )
        return persisted_material_ids

    def _convert_data_from_document_flow(self, order_data: PurchaseOrderCreate) -> ConvertToPurchaseOrderRequest:
        item_ids = list(getattr(order_data, "document_flow_requisition_item_ids", None) or [])
        qty_raw = getattr(order_data, "document_flow_item_quantities", None) or {}
        price_raw = getattr(order_data, "document_flow_item_unit_prices", None) or {}
        sup_raw = getattr(order_data, "document_flow_item_suppliers", None) or {}
        return ConvertToPurchaseOrderRequest(
            item_ids=item_ids,
            item_quantities={int(k): float(v) for k, v in qty_raw.items()} if qty_raw else None,
            item_unit_prices={int(k): float(v) for k, v in price_raw.items()} if price_raw else None,
            item_suppliers={int(k): int(v) for k, v in sup_raw.items()} if sup_raw else None,
            persist_default_supplier_to_material=bool(
                getattr(order_data, "document_flow_persist_default_supplier", False)
            ),
        )

    async def convert_selected_items_to_purchase_orders(
        self,
        tenant_id: int,
        item_ids: List[int],
        created_by: int,
        convert_data: Optional[ConvertToPurchaseOrderRequest] = None,
    ) -> Dict[str, Any]:
        """按申请行 id 转采购订单，可跨多张申请；所选明细合并一张订单。"""
        ordered_ids = [int(v) for v in item_ids if v is not None]
        if convert_data is not None:
            data = ConvertToPurchaseOrderRequest(
                item_ids=ordered_ids,
                supplier_id=convert_data.supplier_id,
                supplier_name=convert_data.supplier_name,
                item_quantities=convert_data.item_quantities,
                item_unit_prices=convert_data.item_unit_prices,
                item_suppliers=convert_data.item_suppliers,
                persist_default_supplier_to_material=convert_data.persist_default_supplier_to_material,
            )
        else:
            data = ConvertToPurchaseOrderRequest(item_ids=ordered_ids)
        plans = await self.plan_purchase_orders_from_requisition_convert(tenant_id, data)
        purchase_orders_out: List[Dict[str, Any]] = []
        persisted_material_ids: List[int] = []
        for plan in plans:
            po = await self.purchase_service.create_purchase_order(
                tenant_id=tenant_id,
                order_data=plan.po_create,
                created_by=created_by,
            )
            item_ids_plan = [int(it.id) for it, _q in plan.conversions if it.id is not None]
            convert_slice = ConvertToPurchaseOrderRequest(
                item_ids=item_ids_plan,
                supplier_id=data.supplier_id,
                supplier_name=data.supplier_name,
                item_quantities={
                    int(it.id): float(qty) for it, qty in plan.conversions if it.id is not None
                },
                item_unit_prices=data.item_unit_prices,
                item_suppliers=data.item_suppliers,
                persist_default_supplier_to_material=data.persist_default_supplier_to_material,
            )
            po_items = await PurchaseOrderItem.filter(
                tenant_id=tenant_id, order_id=po.id
            ).all()
            persisted = await self.finalize_requisition_items_after_purchase_order_created(
                tenant_id=tenant_id,
                purchase_order_id=int(po.id),
                purchase_order_code=po.order_code,
                po_items=po_items,
                created_by=created_by,
                requisition_item_ids=item_ids_plan,
                convert_data=convert_slice,
            )
            for mid in persisted:
                if mid not in persisted_material_ids:
                    persisted_material_ids.append(mid)
            purchase_orders_out.append(
                {
                    "purchase_order_id": po.id,
                    "purchase_order_code": po.order_code,
                    "supplier_id": plan.supplier_id,
                }
            )

        first = purchase_orders_out[0]
        msg = (
            f"转单成功，共生成 {len(purchase_orders_out)} 张采购订单"
            if len(purchase_orders_out) > 1
            else "转单成功"
        )
        return {
            "success": True,
            "message": msg,
            "purchase_order_id": first["purchase_order_id"],
            "purchase_order_code": first["purchase_order_code"],
            "purchase_orders": purchase_orders_out,
            "persisted_material_ids": persisted_material_ids,
        }
