"""
发货通知单数据验证schema

销售通知仓库发货，不直接动库存。

Author: RiverEdge Team
Date: 2026-02-22
"""

from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict

from pydantic import Field
from core.schemas.base import BaseSchema
from apps.kuaizhizao.schemas.document_line_dual_quantity import (
    DocumentLineDualQuantitySchemaMixin,
)

from apps.kuaizhizao.services.document_action_policy.types import ShipmentNoticeCapabilities


# === 发货通知单 ===

class ShipmentNoticeBase(BaseSchema):
    """发货通知单基础schema"""
    notice_code: Optional[str] = Field(None, max_length=50, description="通知单编码（可选，不提供则自动生成）")
    sales_order_id: int = Field(..., description="销售订单ID")
    sales_order_code: str = Field(..., max_length=50, description="销售订单编码")
    customer_id: int = Field(..., description="客户ID")
    customer_name: str = Field(..., max_length=200, description="客户名称")
    customer_contact: Optional[str] = Field(None, max_length=100, description="客户联系人")
    customer_phone: Optional[str] = Field(None, max_length=50, description="客户电话")
    warehouse_id: Optional[int] = Field(None, description="出库仓库ID")
    warehouse_name: Optional[str] = Field(None, max_length=100, description="出库仓库名称")
    planned_ship_date: Optional[date] = Field(None, description="计划发货日期")
    shipping_address: Optional[str] = Field(None, description="收货地址")
    status: str = Field("待发货", max_length=20, description="通知状态")
    currency_code: Optional[str] = Field("CNY", max_length=20, description="币种代码")
    exchange_rate: Decimal = Field(default=Decimal("1"), gt=0, description="汇率（相对本位币）")
    notes: Optional[str] = Field(None, description="备注")
    attachments: Optional[List[dict]] = Field(None, description="附件列表")


class ShipmentNoticeCreate(ShipmentNoticeBase):
    """发货通知单创建schema"""
    items: Optional[List["ShipmentNoticeItemCreate"]] = Field(None, description="通知明细列表")


class ShipmentNoticeUpdate(BaseSchema):
    """发货通知单更新 schema（字段均可选，与 service exclude_unset 部分更新一致）。"""
    notice_code: Optional[str] = Field(None, max_length=50, description="通知单编码")
    sales_order_id: Optional[int] = Field(None, description="销售订单ID")
    sales_order_code: Optional[str] = Field(None, max_length=50, description="销售订单编码")
    customer_id: Optional[int] = Field(None, description="客户ID")
    customer_name: Optional[str] = Field(None, max_length=200, description="客户名称")
    customer_contact: Optional[str] = Field(None, max_length=100, description="客户联系人")
    customer_phone: Optional[str] = Field(None, max_length=50, description="客户电话")
    warehouse_id: Optional[int] = Field(None, description="出库仓库ID")
    warehouse_name: Optional[str] = Field(None, max_length=100, description="出库仓库名称")
    planned_ship_date: Optional[date] = Field(None, description="计划发货日期")
    shipping_address: Optional[str] = Field(None, description="收货地址")
    status: Optional[str] = Field(None, max_length=20, description="通知状态")
    currency_code: Optional[str] = Field(None, max_length=20, description="币种代码")
    exchange_rate: Optional[Decimal] = Field(None, gt=0, description="汇率（相对本位币）")
    notes: Optional[str] = Field(None, description="备注")
    attachments: Optional[List[dict]] = Field(None, description="附件列表")
    items: Optional[List["ShipmentNoticeItemCreate"]] = Field(None, description="通知明细列表")


class ShipmentNoticeNotify(BaseSchema):
    """通知仓库请求体。

    真源为明细行仓/库位：优先 ``line_warehouses`` / ``line_location_ids``；
    ``warehouse_id`` 仅作整单默认（兼容旧调用），灌入尚未指定行仓的明细。
    """
    warehouse_id: Optional[int] = Field(None, description="出库仓库ID（整单默认，兼容旧调用）")
    warehouse_name: Optional[str] = Field(None, max_length=100, description="出库仓库名称")
    line_warehouses: Optional[Dict[str, int]] = Field(
        None,
        description="明细行出库仓库 {shipment_notice_item_id: warehouse_id}",
    )
    line_warehouse_names: Optional[Dict[str, str]] = Field(
        None,
        description="明细行出库仓库名称 {shipment_notice_item_id: warehouse_name}",
    )
    line_location_ids: Optional[Dict[str, int]] = Field(
        None,
        description="明细行库位 {shipment_notice_item_id: location_id}",
    )
    line_location_codes: Optional[Dict[str, str]] = Field(
        None,
        description="明细行库位编码 {shipment_notice_item_id: location_code}",
    )
    push_mode: Optional[str] = Field(
        "draft",
        description="生成销售出库：draft=保存为草稿；confirm=提交审核（免审则已通过）",
    )


class ShipmentNoticeNotifyPreviewRequest(BaseSchema):
    """通知仓库预览请求：可带行仓覆盖，便于按所选仓刷新库存预占校验。"""
    warehouse_id: Optional[int] = Field(None, description="整单默认出库仓库（兼容）")
    line_warehouses: Optional[Dict[str, int]] = Field(
        None,
        description="明细行出库仓库 {shipment_notice_item_id: warehouse_id}",
    )


class ShipmentNoticeResponse(ShipmentNoticeBase):
    """发货通知单响应schema"""
    id: int = Field(..., description="通知单ID")
    tenant_id: int = Field(..., description="租户ID")
    notified_at: Optional[datetime] = Field(None, description="通知仓库时间")
    sales_delivery_id: Optional[int] = Field(None, description="销售出库单ID")
    sales_delivery_code: Optional[str] = Field(None, max_length=50, description="销售出库单编码")
    related_sales_delivery_ids: Optional[List[dict]] = Field(
        None,
        description="关联销售出库单列表（多仓发货）",
    )
    total_quantity: float = Field(0, description="总数量")
    total_amount: float = Field(0, description="总金额")
    lifecycle: Optional[dict] = Field(None, description="生命周期（后端计算，供 UniLifecycle/Stepper 展示）")
    capabilities: Optional[ShipmentNoticeCapabilities] = Field(
        None,
        description="业务态动作 capabilities（不含 RBAC，与 service 门禁一致）",
    )
    created_by: Optional[int] = Field(None, description="创建人ID")
    created_by_name: Optional[str] = Field(None, description="创建人姓名")
    updated_by: Optional[int] = Field(None, description="更新人ID")
    updated_by_name: Optional[str] = Field(None, description="更新人姓名")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    class Config:
        from_attributes = True


class ShipmentNoticeListResponse(ShipmentNoticeResponse):
    """发货通知单列表响应schema"""
    items: Optional[List["ShipmentNoticeItemResponse"]] = Field(
        None, description="通知明细（include_items 时返回）"
    )


class ShipmentNoticeListPaginatedResponse(BaseSchema):
    """发货通知单分页列表响应"""
    data: List[ShipmentNoticeListResponse]
    total: int
    success: bool = True


# === 发货通知单明细 ===

class ShipmentNoticeItemBase(DocumentLineDualQuantitySchemaMixin, BaseSchema):
    """发货通知单明细基础schema"""
    material_id: int = Field(..., description="物料ID")
    material_code: str = Field(..., max_length=50, description="物料编码")
    material_name: str = Field(..., max_length=200, description="物料名称")
    material_spec: Optional[str] = Field(None, max_length=200, description="物料规格")
    material_model: Optional[str] = Field(None, max_length=200, description="物料型号")
    partner_material_code: Optional[str] = Field(None, max_length=100, description="客户料号")
    partner_material_name: Optional[str] = Field(None, max_length=200, description="客户品名")
    material_unit: str = Field(..., max_length=20, description="物料单位")
    notice_quantity: float = Field(..., gt=0, description="通知数量")
    unit_price: float = Field(0, ge=0, description="单价")
    total_amount: Optional[float] = Field(None, ge=0, description="金额")
    is_gift: bool = Field(False, description="是否赠品")
    gift_ref_unit_price: Optional[float] = Field(None, ge=0, description="赠品参考单价")
    sales_order_item_id: Optional[int] = Field(None, description="销售订单明细ID")
    warehouse_id: Optional[int] = Field(None, description="行出库仓库ID")
    warehouse_name: Optional[str] = Field(None, max_length=100, description="行出库仓库名称")
    notes: Optional[str] = Field(None, description="备注")


class ShipmentNoticeItemCreate(ShipmentNoticeItemBase):
    """发货通知单明细创建schema"""
    pass


class ShipmentNoticeItemUpdate(ShipmentNoticeItemBase):
    """发货通知单明细更新schema"""
    pass


class ShipmentNoticeItemResponse(ShipmentNoticeItemBase):
    """发货通知单明细响应schema"""
    id: int = Field(..., description="明细ID")
    tenant_id: int = Field(..., description="租户ID")
    notice_id: int = Field(..., description="通知单ID")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    class Config:
        from_attributes = True


class ShipmentNoticeWithItemsResponse(ShipmentNoticeResponse):
    """发货通知单详情响应（含明细）"""
    items: List[ShipmentNoticeItemResponse] = Field(default_factory=list, description="通知明细列表")
