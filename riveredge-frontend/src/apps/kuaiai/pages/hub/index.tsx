/**
 * 星AI 能力矩阵页（/apps/kuaiai/hub，spec 181 T7；设计 §4）。
 *
 * - 数据：GET /apps/kuaiai/operations/hub?days=7（模型/四指标/八能力，局部降级）；
 * - 能力卡入口：ask/data_query/guide 打开既有 KU-Ask 抽屉并携带
 *   context.extra.capability_mode（ask|query|guide），其余按 API route 跳转；
 *   not_ready / 无路由 / 无目标权限一律禁用 + Tooltip，不跳 404；
 * - 指标卡点击进 /insights、/pulse、/corpus，缺 display 权限禁用；
 * - 指标为 null 显示「—」，绝不伪造 0；整页失败 Result + 重试，403 Result。
 */

import React, { useCallback, useMemo } from 'react';
import {
  Alert,
  Button,
  Result,
  Skeleton,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useAiContext, type AiCapabilityMode } from '../../../../contexts/AiContext';
import { useCurrentUser } from '../../../../hooks/useCurrentUser';
import { hasPermission } from '../../../../utils/permission';
import { useKuaiaiEntryAvailable } from '../../hooks/useKuaiaiEntryAvailable';
import OperationalPageHeader from '../../components/OperationalPageHeader';
import MetricCard from '../../components/MetricCard';
import { openAssistantDrawer } from '../../assistant';
import { getHub } from '../../services/operations';
import { HUB_BRAND_VISUAL_URL } from '../../assets/scenes';
import type { HubCapabilityOut, HubMetricsOut, OperationalStatus } from '../../types/operations';
import '../../ops.less';

/** 后端能力 key → KU-Ask 能力模式；命中即打开助手，未命中按 route 跳转 */
const ASSISTANT_CAP_MODE: Record<string, AiCapabilityMode> = {
  ask: 'ask',
  data_query: 'query',
  guide: 'guide',
};

/** 已注册页内路由 → 页面 display 权限（其余后端下发路由直接跳转，由目标页自检权限） */
const ROUTE_DISPLAY_PERMISSION: Record<string, string> = {
  '/apps/kuaiai/chat': 'kuaiai:entry:read',
  '/apps/kuaiai/hub': 'kuaiai:hub:display',
  '/apps/kuaiai/agent-library': 'kuaiai:library:display',
  '/apps/kuaiai/pulse': 'kuaiai:pulse:display',
  '/apps/kuaiai/corpus': 'kuaiai:corpus:display',
  '/apps/kuaiai/knowledge': 'kuaiai:knowledge:display',
  '/apps/kuaiai/trust': 'kuaiai:trust:display',
  '/apps/kuaiai/insights': 'kuaiai:insights:display',
  '/apps/kuaiai/settings': 'kuaiai:settings:display',
};

const STATUS_TAG: Record<OperationalStatus, { color: string; key: string; fallback: string }> = {
  ready: { color: 'success', key: 'app.kuaiai.catalog.status.ready', fallback: '已就绪' },
  partial: { color: 'warning', key: 'app.kuaiai.catalog.status.degraded', fallback: '降级可用' },
  not_ready: { color: 'default', key: 'app.kuaiai.catalog.status.blocked', fallback: '不可用' },
};

function statusTag(status: OperationalStatus, t: (k: string, o?: any) => string) {
  const conf = STATUS_TAG[status] ?? STATUS_TAG.not_ready;
  return <Tag color={conf.color}>{t(conf.key, { defaultValue: conf.fallback })}</Tag>;
}

const HubPage: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const currentUser = useCurrentUser();
  const { setContext } = useAiContext();
  const kuaiaiEntryAvailable = useKuaiaiEntryAvailable();

  const { data, isPending, isFetching, error, refetch } = useQuery({
    queryKey: ['kuaiai', 'operations', 'hub', { days: 7 }],
    queryFn: () => getHub(7),
    staleTime: 30_000,
  });

  const errorStatus = (error as any)?.response?.status as number | undefined;

  const canNavigateTo = useCallback(
    (route: string | null | undefined): boolean => {
      if (!route) return false;
      const required = ROUTE_DISPLAY_PERMISSION[route];
      if (!required) return true; // 后端下发的非本应用路由：跳转后由目标页权限自控
      return hasPermission(currentUser, required);
    },
    [currentUser],
  );

  const openKuAsk = useCallback(
    (capabilityMode?: AiCapabilityMode) => {
      setContext({
        screen: '/apps/kuaiai/hub',
        screenLabel: t('app.kuaiai.hub.title', { defaultValue: '能力矩阵' }),
        ...(capabilityMode ? { capabilityMode } : {}),
      });
      openAssistantDrawer();
    },
    [setContext, t],
  );

  const noAccessTip = t('app.kuaiai.ops.noPageAccess', {
    defaultValue: '暂无该页面访问权限',
  });

  const metricCards = useMemo(() => {
    const metrics: HubMetricsOut | undefined = data?.metrics;
    return [
      {
        key: 'calls',
        title: t('app.kuaiai.hub.metric.calls', { defaultValue: '近7日 AI 调用' }),
        value: metrics?.total_calls ?? null,
        route: '/apps/kuaiai/insights',
        perm: 'kuaiai:insights:display',
      },
      {
        key: 'pulse',
        title: t('app.kuaiai.hub.metric.pulse', { defaultValue: 'Pulse 异常建议' }),
        value: metrics?.pulse_count ?? null,
        route: '/apps/kuaiai/pulse',
        perm: 'kuaiai:pulse:display',
      },
      {
        key: 'corpus',
        title: t('app.kuaiai.hub.metric.knowledge', { defaultValue: '语料条目' }),
        value: metrics?.corpus_count ?? null,
        route: '/apps/kuaiai/corpus',
        perm: 'kuaiai:corpus:display',
      },
      {
        key: 'latency',
        title: t('app.kuaiai.hub.metric.latency', { defaultValue: '平均响应' }),
        value: metrics?.avg_latency_ms ?? null,
        unit: 'ms',
        route: '/apps/kuaiai/insights',
        perm: 'kuaiai:insights:display',
      },
    ];
  }, [data?.metrics, t]);

  const modelName = data?.model?.configured && data.model.name
    ? data.model.name
    : t('app.kuaiai.hub.modelUnknown', { defaultValue: '未配置' });

  const renderCapabilityCard = (cap: HubCapabilityOut) => {
    const mode = ASSISTANT_CAP_MODE[cap.key];
    const usable = cap.status !== 'not_ready';
    const go = () => {
      if (mode) {
        openKuAsk(mode);
      } else if (cap.route) {
        navigate(cap.route);
      }
    };
    const disabled =
      !usable || (mode ? !kuaiaiEntryAvailable : !canNavigateTo(cap.route));
    const reason = !usable
      ? cap.disabled_reason || t('app.kuaiai.ops.notReady', { defaultValue: '暂未就绪' })
      : disabled
        ? mode
          ? t('app.kuaiai.ops.noAssistant', { defaultValue: 'AI 助手当前不可用' })
          : !cap.route
            ? cap.disabled_reason || noAccessTip
            : noAccessTip
        : null;
    const button = (
      <Button
        type="primary"
        ghost={cap.status === 'partial'}
        disabled={disabled}
        onClick={go}
        aria-label={t('app.kuaiai.hub.capEntryAria', {
          defaultValue: '进入能力入口：{{name}}',
          name: cap.name,
        })}
      >
        {t('app.kuaiai.hub.tryIt', { defaultValue: '去体验' })}
      </Button>
    );
    return (
      <div className="kuaiai-ops-cap-card" key={cap.key}>
        <div className="kuaiai-ops-cap-card-head">
          <span className="kuaiai-ops-cap-card-name">{cap.name}</span>
          {statusTag(cap.status, t)}
        </div>
        <div className="kuaiai-ops-cap-card-desc">{cap.description || '—'}</div>
        <div className="kuaiai-ops-cap-card-foot">
          {reason ? <Tooltip title={reason}>{button}</Tooltip> : button}
        </div>
      </div>
    );
  };

  const header = (
    <OperationalPageHeader
      title={t('app.kuaiai.hub.title', { defaultValue: '能力矩阵' })}
      subtitle={t('app.kuaiai.hub.subtitle', {
        defaultValue: '制造场景 AI 能力总览，当前模型 {{model}}',
        model: modelName,
      })}
      extra={
        <>
          <Tooltip
            title={
              kuaiaiEntryAvailable
                ? ''
                : t('app.kuaiai.ops.noAssistant', { defaultValue: 'AI 助手当前不可用' })
            }
          >
            <Button
              style={{ borderColor: '#722ed1', color: '#722ed1' }}
              disabled={!kuaiaiEntryAvailable}
              onClick={() => openKuAsk()}
              aria-label={t('app.kuaiai.showcase.openAssistant', {
                defaultValue: '打开 KU-Ask',
              })}
            >
              {t('app.kuaiai.showcase.openAssistant', { defaultValue: '打开 KU-Ask' })}
            </Button>
          </Tooltip>
          <Button
            icon={<ReloadOutlined />}
            loading={isFetching}
            onClick={() => void refetch()}
            aria-label={t('common.refresh', { defaultValue: '刷新' })}
          >
            {t('common.refresh', { defaultValue: '刷新' })}
          </Button>
        </>
      }
    />
  );

  // 首次加载：页头保持，内容区同尺寸骨架
  if (isPending && !data) {
    return (
      <div className="kuaiai-ops-page">
        <div className="kuaiai-ops-inner">
          {header}
          <div className="kuaiai-ops-cap-tags">
            <Skeleton.Button active size="small" style={{ width: 84 }} />
            <Skeleton.Button active size="small" style={{ width: 84 }} />
            <Skeleton.Button active size="small" style={{ width: 84 }} />
            <Skeleton.Button active size="small" style={{ width: 84 }} />
          </div>
          <div className="kuaiai-ops-metrics">
            {[0, 1, 2, 3].map((i) => (
              <div className="kuaiai-ops-metric" key={i}>
                <Skeleton active paragraph={{ rows: 1 }} title={{ width: '50%' }} />
              </div>
            ))}
          </div>
          <div className="kuaiai-ops-hub-main">
            <div className="kuaiai-ops-brand-card">
              <Skeleton.Image active style={{ width: 300, height: 300 }} />
            </div>
            <div className="kuaiai-ops-cap-grid">
              {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
                <div className="kuaiai-ops-cap-card" key={i}>
                  <Skeleton active paragraph={{ rows: 2 }} title={{ width: '40%' }} />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // 全部失败 / 403：保留页头
  if (error && !data) {
    const is403 = errorStatus === 403;
    return (
      <div className="kuaiai-ops-page">
        <div className="kuaiai-ops-inner">
          {header}
          <Result
            status={is403 ? '403' : 'error'}
            title={
              is403
                ? t('app.kuaiai.ops.forbidden', { defaultValue: '缺少功能权限' })
                : t('app.kuaiai.hub.loadFailed', { defaultValue: '加载中枢数据失败' })
            }
            subTitle={
              is403
                ? t('app.kuaiai.ops.forbiddenHint', {
                    defaultValue: '当前账号缺少 kuaiai 能力矩阵页面权限，请联系管理员授权',
                  })
                : (error as Error)?.message
            }
            extra={
              !is403 ? (
                <Button type="primary" onClick={() => void refetch()}>
                  {t('common.retry', { defaultValue: '重试' })}
                </Button>
              ) : undefined
            }
          />
        </div>
      </div>
    );
  }

  const capabilities = data?.capabilities ?? [];

  return (
    <div className="kuaiai-ops-page">
      <div className="kuaiai-ops-inner">
        {header}

        {/* 局部刷新失败：保留旧数据，非阻断提示 */}
        {error && data ? (
          <Alert
            style={{ marginTop: 12 }}
            type="warning"
            showIcon
            message={t('app.kuaiai.ops.partialFailed', {
              defaultValue: '部分数据刷新失败，已保留上次结果',
            })}
            action={
              <Button size="small" onClick={() => void refetch()}>
                {t('common.retry', { defaultValue: '重试' })}
              </Button>
            }
          />
        ) : null}

        {/* 能力标签行 */}
        <div className="kuaiai-ops-cap-tags">
          {capabilities.map((cap) => (
            <Tag key={cap.key} color="blue" style={{ paddingInline: 12, lineHeight: '24px' }}>
              {cap.name}
            </Tag>
          ))}
        </div>

        {/* 指标行：null → —，点击按 display 权限启停 */}
        <div className="kuaiai-ops-metrics">
          {metricCards.map((m) => {
            const allowed = hasPermission(currentUser, m.perm);
            return (
              <MetricCard
                key={m.key}
                title={m.title}
                value={m.value}
                unit={m.unit}
                onClick={() => navigate(m.route)}
                disabled={!allowed}
                disabledReason={noAccessTip}
              />
            );
          })}
        </div>

        <Typography.Title level={4} className="kuaiai-ops-section-title">
          {t('app.kuaiai.hub.capabilitiesTitle', { defaultValue: '能力矩阵' })}
        </Typography.Title>

        <div className="kuaiai-ops-hub-main">
          <div className="kuaiai-ops-brand-card">
            <img
              className="kuaiai-ops-brand-visual"
              src={HUB_BRAND_VISUAL_URL}
              alt=""
              aria-hidden="true"
            />
            <div className="kuaiai-ops-brand-body">
              <Typography.Text strong>
                {t('app.kuaiai.name', { defaultValue: '星AI' })}
              </Typography.Text>
              <div
                style={{
                  marginTop: 4,
                  fontSize: 13,
                  color: 'var(--ant-color-text-secondary, rgba(0,0,0,.45))',
                }}
              >
                {t('app.kuaiai.hub.brandDesc', {
                  defaultValue: '面向制造场景的智能辅助能力矩阵',
                })}
              </div>
            </div>
          </div>
          <div className="kuaiai-ops-cap-grid">
            {capabilities.map(renderCapabilityCard)}
          </div>
        </div>
      </div>
    </div>
  );
};

export default HubPage;
