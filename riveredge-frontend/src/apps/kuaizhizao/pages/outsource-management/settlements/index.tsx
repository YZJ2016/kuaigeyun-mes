import React from 'react';
import { Result } from 'antd';
import { useTranslation } from 'react-i18next';
import { ListPageTemplate } from '../../../../../components/layout-templates';

const OutsourceSettlementsPage: React.FC = () => {
  const { t } = useTranslation();
  return (
    <ListPageTemplate>
      <Result
        status="info"
        title={t('app.kuaizhizao.menu.outsource-management.settlements')}
        subTitle={t('app.kuaizhizao.outsourceManagement.settlementsComingSoon')}
      />
    </ListPageTemplate>
  );
};

export default OutsourceSettlementsPage;
