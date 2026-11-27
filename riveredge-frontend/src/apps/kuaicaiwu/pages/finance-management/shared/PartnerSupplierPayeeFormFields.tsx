import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Form } from 'antd';
import { ProFormText } from '@ant-design/pro-components';
import { UniDropdown } from '../../../../../components/uni-dropdown';
import {
  loadCustomerPayeeAccountsById,
  loadEmployeePayeeAccountsById,
  loadSupplierPayeeAccountsById,
  partnerPayeeOptionLabel,
  pickDefaultPartnerPayeeAccount,
  samePartnerPayeeAccount,
  type PartnerPayeeAccount,
} from '../../../utils/partnerPayeeAccounts';

export type PartnerSupplierPayeeFormFieldsProps = {
  /** 往来对象 id（供应商/客户/职员等） */
  supplierFieldName: string;
  partnerSide?: 'supplier' | 'customer';
  counterpartyKindFieldName?: string;
  allowedCounterpartyKinds?: readonly string[];
  accountNameField: string;
  bankNameField: string;
  bankAccountField: string;
  labelAccountPick: string;
  labelAccountPickPlaceholder: string;
  labelAccountEmpty: string;
  labelAccountNeedSupplier: string;
  labelAccountDefaultMark: string;
  /** @deprecated 合并为单一收款账户栏，保留入参以兼容调用方 */
  labelAccountName?: string;
  labelBankName?: string;
  labelBankAccount?: string;
  /** 宿主 resource，用于按 id 解析供应商 uuid 并拉收款账户 */
  hostResource?: string;
  required?: boolean;
};

const DEFAULT_ALLOWED_COUNTERPARTY_KINDS: readonly string[] = ['supplier'];

const DEFAULT_PAYEE_HOST_RESOURCE = 'kuaicaiwu:payment';

export function PartnerSupplierPayeeFormFields({
  supplierFieldName,
  partnerSide = 'supplier',
  counterpartyKindFieldName,
  allowedCounterpartyKinds = DEFAULT_ALLOWED_COUNTERPARTY_KINDS,
  accountNameField,
  bankNameField,
  bankAccountField,
  labelAccountPick,
  labelAccountPickPlaceholder,
  labelAccountEmpty,
  labelAccountNeedSupplier,
  labelAccountDefaultMark,
  hostResource = DEFAULT_PAYEE_HOST_RESOURCE,
  required = false,
}: PartnerSupplierPayeeFormFieldsProps) {
  const form = Form.useFormInstance();
  const allowedKindsKey = useMemo(
    () => allowedCounterpartyKinds.join('\0'),
    [allowedCounterpartyKinds],
  );
  const counterpartyId = Form.useWatch(supplierFieldName, form);
  const counterpartyKind = counterpartyKindFieldName
    ? Form.useWatch(counterpartyKindFieldName, form)
    : 'supplier';
  const accountName = Form.useWatch(accountNameField, form);
  const bankName = Form.useWatch(bankNameField, form);
  const bankAccount = Form.useWatch(bankAccountField, form);
  const [accounts, setAccounts] = useState<PartnerPayeeAccount[]>([]);
  const [supplierFound, setSupplierFound] = useState(false);
  const [loading, setLoading] = useState(false);
  const prevCounterpartyKey = useRef<string | null>(null);

  useEffect(() => {
    const kind = String(counterpartyKind ?? '').trim() || 'supplier';
    const activeKind = counterpartyKindFieldName
      ? allowedCounterpartyKinds.includes(kind)
        ? kind
        : ''
      : 'supplier';
    const id = Number(counterpartyId);
    if (!activeKind || !Number.isFinite(id) || id <= 0) {
      setAccounts([]);
      setSupplierFound(false);
      prevCounterpartyKey.current = null;
      return;
    }
    let cancelled = false;
    setLoading(true);
    const loadAccounts =
      activeKind === 'employee'
        ? () => loadEmployeePayeeAccountsById(id)
        : partnerSide === 'customer'
          ? () => loadCustomerPayeeAccountsById(id)
          : () => loadSupplierPayeeAccountsById(id, hostResource);
    loadAccounts()
      .then(({ found, accounts: rows }) => {
        if (cancelled) return;
        setSupplierFound(found);
        setAccounts(rows);
        const currentName = String(form.getFieldValue(accountNameField) || '').trim();
        const currentBank = String(form.getFieldValue(bankNameField) || '').trim();
        const currentAcct = String(form.getFieldValue(bankAccountField) || '').trim();
        const counterpartyKey = `${activeKind}:${id}`;
        const counterpartyChanged =
          prevCounterpartyKey.current != null && prevCounterpartyKey.current !== counterpartyKey;
        prevCounterpartyKey.current = counterpartyKey;
        const shouldFill = counterpartyChanged || (!currentName && !currentBank && !currentAcct);
        if (!shouldFill) return;
        const picked = pickDefaultPartnerPayeeAccount(rows);
        if (picked) {
          form.setFieldsValue({
            [accountNameField]: picked.accountName || undefined,
            [bankNameField]: picked.bankName || undefined,
            [bankAccountField]: picked.bankAccount || undefined,
          });
          return;
        }
        if (counterpartyChanged) {
          form.setFieldsValue({
            [accountNameField]: undefined,
            [bankNameField]: undefined,
            [bankAccountField]: undefined,
          });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSupplierFound(false);
          setAccounts([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    accountNameField,
    bankAccountField,
    bankNameField,
    allowedKindsKey,
    counterpartyId,
    counterpartyKind,
    counterpartyKindFieldName,
    hostResource,
    partnerSide,
    supplierFieldName,
  ]);

  const kind = String(counterpartyKind ?? '').trim() || 'supplier';
  const activeKind = counterpartyKindFieldName
    ? allowedCounterpartyKinds.includes(kind)
      ? kind
      : ''
    : 'supplier';
  const supplierReady =
    Boolean(activeKind) && Number.isFinite(Number(counterpartyId)) && Number(counterpartyId) > 0;
  const matchedIndex = accounts.findIndex((item) =>
    samePartnerPayeeAccount(item, accountName, bankName, bankAccount),
  );
  const placeholder = !supplierReady
    ? labelAccountNeedSupplier
    : loading
      ? labelAccountPickPlaceholder
      : !supplierFound || accounts.length === 0
        ? labelAccountEmpty
        : labelAccountPickPlaceholder;

  const selectOptions = accounts.map((item, index) => ({
    value: index,
    label: partnerPayeeOptionLabel(item, labelAccountDefaultMark),
  }));

  return (
    <>
      <ProFormText name={accountNameField} hidden />
      <ProFormText name={bankNameField} hidden />
      <Form.Item
        name={bankAccountField}
        label={labelAccountPick}
        required={required}
        getValueProps={() => ({ value: matchedIndex >= 0 ? matchedIndex : undefined })}
        getValueFromEvent={(value) =>
          value == null ? undefined : accounts[Number(value)]?.bankAccount || undefined
        }
        rules={required ? [{
          validator: async () => {
            if (![accountNameField, bankNameField, bankAccountField].every(
              (field) => String(form.getFieldValue(field) ?? '').trim(),
            )) {
              throw new Error(labelAccountPickPlaceholder);
            }
          },
        }] : undefined}
      >
        <UniDropdown
          allowClear
          showSearch
          optionFilterProp="label"
          loading={loading}
          disabled={!supplierReady || loading || accounts.length === 0}
          placeholder={placeholder}
          value={matchedIndex >= 0 ? matchedIndex : undefined}
          options={selectOptions}
          onChange={(value) => {
            if (value == null) {
              form.setFieldsValue({
                [accountNameField]: undefined,
                [bankNameField]: undefined,
                [bankAccountField]: undefined,
              });
              return;
            }
            const picked = accounts[Number(value)];
            if (!picked) return;
            form.setFieldsValue({
              [accountNameField]: picked.accountName || undefined,
              [bankNameField]: picked.bankName || undefined,
              [bankAccountField]: picked.bankAccount || undefined,
            });
          }}
        />
      </Form.Item>
    </>
  );
}
