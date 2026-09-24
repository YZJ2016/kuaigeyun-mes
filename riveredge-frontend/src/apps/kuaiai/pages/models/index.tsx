/**
 * KU-AI 模型目录管理页（spec 138）：厂商目录 + 模型目录两个区块。
 */

import React from 'react';
import { Tabs } from 'antd';
import { useTranslation } from 'react-i18next';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { ProvidersSection } from './ProvidersSection';
import { ModelsSection } from './ModelsSection';

export default function KuaiaiModelsPage() {
  const { t } = useTranslation();

  return (
    <ListPageTemplate>
      <Tabs
        items={[
          {
            key: 'providers',
            label: t('app.kuaiai.models.tabProviders', { defaultValue: '厂商' }),
            children: <ProvidersSection />,
          },
          {
            key: 'models',
            label: t('app.kuaiai.models.tabModels', { defaultValue: '模型' }),
            children: <ModelsSection />,
          },
        ]}
      />
    </ListPageTemplate>
  );
}
