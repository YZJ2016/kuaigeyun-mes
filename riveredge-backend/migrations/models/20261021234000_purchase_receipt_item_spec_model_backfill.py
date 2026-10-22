"""
采购入库明细：从物料档案回填空缺的规格/型号快照。
"""
from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE apps_kuaizhizao_purchase_receipt_items li
        SET material_spec = NULLIF(TRIM(m.specification), '')
        FROM apps_master_data_materials m
        WHERE m.id = li.material_id
          AND (li.material_spec IS NULL OR TRIM(li.material_spec) = '');

        UPDATE apps_kuaizhizao_purchase_receipt_items li
        SET material_model = NULLIF(TRIM(m.model), '')
        FROM apps_master_data_materials m
        WHERE m.id = li.material_id
          AND (li.material_model IS NULL OR TRIM(li.material_model) = '');

        UPDATE apps_kuaizhizao_purchase_receipt_items li
        SET
            partner_material_code = a.code,
            partner_material_name = a.name
        FROM apps_kuaizhizao_purchase_receipts pr,
             apps_master_data_material_code_aliases a
        WHERE pr.id = li.receipt_id
          AND a.tenant_id = li.tenant_id
          AND a.material_id = li.material_id
          AND a.code_type = 'SUPPLIER'
          AND a.external_entity_type = 'supplier'
          AND a.external_entity_id = pr.supplier_id
          AND a.deleted_at IS NULL
          AND li.partner_material_code IS NULL;
        """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- 回填不可逆；降级不清理已写入快照
        SELECT 1;
        """
