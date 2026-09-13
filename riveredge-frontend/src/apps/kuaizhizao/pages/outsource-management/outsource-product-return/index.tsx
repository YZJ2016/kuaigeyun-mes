import React from 'react';
import { useTranslation } from 'react-i18next';
import InboundHub from '../../warehouse-management/inbound';

const OutsourceProductReturnPage: React.FC = () => {
  const { t } = useTranslation();
  return (
    <InboundHub
      fixedReceiptType="outsource_product_return"
      headerTitle={t('app.kuaizhizao.menu.outsource-management.outsource-product-return')}
      columnPersistenceId="apps.kuaizhizao.pages.outsource-management.outsource-product-return-width-v1"
    />
  );
};

export default OutsourceProductReturnPage;
