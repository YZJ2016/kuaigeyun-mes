"""其他费用收入单服务（misc_voucher_service 收入侧绑定）。"""

from apps.kuaicaiwu.services.misc_voucher_service import (
    INCOME_SPEC,
    MiscVoucherService,
)


class OtherIncomeService(MiscVoucherService):
    def __init__(self) -> None:
        super().__init__(INCOME_SPEC)
