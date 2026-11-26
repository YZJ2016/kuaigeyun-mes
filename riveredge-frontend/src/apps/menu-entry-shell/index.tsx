/**
 * 仅菜单聚合、业务页托管在他处的应用入口（快设备 / 快质量 / 行业包等）。
 * 多个应用 manifest 共用本 entry_point，文案按 URL 段 /apps/{code} 解析 i18n。
 */
import React from 'react';
import { Result } from 'antd';
import { AppstoreOutlined } from '@ant-design/icons';
import { useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ListPageTemplate } from '../../components/layout-templates';

function resolveAppCodeFromPath(pathname: string): string {
  const match = pathname.match(/^\/apps\/([^/]+)/);
  return match?.[1] ?? '';
}

export default function MenuEntryShellApp() {
  const { pathname } = useLocation();
  const { t, i18n } = useTranslation();
  const appCode = resolveAppCodeFromPath(pathname);
  const nameKey = appCode ? `app.${appCode}.name` : '';
  const hintKey = appCode ? `app.${appCode}.homeHint` : '';
  const title =
    nameKey && i18n.exists(nameKey) ? t(nameKey) : appCode || t('ui.common.unknownTenant');
  const subTitle = hintKey && i18n.exists(hintKey) ? t(hintKey) : undefined;

  return (
    <ListPageTemplate>
      <Result icon={<AppstoreOutlined />} title={title} subTitle={subTitle} />
    </ListPageTemplate>
  );
}