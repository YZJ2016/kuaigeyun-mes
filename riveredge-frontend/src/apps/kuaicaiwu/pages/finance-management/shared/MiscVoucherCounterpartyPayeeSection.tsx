import React from 'react';
import { ProFormDependency } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { PartnerSupplierPayeeFormFields } from './PartnerSupplierPayeeFormFields';
import { hidesSupplierPayeeAccount } from '../../../utils/financeSharedOptions';

const PAYMENT_I18N = 'app.kuaicaiwu.payment';

/** 其他费用支出/申请：供应商或职员往来时带出收款账户（报销打款） */
export function MiscVoucherCounterpartyPayeeSection({ required = false }: { required?: boolean }) {
  const { t } = useTranslation();
  return (
    <ProFormDependency name={['counterparty_kind', 'payment_method', 'employee_advance_enabled']}>
      {({ counterparty_kind: cpKind, payment_method: method, employee_advance_enabled: advanceOn }) => {
        const kind = String(cpKind ?? '').trim();
        if (!['supplier', 'employee'].includes(kind)) {
          return null;
        }
        if (advanceOn || hidesSupplierPayeeAccount(method)) {
          return null;
        }
        const needLabel =
          kind === 'employee'
            ? t(`${PAYMENT_I18N}.counterpartyAccountNeedEmployee`)
            : t(`${PAYMENT_I18N}.counterpartyAccountNeedSupplier`);
        return (
          <PartnerSupplierPayeeFormFields
            required={required}
            supplierFieldName="counterparty_id"
            counterpartyKindFieldName="counterparty_kind"
            allowedCounterpartyKinds={['supplier', 'employee']}
            accountNameField="counterparty_account_name"
            bankNameField="counterparty_bank_name"
            bankAccountField="counterparty_bank_account"
            labelAccountPick={t(`${PAYMENT_I18N}.counterpartyAccountPick`)}
            labelAccountPickPlaceholder={t(`${PAYMENT_I18N}.counterpartyAccountPickPlaceholder`)}
            labelAccountEmpty={t(`${PAYMENT_I18N}.counterpartyAccountEmpty`)}
            labelAccountNeedSupplier={needLabel}
            labelAccountDefaultMark={t(`${PAYMENT_I18N}.counterpartyAccountDefaultMark`)}
            labelAccountName={t(`${PAYMENT_I18N}.counterpartyAccountName`)}
            labelBankName={t(`${PAYMENT_I18N}.counterpartyBankName`)}
            labelBankAccount={t(`${PAYMENT_I18N}.counterpartyBankAccount`)}
          />
        );
      }}
    </ProFormDependency>
  );
}
