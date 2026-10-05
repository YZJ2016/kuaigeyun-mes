/**
 * 标签工位宿主 path：快制造侧栏已下线；启用行业 document 替代时渲染 OEM 签样页。
 * 通用工位台已迁定制应用，本 path 不再回退 LabelStationWorkbench。
 */
import React, { Suspense } from 'react';
import { Alert } from 'antd';
import { useTranslation } from 'react-i18next';
import { ListPageTemplate } from '../../../../../components/layout-templates';
import PageSkeleton from '../../../../../components/page-skeleton';
import { useDocumentReplacement } from '../../../../../hooks/useDocumentReplacement';

const HOST_PATH = '/apps/kuaizhizao/production-execution/label-station';

function LabelStationOfflineNotice() {
  const { t } = useTranslation();
  return (
    <ListPageTemplate>
      <Alert
        type="info"
        showIcon
        title={t('app.kuaizhizao.labelStation.offlineTitle')}
        description={t('app.kuaizhizao.labelStation.offlineDescription')}
      />
    </ListPageTemplate>
  );
}

export default function LabelStationPage() {
  const { loading, Component } = useDocumentReplacement(HOST_PATH);

  if (loading) {
    return (
      <ListPageTemplate>
        <PageSkeleton />
      </ListPageTemplate>
    );
  }

  if (Component) {
    return (
      <Suspense fallback={<PageSkeleton />}>
        <Component />
      </Suspense>
    );
  }

  return <LabelStationOfflineNotice />;
}
