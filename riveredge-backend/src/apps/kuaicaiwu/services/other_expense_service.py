"""其他费用支出单服务（misc_voucher_service 支出侧绑定）。"""

from typing import Dict, List, Optional

from apps.kuaicaiwu.services.misc_voucher_service import (
    EXPENSE_SPEC,
    MiscVoucherService,
)
from infra.models.user import User


class OtherExpenseService(MiscVoucherService):
    def __init__(self) -> None:
        super().__init__(EXPENSE_SPEC)

    async def _user(self, user_id: int) -> User:
        return await User.get(id=int(user_id))

    async def submit_expense(
        self,
        tenant_id: int,
        expense_id: int,
        user_id: int,
        *,
        selected_approver_user_ids: Optional[List[int]] = None,
        selected_approver_by_node: Optional[Dict[str, List[int]]] = None,
    ):
        return await self.submit(
            tenant_id,
            expense_id,
            await self._user(user_id),
            selected_approver_user_ids=selected_approver_user_ids,
            selected_approver_by_node=selected_approver_by_node,
        )

    async def approve_expense(
        self,
        tenant_id: int,
        expense_id: int,
        *,
        approved: bool,
        operator_id: int,
        review_remarks: Optional[str] = None,
        is_auto_approve: bool = False,
    ):
        return await self._review(
            tenant_id,
            expense_id,
            await self._user(operator_id),
            approve=approved,
            remarks=review_remarks,
            is_auto_approve=is_auto_approve,
        )

    async def withdraw_expense_submit(
        self, tenant_id: int, expense_id: int, user_id: int
    ):
        return await self.withdraw(tenant_id, expense_id, await self._user(user_id))

    async def revoke_expense_approval(
        self, tenant_id: int, expense_id: int, user_id: int
    ):
        return await self.revoke(tenant_id, expense_id, await self._user(user_id))
