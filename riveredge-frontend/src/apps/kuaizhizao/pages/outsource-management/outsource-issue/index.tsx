import React from 'react';
import { useTranslation } from 'react-i18next';
import OutboundHub from '../../warehouse-management/outbound';

const OutsourceIssuePage: React.FC = () => {
  const { t } = useTranslation();
  return (
    <OutboundHub
      fixedOutboundType="outsource_issue"
      permissionResource="kuaizhizao:outsource-issue"
      headerTitle={t('app.kuaizhizao.menu.outsource-management.outsource-issue')}
      columnPersistenceId="apps.kuaizhizao.pages.outsource-management.outsource-issue-width-v1"
    />
  );
};

export default OutsourceIssuePage;
