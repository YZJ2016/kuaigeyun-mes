/**
 * KU-Insights 调用分析（/apps/kuaiai/insights，spec 184 T5；设计 §9/§12.1）。
 *
 * - 门控：entry:read + insights:display 双码缺一即 403，不发 core 请求；
 * - 数据：既有 /core/ai/stats/overview?days=7|30 与 /core/ai/audit/logs，
 *   URL/参数/权限原样复用；页面不自算总量，只用 stats 字段；
 * - 页头右侧 Segmented（近7天/近30天）+ 刷新；切换同步刷新全部区域；
 * - 四指标卡；by_day 缺失日期补 0（Asia/Shanghai），纵轴从 0；
 *   有效数据点 <2 仍显示并附空态说明；null capability → 未分类；
 * - pulse_suggestion_count 为 null 显示「—」，绝不伪造 0；
 * - 每图配数值摘要（可访问替代），颜色不作唯一状态信息；
 * - 空数据按 empty_reason 呈现，与 5xx/网络错误严格区分。
 */

import React, { useMemo, useState } from 'react';
import {
  Button,
  Empty,
  Result,
  Segmented,
  Skeleton,
  Table,
  Tag,
  Typography,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import type { ColumnsType } from 'antd/es/table';
import { useCurrentUser } from '../../../../hooks/useCurrentUser';
import { hasAllPermissions } from '../../../../utils/permission';
import {
  ChartSuspense,
  LazyLine,
  LazyPie,
} from '../../../../components/common/lazyAntCharts';
import OperationalPageHeader from '../../components/OperationalPageHeader';
import MetricCard from '../../components/MetricCard';
import { getAiStatsOverview, listAiAuditLogs } from '../../services/operations';
import { auditStatusTone, capabilityLabel, fillMissingDays } from '../../opsData';
import type { AiAuditLogItemOut } from '../../types/operations';
import '../../ops.less';

const REQUIRED_PERMISSIONS = ['kuaiai:entry:read', 'kuaiai:insights:display'];
const ACTIVITY_PAGE_SIZE = 20;
const CHART_HEIGHT = 280;

const InsightsPage: React.FC = () => {
  const { t } = useTranslation();
  const currentUser = useCurrentUser();
  // 双码门控：缺任一码 → 403 视图，enabled=false 保证不发 core 请求
  const allowed = hasAllPermissions(currentUser, REQUIRED_PERMISSIONS);
  const [days, setDays] = useState<7 | 30>(7);
  const [page, setPage] = useState(1);

  const statsQuery = useQuery({
    queryKey: ['kuaiai', 'core-ai', 'stats-overview', { days }],
    queryFn: ({ signal }) => getAiStatsOverview(days, signal),
    enabled: allowed,
    staleTime: 30_000,
  });

  // days 进 queryKey：7/30 切换同步刷新全部区域
  const activityQuery = useQuery({
    queryKey: ['kuaiai', 'core-ai', 'audit-logs', { days, page }],
    queryFn: ({ signal }) =>
      listAiAuditLogs({ page, page_size: ACTIVITY_PAGE_SIZE }, signal),
    enabled: allowed,
    placeholderData: (prev) => prev,
  });

  const refresh = () => {
    void statsQuery.refetch();
    void activityQuery.refetch();
  };

  const stats = statsQuery.data;

  const trendData = useMemo(
    () => fillMissingDays(stats?.by_day, stats?.days ?? days),
    [stats?.by_day, stats?.days, days],
  );
  const trendNonZero = useMemo(
    () => trendData.filter((d) => d.count > 0).length,
    [trendData],
  );

  const uncategorized = t('app.kuaiai.insights.unknownCap', {
    defaultValue: '未分类',
  });
  const capabilityData = useMemo(
    () =>
      (stats?.by_capability ?? [])
        .map((c) => ({
          capability: capabilityLabel(c.capability, uncategorized),
          count: c.count ?? 0,
        }))
        .filter((c) => c.count > 0),
    [stats?.by_capability, uncategorized],
  );

  // 可访问数值摘要：图表外的等效信息（不靠颜色传达状态）
  const trendSummary = useMemo(() => {
    const total = stats?.total_calls;
    if (total === null || total === undefined) return '';
    const peak = trendData.reduce(
      (best, d) => (d.count > (best?.count ?? -1) ? d : best),
      trendData[0],
    );
    return t('app.kuaiai.insights.trendSummary', {
      defaultValue: '近 {{days}} 天共 {{total}} 次调用，峰值 {{peakDay}} 当日 {{peak}} 次',
      days: stats?.days ?? days,
      total,
      peakDay: peak?.day ?? '—',
      peak: peak?.count ?? 0,
    });
  }, [stats?.total_calls, stats?.days, days, trendData, t]);

  const capabilitySummary = useMemo(
    () =>
      capabilityData
        .map((c) => `${c.capability} ${c.count}`)
        .join('，'),
    [capabilityData],
  );

  const header = (
    <OperationalPageHeader
      title={t('app.kuaiai.insights.title', { defaultValue: '调用分析' })}
      subtitle={t('app.kuaiai.insights.subtitle', {
        defaultValue: 'AI 调用趋势、能力分布与最近动态',
      })}
      extra={
        <>
          <Segmented
            value={days}
            onChange={(v) => setDays(v as 7 | 30)}
            options={[
              {
                value: 7,
                label: t('app.kuaiai.insights.range7', { defaultValue: '近7天' }),
              },
              {
                value: 30,
                label: t('app.kuaiai.insights.range30', { defaultValue: '近30天' }),
              },
            ]}
          />
          <Button
            icon={<ReloadOutlined />}
            loading={statsQuery.isFetching || activityQuery.isFetching}
            onClick={refresh}
            aria-label={t('common.refresh', { defaultValue: '刷新' })}
          >
            {t('common.refresh', { defaultValue: '刷新' })}
          </Button>
        </>
      }
    />
  );

  if (!allowed) {
    return (
      <div className="kuaiai-ops-page">
        <div className="kuaiai-ops-inner">
          {header}
          <Result
            status="403"
            title={t('app.kuaiai.ops.forbidden', { defaultValue: '缺少功能权限' })}
            subTitle={t('app.kuaiai.ops.forbiddenHint', {
              defaultValue: '当前账号缺少对应页面权限，请联系管理员授权',
            })}
          />
        </div>
      </div>
    );
  }

  const statsError = statsQuery.error as any;
  const statsFailed = statsQuery.isError && !statsQuery.data;
  const stats403 = statsError?.response?.status === 403;

  const activityError = activityQuery.error as any;
  const activityFailed = activityQuery.isError && !activityQuery.data;
  const activity403 = activityError?.response?.status === 403;

  const metricCards: {
    key: string;
    title: string;
    value: number | null;
    unit?: string;
  }[] = [
    {
      key: 'total',
      title: t('app.kuaiai.insights.totalCalls', { defaultValue: '总调用次数' }),
      value: stats?.total_calls ?? null,
    },
    {
      key: 'latency',
      title: t('app.kuaiai.insights.avgLatency', { defaultValue: '平均延迟' }),
      value: stats?.avg_latency_ms ?? null,
      unit: 'ms',
    },
    {
      key: 'pulse',
      title: t('app.kuaiai.insights.pulseHits', { defaultValue: 'Pulse 建议数' }),
      // 数据源不可用时后端下发 null → 「—」，绝不伪造 0
      value: stats?.pulse_suggestion_count ?? null,
    },
    {
      key: 'docs',
      title: t('app.kuaiai.insights.knowledgeDocs', {
        defaultValue: '知识语料文档',
      }),
      value: stats?.knowledge_document_count ?? null,
    },
  ];

  const activityColumns: ColumnsType<AiAuditLogItemOut> = [
    {
      title: t('app.kuaiai.trust.col.time', { defaultValue: '时间' }),
      dataIndex: 'created_at',
      width: 180,
      render: (v: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '—'),
    },
    {
      title: t('app.kuaiai.trust.col.capability', { defaultValue: '能力' }),
      dataIndex: 'capability',
      width: 120,
      render: (v: string | null) => capabilityLabel(v, uncategorized),
    },
    {
      title: t('app.kuaiai.trust.col.route', { defaultValue: '路由' }),
      dataIndex: 'route',
      render: (v: string | null) => v || '—',
    },
    {
      title: t('app.kuaiai.trust.col.latency', { defaultValue: '耗时' }),
      dataIndex: 'latency_ms',
      width: 100,
      align: 'right',
      render: (v: number | null) =>
        v === null || v === undefined ? '—' : `${v} ms`,
    },
    {
      title: t('app.kuaiai.trust.col.status', { defaultValue: '状态' }),
      dataIndex: 'status_code',
      width: 90,
      render: (v: number | null) =>
        v === null || v === undefined ? (
          <Tag>—</Tag>
        ) : (
          <Tag color={auditStatusTone(v)}>{v}</Tag>
        ),
    },
  ];

  const trendSection = (
    <div className="kuaiai-ops-insights-chart-card kuaiai-ops-insights-chart-trend">
      <div className="kuaiai-ops-insights-chart-head">
        <Typography.Text strong>
          {t('app.kuaiai.insights.chartCallsByDay', {
            defaultValue: '每日调用趋势',
          })}
        </Typography.Text>
      </div>
      <div
        className="kuaiai-ops-insights-chart-body"
        role="img"
        aria-label={trendSummary || undefined}
      >
        <ChartSuspense fallback={<Skeleton active />}>
          <LazyLine
            data={trendData}
            xField="day"
            yField="count"
            height={CHART_HEIGHT}
            scale={{ y: { domainMin: 0 } }}
            point={{ size: 3 }}
            tooltip={{ items: ['count'] }}
          />
        </ChartSuspense>
      </div>
      {trendNonZero < 2 ? (
        <Typography.Text
          type="secondary"
          className="kuaiai-ops-insights-chart-note"
        >
          {t('app.kuaiai.insights.trendSparse', {
            defaultValue: '有效数据点不足，仅展示现有记录',
          })}
        </Typography.Text>
      ) : null}
      {trendSummary ? (
        <Typography.Paragraph
          type="secondary"
          className="kuaiai-ops-insights-chart-summary"
        >
          {trendSummary}
        </Typography.Paragraph>
      ) : null}
    </div>
  );

  const capabilitySection = (
    <div className="kuaiai-ops-insights-chart-card kuaiai-ops-insights-chart-pie">
      <div className="kuaiai-ops-insights-chart-head">
        <Typography.Text strong>
          {t('app.kuaiai.insights.chartCallsByCapability', {
            defaultValue: '能力调用分布',
          })}
        </Typography.Text>
      </div>
      <div
        className="kuaiai-ops-insights-chart-body"
        role="img"
        aria-label={capabilitySummary || undefined}
      >
        {capabilityData.length ? (
          <ChartSuspense fallback={<Skeleton active />}>
            <LazyPie
              data={capabilityData}
              angleField="count"
              colorField="capability"
              height={CHART_HEIGHT}
              innerRadius={0.6}
              legend={{ color: { position: 'bottom' } }}
              tooltip={{ items: ['count'] }}
            />
          </ChartSuspense>
        ) : (
          <Empty
            style={{ marginTop: 80 }}
            description={
              stats?.empty_reason ||
              t('app.kuaiai.insights.noActivity', {
                defaultValue: '暂无 AI 调用记录',
              })
            }
          />
        )}
      </div>
      {capabilitySummary ? (
        <Typography.Paragraph
          type="secondary"
          className="kuaiai-ops-insights-chart-summary"
        >
          {capabilitySummary}
        </Typography.Paragraph>
      ) : null}
    </div>
  );

  const activitySection = activityFailed ? (
    <Result
      status={activity403 ? '403' : 'error'}
      title={
        activity403
          ? t('app.kuaiai.ops.forbidden', { defaultValue: '缺少功能权限' })
          : t('app.kuaiai.insights.loadFailed', {
              defaultValue: '加载调用分析失败',
            })
      }
      subTitle={
        activity403
          ? t('app.kuaiai.trust.auditForbidden', {
              defaultValue: '当前账号缺少 kuaiai:entry:read，无法读取审计日志',
            })
          : activityError?.message
      }
      extra={
        !activity403 ? (
          <Button type="primary" onClick={() => void activityQuery.refetch()}>
            {t('common.retry', { defaultValue: '重试' })}
          </Button>
        ) : undefined
      }
    />
  ) : (
    <Table<AiAuditLogItemOut>
      rowKey="uuid"
      size="middle"
      loading={activityQuery.isPending || activityQuery.isFetching}
      columns={activityColumns}
      dataSource={activityQuery.data?.items ?? []}
      locale={{
        emptyText: (
          <Empty
            description={
              activityQuery.data?.empty_reason ||
              t('app.kuaiai.insights.noActivity', {
                defaultValue: '暂无 AI 调用记录',
              })
            }
          />
        ),
      }}
      pagination={{
        current: page,
        pageSize: ACTIVITY_PAGE_SIZE,
        total: activityQuery.data?.total ?? 0,
        showSizeChanger: false,
        onChange: setPage,
      }}
      scroll={{ x: 720 }}
    />
  );

  return (
    <div className="kuaiai-ops-page">
      <div className="kuaiai-ops-inner">
        {header}

        {statsQuery.isPending ? (
          <>
            <div className="kuaiai-ops-metrics">
              {[0, 1, 2, 3].map((i) => (
                <div className="kuaiai-ops-metric" key={i}>
                  <Skeleton active paragraph={{ rows: 1 }} title={{ width: '50%' }} />
                </div>
              ))}
            </div>
            <div className="kuaiai-ops-insights-charts">
              <div className="kuaiai-ops-insights-chart-card kuaiai-ops-insights-chart-trend">
                <Skeleton active paragraph={{ rows: 6 }} />
              </div>
              <div className="kuaiai-ops-insights-chart-card kuaiai-ops-insights-chart-pie">
                <Skeleton active paragraph={{ rows: 6 }} />
              </div>
            </div>
          </>
        ) : statsFailed ? (
          <Result
            status={stats403 ? '403' : 'error'}
            title={
              stats403
                ? t('app.kuaiai.ops.forbidden', { defaultValue: '缺少功能权限' })
                : t('app.kuaiai.insights.loadFailed', {
                    defaultValue: '加载调用分析失败',
                  })
            }
            subTitle={
              stats403
                ? t('app.kuaiai.ops.forbiddenHint', {
                    defaultValue: '当前账号缺少对应页面权限，请联系管理员授权',
                  })
                : statsError?.message
            }
            extra={
              !stats403 ? (
                <Button type="primary" onClick={() => void statsQuery.refetch()}>
                  {t('common.retry', { defaultValue: '重试' })}
                </Button>
              ) : undefined
            }
          />
        ) : (
          <>
            <div className="kuaiai-ops-metrics">
              {metricCards.map((m) => (
                <MetricCard
                  key={m.key}
                  title={m.title}
                  value={m.value}
                  unit={m.unit}
                />
              ))}
            </div>

            {stats && stats.total_calls === 0 ? (
              <Empty
                style={{ marginTop: 24 }}
                description={
                  stats.empty_reason ||
                  t('app.kuaiai.insights.empty', {
                    defaultValue: '启用 KU-AI 后将自动统计调用数据',
                  })
                }
              />
            ) : (
              <div className="kuaiai-ops-insights-charts">
                {trendSection}
                {capabilitySection}
              </div>
            )}
          </>
        )}

        <Typography.Title level={4} className="kuaiai-ops-section-title">
          {t('app.kuaiai.insights.recentActivity', { defaultValue: '最近动态' })}
        </Typography.Title>
        {activitySection}
      </div>
    </div>
  );
};

export default InsightsPage;
