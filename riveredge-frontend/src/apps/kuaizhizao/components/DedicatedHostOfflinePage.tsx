/**
 * 快制造宿主 path 已迁定制应用：侧栏下线后，书签打开仅展示说明。
 */
import React from 'react';
import { Alert } from 'antd';
import { useTranslation } from 'react-i18next';
import { ListPageTemplate } from '../../../components/layout-templates';

type Props = {
  titleKey: string;
  descriptionKey: string;
};

export const DedicatedHostOfflinePage: React.FC<Props> = ({ titleKey, descriptionKey }) => {
  const { t } = useTranslation();
  return (
    <ListPageTemplate>
      <Alert type="info" showIcon title={t(titleKey)} description={t(descriptionKey)} />
    </ListPageTemplate>
  );
};
