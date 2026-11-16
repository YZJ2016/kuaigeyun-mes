"""客户供应商价格本 Schema"""

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PartnerPriceVariantLine(BaseModel):
    """属性组合 SKU 单价"""

    variant_attributes: Dict[str, Any] = Field(..., alias="variantAttributes", description="属性组合")
    unit_price: Decimal = Field(..., alias="unitPrice", gt=0, description="该 SKU 单价")

    model_config = ConfigDict(populate_by_name=True)


class PartnerPriceTierLine(BaseModel):
    """数量阶梯单价"""

    min_quantity: Decimal = Field(..., alias="minQuantity", gt=0, description="起订量（含）")
    max_quantity: Optional[Decimal] = Field(None, alias="maxQuantity", description="截止量（含），空表示无上限")
    unit_price: Decimal = Field(..., alias="unitPrice", gt=0, description="该档单价")

    model_config = ConfigDict(populate_by_name=True)


class PartnerPriceBookBase(BaseModel):
    partner_id: int = Field(..., alias="partnerId", description="客户或供应商 ID")
    material_id: int = Field(..., alias="materialId", description="内部物料 ID")
    unit_price: Optional[Decimal] = Field(None, alias="unitPrice", gt=0, description="标准价（统一价）")
    price_type: Optional[str] = Field(
        "tax_inclusive",
        alias="priceType",
        description="价类：tax_inclusive 含税 / tax_exclusive 不含税",
    )
    variant_prices: Optional[List[PartnerPriceVariantLine]] = Field(
        None,
        alias="variantPrices",
        description="按属性组合的 SKU 单价",
    )
    tier_prices: Optional[List[PartnerPriceTierLine]] = Field(
        None,
        alias="tierPrices",
        description="按订购数量的阶梯单价",
    )
    currency_code: Optional[str] = Field(None, alias="currencyCode", description="币种")
    tax_rate: Optional[Decimal] = Field(None, alias="taxRate", description="税率（百分比）")
    unit: Optional[str] = Field(None, description="计价单位")
    effective_from: Optional[date] = Field(None, alias="effectiveFrom", description="生效起始日")
    effective_to: Optional[date] = Field(None, alias="effectiveTo", description="生效截止日")
    remark: Optional[str] = Field(None, description="备注")
    is_active: Optional[bool] = Field(True, alias="isActive", description="是否启用")
    partner_material_code: Optional[str] = Field(
        None, alias="partnerMaterialCode", description="伙伴料号（无映射时可写入物料编号映射）"
    )
    partner_material_name: Optional[str] = Field(
        None, alias="partnerMaterialName", description="伙伴品名（无映射时可写入物料编号映射）"
    )
    sync_partner_alias: bool = Field(
        True, alias="syncPartnerAlias", description="保存时是否回写物料编号映射（仅无现有映射时生效）"
    )

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def validate_effective_range(self):
        if self.effective_from and self.effective_to and self.effective_from > self.effective_to:
            raise ValueError("生效起始日不能晚于截止日")
        return self

    @model_validator(mode="after")
    def validate_prices(self):
        has_standard = self.unit_price is not None and self.unit_price > 0
        has_variant = bool(self.variant_prices)
        has_tier = bool(self.tier_prices)
        if not has_standard and not has_variant and not has_tier:
            raise ValueError("标准价、属性 SKU 单价与数量阶梯至少填写一项")
        if self.tier_prices:
            from apps.master_data.services.partner_price_tier_utils import normalize_tier_prices_for_storage

            normalize_tier_prices_for_storage(
                [line.model_dump(by_alias=True) for line in self.tier_prices]
            )
        if self.variant_prices:
            seen: set[str] = set()
            for line in self.variant_prices:
                norm = json.dumps(line.variant_attributes or {}, sort_keys=True, ensure_ascii=False)
                if norm in seen:
                    raise ValueError("属性 SKU 单价存在重复的属性组合")
                seen.add(norm)
                if not line.variant_attributes:
                    raise ValueError("属性 SKU 单价须填写至少一项属性")
        return self


class PartnerPriceBookCreate(PartnerPriceBookBase):
    pass


class PartnerPriceBookUpdate(BaseModel):
    partner_id: Optional[int] = Field(None, alias="partnerId")
    material_id: Optional[int] = Field(None, alias="materialId")
    unit_price: Optional[Decimal] = Field(None, alias="unitPrice", gt=0)
    price_type: Optional[str] = Field(None, alias="priceType")
    variant_prices: Optional[List[PartnerPriceVariantLine]] = Field(None, alias="variantPrices")
    tier_prices: Optional[List[PartnerPriceTierLine]] = Field(None, alias="tierPrices")
    currency_code: Optional[str] = Field(None, alias="currencyCode")
    tax_rate: Optional[Decimal] = Field(None, alias="taxRate")
    unit: Optional[str] = Field(None)
    effective_from: Optional[date] = Field(None, alias="effectiveFrom")
    effective_to: Optional[date] = Field(None, alias="effectiveTo")
    remark: Optional[str] = Field(None)
    is_active: Optional[bool] = Field(None, alias="isActive")
    partner_material_code: Optional[str] = Field(None, alias="partnerMaterialCode")
    partner_material_name: Optional[str] = Field(None, alias="partnerMaterialName")
    sync_partner_alias: Optional[bool] = Field(None, alias="syncPartnerAlias")

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def validate_update_prices(self):
        if self.unit_price is None and self.variant_prices is None and self.tier_prices is None:
            return self
        has_standard = self.unit_price is not None and self.unit_price > 0
        has_variant = bool(self.variant_prices)
        has_tier = bool(self.tier_prices)
        if self.unit_price is not None or self.variant_prices is not None or self.tier_prices is not None:
            if not has_standard and not has_variant and not has_tier:
                raise ValueError("标准价、属性 SKU 单价与数量阶梯至少填写一项")
        if self.tier_prices:
            from apps.master_data.services.partner_price_tier_utils import normalize_tier_prices_for_storage

            normalize_tier_prices_for_storage(
                [line.model_dump(by_alias=True) for line in self.tier_prices]
            )
        if self.variant_prices:
            seen: set[str] = set()
            for line in self.variant_prices:
                norm = json.dumps(line.variant_attributes or {}, sort_keys=True, ensure_ascii=False)
                if norm in seen:
                    raise ValueError("属性 SKU 单价存在重复的属性组合")
                seen.add(norm)
        return self


class PartnerPriceBookResponse(BaseModel):
    id: int
    uuid: str
    tenant_id: int = Field(..., alias="tenantId")
    partner_type: str = Field(..., alias="partnerType")
    partner_id: int = Field(..., alias="partnerId")
    partner_code: Optional[str] = Field(None, alias="partnerCode")
    partner_name: Optional[str] = Field(None, alias="partnerName")
    material_id: int = Field(..., alias="materialId")
    material_code: Optional[str] = Field(None, alias="materialCode")
    material_name: Optional[str] = Field(None, alias="materialName")
    partner_material_code: Optional[str] = Field(None, alias="partnerMaterialCode")
    partner_material_name: Optional[str] = Field(None, alias="partnerMaterialName")
    unit_price: Optional[Decimal] = Field(None, alias="unitPrice")
    price_type: Optional[str] = Field("tax_inclusive", alias="priceType")
    variant_prices: Optional[List[PartnerPriceVariantLine]] = Field(None, alias="variantPrices")
    tier_prices: Optional[List[PartnerPriceTierLine]] = Field(None, alias="tierPrices")
    currency_code: Optional[str] = Field(None, alias="currencyCode")
    tax_rate: Optional[Decimal] = Field(None, alias="taxRate")
    unit: Optional[str] = None
    effective_from: Optional[date] = Field(None, alias="effectiveFrom")
    effective_to: Optional[date] = Field(None, alias="effectiveTo")
    remark: Optional[str] = None
    is_active: bool = Field(True, alias="isActive")
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")
    created_by_name: Optional[str] = Field(None, alias="createdByName")
    updated_by_name: Optional[str] = Field(None, alias="updatedByName")

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class PartnerPriceBookListResponse(BaseModel):
    data: List[PartnerPriceBookResponse]
    total: int

    model_config = ConfigDict(populate_by_name=True)


ResolveMode = Literal["auto", "standard_only", "tier_only"]


class PartnerPriceResolveRequest(BaseModel):
    partner_id: int = Field(..., alias="partnerId")
    material_id: Optional[int] = Field(None, alias="materialId")
    partner_material_code: Optional[str] = Field(None, alias="partnerMaterialCode")
    variant_attributes: Optional[Dict[str, Any]] = Field(None, alias="variantAttributes")
    as_of: Optional[date] = Field(None, alias="asOf")
    quantity: Optional[Decimal] = Field(None, description="计价数量，用于阶梯价命中")
    resolve_mode: ResolveMode = Field(
        "auto",
        alias="resolveMode",
        description="auto=兼容现网(SKU→有qty且命中阶梯则阶梯否则标准)；standard_only/tier_only 供站点取价顺序",
    )

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def validate_lookup_key(self):
        if not self.material_id and not self.partner_material_code:
            raise ValueError("materialId 与 partnerMaterialCode 至少提供一个")
        return self


class PartnerPriceResolveBatchLineRequest(BaseModel):
    material_id: int = Field(..., alias="materialId")
    variant_attributes: Optional[Dict[str, Any]] = Field(None, alias="variantAttributes")
    quantity: Optional[Decimal] = Field(None, description="计价数量")

    model_config = ConfigDict(populate_by_name=True)


class PartnerPriceResolveBatchRequest(BaseModel):
    partner_id: int = Field(..., alias="partnerId")
    material_ids: Optional[List[int]] = Field(None, alias="materialIds")
    items: Optional[List[PartnerPriceResolveBatchLineRequest]] = Field(None, description="带属性组合的批量询价")
    as_of: Optional[date] = Field(None, alias="asOf")

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def validate_batch_keys(self):
        if not self.material_ids and not self.items:
            raise ValueError("materialIds 与 items 至少提供一个")
        return self


class PartnerPriceResolveResponse(BaseModel):
    found: bool = False
    unit_price: Optional[Decimal] = Field(None, alias="unitPrice")
    is_variant_price: bool = Field(False, alias="isVariantPrice", description="是否命中属性 SKU 单价")
    is_tier_price: bool = Field(False, alias="isTierPrice", description="是否命中数量阶梯价")
    price_source: Optional[str] = Field(
        None,
        alias="priceSource",
        description="book_standard / book_tier / book_variant 等，供调试",
    )
    currency_code: Optional[str] = Field(None, alias="currencyCode")
    tax_rate: Optional[Decimal] = Field(None, alias="taxRate")
    unit: Optional[str] = None
    material_id: Optional[int] = Field(None, alias="materialId")
    partner_material_code: Optional[str] = Field(None, alias="partnerMaterialCode")
    partner_material_name: Optional[str] = Field(None, alias="partnerMaterialName")
    price_book_uuid: Optional[str] = Field(None, alias="priceBookUuid")

    model_config = ConfigDict(populate_by_name=True)


class PartnerPriceResolveBatchResponse(BaseModel):
    items: List[PartnerPriceResolveResponse]

    model_config = ConfigDict(populate_by_name=True)


class PartnerMaterialLinePriceResolveRequest(BaseModel):
    side: Literal["purchase", "sales"]
    partner_id: int = Field(..., alias="partnerId")
    material_id: int = Field(..., alias="materialId")
    quantity: Optional[Decimal] = Field(None, description="计价数量")
    as_of: Optional[date] = Field(None, alias="asOf")
    variant_attributes: Optional[Dict[str, Any]] = Field(None, alias="variantAttributes")

    model_config = ConfigDict(populate_by_name=True)


class PartnerMaterialLinePriceResolveResponse(BaseModel):
    found: bool = False
    unit_price: Optional[Decimal] = Field(None, alias="unitPrice")
    tax_rate: Optional[Decimal] = Field(None, alias="taxRate")
    price_source: Optional[str] = Field(None, alias="priceSource")
    currency_code: Optional[str] = Field(None, alias="currencyCode")
    partner_material_code: Optional[str] = Field(None, alias="partnerMaterialCode")
    partner_material_name: Optional[str] = Field(None, alias="partnerMaterialName")

    model_config = ConfigDict(populate_by_name=True)


class PartnerPriceBookBulkLine(BaseModel):
    material_id: int = Field(..., alias="materialId")
    unit_price: Optional[Decimal] = Field(None, alias="unitPrice", gt=0)
    tier_prices: Optional[List[PartnerPriceTierLine]] = Field(None, alias="tierPrices")
    unit: Optional[str] = Field(None, description="计价单位，空则取物料主单位")
    partner_material_code: Optional[str] = Field(
        None, alias="partnerMaterialCode", description="伙伴料号（可选，可回写编号映射）"
    )
    partner_material_name: Optional[str] = Field(
        None, alias="partnerMaterialName", description="伙伴品名（可选）"
    )

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def validate_bulk_line_prices(self):
        has_standard = self.unit_price is not None and self.unit_price > 0
        has_tier = bool(self.tier_prices)
        if not has_standard and not has_tier:
            raise ValueError("批量登记须填写标准价或至少一档阶梯价")
        if self.tier_prices:
            from apps.master_data.services.partner_price_tier_utils import normalize_tier_prices_for_storage

            normalize_tier_prices_for_storage(
                [line.model_dump(by_alias=True) for line in self.tier_prices]
            )
        return self


class PartnerPriceBookBulkCreate(BaseModel):
    partner_ids: List[int] = Field(..., alias="partnerIds", min_length=1)
    lines: List[PartnerPriceBookBulkLine] = Field(..., min_length=1)
    price_type: Optional[str] = Field(
        "tax_inclusive",
        alias="priceType",
        description="价类：tax_inclusive 含税 / tax_exclusive 不含税",
    )
    tax_rate: Optional[Decimal] = Field(None, alias="taxRate")
    effective_from: Optional[date] = Field(None, alias="effectiveFrom")
    effective_to: Optional[date] = Field(None, alias="effectiveTo")
    remark: Optional[str] = None
    is_active: Optional[bool] = Field(True, alias="isActive")
    sync_partner_alias: Optional[bool] = Field(
        True,
        alias="syncPartnerAlias",
        description="有伙伴料号时是否回写物料编号映射（仅尚无映射时）",
    )
    conflict_policy: Optional[Literal["skip", "overwrite"]] = Field(
        None,
        alias="conflictPolicy",
        description="空=仅预检；skip=跳过冲突；overwrite=覆盖标准价",
    )

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def validate_bulk(self):
        if self.effective_from and self.effective_to and self.effective_from > self.effective_to:
            raise ValueError("生效起始日不能晚于截止日")
        material_ids = [line.material_id for line in self.lines]
        if len(material_ids) != len(set(material_ids)):
            raise ValueError("明细物料不能重复")
        return self


class PartnerPriceBookBulkConflictItem(BaseModel):
    partner_id: int = Field(..., alias="partnerId")
    partner_code: Optional[str] = Field(None, alias="partnerCode")
    partner_name: Optional[str] = Field(None, alias="partnerName")
    material_id: int = Field(..., alias="materialId")
    material_code: Optional[str] = Field(None, alias="materialCode")
    material_name: Optional[str] = Field(None, alias="materialName")
    existing_uuid: str = Field(..., alias="existingUuid")

    model_config = ConfigDict(populate_by_name=True)


class PartnerPriceBookBulkResponse(BaseModel):
    created_count: int = Field(0, alias="createdCount")
    skipped_count: int = Field(0, alias="skippedCount")
    overwritten_count: int = Field(0, alias="overwrittenCount")

    model_config = ConfigDict(populate_by_name=True)


class PartnerPriceBookFilterPartnerOption(BaseModel):
    """列表筛选：仅返回价格本中已有数据的客户/供应商。"""

    id: int
    code: Optional[str] = None
    name: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class PartnerPriceBookFilterPartnerListResponse(BaseModel):
    data: List[PartnerPriceBookFilterPartnerOption]

    model_config = ConfigDict(populate_by_name=True)
