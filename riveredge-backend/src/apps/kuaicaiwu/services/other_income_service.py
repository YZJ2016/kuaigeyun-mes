"""其他费用收入单服务（misc_voucher_service 收入侧绑定）。"""

from typing import Dict, List, Optional

from apps.kuaicaiwu.services.misc_voucher_service import (
    INCOME_SPEC,
    MiscVoucherService,
)
from infra.models.user import User


class OtherIncomeService(MiscVoucherService):
    def __init__(self) -> None:
        super().__init__(INCOME_SPEC)

    async def _user(self, user_id: int) -> User:
        return await User.get(id=int(user_id))

    async def submit_income(
        self,
        tenant_id: int,
        income_id: int,
        user_id: int,
        *,
        selected_approver_user_ids: Optional[List[int]] = None,
        selected_approver_by_node: Optional[Dict[str, List[int]]] = None,
    ):
        return await self.submit(
            tenant_id,
            income_id,
            await self._user(user_id),
            selected_approver_user_ids=selected_approver_user_ids,
            selected_approver_by_node=selected_approver_by_node,
        )

    async def approve_income(
        self,
        tenant_id: int,
        income_id: int,
        *,
        approved: bool,
        operator_id: int,
        review_remarks: Optional[str] = None,
    ):
        return await self._review(
            tenant_id,
            income_id,
            await self._user(operator_id),
            approve=approved,
            remarks=review_remarks,
        )

    async def withdraw_income_submit(
        self, tenant_id: int, income_id: int, user_id: int
    ):
        return await self.withdraw(tenant_id, income_id, await self._user(user_id))

    async def revoke_income_approval(
        self, tenant_id: int, income_id: int, user_id: int
    ):
        return await self.revoke(tenant_id, income_id, await self._user(user_id))
