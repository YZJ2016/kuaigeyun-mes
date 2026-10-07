"""员工档案入职附件：身份证、劳动合同、体检报告、学历证书、残疾证。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaioa_employee_profiles"
            ADD COLUMN IF NOT EXISTS "id_card_file_uuid" VARCHAR(36),
            ADD COLUMN IF NOT EXISTS "labor_contract_file_uuid" VARCHAR(36),
            ADD COLUMN IF NOT EXISTS "medical_report_file_uuid" VARCHAR(36),
            ADD COLUMN IF NOT EXISTS "education_cert_file_uuid" VARCHAR(36),
            ADD COLUMN IF NOT EXISTS "disability_cert_file_uuid" VARCHAR(36);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaioa_employee_profiles"
            DROP COLUMN IF EXISTS "disability_cert_file_uuid",
            DROP COLUMN IF EXISTS "education_cert_file_uuid",
            DROP COLUMN IF EXISTS "medical_report_file_uuid",
            DROP COLUMN IF EXISTS "labor_contract_file_uuid",
            DROP COLUMN IF EXISTS "id_card_file_uuid";
    """
