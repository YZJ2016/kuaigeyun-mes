"""
销售管理服务模块

提供销售管理相关的业务逻辑处理。

Author: Luigi Lu
Date: 2025-12-30
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from decimal import Decimal
from tortoise.transactions import in_transaction
from tortoise.expressions import Q
from loguru import logger

from apps.kuaizhizao.models.sales_forecast import SalesForecast
from apps.kuaizhizao.models.sales_forecast_item import SalesForecastItem
from apps.kuaizhizao.models.demand import Demand
from apps.kuaizhizao.models.demand_item import DemandItem

SALES_FORECAST_SORTABLE_FIELDS = frozenset({
    "forecast_code",
    "forecast_name",
    "forecast_type",
    "forecast_period",
    "start_date",
    "end_date",
    "status",
    "review_status",
    "created_at",
    "updated_at",
})

from apps.kuaizhizao.schemas.sales import (
    SalesForecastCreate,
    SalesForecastUpdate,
    SalesForecastResponse,
    SalesForecastListResponse,
    SalesForecastItemCreate,
    SalesForecastItemResponse,
)

from apps.common.base_service import AppBaseService
from apps.kuaizhizao.constants import ReviewStatus
from apps.kuaizhizao.services.document_action_policy.sales_forecast import assert_sales_forecast_capability
from apps.kuaizhizao.services.document_action_policy.enricher import (
    enrich_sales_forecast_capabilities_on_response,
    enrich_sales_forecast_list_capabilities,
)
from infra.exceptions.exceptions import NotFoundError, ValidationError, BusinessLogicError
from core.utils.timezone_utils import resolve_business_datetime, to_site_date, today_site_str, to_api_isoformat, site_day_bounds_utc


class SalesForecastService(AppBaseService[SalesForecast]):
    """销售预测服务"""

    def __init__(self):
        super().__init__(SalesForecast)

    async def _hydrate_forecast_item_snapshots(
        self, tenant_id: int, items: List[SalesForecastItem]
    ) -> None:
        """按 material_id 回填预测明细物料快照（编码/名称/单位），与仓储单据一致。"""
        if not items:
            return
        from apps.kuaizhizao.services.warehouse_service import _hydrate_item_material_snapshot

        await _hydrate_item_material_snapshot(tenant_id, items)

    @staticmethod
    def _forecast_item_to_response(item: SalesForecastItem) -> SalesForecastItemResponse:
        from decimal import Decimal
        from apps.kuaizhizao.utils.forecast_consumption import forecast_open_quantity

        resp = SalesForecastItemResponse.model_validate(item)
        consumed = getattr(item, "consumed_quantity", None)
        open_qty = forecast_open_quantity(item.forecast_quantity, consumed)
        return resp.model_copy(
            update={
                "consumed_quantity": consumed if consumed is not None else Decimal("0"),
                "open_quantity": open_qty,
            }
        )

    def _is_forecast_pushed_to_computation(self, forecast: Any, demand: Optional[Demand] = None) -> bool:
        if bool(getattr(forecast, "planning_pushed_to_computation", False)):
            return True
        if demand and bool(getattr(demand, "pushed_to_computation", False)):
            return True
        return False

    async def _forecast_has_downstream(self, tenant_id: int, forecast_id: int) -> bool:
        """是否已有会阻断撤审的下游：仅「已下推需求计算」算阻断。

        下推失败时可能已落中间 Demand + 关联，但尚未创建需求计算；此类中间态不得阻断撤审/删除。
        """
        blocked = await self._forecast_downstream_ids(tenant_id, [forecast_id])
        return forecast_id in blocked

    async def _forecast_downstream_ids(self, tenant_id: int, forecast_ids: List[int]) -> set[int]:
        if not forecast_ids:
            return set()
        from apps.kuaizhizao.models.document_relation import DocumentRelation

        blocked: set[int] = set()

        # 销售预测直接关联需求计算
        direct_comp = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="sales_forecast",
            source_id__in=forecast_ids,
            target_type="demand_computation",
        ).values_list("source_id", flat=True)
        blocked.update(int(x) for x in direct_comp)

        demands = await Demand.filter(
            tenant_id=tenant_id,
            source_type="sales_forecast",
            source_id__in=forecast_ids,
            deleted_at__isnull=True,
        ).all()
        if not demands:
            return blocked

        demand_ids = [int(d.id) for d in demands if d.id is not None]
        # 需求已标记下推，或存在 demand→demand_computation 关联
        pushed_forecast_ids = {
            int(d.source_id)
            for d in demands
            if bool(getattr(d, "pushed_to_computation", False)) and d.source_id is not None
        }
        blocked.update(pushed_forecast_ids)

        if demand_ids:
            demand_comp_rels = await DocumentRelation.filter(
                tenant_id=tenant_id,
                source_type="demand",
                source_id__in=demand_ids,
                target_type="demand_computation",
            ).values_list("source_id", flat=True)
            demand_with_comp = {int(x) for x in demand_comp_rels}
            for d in demands:
                if d.id is not None and int(d.id) in demand_with_comp and d.source_id is not None:
                    blocked.add(int(d.source_id))

        return blocked

    async def _cleanup_unpushed_forecast_demand(
        self,
        tenant_id: int,
        forecast_id: int,
        *,
        demand_id: Optional[int] = None,
    ) -> None:
        """清理销售预测下推失败留下的、尚未真正下推到需求计算的中间 Demand。"""
        from apps.kuaizhizao.models.document_relation import DocumentRelation
        from apps.kuaizhizao.services.document_relation_new_service import (
            DocumentRelationNewService,
        )
        from core.utils.timezone_utils import resolve_business_datetime

        q = Demand.filter(
            tenant_id=tenant_id,
            source_type="sales_forecast",
            source_id=forecast_id,
            deleted_at__isnull=True,
            pushed_to_computation=False,
        )
        if demand_id is not None:
            q = q.filter(id=demand_id)
        demands = await q.all()
        if not demands:
            return

        now = resolve_business_datetime()
        for d in demands:
            # 若已挂到需求计算则跳过（双重保险）
            has_comp = await DocumentRelation.filter(
                tenant_id=tenant_id,
                source_type="demand",
                source_id=d.id,
                target_type="demand_computation",
            ).exists()
            if has_comp:
                continue
            async with in_transaction():
                await DemandItem.filter(tenant_id=tenant_id, demand_id=d.id).delete()
                await Demand.filter(tenant_id=tenant_id, id=d.id).update(deleted_at=now, updated_at=now)
                await DocumentRelationNewService().delete_relation(
                    tenant_id,
                    source_type="sales_forecast",
                    source_id=forecast_id,
                    target_type="demand",
                    target_id=d.id,
                )
            logger.info(
                "已清理销售预测 %s 未下推的中间需求 %s",
                forecast_id,
                d.demand_code,
            )

    async def _forecast_has_items_map(self, tenant_id: int, forecast_ids: List[int]) -> Dict[int, bool]:
        if not forecast_ids:
            return {}
        from tortoise.functions import Count

        rows = await SalesForecastItem.filter(
            tenant_id=tenant_id,
            forecast_id__in=forecast_ids,
        ).annotate(cnt=Count("id")).group_by("forecast_id").values("forecast_id", "cnt")
        return {int(r["forecast_id"]): int(r["cnt"] or 0) > 0 for r in rows}

    async def _forecast_total_quantity_map(
        self, tenant_id: int, forecast_ids: List[int]
    ) -> Dict[int, Decimal]:
        """按预测头汇总明细数量（列表订单视图不带 items 时用）。"""
        if not forecast_ids:
            return {}
        from tortoise.functions import Sum

        rows = await SalesForecastItem.filter(
            tenant_id=tenant_id,
            forecast_id__in=forecast_ids,
        ).annotate(total_qty=Sum("forecast_quantity")).group_by("forecast_id").values(
            "forecast_id", "total_qty"
        )
        out: Dict[int, Decimal] = {}
        for r in rows:
            out[int(r["forecast_id"])] = Decimal(str(r["total_qty"] or 0))
        return out

    async def _forecast_items_count_map(
        self, tenant_id: int, forecast_ids: List[int]
    ) -> Dict[int, int]:
        """按预测头统计产品种类（不重复 material_id）。"""
        if not forecast_ids:
            return {}
        rows = await SalesForecastItem.filter(
            tenant_id=tenant_id,
            forecast_id__in=forecast_ids,
        ).values_list("forecast_id", "material_id")
        by_fid: Dict[int, set[int]] = {}
        for fid, mid in rows:
            by_fid.setdefault(int(fid), set()).add(int(mid))
        return {fid: len(mids) for fid, mids in by_fid.items()}

    async def _audit_update_fields(self, updated_by: int) -> Dict[str, Any]:
        """状态流转等 .update() 必须同时写 updated_by / updated_by_name。"""
        user_info = await self.get_user_info(updated_by)
        return {
            "updated_by": updated_by,
            "updated_by_name": user_info["name"],
        }

    async def delete_sales_forecast(self, tenant_id: int, forecast_id: int) -> None:
        forecast = await SalesForecast.get_or_none(
            tenant_id=tenant_id, id=forecast_id, deleted_at__isnull=True
        )
        if not forecast:
            raise NotFoundError(f"销售预测不存在: {forecast_id}")
        assert_sales_forecast_capability(forecast, "delete")
        deleted = await SalesForecast.filter(tenant_id=tenant_id, id=forecast_id).delete()
        if not deleted:
            raise BusinessLogicError("销售预测删除失败")

    async def create_sales_forecast(self, tenant_id: int, forecast_data: SalesForecastCreate, created_by: int) -> SalesForecastResponse:
        """创建销售预测"""
        async with in_transaction():
            user_info = await self.get_user_info(created_by)
            code = getattr(forecast_data, "forecast_code", None) or ""
            code = (code.strip() if isinstance(code, str) else "") or None
            if not code or code == "AUTO":
                today = today_site_str()
                code = await self.generate_code(tenant_id, "SALES_FORECAST_CODE", prefix=f"SF{today}")

            # 准备创建数据，排除 forecast_code 后统一写入
            create_data = forecast_data.model_dump(exclude_unset=True, exclude={'created_by', 'forecast_code'})
            create_data['forecast_code'] = code
            create_data['created_by'] = created_by
            create_data['created_by_name'] = user_info["name"]
            create_data['updated_by'] = created_by
            create_data['updated_by_name'] = user_info["name"]
            
            forecast = await SalesForecast.create(
                tenant_id=tenant_id,
                **create_data
            )
            
            # 创建预测明细（如果提供了items）
            items_data = forecast_data.model_dump().get('items', [])
            created_items: List[SalesForecastItem] = []
            if items_data:
                for item_data in items_data:
                    created_items.append(
                        await SalesForecastItem.create(
                            tenant_id=tenant_id,
                            forecast_id=forecast.id,
                            **item_data,
                        )
                    )
                await self._hydrate_forecast_item_snapshots(tenant_id, created_items)

            # 与提交流程一致：蓝图配置无需审核时，创建后自动审核通过。
            # 不再自动联动需求池（Demand），避免形成「预测→需求计划」隐式链路。
            from infra.services.business_config_service import BusinessConfigService
            from apps.kuaizhizao.constants import DocumentStatus, ReviewStatus
            config_service = BusinessConfigService()
            audit_required = await config_service.check_audit_required(tenant_id, "sales_forecast")
            if not audit_required and str(getattr(forecast, "status", "") or "").strip() in ("草稿", "DRAFT"):
                await SalesForecast.filter(tenant_id=tenant_id, id=forecast.id).update(
                    status=DocumentStatus.AUDITED.value,
                    review_status=ReviewStatus.APPROVED.value,
                    **(await self._audit_update_fields(created_by)),
                )
                await self._try_auto_push_forecast_to_computation(
                    tenant_id=tenant_id,
                    forecast_id=forecast.id,
                    operator_id=created_by,
                )
                forecast = await SalesForecast.get(tenant_id=tenant_id, id=forecast.id)

            demand = await self._get_linked_demand_for_forecast(tenant_id, forecast.id)
            resp = SalesForecastResponse.model_validate(forecast)
            resp = enrich_sales_forecast_capabilities_on_response(
                forecast,
                resp,
                pushed_to_computation=self._is_forecast_pushed_to_computation(forecast, demand),
                has_downstream=await self._forecast_has_downstream(tenant_id, forecast.id),
                has_items=bool(items_data),
            )
            return resp

    async def get_sales_forecast_by_id(self, tenant_id: int, forecast_id: int) -> SalesForecastResponse:
        """根据ID获取销售预测（含明细，与列表 include_items 行为一致）"""
        forecast = await SalesForecast.get_or_none(
            tenant_id=tenant_id,
            id=forecast_id,
            deleted_at__isnull=True,
        )
        if not forecast:
            raise NotFoundError(f"销售预测不存在: {forecast_id}")
        resp = SalesForecastResponse.model_validate(forecast)
        item_rows = await SalesForecastItem.filter(tenant_id=tenant_id, forecast_id=forecast_id).order_by("forecast_date").all()
        await self._hydrate_forecast_item_snapshots(tenant_id, item_rows)
        resp.items = [self._forecast_item_to_response(it) for it in item_rows]
        resp.total_quantity = sum(
            (Decimal(str(it.forecast_quantity or 0)) for it in item_rows),
            Decimal("0"),
        )
        from apps.kuaizhizao.services.document_lifecycle_service import get_sales_forecast_lifecycle, get_document_milestones
        milestones = await get_document_milestones(forecast.tenant_id, "sales_forecast", forecast.id)
        demand = await self._get_linked_demand_for_forecast(tenant_id, forecast_id)
        pushed = bool(demand and getattr(demand, "pushed_to_computation", False))
        resp.lifecycle = get_sales_forecast_lifecycle(
            forecast,
            milestones=milestones,
            pushed_to_computation=pushed,
            delivery_progress=0.0,
            invoice_progress=0.0,
            items=None,
        )
        from core.services.approval.audit_record_enricher import enrich_record

        pushed = self._is_forecast_pushed_to_computation(forecast, demand)
        has_downstream = await self._forecast_has_downstream(tenant_id, forecast_id)
        has_items = bool(item_rows)
        resp = enrich_sales_forecast_capabilities_on_response(
            forecast,
            resp,
            pushed_to_computation=pushed,
            has_downstream=has_downstream,
            has_items=has_items,
        )
        return await enrich_record(tenant_id, "sales_forecast", resp)

    async def list_sales_forecasts(self, tenant_id: int, skip: int = 0, limit: int = 20, **filters) -> Dict[str, Any]:
        """获取销售预测列表"""
        query = SalesForecast.filter(tenant_id=tenant_id, deleted_at__isnull=True)

        # 应用过滤条件
        if filters.get('status'):
            query = query.filter(status=filters['status'])
        if filters.get('forecast_period'):
            query = query.filter(forecast_period=filters['forecast_period'])
        if filters.get('start_date'):
            query = query.filter(start_date__gte=filters['start_date'])
        if filters.get('end_date'):
            query = query.filter(end_date__lte=filters['end_date'])
        if filters.get('keyword'):
            kw = str(filters['keyword']).strip()
            if kw:
                query = query.filter(
                    Q(forecast_code__icontains=kw) | Q(forecast_name__icontains=kw)
                )
        if filters.get('forecast_code'):
            code = str(filters['forecast_code']).strip()
            if code:
                query = query.filter(forecast_code__icontains=code)
        if filters.get('forecast_name'):
            name = str(filters['forecast_name']).strip()
            if name:
                query = query.filter(forecast_name__icontains=name)

        pullable_only = filters.get("pullable_only")
        pull_target_norm = str(filters.get("pull_target") or "").strip().lower()
        if pullable_only and pull_target_norm == "demand_computation":
            from apps.kuaizhizao.constants import LEGACY_AUDITED_VALUES, ReviewStatus

            audited_statuses = (
                "AUDITED",
                "CONFIRMED",
                "已审核",
                "已确认",
                *tuple(LEGACY_AUDITED_VALUES),
            )
            approved_review = (
                ReviewStatus.APPROVED.value,
                "APPROVED",
                "已通过",
                "审核通过",
                "通过",
                "已审核",
            )
            query = query.filter(
                Q(status__in=audited_statuses) | Q(review_status__in=approved_review)
            ).filter(planning_pushed_to_computation=False)

        # 获取总数
        total = await query.count()

        order_by = filters.get('order_by')
        order_clause = order_by if order_by else '-created_at'

        # 获取分页数据
        forecasts = await query.offset(skip).limit(limit).order_by(order_clause, '-id')

        forecast_ids = [f.id for f in forecasts]
        demand_by_fid: Dict[int, Demand] = {}
        if forecast_ids:
            demands = await Demand.filter(
                tenant_id=tenant_id,
                source_type="sales_forecast",
                source_id__in=forecast_ids,
                deleted_at__isnull=True,
            ).all()
            demand_by_fid = {d.source_id: d for d in demands}

        include_items = filters.get('include_items', False)
        items_by_forecast: Dict[int, List[SalesForecastItem]] = {}
        if include_items:
            # 批量获取明细
            forecast_ids = [f.id for f in forecasts]
            if forecast_ids:
                all_items = await SalesForecastItem.filter(tenant_id=tenant_id, forecast_id__in=forecast_ids).order_by('forecast_date').all()
                await self._hydrate_forecast_item_snapshots(tenant_id, all_items)
                for item in all_items:
                    items_by_forecast.setdefault(item.forecast_id, []).append(item)

        from apps.kuaizhizao.services.document_lifecycle_service import get_sales_forecast_lifecycle
        downstream_ids = await self._forecast_downstream_ids(tenant_id, forecast_ids)
        has_items_by_id = await self._forecast_has_items_map(tenant_id, forecast_ids)
        qty_by_id = await self._forecast_total_quantity_map(tenant_id, forecast_ids)
        items_count_by_id = await self._forecast_items_count_map(tenant_id, forecast_ids)
        pushed_by_id: Dict[int, bool] = {}
        for fid, f in zip(forecast_ids, forecasts):
            d = demand_by_fid.get(fid)
            pushed_by_id[fid] = self._is_forecast_pushed_to_computation(f, d)

        list_responses: List[SalesForecastListResponse] = []
        for forecast in forecasts:
            resp = SalesForecastListResponse.model_validate(forecast)
            fid = forecast.id
            d = demand_by_fid.get(fid)
            resp.lifecycle = get_sales_forecast_lifecycle(
                forecast,
                pushed_to_computation=pushed_by_id.get(fid, False),
            )
            resp.total_quantity = qty_by_id.get(fid, Decimal("0"))
            resp.items_count = items_count_by_id.get(fid, 0)
            if include_items:
                f_items = items_by_forecast.get(fid, [])
                resp.items = [self._forecast_item_to_response(it) for it in f_items]
            list_responses.append(resp)

        enriched = enrich_sales_forecast_list_capabilities(
            forecasts,
            list_responses,
            pushed_by_id=pushed_by_id,
            downstream_by_id={fid: fid in downstream_ids for fid in forecast_ids},
            has_items_by_id=has_items_by_id,
        )
        result = [r.model_dump() for r in enriched]
        from core.services.approval.audit_record_enricher import enrich_data_payload

        return await enrich_data_payload(tenant_id, "sales_forecast", {
            "data": result, "total": total, "success": True
        })
        
    async def get_forecast_statistics(self, tenant_id: int) -> Dict[str, Any]:
        """获取销售预测统计（列表页指标卡，字段与销售订单 statistics 对齐）"""
        today = to_site_date(resolve_business_datetime())
        base = SalesForecast.filter(tenant_id=tenant_id, deleted_at__isnull=True)

        cancelled = ["CANCELLED", "已取消", "cancelled"]
        rejected_review = ["REJECTED", "已驳回", "审核驳回", "驳回", "rejected"]
        pending_review_vals = ["PENDING", "PENDING_REVIEW", "待审核", "pending_review"]
        in_progress_status = [
            "IN_PROGRESS", "进行中", "APPROVED", "已审核", "CONFIRMED", "已确认",
            "AUDITED", "RELEASED", "执行中", "EFFECTIVE", "已生效",
        ]
        completed = ["COMPLETED", "已完成", "completed", "CLOSED", "已关闭"]

        try:
            pending_review_count = await base.filter(
                review_status__in=pending_review_vals,
            ).exclude(status__in=cancelled).count()
        except Exception as e:
            logger.warning(f"sales-forecast-statistics pending_review_count: {e}")
            raise

        try:
            today_start, today_end = site_day_bounds_utc(today)
            today_new_count = await base.filter(
                created_at__gte=today_start,
                created_at__lt=today_end,
            ).count()
        except Exception as e:
            logger.warning(f"sales-forecast-statistics today_new_count: {e}")
            raise

        try:
            in_progress_count = await base.filter(
                status__in=in_progress_status,
            ).exclude(review_status__in=rejected_review).exclude(status__in=cancelled + completed).count()
        except Exception as e:
            logger.warning(f"sales-forecast-statistics in_progress_count: {e}")
            raise

        try:
            overdue_count = await base.filter(
                end_date__lt=today,
            ).exclude(status__in=cancelled + completed).count()
        except Exception as e:
            logger.warning(f"sales-forecast-statistics overdue_count: {e}")
            raise

        total_amount = 0.0
        trend_today_new: List[Dict[str, Any]] = []
        trend_today_amount: List[Dict[str, Any]] = []
        trend_pending_review: List[Dict[str, Any]] = []

        try:
            for i in range(6, -1, -1):
                day = today - timedelta(days=i)
                date_str = day.strftime("%Y-%m-%d")
                day_start, day_end = site_day_bounds_utc(day)
                cnt = await base.filter(created_at__gte=day_start, created_at__lt=day_end).count()
                trend_today_new.append({"date": date_str, "value": cnt})
                trend_today_amount.append({"date": date_str, "value": 0})
                pr_cnt = await base.filter(
                    review_status__in=pending_review_vals,
                    created_at__lt=day_end,
                ).exclude(status__in=cancelled).count()
                trend_pending_review.append({"date": date_str, "value": pr_cnt})
        except Exception as e:
            logger.warning(f"sales-forecast-statistics trends: {e}")
            raise

        yesterday_today_new = trend_today_new[-2]["value"] if len(trend_today_new) > 1 else 0
        yesterday_pending_review = (
            trend_pending_review[-2]["value"] if len(trend_pending_review) > 1 else 0
        )

        return {
            "today_new_count": today_new_count,
            "pending_review_count": pending_review_count,
            "in_progress_count": in_progress_count,
            "overdue_count": overdue_count,
            "total_amount": round(total_amount, 2),
            "yesterday_today_new": yesterday_today_new,
            "yesterday_pending_review": yesterday_pending_review,
            "trend_today_new": trend_today_new,
            "trend_today_amount": trend_today_amount,
            "trend_pending_review": trend_pending_review,
        }

    async def update_sales_forecast(
        self,
        tenant_id: int,
        forecast_id: int,
        forecast_data: SalesForecastUpdate,
        updated_by: int,
        approval_edit_context: Optional[Dict[str, Any]] = None,
        approval_edit_comment: Optional[str] = None,
    ) -> SalesForecastResponse:
        """更新销售预测；若提供 items 则先删后增，覆盖全部明细。已审核预测更新后同步关联需求。"""
        from apps.kuaizhizao.constants import DocumentStatus, is_draft_status, normalize_status

        forecast_row = await SalesForecast.get_or_none(
            tenant_id=tenant_id, id=forecast_id, deleted_at__isnull=True
        )
        if not forecast_row:
            raise NotFoundError(f"销售预测不存在: {forecast_id}")
        assert_sales_forecast_capability(forecast_row, "update")
        is_pending = normalize_status(forecast_row.status or "") == DocumentStatus.PENDING_REVIEW.value
        if is_pending and not approval_edit_context:
            from core.services.approval.approval_edit_guard import ApprovalEditGuard

            edit_ctx = await ApprovalEditGuard.get_pending_edit_context(
                tenant_id, "sales_forecast", forecast_id, updated_by
            )
            if not edit_ctx:
                raise BusinessLogicError("单据审核中，仅已开启改单权限的当前审批人可修改")
            approval_edit_context = edit_ctx

        if approval_edit_context:
            from core.config.audit_editable_fields import is_field_editable
            from infra.exceptions.exceptions import ValidationError

            node_editable = approval_edit_context.get("editable_fields")
            preview = forecast_data.model_dump(exclude_unset=True, exclude={"items"})
            for field in preview:
                if field in ("updated_by", "status", "review_status"):
                    continue
                if not is_field_editable("sales_forecast", field, node_editable):
                    raise ValidationError(f"字段「{field}」不允许在审核中修改")
            if forecast_data.items is not None and not is_field_editable(
                "sales_forecast", "items", node_editable
            ):
                raise ValidationError("字段「预测明细」不允许在审核中修改")

        forecast_before = await self.get_sales_forecast_by_id(tenant_id, forecast_id)
        async with in_transaction():
            dumped = forecast_data.model_dump(exclude_unset=True, exclude={'updated_by'})
            items_data = dumped.pop('items', None)
            update_data = {k: v for k, v in dumped.items() if k != 'items'}
            user_info = await self.get_user_info(updated_by)
            update_data['updated_by'] = updated_by
            update_data['updated_by_name'] = user_info["name"]

            await SalesForecast.filter(tenant_id=tenant_id, id=forecast_id).update(**update_data)

            if items_data is not None:
                await SalesForecastItem.filter(tenant_id=tenant_id, forecast_id=forecast_id).delete()
                recreated_items: List[SalesForecastItem] = []
                for item_data in items_data:
                    recreated_items.append(
                        await SalesForecastItem.create(
                            tenant_id=tenant_id,
                            forecast_id=forecast_id,
                            **item_data,
                        )
                    )
                await self._hydrate_forecast_item_snapshots(tenant_id, recreated_items)

            updated_forecast = await self.get_sales_forecast_by_id(tenant_id, forecast_id)
        # 只要有关联需求，预测任意保存都同步需求内容，使需求管理动态随上游变化
        demand_synced = await self._sync_demand_if_exists(tenant_id, forecast_id, updated_by)
        try:
            from apps.kuaizhizao.services.demand_change_event_service import DemandChangeEventService
            await DemandChangeEventService().create_event(
                tenant_id=tenant_id,
                event_type="order",
                source_type="sales_forecast",
                source_id=forecast_id,
                source_code=updated_forecast.forecast_code,
                source_name=updated_forecast.forecast_name or updated_forecast.forecast_code,
                changed_fields=["sales_forecast_updated"],
                payload={"forecast_id": forecast_id},
                effective_at=resolve_business_datetime(),
                trigger_reason="sales_forecast_updated",
                requested_by=updated_by,
                correlation_id=f"sales_forecast:{forecast_id}:{int(resolve_business_datetime().timestamp())}",
                auto_create_task=True,
            )
        except Exception:
            pass
        out = updated_forecast.model_dump()
        out["demand_synced"] = demand_synced
        return SalesForecastResponse(**out)

    async def _get_linked_demand_for_forecast(
        self, tenant_id: int, forecast_id: int
    ) -> Optional[Demand]:
        """获取与销售预测关联的 Demand"""
        return await Demand.get_or_none(
            tenant_id=tenant_id,
            source_type="sales_forecast",
            source_id=forecast_id,
            deleted_at__isnull=True,
        )

    async def _sync_demand_if_exists(self, tenant_id: int, forecast_id: int, operator_id: int) -> bool:
        """销售预测保存后，将关联 Demand/DemandItem 与预测明细对齐（策略 A）。"""
        demand = await self._get_demand_for_forecast(tenant_id, forecast_id)
        if not demand:
            return False
        try:
            from apps.kuaizhizao.services.demand_service import DemandService

            result = await DemandService().sync_from_upstream(
                tenant_id=tenant_id,
                source_type="sales_forecast",
                source_id=forecast_id,
                operator_id=operator_id,
            )
            return bool(result.get("synced"))
        except Exception as e:
            logger.warning("销售预测关联需求同步失败 forecast_id={}: {}", forecast_id, e)
            return False

    async def _create_demand_from_sales_forecast(
        self, tenant_id: int, forecast_id: int, created_by: int
    ) -> Demand:
        """从 SalesForecast 生成 Demand（source_type=sales_forecast, source_id=预测ID）"""
        from apps.kuaizhizao.constants import DemandStatus, ReviewStatus

        forecast = await SalesForecast.get(id=forecast_id)
        items = await SalesForecastItem.filter(
            tenant_id=tenant_id, forecast_id=forecast_id
        ).order_by("id")
        if not items:
            raise BusinessLogicError("销售预测无明细，无法自动产生需求")

        from decimal import Decimal
        from apps.kuaizhizao.utils.forecast_consumption import forecast_open_quantity

        open_qtys = [
            forecast_open_quantity(it.forecast_quantity, getattr(it, "consumed_quantity", 0))
            for it in items
        ]
        total_qty = sum(open_qtys)
        demand_items = []
        for it, open_qty in zip(items, open_qtys):
            if open_qty <= 0:
                continue
            demand_items.append({
                "material_id": it.material_id,
                "material_code": it.material_code,
                "material_name": it.material_name,
                "material_spec": it.material_spec,
                "material_unit": it.material_unit,
                "required_quantity": open_qty,
                "forecast_date": it.forecast_date,
                "remaining_quantity": open_qty,
                "delivery_status": "待交货",
            })
        if not demand_items:
            raise BusinessLogicError("销售预测明细均已被订单冲销，无法自动产生需求")

        demand = await Demand.create(
            tenant_id=tenant_id,
            demand_code=forecast.forecast_code,
            demand_type="sales_forecast",
            business_mode="MTS",
            demand_name=forecast.forecast_name or forecast.forecast_code,
            start_date=forecast.start_date,
            end_date=forecast.end_date,
            forecast_period=forecast.forecast_period,
            total_quantity=Decimal(str(total_qty)),
            total_amount=Decimal("0"),
            status=DemandStatus.AUDITED,
            review_status=ReviewStatus.APPROVED,
            reviewer_id=forecast.reviewer_id,
            reviewer_name=forecast.reviewer_name,
            review_time=forecast.review_time,
            priority=5,
            source_type="sales_forecast",
            source_id=forecast_id,
            source_code=forecast.forecast_code,
            created_by=created_by,
            updated_by=created_by,
        )
        for d in demand_items:
            await DemandItem.create(
                tenant_id=tenant_id,
                demand_id=demand.id,
                delivered_quantity=Decimal("0"),
                **d,
            )
        logger.info("从销售预测 %s 自动产生需求 %s", forecast.forecast_code, demand.demand_code)

        # 建立销售预测→Demand 的 DocumentRelation（支持单据追溯）
        try:
            from apps.kuaizhizao.services.document_relation_new_service import DocumentRelationNewService
            from apps.kuaizhizao.schemas.document_relation import DocumentRelationCreate

            rel_svc = DocumentRelationNewService()
            await rel_svc.create_relation(
                tenant_id=tenant_id,
                relation_data=DocumentRelationCreate(
                    source_type="sales_forecast",
                    source_id=forecast_id,
                    source_code=forecast.forecast_code,
                    source_name=forecast.forecast_name or forecast.forecast_code,
                    target_type="demand",
                    target_id=demand.id,
                    target_code=demand.demand_code,
                    target_name=demand.demand_name or demand.demand_code,
                    relation_type="source",
                    relation_mode="push",
                    relation_desc="销售预测审核通过自动生成需求",
                ),
                created_by=created_by,
            )
        except Exception as e:
            logger.warning("创建销售预测→Demand 单据关联失败: %s", e)

        return demand

    async def approve_forecast(
        self,
        tenant_id: int,
        forecast_id: int,
        approved_by: int,
        rejection_reason: Optional[str] = None,
        *,
        is_auto_approve: bool = False,
    ) -> SalesForecastResponse:
        """审核销售预测"""
        from apps.kuaizhizao.constants import DocumentStatus, ReviewStatus

        forecast_row = await SalesForecast.get_or_none(
            tenant_id=tenant_id, id=forecast_id, deleted_at__isnull=True
        )
        if not forecast_row:
            raise NotFoundError(f"销售预测不存在: {forecast_id}")
        if rejection_reason:
            assert_sales_forecast_capability(forecast_row, "reject")
        else:
            assert_sales_forecast_capability(forecast_row, "approve")

        from infra.services.business_config_service import BusinessConfigService
        from core.services.approval.audit_flow_guard import assert_pending_approval_instance

        audit_required = await BusinessConfigService().check_audit_required(
            tenant_id, "sales_forecast"
        )
        if not is_auto_approve:
            await assert_pending_approval_instance(
                tenant_id=tenant_id,
                entity_type="sales_forecast",
                entity_id=forecast_id,
                audit_required=audit_required,
                doc_label="销售预测",
                verb="驳回" if rejection_reason else "审核",
            )

        async with in_transaction():
            approver_name = await self.get_user_name(approved_by)

            review_status = ReviewStatus.REJECTED.value if rejection_reason else ReviewStatus.APPROVED.value
            status = DocumentStatus.REJECTED.value if rejection_reason else DocumentStatus.AUDITED.value

            await SalesForecast.filter(tenant_id=tenant_id, id=forecast_id).update(
                reviewer_id=approved_by,
                reviewer_name=approver_name,
                review_time=resolve_business_datetime(),
                review_status=review_status,
                review_remarks=rejection_reason,
                status=status,
                **(await self._audit_update_fields(approved_by)),
            )

        demand_synced = False
        updated_forecast = await self.get_sales_forecast_by_id(tenant_id, forecast_id)
        out = updated_forecast.model_dump()
        out["demand_synced"] = demand_synced
        # 自动下推移出事务：失败不回滚已审核态，调用方可见 auto_computation
        if not rejection_reason:
            auto_push_result = await self._try_auto_push_forecast_to_computation(
                tenant_id=tenant_id,
                forecast_id=forecast_id,
                operator_id=approved_by,
            )
            if auto_push_result:
                out["auto_computation"] = auto_push_result
        return SalesForecastResponse(**out)

    async def withdraw_forecast_approval(
        self,
        tenant_id: int,
        forecast_id: int,
        withdrawn_by: int,
    ) -> SalesForecastResponse:
        """撤销审核：一律回到草稿，须重新提交再审。"""
        from apps.kuaizhizao.constants import DocumentStatus, ReviewStatus
        from core.services.approval.audit_transition import (
            resolve_revoke_to_draft_landing_phase,
        )

        forecast_row = await SalesForecast.get_or_none(
            tenant_id=tenant_id, id=forecast_id, deleted_at__isnull=True
        )
        if not forecast_row:
            raise NotFoundError(f"销售预测不存在: {forecast_id}")
        from infra.services.business_config_service import BusinessConfigService

        audit_required = await BusinessConfigService().check_audit_required(
            tenant_id, "sales_forecast"
        )
        _ = resolve_revoke_to_draft_landing_phase(manual_audit_enabled=audit_required)

        # 清理与状态重置同事务，避免 DRAFT 但需求已删的中间态
        async with in_transaction():
            await self._cleanup_unpushed_forecast_demand(tenant_id, forecast_id)
            has_downstream = await self._forecast_has_downstream(tenant_id, forecast_id)
            assert_sales_forecast_capability(
                forecast_row,
                "revoke_approval",
                has_downstream=has_downstream,
            )
            await SalesForecast.filter(tenant_id=tenant_id, id=forecast_id).update(
                status=DocumentStatus.DRAFT.value,
                review_status=ReviewStatus.PENDING.value,
                reviewer_id=None,
                reviewer_name=None,
                review_time=None,
                **(await self._audit_update_fields(withdrawn_by)),
            )
            return await self.get_sales_forecast_by_id(tenant_id, forecast_id)

    async def _try_auto_push_forecast_to_computation(
        self,
        tenant_id: int,
        forecast_id: int,
        operator_id: int,
    ) -> Optional[Dict[str, Any]]:
        """按组织配置在审核通过后自动下推销售预测到需求计算。"""
        from infra.services.business_config_service import BusinessConfigService

        enabled = await BusinessConfigService().auto_push_sales_to_computation_on_approve(tenant_id)
        if not enabled:
            return None
        try:
            return await self.push_to_computation(
                tenant_id=tenant_id,
                forecast_id=forecast_id,
                user_id=operator_id,
            )
        except Exception as exc:
            logger.warning("销售预测自动下推需求计算失败，forecast_id=%s: %s", forecast_id, exc)
            return {"success": False, "message": str(exc)}

    async def add_forecast_item(self, tenant_id: int, forecast_id: int, item_data: SalesForecastItemCreate) -> SalesForecastItemResponse:
        """添加销售预测明细"""
        async with in_transaction():
            # 验证预测存在
            await self.get_sales_forecast_by_id(tenant_id, forecast_id)

            item = await SalesForecastItem.create(
                tenant_id=tenant_id,
                forecast_id=forecast_id,
                **item_data.model_dump(exclude_unset=True)
            )
            await self._hydrate_forecast_item_snapshots(tenant_id, [item])
            return self._forecast_item_to_response(item)

    async def get_forecast_items(self, tenant_id: int, forecast_id: int) -> List[SalesForecastItemResponse]:
        """获取销售预测明细"""
        items = await SalesForecastItem.filter(tenant_id=tenant_id, forecast_id=forecast_id).order_by('forecast_date')
        item_list = list(items)
        await self._hydrate_forecast_item_snapshots(tenant_id, item_list)
        return [self._forecast_item_to_response(item) for item in item_list]

    async def submit_forecast(self, tenant_id: int, forecast_id: int, submitted_by: int) -> SalesForecastResponse:
        """
        提交销售预测
        
        将草稿状态的销售预测提交为待审核状态
        
        Args:
            tenant_id: 租户ID
            forecast_id: 销售预测ID
            submitted_by: 提交人ID
            
        Returns:
            SalesForecastResponse: 更新后的销售预测
            
        Raises:
            NotFoundError: 销售预测不存在
            BusinessLogicError: 销售预测状态不是草稿
        """
        from apps.kuaizhizao.constants import DocumentStatus, ReviewStatus

        forecast_row = await SalesForecast.get_or_none(
            tenant_id=tenant_id, id=forecast_id, deleted_at__isnull=True
        )
        if not forecast_row:
            raise NotFoundError(f"销售预测不存在: {forecast_id}")
        assert_sales_forecast_capability(forecast_row, "submit")

        approval_instance = None
        async with in_transaction():
            # 检查业务配置：若无需审核，则提交后直接设为已审核（考虑中小企业实情）
            from infra.services.business_config_service import BusinessConfigService
            config_service = BusinessConfigService()
            audit_required = await config_service.check_audit_required(tenant_id, "sales_forecast")

            if not audit_required:
                await SalesForecast.filter(tenant_id=tenant_id, id=forecast_id).update(
                    status=DocumentStatus.CONFIRMED.value,
                    review_status=ReviewStatus.APPROVED.value,
                    **(await self._audit_update_fields(submitted_by)),
                )
                # 无需审核时不再自动创建 Demand，保持链路为「销售预测→需求计算（显式下推）」。
                await self._try_auto_push_forecast_to_computation(
                    tenant_id=tenant_id,
                    forecast_id=forecast_id,
                    operator_id=submitted_by,
                )
            else:
                from core.services.approval.audit_flow_guard import start_document_approval_or_raise

                approval_instance = await start_document_approval_or_raise(
                    tenant_id=tenant_id,
                    user_id=submitted_by,
                    node_key="sales_forecast",
                    entity_type="sales_forecast",
                    entity_id=int(forecast_row.id),
                    entity_uuid=str(forecast_row.uuid),
                    title=f"销售预测审批: {forecast_row.forecast_code}",
                    content=f"预测名称: {forecast_row.forecast_name or forecast_row.forecast_code}",
                    doc_label="销售预测",
                )
                await SalesForecast.filter(tenant_id=tenant_id, id=forecast_id).update(
                    status=DocumentStatus.PENDING_REVIEW.value,
                    review_status=ReviewStatus.PENDING.value,
                    **(await self._audit_update_fields(submitted_by)),
                )

        if approval_instance:
            from core.services.approval.audit_flow_guard import approval_instance_finished_on_submit

            if approval_instance_finished_on_submit(approval_instance):
                return await self.approve_forecast(
                    tenant_id,
                    forecast_id,
                    submitted_by,
                    is_auto_approve=True,
                )
        return await self.get_sales_forecast_by_id(tenant_id, forecast_id)

    async def withdraw_forecast(
        self,
        tenant_id: int,
        forecast_id: int,
        withdrawn_by: int,
    ) -> SalesForecastResponse:
        """撤回提交：待审核 → 草稿（提交人撤回，非反审核）"""
        from apps.kuaizhizao.constants import DocumentStatus, ReviewStatus

        forecast_row = await SalesForecast.get_or_none(
            tenant_id=tenant_id, id=forecast_id, deleted_at__isnull=True
        )
        if not forecast_row:
            raise NotFoundError(f"销售预测不存在: {forecast_id}")
        assert_sales_forecast_capability(forecast_row, "withdraw_submit")

        try:
            from core.services.approval.approval_instance_service import ApprovalInstanceService

            await ApprovalInstanceService.cancel_approval(
                tenant_id=tenant_id,
                entity_type="sales_forecast",
                entity_id=forecast_id,
                operator_id=withdrawn_by,
            )
        except Exception as e:
            logger.warning("取消销售预测审批流程失败或无需取消: {}", e)

        await SalesForecast.filter(tenant_id=tenant_id, id=forecast_id).update(
            status=DocumentStatus.DRAFT.value,
            review_status=ReviewStatus.PENDING.value,
            reviewer_id=None,
            reviewer_name=None,
            review_time=None,
            review_remarks=None,
            **(await self._audit_update_fields(withdrawn_by)),
        )
        return await self.get_sales_forecast_by_id(tenant_id, forecast_id)

    async def import_from_data(
        self,
        tenant_id: int,
        data: List[List[Any]],
        created_by: int
    ) -> Dict[str, Any]:
        """
        从二维数组数据批量导入销售预测
        
        接收前端 uni_import 组件传递的二维数组数据，批量创建销售预测。
        数据格式：第一行为表头，第二行为示例数据（跳过），从第三行开始为实际数据。
        
        Args:
            tenant_id: 租户ID
            data: 二维数组数据（从 uni_import 组件传递）
            created_by: 创建人ID
            
        Returns:
            Dict: 导入结果（成功数、失败数、错误列表）
        """
        if not data or len(data) < 2:
            raise ValidationError("导入数据格式错误：至少需要表头和示例数据行")
        
        # 解析表头（第一行，索引0）
        headers = [str(cell).strip() if cell is not None else '' for cell in data[0]]
        
        # 表头字段映射（支持中英文）
        header_map = {
            '预测名称': 'forecast_name',
            '*预测名称': 'forecast_name',
            'forecast_name': 'forecast_name',
            '*forecast_name': 'forecast_name',
            '预测类型': 'forecast_type',
            'forecast_type': 'forecast_type',
            '预测周期': 'forecast_period',
            '*预测周期': 'forecast_period',
            'forecast_period': 'forecast_period',
            '*forecast_period': 'forecast_period',
            '开始日期': 'start_date',
            '*开始日期': 'start_date',
            'start_date': 'start_date',
            '*start_date': 'start_date',
            '结束日期': 'end_date',
            '*结束日期': 'end_date',
            'end_date': 'end_date',
            '*end_date': 'end_date',
            '备注': 'notes',
            'notes': 'notes',
        }
        
        # 找到表头索引
        header_index_map = {}
        for idx, header in enumerate(headers):
            if header and header in header_map:
                header_index_map[header_map[header]] = idx
        
        # 验证必填字段
        required_fields = ['forecast_name', 'forecast_period', 'start_date', 'end_date']
        missing_fields = [f for f in required_fields if f not in header_index_map]
        if missing_fields:
            raise ValidationError(f"缺少必填字段：{', '.join(missing_fields)}")
        
        # 解析数据行（从第三行开始，索引2，跳过表头和示例数据行）
        rows = data[2:] if len(data) > 2 else []
        
        # 过滤空行
        non_empty_rows = [
            (row, idx + 3) for idx, row in enumerate(rows)
            if any(cell is not None and str(cell).strip() for cell in row)
        ]
        
        if not non_empty_rows:
            raise ValidationError("没有可导入的数据行（所有行都为空）")
        
        success_count = 0
        failure_count = 0
        errors = []
        
        for row, row_idx in non_empty_rows:
            try:
                # 解析行数据
                forecast_data = {}
                for field, col_idx in header_index_map.items():
                    if col_idx < len(row):
                        value = row[col_idx]
                        if value is not None:
                            value_str = str(value).strip()
                            if value_str:
                                # 日期字段需要转换
                                if field in ['start_date', 'end_date']:
                                    try:
                                        from datetime import datetime as dt
                                        # 尝试多种日期格式
                                        for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d']:
                                            try:
                                                forecast_data[field] = dt.strptime(value_str, fmt).date()
                                                break
                                            except ValueError:
                                                continue
                                        else:
                                            raise ValueError(f"日期格式错误：{value_str}")
                                    except Exception as e:
                                        errors.append({
                                            "row": row_idx,
                                            "error": f"日期格式错误：{value_str}，错误：{str(e)}"
                                        })
                                        failure_count += 1
                                        break
                                else:
                                    forecast_data[field] = value_str
                
                # 验证必填字段
                if not forecast_data.get('forecast_name') or not forecast_data.get('forecast_period'):
                    errors.append({
                        "row": row_idx,
                        "error": "预测名称或预测周期为空"
                    })
                    failure_count += 1
                    continue
                
                if 'start_date' not in forecast_data or 'end_date' not in forecast_data:
                    errors.append({
                        "row": row_idx,
                        "error": "开始日期或结束日期为空或格式错误"
                    })
                    failure_count += 1
                    continue
                
                # 设置默认值
                forecast_data.setdefault('forecast_type', 'MTS')
                from apps.kuaizhizao.constants import DocumentStatus, ReviewStatus
                forecast_data.setdefault('status', DocumentStatus.DRAFT.value)
                forecast_data.setdefault('review_status', ReviewStatus.PENDING.value)
                
                # 创建销售预测
                forecast_create = SalesForecastCreate(**forecast_data)
                await self.create_sales_forecast(tenant_id, forecast_create, created_by)
                success_count += 1
                
            except Exception as e:
                logger.error(f"导入销售预测失败（第{row_idx}行）: {str(e)}")
                errors.append({
                    "row": row_idx,
                    "error": str(e)
                })
                failure_count += 1
        
        return {
            "success": True,
            "message": "导入完成",
            "total": success_count + failure_count,
            "success_count": success_count,
            "failure_count": failure_count,
            "errors": errors,
        }

    async def export_to_excel(
        self,
        tenant_id: int,
        **filters
    ) -> str:
        """
        导出销售预测到Excel文件
        
        Args:
            tenant_id: 租户ID
            **filters: 过滤条件
            
        Returns:
            str: Excel文件路径
        """
        import csv
        import os
        import tempfile
        from datetime import datetime
        
        # 查询所有符合条件的销售预测（不分页）
        forecasts = await self.list_sales_forecasts(tenant_id, skip=0, limit=10000, **filters)
        
        # 创建导出目录
        export_dir = os.path.join(tempfile.gettempdir(), 'riveredge_exports')
        os.makedirs(export_dir, exist_ok=True)
        
        # 生成文件名
        timestamp = resolve_business_datetime().strftime('%Y%m%d_%H%M%S')
        filename = f"sales_forecasts_{timestamp}.csv"
        file_path = os.path.join(export_dir, filename)
        
        # 写入CSV文件
        with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            
            # 写入表头
            writer.writerow([
                '预测编号', '预测名称', '预测类型', '预测周期', 
                '开始日期', '结束日期', '状态', '审核状态', 
                '审核人', '审核时间', '备注', '创建时间'
            ])
            
            # 写入数据
            for forecast in forecasts:
                writer.writerow([
                    forecast.forecast_code,
                    forecast.forecast_name,
                    forecast.forecast_type,
                    forecast.forecast_period,
                    forecast.start_date.strftime('%Y-%m-%d') if forecast.start_date else '',
                    forecast.end_date.strftime('%Y-%m-%d') if forecast.end_date else '',
                    forecast.status,
                    forecast.review_status,
                    forecast.reviewer_name or '',
                    to_api_isoformat(forecast.review_time) if forecast.review_time else '',
                    forecast.notes or '',
                    to_api_isoformat(forecast.created_at) if forecast.created_at else '',
                ])
        
        return file_path

    async def preview_push_to_computation(
        self,
        tenant_id: int,
        forecast_id: int,
    ) -> Dict[str, Any]:
        """下推需求计算预览：返回预测明细数量、已下推、可下推，不实际创建。"""
        from apps.kuaizhizao.services.demand_service import DemandService
        from apps.kuaizhizao.services.document_action_policy.sales_forecast import (
            derive_sales_forecast_capabilities,
        )
        from apps.master_data.services.material_service import MaterialService

        forecast_row = await SalesForecast.get_or_none(
            tenant_id=tenant_id, id=forecast_id, deleted_at__isnull=True
        )
        if not forecast_row:
            raise NotFoundError(f"销售预测不存在: {forecast_id}")

        demand = await self._get_linked_demand_for_forecast(tenant_id, forecast_id)
        pushed = self._is_forecast_pushed_to_computation(forecast_row, demand)
        item_count = await SalesForecastItem.filter(
            tenant_id=tenant_id, forecast_id=forecast_id
        ).count()
        caps = derive_sales_forecast_capabilities(
            forecast_row,
            pushed_to_computation=pushed,
            has_items=item_count > 0,
        )
        push_allowed = caps.push_computation.allowed
        blocking_reason = caps.push_computation.reason if not push_allowed else None

        if demand and push_allowed and not pushed:
            preview = await DemandService().preview_push_demand_to_computation(
                tenant_id, demand.id
            )
            preview["forecast_code"] = forecast_row.forecast_code
            preview["demand_exists"] = True
            return preview

        items = await SalesForecastItem.filter(
            tenant_id=tenant_id, forecast_id=forecast_id
        ).order_by("id")
        if not items:
            raise BusinessLogicError("销售预测无明细，无法下推需求计算")

        material_ids = [
            int(it.material_id)
            for it in items
            if getattr(it, "material_id", None) and int(it.material_id) > 0
        ]
        bom_map = await MaterialService.batch_check_has_bom(
            tenant_id=tenant_id,
            material_ids=material_ids,
            only_active=True,
        )

        preview_items = []
        for it in items:
            qty = float(it.forecast_quantity or 0)
            if qty <= 0:
                continue
            material_id = int(it.material_id) if getattr(it, "material_id", None) else None
            preview_items.append({
                "item_id": int(it.id),
                "material_id": material_id,
                "material_code": str(it.material_code or "").strip(),
                "material_name": str(it.material_name or "").strip(),
                "quantity": float(qty),
                "pushed_quantity": float(qty) if pushed else 0.0,
                "max_push_quantity": 0.0 if pushed or not push_allowed else float(qty),
                "forecast_date": str(it.forecast_date) if it.forecast_date else None,
                "forecast_month": str(it.forecast_month) if getattr(it, "forecast_month", None) else None,
                "has_bom": bom_map.get(material_id, False) if material_id else False,
            })

        if not preview_items:
            push_allowed = False
            blocking_reason = blocking_reason or "sales_forecast.push_computation.no_items"

        pushable_count = sum(
            1 for row in preview_items if float(row.get("max_push_quantity") or 0) > 0
        )
        return {
            "target_type": "demand_computation",
            "summary": (
                f"请确认将下推的预测明细（{pushable_count}/{len(preview_items)} 行可下推）"
                if push_allowed
                else "当前销售预测不可下推需求计算"
            ),
            "forecast_code": forecast_row.forecast_code,
            "demand_exists": demand is not None,
            "items": preview_items,
            "has_blocking_issues": not push_allowed,
            "blocking_reason": blocking_reason if not push_allowed else None,
            "tip": "确认后将创建需求并下推需求计算任务；整单下推后不可重复操作。",
        }

    async def push_to_computation(
        self,
        tenant_id: int,
        forecast_id: int,
        planning_horizon: int = 12,
        time_bucket: str = "week",
        user_id: int = None
    ) -> Dict[str, Any]:
        """
        下推到需求计算（统一使用 demand_computation，替代原 MRP 运算）
        
        从销售预测获取或创建 Demand，然后下推到 DemandComputation。
        
        Args:
            tenant_id: 租户ID
            forecast_id: 销售预测ID
            planning_horizon: 计划周期（月数，默认12个月，保留参数兼容）
            time_bucket: 时间粒度（week/month，保留参数兼容）
            user_id: 用户ID（可选）
            
        Returns:
            Dict: 需求计算结果，含 computation_id、computation_code 等
        """
        from apps.kuaizhizao.services.demand_service import DemandService

        forecast_row = await SalesForecast.get_or_none(
            tenant_id=tenant_id, id=forecast_id, deleted_at__isnull=True
        )
        if not forecast_row:
            raise NotFoundError(f"销售预测不存在: {forecast_id}")
        demand = await self._get_linked_demand_for_forecast(tenant_id, forecast_id)
        pushed = self._is_forecast_pushed_to_computation(forecast_row, demand)
        item_count = await SalesForecastItem.filter(tenant_id=tenant_id, forecast_id=forecast_id).count()
        assert_sales_forecast_capability(
            forecast_row,
            "push_computation",
            pushed_to_computation=pushed,
            has_items=item_count > 0,
        )

        forecast = await self.get_sales_forecast_by_id(tenant_id, forecast_id)

        demand_created_here = False
        if not demand:
            demand = await self._create_demand_from_sales_forecast(
                tenant_id, forecast_id, user_id or forecast.created_by
            )
            demand_created_here = True

        try:
            result = await DemandService().push_to_computation(
                tenant_id=tenant_id,
                demand_id=demand.id,
                created_by=user_id or forecast.created_by,
            )
        except Exception:
            # 编码规则缺失等失败时，勿留下阻断撤审的中间 Demand
            if demand_created_here:
                await self._cleanup_unpushed_forecast_demand(
                    tenant_id, forecast_id, demand_id=demand.id
                )
            raise
        return {
            "forecast_id": forecast_id,
            "forecast_code": forecast.forecast_code,
            "demand_computation": result,
            "computation_id": result.get("computation_id"),
            "computation_code": result.get("computation_code"),
            "message": result.get("message", "需求计算下推成功"),
        }

    async def push_to_mrp(
        self,
        tenant_id: int,
        forecast_id: int,
        planning_horizon: int = 12,
        time_bucket: str = "week",
        user_id: int = None
    ) -> Dict[str, Any]:
        """兼容旧命名：push_to_mrp -> push_to_computation。"""
        return await self.push_to_computation(
            tenant_id=tenant_id,
            forecast_id=forecast_id,
            planning_horizon=planning_horizon,
            time_bucket=time_bucket,
            user_id=user_id,
        )
