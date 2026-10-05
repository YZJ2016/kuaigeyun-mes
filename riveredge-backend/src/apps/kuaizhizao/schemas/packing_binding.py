"""
装箱打包绑定记录数据验证 Schema
"""

from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal

from apps.kuaizhizao.services.document_action_policy.types import PackingBindingCapabilities

MAX_DECIMAL_12_2 = Decimal("9999999999.99")

SealStatus = Literal["bound", "sealed"]
PackingLevel = Literal["carton", "inner", "pallet"]
SourceType = Literal["sales_delivery", "finished_goods_receipt"]


class PackingBindingBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    finished_goods_receipt_id: Optional[int] = Field(None, description="成品入库单ID")
    sales_delivery_id: Optional[int] = Field(None, description="销售出库单ID")
    source_line_id: Optional[int] = Field(None, description="来源明细行ID")
    product_id: int = Field(..., description="产品ID")
    product_code: str = Field(..., description="产品编码")
    product_name: str = Field(..., description="产品名称")
    product_serial_no: Optional[str] = Field(None, description="主序列号")
    serial_numbers: Optional[List[str]] = Field(None, description="箱内序列号列表")
    packing_material_id: Optional[int] = Field(None, description="包装物料ID")
    packing_material_code: Optional[str] = Field(None, description="包装物料编码")
    packing_material_name: Optional[str] = Field(None, description="包装物料名称")
    packing_quantity: Decimal = Field(..., gt=0, le=MAX_DECIMAL_12_2, description="装箱数量")
    box_no: Optional[str] = Field(None, description="箱号")
    packing_level: PackingLevel = Field("carton", description="包装层级")
    parent_box_no: Optional[str] = Field(None, description="父箱号")
    pallet_no: Optional[str] = Field(None, description="托盘号")
    binding_method: str = Field("manual", description="绑定方式 scan/manual")
    barcode: Optional[str] = Field(None, description="条码")
    seal_status: SealStatus = Field("bound", description="封箱状态")
    bound_at: datetime = Field(default_factory=datetime.now, description="绑定时间")
    remarks: Optional[str] = Field(None, description="备注")
    attachments: Optional[List[dict]] = Field(None, description="附件列表")


class PackingBindingCreateFromDelivery(BaseModel):
    product_id: int = Field(..., description="产品ID")
    product_code: Optional[str] = Field(None, description="产品编码")
    product_name: Optional[str] = Field(None, description="产品名称")
    source_line_id: Optional[int] = Field(None, description="出库明细行ID")
    product_serial_no: Optional[str] = Field(None, description="主序列号")
    serial_numbers: Optional[List[str]] = Field(None, description="箱内序列号列表")
    packing_material_id: Optional[int] = Field(None, description="包装物料ID")
    packing_material_code: Optional[str] = Field(None, description="包装物料编码")
    packing_material_name: Optional[str] = Field(None, description="包装物料名称")
    packing_quantity: Decimal = Field(..., gt=0, le=MAX_DECIMAL_12_2, description="装箱数量")
    box_no: Optional[str] = Field(None, description="箱号")
    packing_level: PackingLevel = Field("carton", description="包装层级")
    parent_box_no: Optional[str] = Field(None, description="父箱号")
    pallet_no: Optional[str] = Field(None, description="托盘号")
    binding_method: str = Field("manual", description="绑定方式")
    barcode: Optional[str] = Field(None, description="条码")
    seal_status: SealStatus = Field("bound", description="封箱状态")
    bound_at: Optional[datetime] = Field(None, description="绑定时间")
    remarks: Optional[str] = Field(None, description="备注")


class PackingBindingCreateFromReceipt(BaseModel):
    product_id: int = Field(..., description="产品ID")
    product_code: Optional[str] = Field(None, description="产品编码")
    product_name: Optional[str] = Field(None, description="产品名称")
    source_line_id: Optional[int] = Field(None, description="入库明细行ID")
    product_serial_no: Optional[str] = Field(None, description="主序列号")
    serial_numbers: Optional[List[str]] = Field(None, description="箱内序列号列表")
    packing_material_id: Optional[int] = Field(None, description="包装物料ID")
    packing_material_code: Optional[str] = Field(None, description="包装物料编码")
    packing_material_name: Optional[str] = Field(None, description="包装物料名称")
    packing_quantity: Decimal = Field(..., gt=0, le=MAX_DECIMAL_12_2, description="装箱数量")
    box_no: Optional[str] = Field(None, description="箱号")
    packing_level: PackingLevel = Field("carton", description="包装层级")
    parent_box_no: Optional[str] = Field(None, description="父箱号")
    pallet_no: Optional[str] = Field(None, description="托盘号")
    binding_method: str = Field("manual", description="绑定方式")
    barcode: Optional[str] = Field(None, description="条码")
    seal_status: SealStatus = Field("bound", description="封箱状态")
    bound_at: Optional[datetime] = Field(None, description="绑定时间")
    remarks: Optional[str] = Field(None, description="备注")


class PackingBindingUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    packing_quantity: Optional[Decimal] = Field(None, gt=0, le=MAX_DECIMAL_12_2)
    box_no: Optional[str] = None
    remarks: Optional[str] = None
    attachments: Optional[List[dict]] = None
    product_serial_no: Optional[str] = None
    serial_numbers: Optional[List[str]] = None
    packing_material_id: Optional[int] = None
    packing_material_code: Optional[str] = None
    packing_material_name: Optional[str] = None
    packing_level: Optional[PackingLevel] = None
    parent_box_no: Optional[str] = None
    pallet_no: Optional[str] = None
    seal_status: Optional[SealStatus] = None


class PackingBindingResponse(PackingBindingBase):
    id: int
    uuid: str
    tenant_id: int
    bound_by: int
    bound_by_name: str
    created_at: datetime
    updated_at: datetime
    capabilities: Optional[PackingBindingCapabilities] = None


class PackingBindingListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    finished_goods_receipt_id: Optional[int] = None
    sales_delivery_id: Optional[int] = None
    source_line_id: Optional[int] = None
    product_code: str
    product_name: str
    product_serial_no: Optional[str] = None
    serial_numbers: Optional[List[str]] = None
    packing_material_code: Optional[str] = None
    packing_material_name: Optional[str] = None
    packing_quantity: Decimal
    box_no: Optional[str] = None
    packing_level: Optional[str] = "carton"
    parent_box_no: Optional[str] = None
    pallet_no: Optional[str] = None
    binding_method: str
    seal_status: Optional[str] = "bound"
    bound_by_name: str
    bound_at: datetime
    created_at: datetime
    updated_at: datetime
    capabilities: Optional[PackingBindingCapabilities] = None


class PackingBindingPageResponse(BaseModel):
    data: List[PackingBindingListResponse] = Field(default_factory=list)
    total: int = 0
    success: bool = True


class PackingBindingStatisticsResponse(BaseModel):
    total: int = 0
    scan: int = 0
    manual: int = 0
    sealed: int = 0
    bound: int = 0


class PackingBindingTaskPoolItemResponse(BaseModel):
    id: int = Field(..., description="来源单据ID")
    source_type: SourceType = Field(..., description="来源类型")
    doc_code: str = Field(..., description="单据编号")
    party_name: str = Field("", description="客户或厂区名称")
    review_status: str = Field("", description="审核状态")
    status: str = Field("", description="单据状态")
    required_quantity: Decimal = Field(Decimal("0"), description="应绑数量")
    packed_quantity: Decimal = Field(Decimal("0"), description="已绑数量")
    remaining_quantity: Decimal = Field(Decimal("0"), description="剩余可绑")
    box_count: int = Field(0, description="已绑箱数")
    updated_at: datetime
    # 兼容旧前端字段
    delivery_code: Optional[str] = None
    customer_name: Optional[str] = None


class PackingBindingTaskPoolResponse(BaseModel):
    pending_review: int = 0
    pending_outbound: int = 0
    pending_receipt: int = 0
    total: int = 0
    items: List[PackingBindingTaskPoolItemResponse] = Field(default_factory=list)


class PackingSourceRemainingLine(BaseModel):
    source_line_id: int
    product_id: int
    product_code: str
    product_name: str
    required_quantity: Decimal
    packed_quantity: Decimal
    remaining_quantity: Decimal
    box_count: int = 0


class PackingSourceRemainingResponse(BaseModel):
    source_type: SourceType
    source_id: int
    lines: List[PackingSourceRemainingLine] = Field(default_factory=list)
    required_quantity: Decimal = Decimal("0")
    packed_quantity: Decimal = Decimal("0")
    remaining_quantity: Decimal = Decimal("0")
    box_count: int = 0


class PackingAsnLine(BaseModel):
    box_no: Optional[str] = None
    packing_level: Optional[str] = None
    parent_box_no: Optional[str] = None
    pallet_no: Optional[str] = None
    product_code: str
    product_name: str
    packing_quantity: Decimal
    product_serial_no: Optional[str] = None
    serial_numbers: Optional[List[str]] = None
    seal_status: Optional[str] = None


class PackingAsnResponse(BaseModel):
    """出货装箱单（ASN 摘要），按销售出库单汇总。"""
    sales_delivery_id: int
    delivery_code: str
    customer_name: str
    box_count: int
    total_quantity: Decimal
    lines: List[PackingAsnLine] = Field(default_factory=list)
