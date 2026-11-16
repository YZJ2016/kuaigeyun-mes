import React, { useMemo } from 'react';
import { ProFormDependency, ProFormSelect } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { financeColHalf } from '../../../utils/financeFormLayout';
import { EMPLOYEE_ADVANCE_PAYMENT_METHOD } from '../../../utils/financeSharedOptions';
import { loadUserFormReferenceOptions } from '../../../../../utils/documentFormReferenceLoad';

const P = 'app.kuaicaiwu.payment';

type PaymentAdvancePayeeFieldProps = {
  methodField?: string;
  payeeIdField?: string;
  /** 付款申请等 Row/Col 表单不传 colProps */
  colProps?: typeof financeColHalf | false;
};

/** 付款方式选「员工垫付」时必填领款人 */
export function PaymentAdvancePayeeField({
  methodField = 'payment_method',
  payeeIdField = 'advance_payee_id',
  colProps = financeColHalf,
}: PaymentAdvancePayeeFieldProps) {
  const { t } = useTranslation();
  const { data: userOptions = [] } = useQuery({
    queryKey: ['payment-advance-payee-users'],
    queryFn: () => loadUserFormReferenceOptions(),
    staleTime: 60_000,
  });
  const options = useMemo(
    () => userOptions.map((o) => ({ label: o.label, value: o.value })),
    [userOptions],
  );

  return (
    <ProFormDependency name={[methodField]} formItemProps={{ style: { marginBottom: 0 } }}>
      {(depValues) => {
        const method = depValues[methodField];
        if (method !== EMPLOYEE_ADVANCE_PAYMENT_METHOD) {
          return null;
        }
        return (
          <ProFormSelect
            name={payeeIdField}
            label={t(`${P}.advancePayee`)}
            options={options}
            rules={[{ required: true, message: t(`${P}.advancePayeeRequired`) }]}
            showSearch
            {...(colProps === false ? {} : { colProps: colProps || financeColHalf })}
          />
        );
      }}
    </ProFormDependency>
  );
}

export function resolveAdvancePayeeName(
  payeeId: unknown,
  userOptions: Array<{ label: string; value: number | string }>,
): string | undefined {
  if (payeeId == null || payeeId === '') {
    return undefined;
  }
  const label = userOptions.find((o) => o.value === payeeId)?.label;
  return label ? String(label).trim() : undefined;
}
