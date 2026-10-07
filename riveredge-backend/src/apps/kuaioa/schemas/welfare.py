"""节日福利 schemas。"""

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class WelfareBatchCreate(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    festival_type: str = Field(..., max_length=30)
    # 多车间（优先）；与 workshop_name 至少填一个
    workshop_names: Optional[List[str]] = Field(default=None)
    workshop_name: Optional[str] = Field(default=None, max_length=500)
    employment_types: Optional[List[str]] = Field(
        default=None, description="用工类型多选 formal/temp/labor，空表示全部"
    )
    notes: Optional[str] = Field(default=None)

    @model_validator(mode="after")
    def require_workshop(self) -> "WelfareBatchCreate":
        names = [str(x).strip() for x in (self.workshop_names or []) if str(x).strip()]
        single = (self.workshop_name or "").strip()
        if not names and not single:
            raise ValueError("车间不能为空")
        if names and not single:
            self.workshop_name = "、".join(names)
        if single and not names:
            self.workshop_names = [single]
        return self


class WelfareBatchUpdate(BaseModel):
    notes: Optional[str] = None


class WelfareBatchLineUpdate(BaseModel):
    amount: Optional[Decimal] = None
    received: Optional[bool] = None
    notes: Optional[str] = None
