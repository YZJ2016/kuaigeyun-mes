"""最低工资 schemas。"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class MinimumWageCreate(BaseModel):
    amount: Decimal
    effective_date: str = Field(..., description="YYYY-MM-DD")
    notes: Optional[str] = None


class MinimumWageUpdate(BaseModel):
    amount: Optional[Decimal] = None
    effective_date: Optional[str] = None
    notes: Optional[str] = None
