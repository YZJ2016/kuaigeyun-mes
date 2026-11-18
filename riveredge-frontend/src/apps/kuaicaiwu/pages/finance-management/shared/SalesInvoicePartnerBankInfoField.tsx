import React, { useEffect, useRef, useState } from 'react';
import { Col, Form } from 'antd';
import { ProFormItem, ProFormText } from '@ant-design/pro-components';
import { financeColFull } from '../../../utils/financeFormLayout';
import { useTranslation } from 'react-i18next';
import { UniDropdown } from '../../../../../components/uni-dropdown';
import {
  loadCustomerPayeeAccountsById,
  partnerPayeeAccountDisplayText,
  partnerPayeeAccountFromBankInfoText,
  partnerPayeeOptionLabel,
  pickDefaultPartnerPayeeAccount,
  type PartnerPayeeAccount,
} from '../../../utils/partnerPayeeAccounts';

const P = 'app.kuaicaiwu.salesInvoice';

/** 销项发票购方开户行及账号：仅能从客户资料收款账户选择 */
export function SalesInvoicePartnerBankInfoField() {
  const { t } = useTranslation();
  const form = Form.useFormInstance();
  const customerId = Form.useWatch('customer_id', form);
  const partnerBankInfo = Form.useWatch('partner_bank_info', form);
  const [accounts, setAccounts] = useState<PartnerPayeeAccount[]>([]);
  const [customerFound, setCustomerFound] = useState(false);
  const [loading, setLoading] = useState(false);
  const prevCustomerId = useRef<number | null>(null);

  useEffect(() => {
    const id = Number(customerId);
    if (!Number.isFinite(id) || id <= 0) {
      setAccounts([]);
      setCustomerFound(false);
      prevCustomerId.current = null;
      return;
    }
    let cancelled = false;
    setLoading(true);
    loadCustomerPayeeAccountsById(id)
      .then(({ found, accounts: rows }) => {
        if (cancelled) return;
        setCustomerFound(found);
        setAccounts(rows);
        const changed = prevCustomerId.current != null && prevCustomerId.current !== id;
        prevCustomerId.current = id;
        const current = String(form.getFieldValue('partner_bank_info') || '').trim();
        if (!changed && current) return;
        const picked = pickDefaultPartnerPayeeAccount(rows);
        form.setFieldsValue({
          partner_bank_info: picked ? partnerPayeeAccountDisplayText(picked) : undefined,
        });
      })
      .catch(() => {
        if (!cancelled) {
          setCustomerFound(false);
          setAccounts([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [customerId, form]);

  const customerReady = Number.isFinite(Number(customerId)) && Number(customerId) > 0;
  const matchedIndex = partnerPayeeAccountFromBankInfoText(partnerBankInfo, accounts);
  const placeholder = !customerReady
    ? t(`${P}.partnerBankInfoNeedCustomer`)
    : loading
      ? t(`${P}.partnerBankInfoPlaceholder`)
      : !customerFound || accounts.length === 0
        ? t(`${P}.partnerBankInfoEmpty`)
        : t(`${P}.partnerBankInfoPlaceholder`);

  return (
    <>
      <ProFormText name="partner_bank_info" hidden />
      <Col {...financeColFull}>
        <ProFormItem label={t(`${P}.col.partnerBankInfo`)}>
          <UniDropdown
          allowClear
          showSearch
          optionFilterProp="label"
          loading={loading}
          disabled={!customerReady || loading || accounts.length === 0}
          placeholder={placeholder}
          value={matchedIndex}
          options={accounts.map((item, index) => ({
            value: index,
            label: partnerPayeeOptionLabel(item, t('app.kuaicaiwu.payment.counterpartyAccountDefaultMark')),
          }))}
          onChange={(value) => {
            if (value == null) {
              form.setFieldsValue({ partner_bank_info: undefined });
              return;
            }
            const picked = accounts[Number(value)];
            if (!picked) return;
            form.setFieldsValue({
              partner_bank_info: partnerPayeeAccountDisplayText(picked),
            });
          }}
        />
        </ProFormItem>
      </Col>
    </>
  );
}