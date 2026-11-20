/** 客户同步字段白名单 + 苍穹客户查询别名（与销售订单同步别名独立） */

import type { SyncTargetField } from '../../../../../components/sync-from-source-modal/types';

export const CUSTOMER_SYNC_TARGET_FIELDS: SyncTargetField[] = [
  { value: 'code', labelKey: 'app.master-data.customers.syncField.code', required: true },
  { value: 'name', labelKey: 'app.master-data.customers.syncField.name', required: true },
  { value: 'short_name', labelKey: 'app.master-data.customers.syncField.shortName' },
  { value: 'contact_person', labelKey: 'app.master-data.customers.syncField.contactPerson' },
  { value: 'phone', labelKey: 'app.master-data.customers.syncField.phone' },
  { value: 'email', labelKey: 'app.master-data.customers.syncField.email' },
  { value: 'address', labelKey: 'app.master-data.customers.syncField.address' },
  { value: 'partner_type', labelKey: 'app.master-data.customers.syncField.partnerType' },
  { value: 'biz_function', labelKey: 'app.master-data.customers.syncField.bizFunction' },
];

export const CUSTOMER_SYNC_AVAILABLE_TARGET_FIELDS: SyncTargetField[] = [
  { value: 'category', labelKey: 'app.master-data.customers.syncField.category' },
  { value: 'contact_title', labelKey: 'app.master-data.customers.syncField.contactTitle' },
  { value: 'industry_code', labelKey: 'app.master-data.customers.syncField.industryCode' },
  { value: 'customer_level_code', labelKey: 'app.master-data.customers.syncField.customerLevelCode' },
  { value: 'estimated_annual_purchase', labelKey: 'app.master-data.customers.syncField.estimatedAnnualPurchase' },
  { value: 'lead_source_code', labelKey: 'app.master-data.customers.syncField.leadSourceCode' },
  { value: 'credit_limit', labelKey: 'app.master-data.customers.syncField.creditLimit' },
  { value: 'tax_registration_no', labelKey: 'app.master-data.customers.syncField.taxRegistrationNo' },
  { value: 'invoice_title', labelKey: 'app.master-data.customers.syncField.invoiceTitle' },
  { value: 'invoice_address', labelKey: 'app.master-data.customers.syncField.invoiceAddress' },
  { value: 'invoice_phone', labelKey: 'app.master-data.customers.syncField.invoicePhone' },
  { value: 'invoice_bank_name', labelKey: 'app.master-data.customers.syncField.invoiceBankName' },
  { value: 'invoice_bank_account', labelKey: 'app.master-data.customers.syncField.invoiceBankAccount' },
  { value: 'legal_representative', labelKey: 'app.master-data.customers.syncField.legalRepresentative' },
  { value: 'payment_terms_days', labelKey: 'app.master-data.customers.syncField.paymentTermsDays' },
  {
    value: 'default_payment_method_code',
    labelKey: 'app.master-data.customers.syncField.defaultPaymentMethodCode',
  },
  { value: 'settlement_terms_code', labelKey: 'app.master-data.customers.syncField.settlementTermsCode' },
  { value: 'finance_contact_name', labelKey: 'app.master-data.customers.syncField.financeContactName' },
  { value: 'finance_contact_phone', labelKey: 'app.master-data.customers.syncField.financeContactPhone' },
  { value: 'delivery_contact_name', labelKey: 'app.master-data.customers.syncField.deliveryContactName' },
  { value: 'delivery_contact_phone', labelKey: 'app.master-data.customers.syncField.deliveryContactPhone' },
  { value: 'delivery_address', labelKey: 'app.master-data.customers.syncField.deliveryAddress' },
  { value: 'salesman_name', labelKey: 'app.master-data.customers.syncField.salesmanName' },
  { value: 'is_active', labelKey: 'app.master-data.customers.syncField.isActive' },
];

/**
 * 苍穹客户查询 bd_customer/query（预置 query_customer）→ 本系统目标字段别名。
 * 真源：`docs/客户信息.md` 返回参数 + 示例 JSON。
 * 与销售订单同步别名互不共用；entry_linkman / entry_bank 为嵌套分录，预览不摊平，故邮箱/开户行等无表头列时不自动匹配。
 */
export const CUSTOMER_SYNC_TARGET_ALIASES: Record<string, string[]> = {
  code: ['number', 'FNumber'],
  name: ['name', 'FName'],
  short_name: ['simplename', 'FShortName'],
  contact_person: ['linkman'],
  phone: ['bizpartner_phone'],
  // 表头无邮箱字段；联系人分录 email 未摊平到预览列
  email: [],
  address: ['bizpartner_address'],
  partner_type: ['type'],
  biz_function: ['bizfunction'],
  category: ['group_number'],
  tax_registration_no: ['societycreditcode', 'taxno', 'tx_register_no'],
  legal_representative: ['artificialperson'],
  is_active: ['enable'],
  delivery_contact_name: ['linkman'],
  delivery_contact_phone: ['bizpartner_phone'],
  delivery_address: ['bizpartner_address'],
};

export const CUSTOMER_SYNC_REQUIRED_TARGETS = ['code', 'name'];
export const CUSTOMER_SYNC_CUSTOM_FIELD_TABLE = 'master_data_customers';
export const CUSTOMER_SYNC_MAPPING_EXPORT_FILENAME = 'customer-sync-field-mapping.json';
