"""售后链路上游状态联动（创建/完工下游单据时的唯一写路径）。

手工新建与下推共用，避免「只有下推才改状态、新建选来源不改」的双路径。
"""

from __future__ import annotations

from typing import Optional

from apps.common.audit_actor import apply_update_audit
from apps.kuaizhizao.models.after_sales_service import RepairOrder
from apps.kuaizhizao.models.after_sales_ticket import AfterSalesTicket
from apps.kuaizhizao.models.install_execution_job import InstallExecutionJob
from infra.models.user import User


async def bump_ticket_to_processing(
    tenant_id: int,
    ticket_id: int,
    current_user: User,
) -> None:
    """售后工单：待处理 → 处理中。"""
    row = await AfterSalesTicket.filter(
        id=ticket_id,
        tenant_id=tenant_id,
        deleted_at__isnull=True,
    ).first()
    if not row:
        return
    if str(row.status or "").strip() != "待处理":
        return
    dump = {"status": "处理中"}
    apply_update_audit(dump, current_user)
    await AfterSalesTicket.filter(id=ticket_id, tenant_id=tenant_id).update(**dump)


async def bump_repair_on_dispatch_created(
    tenant_id: int,
    repair_order_id: int,
    current_user: User,
) -> None:
    """维修单：待派工 → 维修中（生成服务派工时）。"""
    row = await RepairOrder.filter(
        id=repair_order_id,
        tenant_id=tenant_id,
        deleted_at__isnull=True,
    ).first()
    if not row:
        return
    if str(row.status or "").strip() != "待派工":
        return
    dump = {"status": "维修中"}
    apply_update_audit(dump, current_user)
    await RepairOrder.filter(id=repair_order_id, tenant_id=tenant_id).update(**dump)


async def bump_repair_on_dispatch_completed(
    tenant_id: int,
    repair_order_id: int,
    current_user: User,
) -> None:
    """维修单：维修中 → 待验收（派工完工时）。"""
    row = await RepairOrder.filter(
        id=repair_order_id,
        tenant_id=tenant_id,
        deleted_at__isnull=True,
    ).first()
    if not row:
        return
    if str(row.status or "").strip() != "维修中":
        return
    dump = {"status": "待验收"}
    apply_update_audit(dump, current_user)
    await RepairOrder.filter(id=repair_order_id, tenant_id=tenant_id).update(**dump)


async def bump_install_on_dispatch_created(
    tenant_id: int,
    install_execution_id: int,
    current_user: User,
) -> None:
    """安装执行：待派工 → 进行中（生成服务派工时）。"""
    row = await InstallExecutionJob.filter(
        id=install_execution_id,
        tenant_id=tenant_id,
        deleted_at__isnull=True,
    ).first()
    if not row:
        return
    if str(row.status or "").strip() != "待派工":
        return
    dump = {"status": "进行中"}
    apply_update_audit(dump, current_user)
    await InstallExecutionJob.filter(id=install_execution_id, tenant_id=tenant_id).update(**dump)


async def sync_upstream_on_dispatch_created(
    tenant_id: int,
    *,
    source_type: str,
    source_id: int,
    current_user: User,
) -> None:
    st = (source_type or "").strip()
    if st == "repair_order":
        await bump_repair_on_dispatch_created(tenant_id, source_id, current_user)
    elif st == "install_execution":
        await bump_install_on_dispatch_created(tenant_id, source_id, current_user)


async def sync_upstream_on_dispatch_completed(
    tenant_id: int,
    *,
    source_type: str,
    source_id: int,
    current_user: User,
) -> None:
    st = (source_type or "").strip()
    if st == "repair_order":
        await bump_repair_on_dispatch_completed(tenant_id, source_id, current_user)


async def sync_upstream_on_visit_created(
    tenant_id: int,
    *,
    source_type: str,
    source_id: int,
    current_user: User,
) -> None:
    st = (source_type or "").strip()
    if st == "after_sales_ticket":
        await bump_ticket_to_processing(tenant_id, source_id, current_user)
    elif st == "repair_order":
        # 回访通常在维修收尾；若仍待派工则至少进入维修中
        await bump_repair_on_dispatch_created(tenant_id, source_id, current_user)


async def existing_active_dispatch_code(
    tenant_id: int,
    source_type: str,
    source_id: int,
) -> Optional[str]:
    from apps.kuaizhizao.models.after_sales_service import ServiceDispatchOrder

    existing = await ServiceDispatchOrder.filter(
        tenant_id=tenant_id,
        source_type=source_type,
        source_id=source_id,
        deleted_at__isnull=True,
    ).exclude(status="已取消").first()
    return existing.dispatch_code if existing else None


async def existing_visit_code(
    tenant_id: int,
    source_type: str,
    source_id: int,
) -> Optional[str]:
    from apps.kuaizhizao.models.after_sales_service import CustomerReturnVisit

    existing = await CustomerReturnVisit.filter(
        tenant_id=tenant_id,
        source_type=source_type,
        source_id=source_id,
        deleted_at__isnull=True,
    ).first()
    return existing.visit_code if existing else None


async def existing_settlement_code_for_source(
    tenant_id: int,
    source_type: str,
    source_id: int,
) -> Optional[str]:
    from apps.kuaizhizao.models.after_sales_service import ServiceSettlementItem, ServiceSettlement

    item = await ServiceSettlementItem.filter(
        tenant_id=tenant_id,
        source_type=source_type,
        source_id=source_id,
    ).first()
    if not item:
        return None
    settlement = await ServiceSettlement.filter(
        id=item.settlement_id,
        tenant_id=tenant_id,
        deleted_at__isnull=True,
    ).first()
    return settlement.settlement_code if settlement else None
