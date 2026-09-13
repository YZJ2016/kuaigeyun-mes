import React from 'react';
import { useTranslation } from 'react-i18next';
import InboundHub from '../../warehouse-management/inbound';

const PurchaseInboundPage: React.FC = () => {
  const { t } = useTranslation();
  return (
    <InboundHub
      fixedReceiptType="purchase"
      headerTitle={t('app.kuaizhizao.menu.purchase-management.inbound')}
      columnPersistenceId="apps.kuaizhizao.pages.purchase-management.inbound-width-v1"
    />
  );
};

export default PurchaseInboundPage;
