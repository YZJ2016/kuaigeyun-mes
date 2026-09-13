import React from 'react';
import { useTranslation } from 'react-i18next';
import InboundHub from '../../warehouse-management/inbound';

const SalesInboundPage: React.FC = () => {
  const { t } = useTranslation();
  return (
    <InboundHub
      fixedReceiptType="sales_return"
      headerTitle={t('app.kuaizhizao.menu.sales-management.inbound')}
      columnPersistenceId="apps.kuaizhizao.pages.sales-management.inbound-width-v1"
    />
  );
};

export default SalesInboundPage;
