"""节日福利 schemas。"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class WelfareBatchCreate(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    festival_type: str = Field(..., max_length=30)
    workshop_name: str = Field(..., max_length=100)
    notes: Optional[str] = None


class WelfareBatchUpdate(BaseModel):
    notes: Optional[str] = None


class WelfareBatchLineUpdate(BaseModel):
    amount: Optional[Decimal] = None
    received: Optional[bool] = None
    notes: Optional[str] = None
