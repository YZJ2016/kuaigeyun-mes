"""租户金蝶强一致编排：审计只读；修复走主数据/即时库存 sync-from-source 与外推 API。"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Type

from infra.exceptions.exceptions import BusinessLogicError, ValidationError
from infra.models.user import User

from apps.kuaizhizao.schemas.inventory_sync import InventorySyncFromSourceRequest
from apps.kuaizhizao.schemas.kingdee_consistency import (
    KingdeeConsistencyAuditOut,
    KingdeeConsistencyBlocker,
    KingdeeConsistencyDuplicateWarehouse,
    KingdeeConsistencyEmptyLocationBatch,
    KingdeeConsistencyInventoryOut,
    KingdeeConsistencyMasterDataOut,
    KingdeeConsistencyMasterDataStepOut,
    KingdeeConsistencyRemediation,
)
from apps.master_data.schemas.master_data_sync import MasterDataSyncFromSourceRequest

_MASTER_DATA_CHAIN: Tuple[
    Tuple[str, str, str, Type[Any], bool, bool],
    ...,
] = (
    ("unit", "unit_sync_service", "MaterialUnitSyncService", "MaterialUnitSyncBinding", False, False),
    ("group", "material_group_sync_service", "MaterialGroupSyncService", "MaterialGroupSyncBinding", False, False),
    (
        "material",
        "material_sync_service",
        "MaterialSyncService",
        "MaterialSyncBinding",
        False,
        True,
    ),
    (
        "material_multi_unit",
        "material_multi_unit_sync_service",
        "MaterialMultiUnitSyncService",
        "MaterialMultiUnitSyncBinding",
        False,
        False,
    ),
    (
        "material_batch_manage",
        "material_batch_manage_sync_service",
        "MaterialBatchManageSyncService",
        "MaterialBatchManageSyncBinding",
        False,
        False,
    ),
    ("customer", "customer_sync_service", "CustomerSyncService", "CustomerSyncBinding", True, False),
    ("supplier", "supplier_sync_service", "SupplierSyncService", "SupplierSyncBinding", True, False),
    ("warehouse", "warehouse_sync_service", "WarehouseSyncService", "WarehouseSyncBinding", True, False),
    (
        "warehouse_location_ref",
        "warehouse_location_ref_sync_service",
        "WarehouseLocationRefSyncService",
        "WarehouseLocationRefSyncBinding",
        True,
        False,
    ),
    (
        "storage_location",
        "storage_location_sync_service",
        "StorageLocationSyncService",
        "StorageLocationSyncBinding",
        True,
        False,
    ),
)

_WITHDRAW_PATH_BY_SOURCE: Dict[str, str] = {
    "purchase_receipt": "/api/v1/apps/kuaizhizao/warehouse-execution/purchase-receipts/{source_id}/withdraw",
    "sales_delivery": "/api/v1/apps/kuaizhizao/warehouse-execution/sales-deliveries/{source_id}/withdraw",
    "other_outbound": "/api/v1/apps/kuaizhizao/warehouse-execution/other-outbounds/{source_id}/withdraw",
    "other_inbound": "/api/v1/apps/kuaizhizao/warehouse-execution/other-inbounds/{source_id}/withdraw",
    "production_picking": "/api/v1/apps/kuaizhizao/warehouse-execution/production-pickings/{source_id}/withdraw",
    "finished_goods_receipt": (
        "/api/v1/apps/kuaizhizao/warehouse-execution/finished-goods-receipts/{source_id}/withdraw"
    ),
}


def _binding_configured(binding: Any) -> bool:
    if binding is None:
        return False
    sources = getattr(binding, "sources", None)
    if sources:
        return True
    if getattr(binding, "api_uuid", None) or getattr(binding, "dataset_uuid", None):
        return True
    return False


def _inbound_sync_service(module_leaf: str, class_name: str) -> Any:
    """入站同步服务解析：优先 kuaiconnect 单一真源，兼容既有 master_data/kuaizhizao 模块。"""
    import importlib

    for pkg in (
        "apps.kuaiconnect.services.inbound_sync",
        "apps.master_data.services",
        "apps.kuaizhizao.services",
    ):
        try:
            mod = importlib.import_module(f"{pkg}.{module_leaf}")
        except ImportError:
            continue
        return getattr(mod, class_name)()
    raise ImportError(module_leaf)


def _remediation_for_blocker(record: Dict[str, Any]) -> List[KingdeeConsistencyRemediation]:
    reason = str(record.get("reason") or "")
    source_type = str(record.get("source_type") or "")
    source_id = int(record.get("source_id") or 0)
    out: List[KingdeeConsistencyRemediation] = []
    if "尚未关联金蝶单" in reason:
        out.append(
            KingdeeConsistencyRemediation(
                action="document_push",
                method="POST",
                path="/api/v1/apps/kuaizhizao/document-push",
                body={
                    "source_type": source_type,
                    "source_id": source_id,
                    "target_profile": "*",
                },
                note="列表外推或单据详情外推；与 PC SyncPushHub 同一接口",
            )
        )
    elif "金蝶撤回失败" in reason:
        tpl = _WITHDRAW_PATH_BY_SOURCE.get(source_type)
        if tpl:
            out.append(
                KingdeeConsistencyRemediation(
                    action="retry_withdraw",
                    method="POST",
                    path=tpl.format(source_id=source_id),
                    note="重试撤回至金蝶成功后再做即时库存全量入站",
                )
            )
    elif "金蝶最近一次撤回已成功" in reason or "金蝶仍保留已推送单据" in reason:
        out.append(
            KingdeeConsistencyRemediation(
                action="align_document_state",
                method="POST",
                path="/api/v1/apps/kuaizhizao/document-push",
                body={
                    "source_type": source_type,
                    "source_id": source_id,
                    "target_profile": "*",
                },
                note="对齐本地过账/撤回与金蝶单据：补推、反过账或金蝶侧删单后清关联",
            )
        )
    return out


class KingdeeConsistencyOrchestrator:
    """强一致唯一路径：与 PC/API 相同的入站与外推服务。"""

    @classmethod
    async def audit(cls, tenant_id: int) -> KingdeeConsistencyAuditOut:
        from apps.kuaiconnect.services.document_push.warehouse_kingdee_alignment import (
            list_inventory_pull_blocker_records,
        )

        records = await list_inventory_pull_blocker_records(tenant_id)
        blockers = [
            KingdeeConsistencyBlocker(
                reason=str(r.get("reason") or ""),
                label=str(r.get("label") or ""),
                code=str(r.get("code") or ""),
                source_type=str(r.get("source_type") or ""),
                source_id=int(r.get("source_id") or 0),
                remediation=_remediation_for_blocker(r),
            )
            for r in records
        ]
        dup = await cls._audit_duplicate_warehouses(tenant_id)
        empty = await cls._audit_empty_location_batches(tenant_id)
        notes = [
            "空仓位批次勿 SQL 改库：清零红灯后执行 POST /reports/inventory/sync-from-source 全量入站",
            "仓库同名多编码：POST 主数据仓库 sync-from-source 后由数据 steward 合并/停用",
            "金额/状态：业财对账 + document-push 历史；本审计不猜金额",
        ]
        return KingdeeConsistencyAuditOut(
            inventory_pull_blockers=blockers,
            duplicate_warehouse_names=dup,
            empty_location_batches=empty,
            inventory_sync_allowed=len(blockers) == 0,
            notes=notes,
        )

    @classmethod
    async def _audit_duplicate_warehouses(cls, tenant_id: int) -> List[KingdeeConsistencyDuplicateWarehouse]:
        from apps.master_data.models.warehouse import Warehouse

        rows = await Warehouse.filter(tenant_id=tenant_id, deleted_at__isnull=True).values(
            "id", "code", "name"
        )
        by_name: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            name = str(row.get("name") or "").strip()
            if name:
                by_name[name].append(row)
        out: List[KingdeeConsistencyDuplicateWarehouse] = []
        for name, items in sorted(by_name.items()):
            codes = sorted({str(i.get("code") or "") for i in items if str(i.get("code") or "").strip()})
            if len(codes) > 1:
                out.append(
                    KingdeeConsistencyDuplicateWarehouse(
                        name=name,
                        codes=codes,
                        warehouse_ids=[int(i["id"]) for i in items],
                    )
                )
        return out

    @classmethod
    async def _audit_empty_location_batches(
        cls, tenant_id: int
    ) -> List[KingdeeConsistencyEmptyLocationBatch]:
        from apps.master_data.models.material_batch import MaterialBatch
        from apps.master_data.models.warehouse import Warehouse
        from apps.master_data.services.warehouse_service import WarehouseService

        batches = await MaterialBatch.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            quantity__gt=0,
        ).values("material_id", "warehouse_id", "location_code", "batch_no", "quantity")
        wh_ids = {int(b["warehouse_id"]) for b in batches if b.get("warehouse_id")}
        wh_map = {
            int(w.id): str(w.code or "")
            for w in await Warehouse.filter(tenant_id=tenant_id, id__in=list(wh_ids)).all()
        }
        out: List[KingdeeConsistencyEmptyLocationBatch] = []
        default_cache: Dict[int, Tuple[int | None, str | None]] = {}
        for b in batches:
            loc = str(b.get("location_code") or "").strip()
            if loc:
                continue
            wh_id = int(b.get("warehouse_id") or 0)
            if wh_id <= 0:
                continue
            if wh_id not in default_cache:
                default_cache[wh_id] = await WarehouseService.resolve_kingdee_default_storage_location(
                    tenant_id, wh_id
                )
            _def_id, def_code = default_cache[wh_id]
            if not def_code:
                continue
            if Decimal(str(b.get("quantity") or 0)) <= 0:
                continue
            out.append(
                KingdeeConsistencyEmptyLocationBatch(
                    material_id=int(b.get("material_id") or 0),
                    warehouse_code=wh_map.get(wh_id, ""),
                    quantity=str(b.get("quantity")),
                    batch_no=b.get("batch_no"),
                    expected_location_code=str(def_code),
                )
            )
        return out

    @classmethod
    async def _resolve_actor(cls, tenant_id: int, binding: Any) -> Optional[User]:
        for attr in ("updated_by", "created_by"):
            uid = getattr(binding, attr, None)
            if uid:
                user = await User.filter(id=uid, tenant_id=tenant_id, deleted_at__isnull=True).first()
                if user:
                    return user
        return await User.filter(tenant_id=tenant_id, is_active=True, deleted_at__isnull=True).order_by("id").first()

    @classmethod
    def _load_binding_model(cls, class_name: str) -> Optional[Type[Any]]:
        from apps.master_data.models import master_data_sync_binding as m

        return getattr(m, class_name, None)

    @classmethod
    async def run_master_data_chain(
        cls,
        tenant_id: int,
        actor: User,
        *,
        incremental: bool = False,
        skip_unconfigured_bindings: bool = True,
    ) -> KingdeeConsistencyMasterDataOut:
        from apps.master_data.api._sync_from_source_run_log import master_data_sync_from_source_with_run_log

        steps: List[KingdeeConsistencyMasterDataStepOut] = []
        for (
            entity_type,
            module_leaf,
            class_name,
            binding_class_name,
            require_user,
            skip_prerequisite,
        ) in _MASTER_DATA_CHAIN:
            binding_model = cls._load_binding_model(binding_class_name)
            if binding_model is None:
                steps.append(
                    KingdeeConsistencyMasterDataStepOut(
                        entity_type=entity_type,
                        status="skipped",
                        detail="本地未提供该入站域（主数据同步服务未部署）",
                    )
                )
                continue
            binding = await binding_model.filter(tenant_id=tenant_id).first()
            if not _binding_configured(binding):
                if skip_unconfigured_bindings:
                    steps.append(
                        KingdeeConsistencyMasterDataStepOut(
                            entity_type=entity_type,
                            status="skipped",
                            detail="无入站绑定或未配置数据源",
                        )
                    )
                    continue
                raise ValidationError(f"{entity_type} 未配置入站绑定")
            user = actor
            if require_user:
                resolved = await cls._resolve_actor(tenant_id, binding)
                if resolved is None:
                    steps.append(
                        KingdeeConsistencyMasterDataStepOut(
                            entity_type=entity_type,
                            status="error",
                            detail="无法解析执行用户（绑定无 updated_by 且租户无活跃用户）",
                        )
                    )
                    continue
                user = resolved
            request = MasterDataSyncFromSourceRequest(
                incremental=incremental,
                skip_prerequisite_syncs=skip_prerequisite,
            )
            try:
                service = _inbound_sync_service(module_leaf, class_name)
            except (ImportError, AttributeError):
                steps.append(
                    KingdeeConsistencyMasterDataStepOut(
                        entity_type=entity_type,
                        status="skipped",
                        detail="本地未提供该入站域（主数据同步服务未部署）",
                    )
                )
                continue

            async def _run(
                svc=service,
                req=request,
                u=user,
                sk=skip_prerequisite,
            ) -> Any:
                if sk:
                    return await svc.sync_from_source(tenant_id, u, req, skip_prerequisite_syncs=True)
                return await svc.sync_from_source(tenant_id, u, req)

            try:
                result = await master_data_sync_from_source_with_run_log(
                    tenant_id=tenant_id,
                    entity_type=entity_type,
                    binding_model=binding_model,
                    run_sync=_run,
                )
                steps.append(
                    KingdeeConsistencyMasterDataStepOut(
                        entity_type=entity_type,
                        status="ok",
                        result=result.model_dump() if hasattr(result, "model_dump") else dict(result),
                    )
                )
            except (ValidationError, BusinessLogicError) as e:
                steps.append(
                    KingdeeConsistencyMasterDataStepOut(
                        entity_type=entity_type,
                        status="error",
                        detail=str(e),
                    )
                )
        return KingdeeConsistencyMasterDataOut(steps=steps)

    @classmethod
    async def run_inventory_sync(
        cls,
        tenant_id: int,
        actor: User,
        *,
        incremental: bool = False,
        active_only: bool = True,
    ) -> KingdeeConsistencyInventoryOut:
        from apps.kuaiconnect.services.document_push.warehouse_kingdee_alignment import (
            list_inventory_pull_blockers,
        )
        from apps.kuaizhizao.api._inbound_sync_run_log import kuaizhizao_sync_from_source_with_run_log
        from apps.kuaizhizao.models.inventory_sync_binding import InventorySyncBinding

        blockers = await list_inventory_pull_blockers(tenant_id)
        if blockers:
            preview = "；".join(blockers[:5])
            if len(blockers) > 5:
                preview += f" 等共 {len(blockers)} 条"
            return KingdeeConsistencyInventoryOut(
                skipped=True,
                reason=f"仓储单据与金蝶未对齐：{preview}",
            )

        body = InventorySyncFromSourceRequest(incremental=incremental, active_only=active_only)
        svc = _inbound_sync_service("inventory_sync_service", "InventorySyncService")

        async def _run() -> Any:
            return await svc.sync_from_source(tenant_id, actor, body)

        result = await kuaizhizao_sync_from_source_with_run_log(
            tenant_id=tenant_id,
            entity_type="inventory",
            binding_model=InventorySyncBinding,
            run_sync=_run,
        )
        payload = result.model_dump() if hasattr(result, "model_dump") else dict(result)
        return KingdeeConsistencyInventoryOut(skipped=False, result=payload)
