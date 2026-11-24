/**
 * 电汇+银行承兑组合付款方式比例录入（客户主数据内联）
 */
import React from 'react';
import { Col, Row } from 'antd';
import { ProFormDigit, type ProFormInstance } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { isMixedPaymentMethodCode } from '../utils/paymentMethodMix';

export const PARTNER_MIXED_PAYMENT_METHOD = 'bank_transfer_and_acceptance';

type PaymentMethodFieldNames = {
  wire: string;
  acceptance: string;
};

const DEFAULT_FIELD_NAMES: PaymentMethodFieldNames = {
  wire: 'defaultPaymentWirePercent',
  acceptance: 'defaultPaymentAcceptancePercent',
};

type Props = {
  paymentMethodCode?: string | null;
  fieldNames?: PaymentMethodFieldNames;
};

export const MixedPaymentMethodRatioFields: React.FC<Props> = ({
  paymentMethodCode,
  fieldNames = DEFAULT_FIELD_NAMES,
}) => {
  const { t } = useTranslation();
  if (!isMixedPaymentMethodCode(paymentMethodCode)) {
    return null;
  }
  return (
    <Col span={24}>
      <Row gutter={16}>
        <Col span={12}>
          <ProFormDigit
            name={fieldNames.wire}
            label={t('field.partner.paymentMix.wirePercent')}
            min={0}
            max={100}
            fieldProps={{ precision: 2, addonAfter: '%', style: { width: '100%' } }}
            rules={[{ required: true, message: t('field.partner.paymentMix.wireRequired') }]}
          />
        </Col>
        <Col span={12}>
          <ProFormDigit
            name={fieldNames.acceptance}
            label={t('field.partner.paymentMix.acceptancePercent')}
            min={0}
            max={100}
            fieldProps={{ precision: 2, addonAfter: '%', style: { width: '100%' } }}
            rules={[{ required: true, message: t('field.partner.paymentMix.acceptanceRequired') }]}
          />
        </Col>
      </Row>
    </Col>
  );
};