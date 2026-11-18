"""客户/供应商地址明细：类型编码（与前端 field.partner.addressType.* 一致）"""

from __future__ import annotations

from typing import Optional

PARTNER_ADDRESS_TYPE_CODES = frozenset({"registered", "delivery", "invoice", "other"})


def coerce_partner_address_type_code(value: object) -> Optional[str]:
    if value is None or (isinstance(value, str) and not str(value).strip()):
        return None
    code = str(value).strip().lower()
    if code not in PARTNER_ADDRESS_TYPE_CODES:
        return None
    return code
