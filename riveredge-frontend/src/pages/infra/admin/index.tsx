/**
 * 平台超级管理员管理页面
 *
 * 用于管理平台超级管理员信息（查看、编辑、改密）
 * 平台超级管理员是平台唯一的，只能有一个
 */

import { App } from 'antd';
import { SettingOutlined, UserOutlined, GlobalOutlined, DeploymentUnitOutlined } from '@ant-design/icons';
import { useMemo, useState, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { MultiTabListPageTemplate } from '../../../components/layout-templates';
import { getInfraSuperAdmin } from '../../../services/infraAdmin';
import { clearAuth } from '../../../utils/auth';
import { redirectAfterLogout } from '../../../utils/loginEntry';
import { useNavigate } from 'react-router-dom';
import { useGlobalStore } from '../../../stores';
import { useTranslation } from 'react-i18next';
import PlatformSettingsPage from './settings';
import BuildProvenanceSummaryTab from './build-provenance-summary';
import { getBuildProvenance } from '../../../services/platformSettings';
import { canShowRegistrySummaryAdmin } from '../../../utils/officialRegistrySite';
import { getAntdModal } from '../../../utils/antdAppApis';
import InfraAdminInfoPane from './InfraAdminInfoPane';

/**
 * 平台超级管理员管理页面组件
 */
export default function InfraSuperAdminPage() {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const setCurrentUser = useGlobalStore((s) => s.setCurrentUser);
  const [activeTabKey, setActiveTabKey] = useState('settings');

  const { data: admin, isLoading } = useQuery({
    queryKey: ['infraSuperAdmin'],
    queryFn: getInfraSuperAdmin,
  });

  const { data: buildProvenance } = useQuery({
    queryKey: ['buildProvenanceAdminGate'],
    queryFn: getBuildProvenance,
    staleTime: 5 * 60 * 1000,
  });

  const showProvenanceSummaryTab = canShowRegistrySummaryAdmin(
    buildProvenance?.registry_summary_admin_available,
  );

  const handleLogout = useCallback(() => {
    getAntdModal().confirm({
      title: t('pages.infra.admin.logoutConfirmTitle'),
      content: t('pages.infra.admin.logoutConfirmContent'),
      onOk: () => {
        clearAuth();
        setCurrentUser(undefined);
        queryClient.clear();
        messageApi.success(t('pages.infra.admin.logoutSuccess'));
        redirectAfterLogout(navigate);
      },
    });
  }, [messageApi, navigate, queryClient, setCurrentUser, t]);

  const tabItems = useMemo(() => {
    const items = [
      {
        key: 'settings',
        label: (
          <span>
            <SettingOutlined />
            {t('pages.infra.admin.tabSettings')}
          </span>
        ),
        children: <PlatformSettingsPage mode="basic" />,
      },
      {
        key: 'login-settings',
        label: (
          <span>
            <GlobalOutlined />
            {t('pages.infra.platform.loginConfig')}
          </span>
        ),
        children: <PlatformSettingsPage mode="login" />,
      },
    ];

    if (showProvenanceSummaryTab) {
      items.push({
        key: 'provenance-summary',
        label: (
          <span>
            <DeploymentUnitOutlined />
            {t('pages.infra.admin.tabProvenanceSummary')}
          </span>
        ),
        children: <BuildProvenanceSummaryTab />,
      });
    }

    items.push({
      key: 'admin',
      label: (
        <span>
          <UserOutlined />
          {t('pages.infra.admin.tabAdmin')}
        </span>
      ),
      children: (
        <InfraAdminInfoPane
          admin={admin}
          loading={isLoading}
          onLogout={handleLogout}
          onUpdated={() => {
            void queryClient.invalidateQueries({ queryKey: ['infraSuperAdmin'] });
          }}
        />
      ),
    });

    return items;
  }, [admin, handleLogout, isLoading, queryClient, showProvenanceSummaryTab, t]);

  return (
    <MultiTabListPageTemplate
      activeTabKey={activeTabKey}
      onTabChange={setActiveTabKey}
      tabs={tabItems}
    />
  );
}
