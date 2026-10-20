"""采购询价需方 Schema"""

from datetime import datetime
from typing import Optional

from pydantic import Field

from core.schemas.base import BaseSchema


class PurchaseDemandPartyCreate(BaseSchema):
    code: Optional[str] = Field(None, max_length=50)
    name: str = Field(..., max_length=200)
    contact_name: Optional[str] = Field(None, max_length=100)
    contact_phone: Optional[str] = Field(None, max_length=50)
    contact_email: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = Field(None, max_length=500)
    tax_no: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0


class PurchaseDemandPartyUpdate(BaseSchema):
    name: Optional[str] = Field(None, max_length=200)
    contact_name: Optional[str] = Field(None, max_length=100)
    contact_phone: Optional[str] = Field(None, max_length=50)
    contact_email: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = Field(None, max_length=500)
    tax_no: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class PurchaseDemandPartyResponse(BaseSchema):
    id: int
    tenant_id: int
    code: str
    name: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    address: Optional[str] = None
    tax_no: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
