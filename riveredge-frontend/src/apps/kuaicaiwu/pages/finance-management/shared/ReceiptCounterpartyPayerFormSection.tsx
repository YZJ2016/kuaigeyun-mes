import React from 'react';
import { ProFormDependency } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { hidesSupplierPayeeAccount } from '../../../utils/financeSharedOptions';
import { PartnerSupplierPayeeFormFields } from './PartnerSupplierPayeeFormFields';

const R = 'app.kuaicaiwu.receipt';
const P = 'app.kuaicaiwu.payment';

/** 收款单对方付款账户（从客户收款账户带出；预付抵扣等不展示） */
export function ReceiptCounterpartyPayerFormSection() {
  const { t } = useTranslation();
  return (
    <ProFormDependency name={['payment_method']}>
      {({ payment_method: method }) => {
        if (hidesSupplierPayeeAccount(method)) {
          return null;
        }
        return (
          <PartnerSupplierPayeeFormFields
            partnerSide="customer"
            supplierFieldName="customer_id"
            accountNameField="counterparty_account_name"
            bankNameField="counterparty_bank_name"
            bankAccountField="counterparty_bank_account"
            labelAccountPick={t(`${R}.counterpartyAccountPick`)}
            labelAccountPickPlaceholder={t(`${R}.counterpartyAccountPickPlaceholder`)}
            labelAccountEmpty={t(`${R}.counterpartyAccountEmpty`)}
            labelAccountNeedSupplier={t(`${R}.counterpartyAccountNeedCustomer`)}
            labelAccountDefaultMark={t(`${P}.counterpartyAccountDefaultMark`)}
          />
        );
      }}
    </ProFormDependency>
  );
}