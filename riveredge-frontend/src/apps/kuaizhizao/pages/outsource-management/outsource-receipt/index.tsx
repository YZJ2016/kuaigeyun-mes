import React from 'react';
import { useTranslation } from 'react-i18next';
import InboundHub from '../../warehouse-management/inbound';

const OutsourceReceiptPage: React.FC = () => {
  const { t } = useTranslation();
  return (
    <InboundHub
      fixedReceiptType="outsource_receipt"
      headerTitle={t('app.kuaizhizao.menu.outsource-management.outsource-receipt')}
      columnPersistenceId="apps.kuaizhizao.pages.outsource-management.outsource-receipt-width-v1"
    />
  );
};

export default OutsourceReceiptPage;
