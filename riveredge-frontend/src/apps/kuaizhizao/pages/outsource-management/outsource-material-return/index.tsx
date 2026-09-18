import React from 'react';
import { useTranslation } from 'react-i18next';
import InboundHub from '../../warehouse-management/inbound';

const OutsourceMaterialReturnPage: React.FC = () => {
  const { t } = useTranslation();
  return (
    <InboundHub
      fixedReceiptType="outsource_material_return"
      permissionResource="kuaizhizao:outsource-material-return"
      headerTitle={t('app.kuaizhizao.menu.outsource-management.outsource-material-return')}
      columnPersistenceId="apps.kuaizhizao.pages.outsource-management.outsource-material-return-width-v1"
    />
  );
};

export default OutsourceMaterialReturnPage;
