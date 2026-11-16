"""单据行主/副数量 schema 字段。"""

from typing import Optional

from pydantic import Field

from core.schemas.base import BaseSchema


class DocumentLineDualQuantitySchemaMixin(BaseSchema):
    aux_quantity: Optional[float] = Field(None, ge=0, description="副数量")
    aux_unit: Optional[str] = Field(None, max_length=20, description="副单位")
    unit_conversion_rate: Optional[float] = Field(
        None,
        gt=0,
        description="行换算率（1 副单位 = rate 主单位）",
    )
