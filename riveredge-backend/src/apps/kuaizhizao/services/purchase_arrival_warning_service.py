"""采购到货预警服务"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from tortoise.expressions import Q

from apps.common.base_service import AppBaseService
from apps.kuaizhizao.models.purchase_order import (
    PurchaseOrder,
    PurchaseOrderItem,
    effective_po_item_outstanding,
)
from apps.kuaizhizao.models.purchase_arrival_delay_report import PurchaseArrivalDelayReport
from apps.kuaizhizao.utils.purchase_arrival_warning import (
    DEFAULT_ARRIVAL_IMMINENT_DAYS,
    PO_TERMINAL_STATUSES,
    WARNING_LEVEL_IMMINENT,
    WARNING_LEVEL_OVERDUE,
    compute_warning_level,
    enrich_line_warning_fields,
    line_has_open_receipt,
    resolve_arrival_processing_status,
)
from core.services.authorization.data_scope_service import DataScopeService
from core.utils.timezone_utils import resolve_business_datetime, to_site_date
from infra.models.user import User as CurrentUser
from infra.services.business_config_service import BusinessConfigService


class PurchaseArrivalWarningService(AppBaseService[PurchaseOrder]):
    """行级采购到货预警查询（与进度报表口径一致）。"""

    async def get_arrival_imminent_days(self, tenant_id: int) -> int:
        cfg = await BusinessConfigService().get_business_config(tenant_id)
        raw = (
            cfg.get("parameters", {})
            .get("procurement", {})
            .get("arrival_imminent_days", DEFAULT_ARRIVAL_IMMINENT_DAYS)
        )
        try:
            days = int(raw)
        except (TypeError, ValueError):
            days = DEFAULT_ARRIVAL_IMMINENT_DAYS
        return max(0, days)

    async def _scoped_po_query(self, tenant_id: int, current_user: Optional[CurrentUser] = None):
        query = PurchaseOrder.filter(tenant_id=tenant_id, deleted_at__isnull=True).exclude(
            status__in=list(PO_TERMINAL_STATUSES)
        )
        if current_user is None:
            return query
        return await DataScopeService.apply(
            query,
            tenant_id=tenant_id,
            user=current_user,
            resource="kuaizhizao:purchase-order",
        )

    async def _latest_delay_by_item(
        self, tenant_id: int, item_ids: List[int]
    ) -> Dict[int, PurchaseArrivalDelayReport]:
        if not item_ids:
            return {}
        rows = (
            await PurchaseArrivalDelayReport.filter(
                tenant_id=tenant_id,
                purchase_order_item_id__in=item_ids,
                deleted_at__isnull=True,
            )
            .order_by("-updated_at", "-id")
            .all()
        )
        stale_change_ids = [
            int(row.purchase_order_change_id)
            for row in rows
            if row.purchase_order_change_id
        ]
        active_change_ids: set[int] = set()
        if stale_change_ids:
            from apps.kuaizhizao.models.purchase_order_change_order import PurchaseOrderChangeOrder

            active_change_ids = set(
                await PurchaseOrderChangeOrder.filter(
                    tenant_id=tenant_id,
                    id__in=stale_change_ids,
                    deleted_at__isnull=True,
                ).values_list("id", flat=True)
            )

        out: Dict[int, PurchaseArrivalDelayReport] = {}
        for row in rows:
            key = int(row.purchase_order_item_id)
            if key in out:
                continue
            if row.purchase_order_change_id and int(row.purchase_order_change_id) not in active_change_ids:
                row.purchase_order_change_id = None
                row.purchase_order_change_code = None
                if str(row.status or "").lower() == "change_generated":
                    row.deleted_at = resolve_business_datetime()
                    await row.save()
                    continue
            out[key] = row
        return out

    async def _change_status_by_id(
        self, tenant_id: int, change_ids: List[int]
    ) -> Dict[int, str]:
        if not change_ids:
            return {}
        from apps.kuaizhizao.models.purchase_order_change_order import PurchaseOrderChangeOrder

        rows = await PurchaseOrderChangeOrder.filter(
            tenant_id=tenant_id,
            id__in=change_ids,
            deleted_at__isnull=True,
        ).values("id", "status")
        return {int(row["id"]): str(row.get("status") or "") for row in rows}

    def _resolve_processing_status(
        self,
        delay: Optional[PurchaseArrivalDelayReport],
        change_status: Optional[str] = None,
    ) -> str:
        if delay is None:
            return resolve_arrival_processing_status()
        return resolve_arrival_processing_status(
            delay_status=delay.status,
            delay_review_status=delay.review_status,
            change_order_id=delay.purchase_order_change_id,
            change_order_status=change_status,
        )

    async def list_warnings(
        self,
        tenant_id: int,
        *,
        skip: int = 0,
        limit: int = 20,
        warning_level: Optional[str] = None,
        supplier_id: Optional[int] = None,
        supplier_keyword: Optional[str] = None,
        order_code: Optional[str] = None,
        material_keyword: Optional[str] = None,
        processing_status: Optional[str] = None,
        current_user: Optional[CurrentUser] = None,
    ) -> Dict[str, Any]:
        imminent_days = await self.get_arrival_imminent_days(tenant_id)
        site_today = to_site_date(resolve_business_datetime())

        po_q = await self._scoped_po_query(tenant_id, current_user)
        if supplier_id:
            po_q = po_q.filter(supplier_id=supplier_id)
        if supplier_keyword:
            po_q = po_q.filter(supplier_name__icontains=supplier_keyword.strip())
        if order_code:
            kw = order_code.strip()
            if supplier_keyword:
                po_q = po_q.filter(order_code__icontains=kw)
            else:
                po_q = po_q.filter(Q(order_code__icontains=kw) | Q(supplier_name__icontains=kw))

        po_ids = list(await po_q.values_list("id", flat=True))
        if not po_ids:
            return {"data": [], "total": 0, "success": True, "summary": self._empty_summary()}

        item_q = PurchaseOrderItem.filter(
            tenant_id=tenant_id,
            order_id__in=po_ids,
            deleted_at__isnull=True,
            outstanding_quantity__gt=0,
        )
        if material_keyword:
            kw = material_keyword.strip()
            item_q = item_q.filter(
                Q(material_code__icontains=kw) | Q(material_name__icontains=kw)
            )
        # 预警等级可下推到库：避免先拉全量明细再在 Python 过滤（角标/中心页易拖成 504）
        if warning_level == WARNING_LEVEL_OVERDUE:
            item_q = item_q.filter(required_date__lt=site_today)
        elif warning_level == WARNING_LEVEL_IMMINENT:
            imminent_end = site_today + timedelta(days=max(0, int(imminent_days)))
            item_q = item_q.filter(
                required_date__gte=site_today,
                required_date__lte=imminent_end,
            )
        elif warning_level == "normal":
            normal_start = site_today + timedelta(days=max(0, int(imminent_days)) + 1)
            item_q = item_q.filter(required_date__gte=normal_start)

        items = await item_q.order_by("required_date", "id").all()
        heads = await PurchaseOrder.filter(id__in=po_ids).values(
            "id",
            "order_code",
            "order_date",
            "supplier_id",
            "supplier_name",
            "buyer_id",
            "buyer_name",
            "status",
            "delivery_date",
        )
        head_map = {int(h["id"]): h for h in heads}

        delay_map = await self._latest_delay_by_item(
            tenant_id, [int(i.id) for i in items if i.id]
        )
        change_ids = sorted(
            {
                int(delay.purchase_order_change_id)
                for delay in delay_map.values()
                if delay.purchase_order_change_id
            }
        )
        change_status_map = await self._change_status_by_id(tenant_id, change_ids)

        rows: List[dict] = []

        for item in items:
            if not line_has_open_receipt(item):
                continue
            head = head_map.get(int(item.order_id), {})
            pending = float(effective_po_item_outstanding(item))
            row = {
                "id": int(item.id),
                "purchase_order_id": int(item.order_id),
                "purchase_order_item_id": int(item.id),
                "order_code": head.get("order_code") or "",
                "order_date": head.get("order_date"),
                "supplier_id": head.get("supplier_id"),
                "supplier_name": head.get("supplier_name") or "",
                "buyer_name": head.get("buyer_name") or "",
                "status": head.get("status") or "",
                "material_id": item.material_id,
                "material_code": item.material_code,
                "material_name": item.material_name,
                "material_spec": item.material_spec,
                "unit": item.unit,
                "ordered_quantity": float(item.ordered_quantity or 0),
                "received_quantity": float(item.received_quantity or 0),
                "outstanding_quantity": pending,
                "required_date": item.required_date,
            }
            enrich_line_warning_fields(row, site_today=site_today, imminent_days=imminent_days)
            if row.get("warning_level") is None:
                continue

            delay = delay_map.get(int(item.id))
            change_status = (
                change_status_map.get(int(delay.purchase_order_change_id))
                if delay and delay.purchase_order_change_id
                else None
            )
            row["processing_status"] = self._resolve_processing_status(delay, change_status)
            row["delay_report_id"] = delay.id if delay else None
            row["delay_report_code"] = delay.report_code if delay else None
            row["delay_status"] = delay.status if delay else None
            row["delay_review_status"] = delay.review_status if delay else None
            row["purchase_order_change_id"] = delay.purchase_order_change_id if delay else None
            # 影响总成先占位，仅对本页行再批量解析，避免全量明细做溯源
            row["impacted_assembly"] = (
                delay.impacted_assembly_summary if delay else None
            ) or ""

            if warning_level and row["warning_level"] != warning_level:
                continue
            if processing_status and row["processing_status"] != processing_status:
                continue
            rows.append(row)

        summary = {"normal": 0, "imminent": 0, "overdue": 0, "total_open_lines": 0}
        for row in rows:
            if row.get("processing_status") == "changed":
                continue
            summary["total_open_lines"] += 1
            wl = row.get("warning_level")
            if wl in summary:
                summary[wl] += 1

        total = len(rows)
        page = rows[skip : skip + limit]
        await self._attach_delay_audit(tenant_id, page, delay_map, current_user)
        if page:
            from apps.kuaizhizao.services.purchase_po_line_impact_service import (
                PurchasePoLineImpactService,
            )

            page_item_ids = {int(r["purchase_order_item_id"]) for r in page}
            page_items = [item for item in items if int(item.id) in page_item_ids]
            impact_map = await PurchasePoLineImpactService().batch_resolve_impact_summaries(
                tenant_id, page_items
            )
            for row in page:
                iid = int(row["purchase_order_item_id"])
                if impact_map.get(iid):
                    row["impacted_assembly"] = impact_map[iid]
        return {"data": page, "total": total, "success": True, "summary": summary}

    def _empty_summary(self) -> dict:
        return {"normal": 0, "imminent": 0, "overdue": 0, "total_open_lines": 0}

    async def _attach_delay_audit(
        self,
        tenant_id: int,
        page: List[dict],
        delay_map: Dict[int, PurchaseArrivalDelayReport],
        current_user: Optional[CurrentUser],
    ) -> None:
        from apps.kuaizhizao.services.purchase_arrival_delay_service import (
            derive_purchase_arrival_delay_capabilities,
        )
        from core.services.approval.audit_record_enricher import enrich_items, resolve_viewer_id

        shadows: List[dict] = []
        for row in page:
            delay = delay_map.get(int(row["purchase_order_item_id"]))
            if delay is None:
                continue
            shadows.append(
                {
                    "id": int(delay.id),
                    "status": delay.status,
                    "review_status": delay.review_status,
                    "capabilities": derive_purchase_arrival_delay_capabilities(
                        delay.status,
                        delay.review_status,
                        delay.purchase_order_change_id,
                    ),
                    "_row": row,
                }
            )
        if not shadows:
            return
        await enrich_items(
            tenant_id,
            "purchase_arrival_delay",
            shadows,
            viewer_id=resolve_viewer_id(current_user),
        )
        for shadow in shadows:
            row = shadow["_row"]
            row["audit"] = shadow.get("audit")
            row["capabilities"] = shadow.get("capabilities")

    async def _count_open_lines_by_warning_level(
        self,
        tenant_id: int,
        *,
        warning_level: str,
        current_user: Optional[CurrentUser] = None,
    ) -> int:
        """角标/汇总专用计数：只做范围 PO + 明细条件 count，禁止走 list_warnings 全量装配。"""
        imminent_days = await self.get_arrival_imminent_days(tenant_id)
        site_today = to_site_date(resolve_business_datetime())
        po_q = await self._scoped_po_query(tenant_id, current_user)
        po_ids = list(await po_q.values_list("id", flat=True))
        if not po_ids:
            return 0

        item_q = PurchaseOrderItem.filter(
            tenant_id=tenant_id,
            order_id__in=po_ids,
            deleted_at__isnull=True,
            outstanding_quantity__gt=0,
            required_date__isnull=False,
        )
        level = str(warning_level or "").strip().lower()
        if level == WARNING_LEVEL_OVERDUE:
            item_q = item_q.filter(required_date__lt=site_today)
        elif level == WARNING_LEVEL_IMMINENT:
            imminent_end = site_today + timedelta(days=max(0, int(imminent_days)))
            item_q = item_q.filter(
                required_date__gte=site_today,
                required_date__lte=imminent_end,
            )
        else:
            return 0
        return int(await item_q.count())

    async def count_overdue_open_lines(
        self,
        tenant_id: int,
        *,
        current_user: Optional[CurrentUser] = None,
    ) -> int:
        return await self._count_open_lines_by_warning_level(
            tenant_id,
            warning_level=WARNING_LEVEL_OVERDUE,
            current_user=current_user,
        )

    async def count_imminent_open_lines(
        self,
        tenant_id: int,
        *,
        current_user: Optional[CurrentUser] = None,
    ) -> int:
        return await self._count_open_lines_by_warning_level(
            tenant_id,
            warning_level=WARNING_LEVEL_IMMINENT,
            current_user=current_user,
        )

    async def batch_po_has_arrival_overdue(
        self, tenant_id: int, po_ids: List[int]
    ) -> Dict[int, bool]:
        """批量判断采购订单是否存在逾期未关闭明细行（列表高亮用）。"""
        if not po_ids:
            return {}
        imminent_days = await self.get_arrival_imminent_days(tenant_id)
        site_today = to_site_date(resolve_business_datetime())

        heads = await PurchaseOrder.filter(
            tenant_id=tenant_id,
            id__in=po_ids,
            deleted_at__isnull=True,
        ).exclude(status__in=list(PO_TERMINAL_STATUSES)).values_list("id", flat=True)
        eligible_ids = [int(i) for i in heads]
        if not eligible_ids:
            return {int(i): False for i in po_ids}

        items = await PurchaseOrderItem.filter(
            tenant_id=tenant_id,
            order_id__in=eligible_ids,
            deleted_at__isnull=True,
        ).all()

        overdue_by_po: Dict[int, bool] = {int(i): False for i in po_ids}
        for item in items:
            if not line_has_open_receipt(item):
                continue
            dd = item.required_date
            if hasattr(dd, "date"):
                dd = dd.date() if callable(getattr(dd, "date", None)) else dd
            level = compute_warning_level(
                dd,
                site_today,
                imminent_days=imminent_days,
                has_open_qty=True,
            )
            if level == WARNING_LEVEL_OVERDUE:
                overdue_by_po[int(item.order_id)] = True
        return overdue_by_po
