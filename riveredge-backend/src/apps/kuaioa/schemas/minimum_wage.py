"""最低工资 schemas。"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class MinimumWageCreate(BaseModel):
    amount: Decimal
    effective_date: str = Field(..., description="YYYY-MM-DD")
    end_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    is_current: bool = False
    notes: Optional[str] = None


class MinimumWageUpdate(BaseModel):
    amount: Optional[Decimal] = None
    effective_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: Optional[bool] = None
    notes: Optional[str] = None
