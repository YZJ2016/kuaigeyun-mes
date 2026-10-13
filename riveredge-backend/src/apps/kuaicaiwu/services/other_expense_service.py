"""其他费用支出单服务（misc_voucher_service 支出侧绑定）。"""

from apps.kuaicaiwu.services.misc_voucher_service import (
    EXPENSE_SPEC,
    MiscVoucherService,
)


class OtherExpenseService(MiscVoucherService):
    def __init__(self) -> None:
        super().__init__(EXPENSE_SPEC)
