"""外贸销售行业插件：外贸客户、询盘导入、跟进。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field

from apps.kuaizhizao.schemas.customer_follow_up import (
    CustomerFollowUpCreate,
    CustomerFollowUpDashboardSnapshot,
    CustomerFollowUpListEnvelope as FollowUpListEnvelope,
    CustomerFollowUpResponse,
    CustomerFollowUpUpdate,
)
from apps.kuaizhizao.schemas.customer_pool import CustomerPoolListEnvelope
from apps.kuaizhizao.services.customer_follow_up_service import (
    CUSTOMER_FOLLOW_UP_SORTABLE_FIELDS,
    CustomerFollowUpService,
)
from apps.kuaizhizao.services.customer_pool_service import CustomerPoolService
from apps.master_data.models.customer import Customer
from apps.master_data.schemas.supply_chain_schemas import (
    CustomerCreate,
    CustomerResponse,
    CustomerUpdate,
)
from apps.master_data.services.supply_chain_service import SupplyChainService
from core.api.deps.access import require_permission_codes
from core.api.deps.deps import get_current_tenant
from core.config.code_rule_pages import get_canonical_rule_code
from core.services.business.code_generation_service import CodeGenerationService
from core.services.business.code_rule_service import CodeRuleService
from core.utils.timezone_utils import (
    coerce_business_datetime_to_utc,
    resolve_business_datetime,
    today_site_str,
)
from infra.api.deps.deps import get_current_user
from infra.exceptions.exceptions import NotFoundError, ValidationError
from infra.models.user import User

router = APIRouter(prefix="", tags=["App - Industry Foreign Trade"])

INQUIRY_COLUMNS = (
    "created_time",
    "campaign_name",
    "your_packaging_materials",
    "required_production_capacity",
    "phone_number",
    "email",
    "full_name",
    "company_name",
    "job_title",
)


class InquiryImportRow(BaseModel):
    created_time: Optional[str] = None
    campaign_name: Optional[str] = None
    your_packaging_materials: Optional[str] = None
    required_production_capacity: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    job_title: Optional[str] = None


class InquiryImportRequest(BaseModel):
    items: List[InquiryImportRow] = Field(..., min_length=1, max_length=200)


class InquiryImportResultItem(BaseModel):
    index: int
    success: bool
    customer_id: Optional[int] = None
    customer_code: Optional[str] = None
    error: Optional[str] = None


class InquiryImportResponse(BaseModel):
    total: int
    success_count: int
    failed_count: int
    items: List[InquiryImportResultItem]


def _parse_created_time(raw: Optional[str]) -> Optional[datetime]:
    text = str(raw or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return coerce_business_datetime_to_utc(datetime.strptime(text, fmt))
        except Exception:
            continue
    try:
        return coerce_business_datetime_to_utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except Exception as exc:
        raise ValidationError(f"创建时间无法解析: {text}") from exc


async def _next_export_customer_code(tenant_id: int, index: int) -> str:
    page_code = "master-data-supply-chain-customer"
    rule_code = get_canonical_rule_code(page_code)
    if rule_code:
        rule = await CodeRuleService.get_rule_by_code(tenant_id, rule_code, active_only=True)
        if rule:
            return await CodeGenerationService.generate_code(tenant_id, rule_code)
    return f"FT{today_site_str()}{index:04d}"


@router.get(
    "/export-customers",
    response_model=CustomerPoolListEnvelope,
    summary="List export-market customers",
)
async def list_export_customers(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(None),
    salesman_id: Optional[int] = Query(None, alias="salesmanId", ge=1),
    follow_status: Optional[str] = Query(None, alias="followStatus"),
    inactive_7d: Optional[bool] = Query(None, alias="inactive7d"),
    customer_level_code: Optional[str] = Query(None, alias="customerLevelCode"),
    intent_material_name: Optional[str] = Query(None, alias="intentMaterialName"),
    country_code: Optional[str] = Query(None, alias="countryCode", description="国家/地区（模糊）"),
    last_follow_up_from: Optional[datetime] = Query(None, alias="lastFollowUpFrom"),
    last_follow_up_to: Optional[datetime] = Query(None, alias="lastFollowUpTo"),
    created_start_date: Optional[str] = Query(None, alias="createdStartDate"),
    created_end_date: Optional[str] = Query(None, alias="createdEndDate"),
    order_by: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _auth: object = Depends(require_permission_codes("ind-foreign-trade:export-customer:read")),
):
    return await CustomerPoolService.list_customers(
        tenant_id=tenant_id,
        current_user=current_user,
        scope="all",
        skip=skip,
        limit=limit,
        keyword=keyword,
        salesman_id=salesman_id,
        follow_status=follow_status,
        market_scope="export",
        country_code=country_code,
        inactive_7d=inactive_7d,
        customer_level_code=customer_level_code,
        intent_material_name=intent_material_name,
        last_follow_up_from=last_follow_up_from,
        last_follow_up_to=last_follow_up_to,
        created_start_date=created_start_date,
        created_end_date=created_end_date,
        order_by=order_by,
    )


async def _require_export_customer(tenant_id: int, customer_uuid: str) -> Customer:
    row = await Customer.filter(
        tenant_id=tenant_id,
        uuid=customer_uuid,
        deleted_at__isnull=True,
    ).first()
    if not row:
        raise NotFoundError("外贸客户不存在")
    if str(getattr(row, "market_scope", None) or "").strip().lower() != "export":
        raise ValidationError("该客户不是外贸客户")
    return row


async def _require_export_customer_id(tenant_id: int, customer_id: int) -> Customer:
    row = await Customer.filter(
        id=customer_id,
        tenant_id=tenant_id,
        deleted_at__isnull=True,
    ).first()
    if not row:
        raise NotFoundError("外贸客户不存在")
    if str(getattr(row, "market_scope", None) or "").strip().lower() != "export":
        raise ValidationError("该客户不是外贸客户")
    return row


@router.get(
    "/stats",
    response_model=CustomerFollowUpDashboardSnapshot,
    summary="Export-market CRM snapshot",
)
async def export_crm_stats(
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    limit: int = Query(8, ge=1, le=20),
    _auth: object = Depends(require_permission_codes("ind-foreign-trade:entry:read")),
):
    return await CustomerFollowUpService.dashboard_follow_up_snapshot(
        tenant_id,
        current_user,
        limit=limit,
        market_scope="export",
    )


@router.get(
    "/follow-ups",
    response_model=FollowUpListEnvelope,
    summary="List export-customer follow-ups",
)
async def list_export_follow_ups(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    customer_id: Optional[int] = Query(None, alias="customerId"),
    activity_type_code: Optional[str] = Query(None, alias="activityTypeCode"),
    keyword: Optional[str] = Query(None),
    occurred_from: Optional[datetime] = Query(None, alias="occurredFrom"),
    occurred_to: Optional[datetime] = Query(None, alias="occurredTo"),
    pending_only: bool = Query(False, alias="pendingOnly"),
    order_by: Optional[str] = Query(None, alias="orderBy"),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _auth: object = Depends(require_permission_codes("ind-foreign-trade:follow-up:read")),
):
    safe_order_by = None
    if order_by:
        field = order_by.lstrip("-")
        if field in CUSTOMER_FOLLOW_UP_SORTABLE_FIELDS:
            safe_order_by = order_by
    return await CustomerFollowUpService.list_follow_ups(
        tenant_id=tenant_id,
        skip=skip,
        limit=limit,
        customer_id=customer_id,
        activity_type_code=activity_type_code,
        keyword=keyword,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        pending_only=pending_only,
        order_by=safe_order_by,
        current_user=current_user,
        market_scope="export",
    )


@router.get(
    "/follow-ups/{follow_id}",
    response_model=CustomerFollowUpResponse,
    summary="Get export follow-up",
)
async def get_export_follow_up(
    follow_id: int = Path(..., ge=1),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _auth: object = Depends(require_permission_codes("ind-foreign-trade:follow-up:read")),
):
    try:
        item = await CustomerFollowUpService.get(tenant_id, follow_id, current_user)
        await _require_export_customer_id(tenant_id, item.customer_id)
        return item
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/follow-ups",
    response_model=CustomerFollowUpResponse,
    summary="Create export follow-up",
)
async def create_export_follow_up(
    body: CustomerFollowUpCreate,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _auth: object = Depends(require_permission_codes("ind-foreign-trade:follow-up:create")),
):
    try:
        await _require_export_customer_id(tenant_id, body.customer_id)
        return await CustomerFollowUpService.create(tenant_id, body, current_user)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put(
    "/follow-ups/{follow_id}",
    response_model=CustomerFollowUpResponse,
    summary="Update export follow-up",
)
async def update_export_follow_up(
    body: CustomerFollowUpUpdate,
    follow_id: int = Path(..., ge=1),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _auth: object = Depends(require_permission_codes("ind-foreign-trade:follow-up:update")),
):
    try:
        existing = await CustomerFollowUpService.get(tenant_id, follow_id, current_user)
        await _require_export_customer_id(tenant_id, existing.customer_id)
        return await CustomerFollowUpService.update(tenant_id, follow_id, body, current_user)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete(
    "/follow-ups/{follow_id}",
    summary="Delete export follow-up",
)
async def delete_export_follow_up(
    follow_id: int = Path(..., ge=1),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _auth: object = Depends(require_permission_codes("ind-foreign-trade:follow-up:delete")),
):
    try:
        existing = await CustomerFollowUpService.get(tenant_id, follow_id, current_user)
        await _require_export_customer_id(tenant_id, existing.customer_id)
        await CustomerFollowUpService.delete(tenant_id, follow_id, current_user)
        return {"ok": True}
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/export-customers/{customer_uuid}",
    response_model=CustomerResponse,
    summary="Get export customer",
)
async def get_export_customer(
    customer_uuid: str,
    tenant_id: int = Depends(get_current_tenant),
    _auth: object = Depends(require_permission_codes("ind-foreign-trade:export-customer:read")),
):
    await _require_export_customer(tenant_id, customer_uuid)
    return await SupplyChainService.get_customer_by_uuid(tenant_id, customer_uuid)


@router.post(
    "/export-customers",
    response_model=CustomerResponse,
    summary="Create export customer",
)
async def create_export_customer(
    body: CustomerCreate,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _auth: object = Depends(require_permission_codes("ind-foreign-trade:export-customer:create")),
):
    payload = body.model_copy(update={"market_scope": "export"})
    if not payload.follow_status:
        payload = payload.model_copy(update={"follow_status": "pending"})
    return await SupplyChainService.create_customer(tenant_id, payload, current_user)


@router.put(
    "/export-customers/{customer_uuid}",
    response_model=CustomerResponse,
    summary="Update export customer",
)
async def update_export_customer(
    customer_uuid: str,
    body: CustomerUpdate,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _auth: object = Depends(require_permission_codes("ind-foreign-trade:export-customer:update")),
):
    await _require_export_customer(tenant_id, customer_uuid)
    payload = body.model_copy(update={"market_scope": "export"})
    return await SupplyChainService.update_customer(tenant_id, customer_uuid, payload, current_user)


@router.get("/inquiry-import/columns", summary="Inquiry import column template")
async def inquiry_import_columns(
    _auth: object = Depends(require_permission_codes("ind-foreign-trade:export-customer:import")),
):
    return {
        "columns": list(INQUIRY_COLUMNS),
        "labels_zh": {
            "created_time": "创建时间",
            "campaign_name": "广告系列名称",
            "your_packaging_materials": "采购包装物料名称",
            "required_production_capacity": "所需生产能力",
            "phone_number": "手机号",
            "email": "邮箱",
            "full_name": "姓名",
            "company_name": "公司名称",
            "job_title": "职位",
        },
    }


@router.post(
    "/inquiry-import",
    response_model=InquiryImportResponse,
    summary="Import foreign-trade inquiry rows",
)
async def import_inquiry_rows(
    body: InquiryImportRequest,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
    _auth: object = Depends(require_permission_codes("ind-foreign-trade:export-customer:import")),
):
    results: List[InquiryImportResultItem] = []
    success_count = 0
    for idx, row in enumerate(body.items):
        company = str(row.company_name or "").strip()
        phone = str(row.phone_number or "").strip()
        email = str(row.email or "").strip()
        if not company:
            results.append(
                InquiryImportResultItem(index=idx, success=False, error="公司名称不能为空")
            )
            continue
        if not phone and not email:
            results.append(
                InquiryImportResultItem(index=idx, success=False, error="手机号与邮箱至少填写一项")
            )
            continue
        try:
            created_at = _parse_created_time(row.created_time)
            payload = CustomerCreate(
                code=await _next_export_customer_code(tenant_id, idx + 1),
                name=company,
                contact_person=str(row.full_name or "").strip() or None,
                contact_title=str(row.job_title or "").strip() or None,
                phone=phone or None,
                email=email or None,
                salesman_id=current_user.id,
                market_scope="export",
                follow_status="pending",
                intent_material_name=str(row.your_packaging_materials or "").strip() or None,
                campaign_name=str(row.campaign_name or "").strip() or None,
                required_capacity_text=str(row.required_production_capacity or "").strip() or None,
                project_description=None,
            )
            created = await SupplyChainService.create_customer(tenant_id, payload, current_user)
            if created_at is not None:
                from apps.master_data.models.customer import Customer

                cust = await Customer.filter(id=created.id, tenant_id=tenant_id).first()
                if cust:
                    cust.created_at = created_at
                    await cust.save(update_fields=["created_at"])
            success_count += 1
            results.append(
                InquiryImportResultItem(
                    index=idx,
                    success=True,
                    customer_id=created.id,
                    customer_code=created.code,
                )
            )
        except Exception as exc:
            results.append(
                InquiryImportResultItem(index=idx, success=False, error=str(exc) or "导入失败")
            )

    return InquiryImportResponse(
        total=len(body.items),
        success_count=success_count,
        failed_count=len(body.items) - success_count,
        items=results,
    )


@router.get("/health", summary="Plugin health")
async def health():
    return {"ok": True, "now": resolve_business_datetime().isoformat()}
