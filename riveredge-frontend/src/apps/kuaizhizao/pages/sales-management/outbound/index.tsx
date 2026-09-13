import React from 'react';
import { useTranslation } from 'react-i18next';
import OutboundHub from '../../warehouse-management/outbound';

const SalesOutboundPage: React.FC = () => {
  const { t } = useTranslation();
  return (
    <OutboundHub
      fixedOutboundType="sales_delivery"
      headerTitle={t('app.kuaizhizao.menu.sales-management.outbound')}
      columnPersistenceId="apps.kuaizhizao.pages.sales-management.outbound-width-v1"
    />
  );
};

export default SalesOutboundPage;
