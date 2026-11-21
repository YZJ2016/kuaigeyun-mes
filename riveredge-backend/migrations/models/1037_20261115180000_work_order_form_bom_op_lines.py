"""
工单表单：头字段、子件明细表、工序工价/作业要求。
"""
from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE apps_kuaizhizao_work_orders
            ADD COLUMN IF NOT EXISTS warehouse_id INT NULL,
            ADD COLUMN IF NOT EXISTS warehouse_name VARCHAR(200) NULL,
            ADD COLUMN IF NOT EXISTS manufacturing_department_id INT NULL,
            ADD COLUMN IF NOT EXISTS manufacturing_department_name VARCHAR(200) NULL,
            ADD COLUMN IF NOT EXISTS customer_id INT NULL,
            ADD COLUMN IF NOT EXISTS customer_name VARCHAR(200) NULL,
            ADD COLUMN IF NOT EXISTS customer_order_no VARCHAR(100) NULL,
            ADD COLUMN IF NOT EXISTS required_date TIMESTAMPTZ NULL;

        COMMENT ON COLUMN apps_kuaizhizao_work_orders.warehouse_id IS '成品/领料默认仓库';
        COMMENT ON COLUMN apps_kuaizhizao_work_orders.manufacturing_department_id IS '生产部门';
        COMMENT ON COLUMN apps_kuaizhizao_work_orders.customer_id IS '客户';
        COMMENT ON COLUMN apps_kuaizhizao_work_orders.customer_order_no IS '客户订单号';
        COMMENT ON COLUMN apps_kuaizhizao_work_orders.required_date IS '需求日';

        ALTER TABLE apps_kuaizhizao_work_order_operations
            ADD COLUMN IF NOT EXISTS piece_rate DECIMAL(14,4) NULL,
            ADD COLUMN IF NOT EXISTS work_requirement TEXT NULL;

        COMMENT ON COLUMN apps_kuaizhizao_work_order_operations.piece_rate IS '工价';
        COMMENT ON COLUMN apps_kuaizhizao_work_order_operations.work_requirement IS '作业要求';

        CREATE TABLE IF NOT EXISTS apps_kuaizhizao_work_order_bom_lines (
            id SERIAL PRIMARY KEY,
            tenant_id INT NOT NULL,
            uuid UUID NOT NULL,
            work_order_id INT NOT NULL,
            sequence INT NOT NULL DEFAULT 1,
            material_id INT NOT NULL,
            material_code VARCHAR(50) NOT NULL,
            material_name VARCHAR(200) NOT NULL,
            material_spec VARCHAR(500) NULL,
            warehouse_id INT NULL,
            warehouse_name VARCHAR(200) NULL,
            unit VARCHAR(50) NULL,
            required_quantity DECIMAL(14,4) NOT NULL DEFAULT 0,
            batch_no VARCHAR(100) NULL,
            bom_version VARCHAR(20) NULL,
            line_remarks TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_by INT NULL,
            created_by_name VARCHAR(100) NULL,
            updated_by INT NULL,
            updated_by_name VARCHAR(100) NULL,
            deleted_at TIMESTAMPTZ NULL
        );

        CREATE INDEX IF NOT EXISTS idx_wo_bom_lines_tenant_wo
            ON apps_kuaizhizao_work_order_bom_lines (tenant_id, work_order_id);
        CREATE INDEX IF NOT EXISTS idx_wo_bom_lines_tenant_material
            ON apps_kuaizhizao_work_order_bom_lines (tenant_id, material_id);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS apps_kuaizhizao_work_order_bom_lines;

        ALTER TABLE apps_kuaizhizao_work_order_operations
            DROP COLUMN IF EXISTS work_requirement,
            DROP COLUMN IF EXISTS piece_rate;

        ALTER TABLE apps_kuaizhizao_work_orders
            DROP COLUMN IF EXISTS required_date,
            DROP COLUMN IF EXISTS customer_order_no,
            DROP COLUMN IF EXISTS customer_name,
            DROP COLUMN IF EXISTS customer_id,
            DROP COLUMN IF EXISTS manufacturing_department_name,
            DROP COLUMN IF EXISTS manufacturing_department_id,
            DROP COLUMN IF EXISTS warehouse_name,
            DROP COLUMN IF EXISTS warehouse_id;
    """