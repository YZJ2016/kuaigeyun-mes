import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { App, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  CustomerServiceOutlined,
  GlobalOutlined,
  ImportOutlined,
  TeamOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import {
  ModuleActionMasonry,
  ModuleActionPanel,
  ModuleCenterLayout,
  ModuleFeedList,
  ModuleKpiRow,
  ModuleShortcutGrid,
  masonryWeightFromRows,
} from '../../../kuaizhizao/components/module-center';
import type { ModuleKpiDef, ModuleShortcutDef } from '../../../kuaizhizao/components/module-center';
import { foreignTradeApi, type CustomerFollowUp, type ForeignTradeCrmStats } from '../../services/foreignTradeApi';
import { formatDateTime } from '../../../../utils/format';

const { Text } = Typography;

export default function ForeignTradeDashboardPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<ForeignTradeCrmStats | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await foreignTradeApi.getStats(8);
      setStats(res);
    } catch (e: any) {
      message.error(e?.message || t('app.ind-foreign-trade.dashboard.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [message, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const pending = stats?.pending_customers ?? 0;
  const overdue = stats?.overdue_customers ?? 0;
  const inactiveAlertDays = Math.max(1, Number(stats?.inactive_alert_days) || 7);
  const inactiveCustomers = stats?.inactive_customers ?? 0;
  const followed = stats?.follow_status_followed ?? 0;
  const unfollowed = stats?.follow_status_pending ?? 0;
  const records = stats?.follow_up_records_total ?? 0;
  const pendingItems: CustomerFollowUp[] = stats?.items || [];
  const levelCounts = stats?.level_counts || {};

  const kpis: ModuleKpiDef[] = useMemo(
    () => [
      {
        key: 'pending',
        title: t('app.kuaizhizao.salesDashboard.kpi.pendingFollowUps'),
        value: pending,
        subtitle: t('app.kuaizhizao.salesDashboard.kpi.pendingFollowUpsSubtitle'),
        icon: <CustomerServiceOutlined style={{ fontSize: 24, color: '#fff' }} />,
        gradient: 'linear-gradient(135deg, #fa8c16 0%, #ffc069 100%)',
        boxShadow: '0 4px 12px rgba(250, 140, 22, 0.15)',
        onClick: () => navigate('/apps/ind-foreign-trade/follow-ups'),
        sideMetrics: [{ label: t('app.kuaizhizao.salesDashboard.kpi.overdue'), value: overdue }],
      },
      {
        key: 'inactive',
        title: t('app.kuaizhizao.salesDashboard.kpi.inactiveDays', { days: inactiveAlertDays }),
        value: inactiveCustomers,
        subtitle: t('app.ind-foreign-trade.dashboard.inactiveHint'),
        icon: <WarningOutlined style={{ fontSize: 24, color: '#fff' }} />,
        gradient: 'linear-gradient(135deg, #ff4d4f 0%, #ff7875 100%)',
        boxShadow: '0 4px 12px rgba(255, 77, 79, 0.15)',
        onClick: () => navigate('/apps/ind-foreign-trade/export-customers'),
        sideMetrics: [
          { label: t('app.kuaizhizao.customerPool.followStatusPending'), value: unfollowed },
        ],
      },
      {
        key: 'followed',
        title: t('app.kuaizhizao.customerPool.followStatusFollowed'),
        value: followed,
        subtitle: t('app.ind-foreign-trade.dashboard.recordsHint', { count: records }),
        icon: <TeamOutlined style={{ fontSize: 24, color: '#fff' }} />,
        gradient: 'linear-gradient(135deg, #52c41a 0%, #95de64 100%)',
        boxShadow: '0 4px 12px rgba(82, 196, 26, 0.15)',
        onClick: () => navigate('/apps/ind-foreign-trade/export-customers'),
      },
    ],
    [
      followed,
      inactiveAlertDays,
      inactiveCustomers,
      navigate,
      overdue,
      pending,
      records,
      t,
      unfollowed,
    ],
  );

  const shortcuts: ModuleShortcutDef[] = useMemo(
    () => [
      {
        key: 'customers',
        title: t('app.ind-foreign-trade.menu.exportCustomers'),
        icon: <GlobalOutlined style={{ fontSize: 22, color: '#1890ff' }} />,
        path: '/apps/ind-foreign-trade/export-customers',
      },
      {
        key: 'import',
        title: t('app.ind-foreign-trade.menu.inquiryImport'),
        icon: <ImportOutlined style={{ fontSize: 22, color: '#722ed1' }} />,
        path: '/apps/ind-foreign-trade/inquiry-import',
      },
      {
        key: 'follow',
        title: t('app.ind-foreign-trade.menu.followUps'),
        icon: <CustomerServiceOutlined style={{ fontSize: 22, color: '#fa8c16' }} />,
        path: '/apps/ind-foreign-trade/follow-ups',
      },
    ],
    [t],
  );

  const pendingFeed = useMemo(
    () =>
      pendingItems.map((item) => ({
        id: item.id,
        title: item.customer_name,
        subtitle: item.content || t('app.kuaizhizao.salesDashboard.noFollowUpContent'),
        meta: (
          <Text type="secondary" style={{ fontSize: 10 }}>
            {item.next_follow_up_at
              ? formatDateTime(item.next_follow_up_at, 'YYYY-MM-DD')
              : '—'}
          </Text>
        ),
        onClick: () => navigate('/apps/ind-foreign-trade/follow-ups'),
      })),
    [navigate, pendingItems, t],
  );

  const levelFeed = useMemo(
    () =>
      Object.entries(levelCounts)
        .sort((a, b) => b[1] - a[1])
        .map(([code, count]) => ({
          id: code,
          title: code === '_unset' ? t('app.kuaizhizao.salesDashboard.crm.levelUnset') : code,
          meta: <Text style={{ fontWeight: 600 }}>{count}</Text>,
        })),
    [levelCounts, t],
  );

  return (
    <ModuleCenterLayout
      loading={loading}
      showSidebar={false}
      kpiRow={<ModuleKpiRow items={kpis} colProps={{ xs: 24, sm: 12, lg: 8 }} />}
      shortcutRow={<ModuleShortcutGrid items={shortcuts} />}
      actionRow={
        <ModuleActionMasonry>
          <ModuleActionPanel
            layout="masonry"
            title={t('app.kuaizhizao.salesDashboard.followUpTodayTitle')}
            loading={loading}
            masonryWeight={masonryWeightFromRows(Math.max(pendingFeed.length, 3))}
          >
            <ModuleFeedList items={pendingFeed} emptyText={t('common.noData')} />
          </ModuleActionPanel>
          <ModuleActionPanel
            layout="masonry"
            title={t('app.kuaizhizao.salesDashboard.crm.statsTitle')}
            loading={loading}
            masonryWeight={masonryWeightFromRows(Math.max(levelFeed.length, 3))}
          >
            <ModuleFeedList
              items={levelFeed}
              emptyText={t('app.kuaizhizao.salesDashboard.crm.levelEmpty')}
            />
          </ModuleActionPanel>
        </ModuleActionMasonry>
      }
    />
  );
}
