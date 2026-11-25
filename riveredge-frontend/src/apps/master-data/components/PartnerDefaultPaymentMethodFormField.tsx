/**
 * 客商主数据默认付款方式：与采购订单同款标签 / extra / 组合比例弹窗（不含员工垫付）
 */
import React, { useMemo } from 'react';
import { Col } from 'antd';
import type { ProFormInstance } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { PaymentMethodWithMixFormItems } from '../../kuaizhizao/components/PaymentMethodWithMixFormItems';
import { partnerPaymentMethodSelectOptions } from '../utils/partner-static-labels';

type Props = {
  formRef: React.MutableRefObject<ProFormInstance | undefined>;
};

export const PartnerDefaultPaymentMethodFormField: React.FC<Props> = ({ formRef }) => {
  const { t } = useTranslation();
  const options = useMemo(() => partnerPaymentMethodSelectOptions(t), [t]);

  return (
    <Col span={12}>
      <PaymentMethodWithMixFormItems
        formRef={formRef}
        options={options}
        methodLabel={t('field.partner.defaultPaymentMethod')}
        methodPlaceholder={t('field.partner.defaultPaymentMethodPlaceholder')}
        methodField="defaultPaymentMethodCode"
        wireField="defaultPaymentWirePercent"
        acceptanceField="defaultPaymentAcceptancePercent"
        enableEmployeeAdvance={false}
      />
    </Col>
  );
};