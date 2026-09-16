"""结算行导入 schemas。"""

from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field


class PayrollLineImportRow(BaseModel):
    employee_name: str = Field(..., max_length=100)
    amount: Decimal
    target_field: Literal["basic_wage", "piece_wage"] = "basic_wage"


class PayrollLineImportRequest(BaseModel):
    rows: list[PayrollLineImportRow] = Field(..., min_length=1)


class PayrollSettlementLineAllocation(BaseModel):
    line_total_output: Optional[Decimal] = None
    line_total_hours: Optional[Decimal] = None
    line_total_wage: Optional[Decimal] = None
    line_bonus_rate: Optional[Decimal] = None
