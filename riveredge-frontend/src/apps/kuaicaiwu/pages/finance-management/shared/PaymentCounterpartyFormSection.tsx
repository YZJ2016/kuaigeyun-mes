import React from 'react';
import { Col, Row } from 'antd';
import { ProFormDependency, ProFormText } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { hidesSupplierPayeeAccount } from '../../../utils/financeSharedOptions';

const P = 'app.kuaicaiwu.payment';

/** 付款单对方收款账户（扁平三列；预付抵扣/员工垫付不展示） */
export function PaymentCounterpartyFormSection() {
  const { t } = useTranslation();
  return (
    <ProFormDependency name={['payment_method']}>
      {({ payment_method: method }) => {
        if (hidesSupplierPayeeAccount(method)) {
          return null;
        }
        return (
          <Row gutter={16}>
            <Col span={8}>
              <ProFormText name="counterparty_account_name" label={t(`${P}.counterpartyAccountName`)} />
            </Col>
            <Col span={8}>
              <ProFormText name="counterparty_bank_name" label={t(`${P}.counterpartyBankName`)} />
            </Col>
            <Col span={8}>
              <ProFormText
                name="counterparty_bank_account"
                label={t(`${P}.counterpartyBankAccount`)}
              />
            </Col>
          </Row>
        );
      }}
    </ProFormDependency>
  );
}
