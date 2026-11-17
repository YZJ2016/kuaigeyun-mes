import React, { useEffect, useRef, useState } from 'react';
import { Col, Form, Row, Select } from 'antd';
import { ProFormText } from '@ant-design/pro-components';
import {
  loadEmployeePayeeAccountsById,
  loadSupplierPayeeAccountsById,
  partnerPayeeOptionLabel,
  pickDefaultPartnerPayeeAccount,
  samePartnerPayeeAccount,
  type PartnerPayeeAccount,
} from '../../../utils/partnerPayeeAccounts';

export type PartnerSupplierPayeeFormFieldsProps = {
  /** 往来对象 id（供应商/职员等） */
  supplierFieldName: string;
  counterpartyKindFieldName?: string;
  allowedCounterpartyKinds?: string[];
  accountNameField: string;
  bankNameField: string;
  bankAccountField: string;
  labelAccountPick: string;
  labelAccountPickPlaceholder: string;
  labelAccountEmpty: string;
  labelAccountNeedSupplier: string;
  labelAccountDefaultMark: string;
  labelAccountName: string;
  labelBankName: string;
  labelBankAccount: string;
};

export function PartnerSupplierPayeeFormFields({
  supplierFieldName,
  counterpartyKindFieldName,
  allowedCounterpartyKinds = ['supplier'],
  accountNameField,
  bankNameField,
  bankAccountField,
  labelAccountPick,
  labelAccountPickPlaceholder,
  labelAccountEmpty,
  labelAccountNeedSupplier,
  labelAccountDefaultMark,
  labelAccountName,
  labelBankName,
  labelBankAccount,
}: PartnerSupplierPayeeFormFieldsProps) {
  const form = Form.useFormInstance();
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
        : () => loadSupplierPayeeAccountsById(id);
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
    form,
    allowedCounterpartyKinds,
    counterpartyId,
    counterpartyKind,
    counterpartyKindFieldName,
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
  const showAccountPicker = accounts.length > 1;
  const placeholder = !supplierReady
    ? labelAccountNeedSupplier
    : loading
      ? labelAccountPickPlaceholder
      : !supplierFound || accounts.length === 0
        ? labelAccountEmpty
        : labelAccountPickPlaceholder;

  return (
    <Row gutter={16}>
      {showAccountPicker ? (
        <Col span={24}>
          <Form.Item label={labelAccountPick} style={{ marginBottom: 8 }}>
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              loading={loading}
              disabled={!supplierReady || loading}
              placeholder={placeholder}
              value={matchedIndex >= 0 ? matchedIndex : undefined}
              options={accounts.map((item, index) => ({
                value: index,
                label: partnerPayeeOptionLabel(item, labelAccountDefaultMark),
              }))}
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
        </Col>
      ) : null}
      <Col span={8}>
        <ProFormText name={accountNameField} label={labelAccountName} />
      </Col>
      <Col span={8}>
        <ProFormText name={bankNameField} label={labelBankName} />
      </Col>
      <Col span={8}>
        <ProFormText name={bankAccountField} label={labelBankAccount} />
      </Col>
    </Row>
  );
}
