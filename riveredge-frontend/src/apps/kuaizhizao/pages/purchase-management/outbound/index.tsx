import React from 'react';
import { useTranslation } from 'react-i18next';
import OutboundHub from '../../warehouse-management/outbound';

/** 采购管理入口：固定为采购退货出库（对齐销售管理「销售退货入库」） */
const PurchaseOutboundPage: React.FC = () => {
  const { t } = useTranslation();
  return (
    <OutboundHub
      fixedOutboundType="purchase_return"
      headerTitle={t('app.kuaizhizao.menu.purchase-management.outbound')}
      columnPersistenceId="apps.kuaizhizao.pages.purchase-management.outbound-width-v2"
      permissionResource="kuaizhizao:purchase-return"
    />
  );
};

export default PurchaseOutboundPage;
