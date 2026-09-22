"""岗位补贴 schemas。"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class PostSubsidyCreate(BaseModel):
    year_month: str = Field(..., min_length=7, max_length=7)
    employee_id: int
    item_name: str = Field(..., max_length=100)
    amount: Decimal
    notes: Optional[str] = None


class PostSubsidyUpdate(BaseModel):
    item_name: Optional[str] = Field(None, max_length=100)
    amount: Optional[Decimal] = None
    notes: Optional[str] = None
