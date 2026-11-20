/** 供应商同步字段白名单 + 苍穹供应商查询别名 */

import type { SyncTargetField } from '../../../../../components/sync-from-source-modal/types';

export const SUPPLIER_SYNC_TARGET_FIELDS: SyncTargetField[] = [
  { value: 'code', labelKey: 'app.master-data.suppliers.syncField.code', required: true },
  { value: 'name', labelKey: 'app.master-data.suppliers.syncField.name', required: true },
  { value: 'short_name', labelKey: 'app.master-data.suppliers.syncField.shortName' },
  { value: 'category', labelKey: 'app.master-data.suppliers.syncField.category' },
  { value: 'is_active', labelKey: 'app.master-data.suppliers.syncField.isActive' },
];

export const SUPPLIER_SYNC_AVAILABLE_TARGET_FIELDS: SyncTargetField[] = [
  { value: 'contact_person', labelKey: 'app.master-data.suppliers.syncField.contactPerson' },
  { value: 'phone', labelKey: 'app.master-data.suppliers.syncField.phone' },
  { value: 'email', labelKey: 'app.master-data.suppliers.syncField.email' },
  { value: 'address', labelKey: 'app.master-data.suppliers.syncField.address' },
  { value: 'contact_title', labelKey: 'app.master-data.suppliers.syncField.contactTitle' },
  { value: 'industry_code', labelKey: 'app.master-data.suppliers.syncField.industryCode' },
  { value: 'estimated_annual_purchase', labelKey: 'app.master-data.suppliers.syncField.estimatedAnnualPurchase' },
  { value: 'source_channel_code', labelKey: 'app.master-data.suppliers.syncField.sourceChannelCode' },
  { value: 'credit_limit', labelKey: 'app.master-data.suppliers.syncField.creditLimit' },
  { value: 'tax_registration_no', labelKey: 'app.master-data.suppliers.syncField.taxRegistrationNo' },
  { value: 'invoice_title', labelKey: 'app.master-data.suppliers.syncField.invoiceTitle' },
  { value: 'invoice_address', labelKey: 'app.master-data.suppliers.syncField.invoiceAddress' },
  { value: 'invoice_phone', labelKey: 'app.master-data.suppliers.syncField.invoicePhone' },
  { value: 'invoice_bank_name', labelKey: 'app.master-data.suppliers.syncField.invoiceBankName' },
  { value: 'invoice_bank_account', labelKey: 'app.master-data.suppliers.syncField.invoiceBankAccount' },
  { value: 'payment_account_name', labelKey: 'app.master-data.suppliers.syncField.paymentAccountName' },
  { value: 'payment_bank_name', labelKey: 'app.master-data.suppliers.syncField.paymentBankName' },
  { value: 'payment_bank_account', labelKey: 'app.master-data.suppliers.syncField.paymentBankAccount' },
  { value: 'legal_representative', labelKey: 'app.master-data.suppliers.syncField.legalRepresentative' },
  { value: 'payment_terms_days', labelKey: 'app.master-data.suppliers.syncField.paymentTermsDays' },
  {
    value: 'default_payment_method_code',
    labelKey: 'app.master-data.suppliers.syncField.defaultPaymentMethodCode',
  },
  { value: 'settlement_terms_code', labelKey: 'app.master-data.suppliers.syncField.settlementTermsCode' },
  { value: 'buyer_name', labelKey: 'app.master-data.suppliers.syncField.buyerName' },
];

/**
 * 苍穹供应商查询 bd_supplier/query（预置 query_supplier）→ 本系统目标字段别名。
 * 真源：`docs/供应商.md` 返回参数 + 示例 JSON。
 * 空数组 = 禁止自动匹配（文档无对应列，避免误绑）。
 * 注意：返回里的 status 是数据状态(A/B/C)，不是启用态；启用态用 enable。
 */
export const SUPPLIER_SYNC_TARGET_ALIASES: Record<string, string[]> = {
  code: ['number', 'FNumber'],
  name: ['name', 'FName'],
  // 供应商 query 无简称列（客户接口有 simplename）
  short_name: [],
  is_active: ['enable'],
  // 定制 pbdfl：group_number/group_name；标品 query 无分类列，勿用 supplier_status 冒充
  category: ['group_number', 'group_name', 'group.number', 'group.name'],
  // 伙伴类型 type：本系统无独立伙伴类型字段，不自动匹配到企业类型以免误写
};

export const SUPPLIER_SYNC_REQUIRED_TARGETS = ['code', 'name'];
export const SUPPLIER_SYNC_CUSTOM_FIELD_TABLE = 'master_data_suppliers';
export const SUPPLIER_SYNC_MAPPING_EXPORT_FILENAME = 'supplier-sync-field-mapping.json';

/** 拉取预览优先展示的源列（与 docs/供应商.md rows 字段一致） */
export const SUPPLIER_SYNC_PREVIEW_PREFERRED_SOURCE_KEYS = [
  'number',
  'name',
  'enable',
  'status',
  'id',
  'type',
  'group_number',
  'group_name',
  'group_longnumber',
  'supplier_status_number',
  'supplier_status_name',
  'createorg_number',
  'createtime',
  'modifytime',
  'masterid',
  'ctrlstrategy',
];
