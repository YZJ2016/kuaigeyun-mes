import React from 'react';
import { useTranslation } from 'react-i18next';
import OutboundHub from '../../warehouse-management/outbound';

const ProductionOutboundPage: React.FC = () => {
  const { t } = useTranslation();
  return (
    <OutboundHub
      fixedOutboundType="production_picking"
      headerTitle={t('app.kuaizhizao.menu.production-execution.outbound')}
      columnPersistenceId="apps.kuaizhizao.pages.production-execution.outbound-width-v2"
    />
  );
};

export default ProductionOutboundPage;
