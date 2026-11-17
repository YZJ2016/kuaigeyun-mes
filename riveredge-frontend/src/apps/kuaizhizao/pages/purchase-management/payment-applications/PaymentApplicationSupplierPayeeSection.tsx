import React from 'react';
import { ProFormDependency } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { PartnerSupplierPayeeFormFields } from '../../../../kuaicaiwu/pages/finance-management/shared/PartnerSupplierPayeeFormFields';
import { hidesSupplierPayeeAccount } from '../../../../kuaicaiwu/utils/financeSharedOptions';

const PAYMENT_I18N = 'app.kuaicaiwu.payment';
const APP_I18N = 'app.kuaizhizao.paymentApplication';

/** 付款申请供应商收款账户（与付款单同一主数据口径） */
export function PaymentApplicationSupplierPayeeSection() {
  const { t } = useTranslation();
  return (
    <ProFormDependency name={['paymentMethod']}>
      {({ paymentMethod: method }) => {
        if (hidesSupplierPayeeAccount(method)) {
          return null;
        }
        return (
          <PartnerSupplierPayeeFormFields
            supplierFieldName="supplierId"
            accountNameField="supplierAccountName"
            bankNameField="supplierBankName"
            bankAccountField="supplierBankAccount"
            labelAccountPick={t(`${PAYMENT_I18N}.counterpartyAccountPick`)}
            labelAccountPickPlaceholder={t(`${PAYMENT_I18N}.counterpartyAccountPickPlaceholder`)}
            labelAccountEmpty={t(`${PAYMENT_I18N}.counterpartyAccountEmpty`)}
            labelAccountNeedSupplier={t(`${PAYMENT_I18N}.counterpartyAccountNeedSupplier`)}
            labelAccountDefaultMark={t(`${PAYMENT_I18N}.counterpartyAccountDefaultMark`)}
            labelAccountName={t(`${APP_I18N}.supplierAccountName`)}
            labelBankName={t(`${APP_I18N}.supplierBankName`)}
            labelBankAccount={t(`${APP_I18N}.supplierBankAccount`)}
          />
        );
      }}
    </ProFormDependency>
  );
}
