import React from 'react';
import { useTranslation } from 'react-i18next';
import InboundHub from '../../warehouse-management/inbound';

const PRODUCTION_INBOUND_SCOPED = [
  'finished_goods',
  'semi_finished_goods',
  'production_return',
] as const;

const ProductionInboundPage: React.FC = () => {
  const { t } = useTranslation();
  return (
    <InboundHub
      scopedReceiptTypes={PRODUCTION_INBOUND_SCOPED}
      headerTitle={t('app.kuaizhizao.menu.production-execution.inbound')}
      columnPersistenceId="apps.kuaizhizao.pages.production-execution.inbound-width-v1"
    />
  );
};

export default ProductionInboundPage;
