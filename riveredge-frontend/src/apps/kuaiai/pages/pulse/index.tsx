/**
 * KU-Pulse 异常感知页（/apps/kuaiai/pulse，spec 182 T6；设计 §6）。
 *
 * - 数据：GET /apps/kuaiai/operations/pulse（entry:read + pulse:display）；
 * - 五指标一行；按领域分节；异常卡三列（<1100 两列、<768 单列），卡片同高、
 *   跳转按钮贴底，跳转只使用服务端白名单 route；
 * - domain/severity 筛选写入 URL search params（可分享）；分页本地页状态；
 * - AbortController 取消旧请求 + reqId 守卫：旧响应不得覆盖新筛选；
 * - >400ms 出骨架、>15s 显示「仍在计算」+ 取消/重试；取消显示已取消态；
 * - complete=false → 「部分数据」标识 + 逐领域错误 Alert + 重试；
 *   not_connected 领域显示「尚未接入检测器」信息条；
 * - 空结果与加载失败严格区分，不伪造 0 正常。
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Empty,
  Pagination,
  Result,
  Select,
  Skeleton,
  Spin,
  Tag,
  Typography,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import OperationalPageHeader from '../../components/OperationalPageHeader';
import MetricCard from '../../components/MetricCard';
import { getPulse } from '../../services/operations';
import type {
  PulseDomain,
  PulseErrorOut,
  PulseGroupOut,
  PulseItemOut,
  PulseOut,
  PulseSeverity,
} from '../../types/operations';
import '../../ops.less';

const PAGE_SIZE = 60;
const SKELETON_DELAY_MS = 400;
const SLOW_MS = 15000;

const DOMAIN_OPTIONS: PulseDomain[] = [
  'production',
  'inventory',
  'sales',
  'quality',
  'equipment',
];

const SEVERITY_OPTIONS: PulseSeverity[] = [
  'critical',
  'error',
  'warning',
  'info',
];

const SEVERITY_TAG_COLOR: Record<string, string> = {
  critical: 'red',
  error: 'volcano',
  warning: 'gold',
  info: 'blue',
};

const PRIORITY_TAG_COLOR: Record<string, string> = {
  high: 'red',
  medium: 'default',
  low: 'default',
};

const DOMAIN_TAG_COLOR = 'geekblue';

type LoadStatus =
  | 'loading'
  | 'slow'
  | 'done'
  | 'error'
  | 'cancelled';

function isAbortError(err: unknown): boolean {
  const e = err as { name?: string; code?: string };
  return (
    e?.name === 'AbortError' ||
    e?.name === 'CanceledError' ||
    e?.code === 'ERR_CANCELED'
  );
}

const PulsePage: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const domainParam = (searchParams.get('domain') || '').trim();
  const severityParam = (searchParams.get('severity') || '').trim();
  const selectedDomains = useMemo(
    () =>
      domainParam
        .split(',')
        .map((d) => d.trim())
        .filter((d): d is PulseDomain =>
          DOMAIN_OPTIONS.includes(d as PulseDomain),
        ),
    [domainParam],
  );
  const severity = SEVERITY_OPTIONS.includes(severityParam as PulseSeverity)
    ? (severityParam as PulseSeverity)
    : undefined;
  // 只发白名单内的领域值：手改 ?domain=bogus 时退化为全量而非把脏参数透传给后端
  const domainQuery = useMemo(
    () => selectedDomains.join(','),
    [selectedDomains],
  );

  const [page, setPage] = useState(1);
  const [data, setData] = useState<PulseOut | null>(null);
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [showSkeleton, setShowSkeleton] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);

  const abortRef = useRef<AbortController | null>(null);
  const reqIdRef = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    abortRef.current?.abort();
    abortRef.current = controller;
    const reqId = ++reqIdRef.current;
    setStatus('loading');
    setLoadError(null);
    // 保留上次成功数据（设计 §2.3：刷新失败保留内容 + 非阻塞错误，不整页闪白）
    setShowSkeleton(false);

    const skeletonTimer = window.setTimeout(() => {
      if (reqIdRef.current === reqId) setShowSkeleton(true);
    }, SKELETON_DELAY_MS);
    const slowTimer = window.setTimeout(() => {
      if (reqIdRef.current === reqId) {
        setStatus((s) => (s === 'loading' ? 'slow' : s));
      }
    }, SLOW_MS);

    getPulse(
      {
        domain: domainQuery || undefined,
        severity,
        page,
        page_size: PAGE_SIZE,
      },
      controller.signal,
    )
      .then((res) => {
        if (reqIdRef.current !== reqId) return; // 旧响应不得覆盖新筛选
        setData(res);
        setStatus('done');
      })
      .catch((err) => {
        if (reqIdRef.current !== reqId) return;
        if (isAbortError(err)) {
          setStatus('cancelled');
          return;
        }
        setLoadError(err instanceof Error ? err : new Error(String(err)));
        setStatus('error');
      })
      .finally(() => {
        window.clearTimeout(skeletonTimer);
        window.clearTimeout(slowTimer);
        if (reqIdRef.current === reqId) setShowSkeleton(false);
      });

    return () => {
      window.clearTimeout(skeletonTimer);
      window.clearTimeout(slowTimer);
      controller.abort();
    };
  }, [domainQuery, severity, page, reloadTick]);

  // 卸载兜底取消
  useEffect(
    () => () => {
      abortRef.current?.abort();
    },
    [],
  );

  const retry = useCallback(() => setReloadTick((n) => n + 1), []);
  const cancelLoad = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const updateParams = useCallback(
    (domains: PulseDomain[], sev?: PulseSeverity) => {
      const next = new URLSearchParams(searchParams);
      if (domains.length) next.set('domain', domains.join(','));
      else next.delete('domain');
      if (sev) next.set('severity', sev);
      else next.delete('severity');
      // 筛选变化在同一批次回第一页：避免先携带旧 page 发一次瞬时请求再回 1
      setPage(1);
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const domainLabel = useCallback(
    (domain: string) =>
      t(`app.kuaiai.pulse.category.${domain}`, { defaultValue: domain }),
    [t],
  );

  const severityLabel = useCallback(
    (sev: string) =>
      t(`app.kuaiai.pulse.type.${sev}`, { defaultValue: sev }),
    [t],
  );

  const priorityLabel = useCallback(
    (pri: string) =>
      t(`app.kuaiai.pulse.priority.${pri}`, { defaultValue: pri }),
    [t],
  );

  const cardActionLabel = useCallback(
    (item: PulseItemOut) => {
      if (item.resource_type === 'work_order') {
        return t('app.kuaiai.pulse.viewWorkOrder', { defaultValue: '查看工单' });
      }
      if (item.resource_type === 'sales_order') {
        return t('app.kuaiai.pulse.viewSalesOrder', {
          defaultValue: '查看销售订单',
        });
      }
      return t('app.kuaiai.pulse.viewDetail', { defaultValue: '查看详情' });
    },
    [t],
  );

  const header = (
    <OperationalPageHeader
      title={t('app.kuaiai.pulse.title', { defaultValue: '异常感知' })}
      subtitle={t('app.kuaiai.pulse.subtitle', {
        defaultValue: '全局捕捉生产、库存、销售、质量与设备异常，分卡片展示',
      })}
      extra={
        <Button
          icon={<ReloadOutlined />}
          loading={status === 'loading' || status === 'slow'}
          onClick={retry}
          aria-label={t('common.refresh', { defaultValue: '刷新' })}
        >
          {t('common.refresh', { defaultValue: '刷新' })}
        </Button>
      }
    />
  );

  const filters = (
    <div className="kuaiai-ops-pulse-filters">
      <Select
        mode="multiple"
        allowClear
        maxTagCount="responsive"
        style={{ minWidth: 240 }}
        placeholder={t('app.kuaiai.pulse.filter.domain', {
          defaultValue: '领域（默认全部）',
        })}
        value={selectedDomains}
        onChange={(vals) => updateParams(vals as PulseDomain[], severity)}
        options={DOMAIN_OPTIONS.map((d) => ({
          value: d,
          label: domainLabel(d),
        }))}
        aria-label={t('app.kuaiai.pulse.filter.domain', {
          defaultValue: '领域筛选',
        })}
      />
      <Select
        allowClear
        style={{ minWidth: 160 }}
        placeholder={t('app.kuaiai.pulse.filter.severity', {
          defaultValue: '严重度（默认全部）',
        })}
        value={severity}
        onChange={(val) =>
          updateParams(selectedDomains, val as PulseSeverity | undefined)
        }
        options={SEVERITY_OPTIONS.map((s) => ({
          value: s,
          label: severityLabel(s),
        }))}
        aria-label={t('app.kuaiai.pulse.filter.severity', {
          defaultValue: '严重度筛选',
        })}
      />
    </div>
  );

  // 长加载：骨架（>400ms）；>15s「仍在计算」+ 取消/重试。
  // 已有数据时保留旧内容继续渲染（keep-stale），由页头刷新按钮展示加载态。
  if ((status === 'loading' || status === 'slow') && !data) {
    return (
      <div className="kuaiai-ops-page">
        <div className="kuaiai-ops-inner">
          {header}
          {filters}
          {status === 'slow' ? (
            <Alert
              style={{ marginTop: 16 }}
              type="info"
              showIcon
              message={t('app.kuaiai.pulse.stillComputing', {
                defaultValue: '仍在计算，数据量较大时可取消后重试',
              })}
              action={
                <>
                  <Button size="small" onClick={cancelLoad}>
                    {t('app.kuaiai.pulse.cancelLoad', {
                      defaultValue: '取消加载',
                    })}
                  </Button>
                  <Button size="small" type="primary" onClick={retry}>
                    {t('common.retry', { defaultValue: '重试' })}
                  </Button>
                </>
              }
            />
          ) : null}
          {showSkeleton ? (
            <>
              <div className="kuaiai-ops-pulse-metrics">
                {[0, 1, 2, 3, 4].map((i) => (
                  <div className="kuaiai-ops-metric" key={i}>
                    <Skeleton
                      active
                      paragraph={{ rows: 1 }}
                      title={{ width: '50%' }}
                    />
                  </div>
                ))}
              </div>
              <div className="kuaiai-ops-pulse-grid">
                {[0, 1, 2, 3, 4, 5].map((i) => (
                  <div className="kuaiai-ops-pulse-card" key={i}>
                    <Skeleton
                      active
                      paragraph={{ rows: 3 }}
                      title={{ width: '60%' }}
                    />
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="kuaiai-ops-pulse-loading">
              <Spin />
            </div>
          )}
        </div>
      </div>
    );
  }

  if (status === 'cancelled' && !data) {
    return (
      <div className="kuaiai-ops-page">
        <div className="kuaiai-ops-inner">
          {header}
          {filters}
          <Result
            status="info"
            title={t('app.kuaiai.pulse.cancelled', {
              defaultValue: '已取消加载',
            })}
            extra={
              <Button type="primary" onClick={retry}>
                {t('common.retry', { defaultValue: '重试' })}
              </Button>
            }
          />
        </div>
      </div>
    );
  }

  // 整页失败 / 403：保留页头，与加载空态严格区分
  if (status === 'error' && !data) {
    const statusCode = (loadError as any)?.response?.status as
      | number
      | undefined;
    const is403 = statusCode === 403;
    return (
      <div className="kuaiai-ops-page">
        <div className="kuaiai-ops-inner">
          {header}
          {filters}
          <Result
            status={is403 ? '403' : 'error'}
            title={
              is403
                ? t('app.kuaiai.ops.forbidden', { defaultValue: '缺少功能权限' })
                : t('app.kuaiai.pulse.loadFailed', {
                    defaultValue: '加载异常感知失败',
                  })
            }
            subTitle={
              is403
                ? t('app.kuaiai.ops.forbiddenHint', {
                    defaultValue:
                      '当前账号缺少对应页面权限，请联系管理员授权',
                  })
                : loadError?.message
            }
            extra={
              !is403 ? (
                <Button type="primary" onClick={retry}>
                  {t('common.retry', { defaultValue: '重试' })}
                </Button>
              ) : undefined
            }
          />
        </div>
      </div>
    );
  }

  const summary = data?.summary;
  const groups: PulseGroupOut[] = data?.groups ?? [];
  const domainErrors: PulseErrorOut[] = (data?.errors ?? []).filter(
    (e) => e.code !== 'not_connected',
  );
  const notConnected: PulseErrorOut[] = (data?.errors ?? []).filter(
    (e) => e.code === 'not_connected',
  );

  const metricCards = [
    {
      key: 'total',
      title: t('app.kuaiai.pulse.metric.total', { defaultValue: '异常总数' }),
      value: summary?.total ?? null,
    },
    {
      key: 'high',
      title: t('app.kuaiai.pulse.metric.highPriority', {
        defaultValue: '高优先级',
      }),
      value: summary?.high_priority ?? null,
    },
    {
      key: 'critical',
      title: t('app.kuaiai.pulse.metric.urgent', { defaultValue: '紧急' }),
      value: summary?.critical ?? null,
    },
    {
      key: 'attention',
      title: t('app.kuaiai.pulse.metric.attention', {
        defaultValue: '警告与错误',
      }),
      value: summary?.warning_or_error ?? null,
    },
    {
      key: 'domains',
      title: t('app.kuaiai.pulse.metric.domains', {
        defaultValue: '涉及场景',
      }),
      value: summary?.domain_count ?? null,
    },
  ];

  const renderCard = (item: PulseItemOut) => (
    <div className="kuaiai-ops-pulse-card" key={item.id}>
      <div className="kuaiai-ops-pulse-card-tags">
        <Tag color={SEVERITY_TAG_COLOR[item.severity] ?? 'default'}>
          {severityLabel(item.severity)}
        </Tag>
        <Tag color={DOMAIN_TAG_COLOR}>{domainLabel(item.domain)}</Tag>
        <Tag color={PRIORITY_TAG_COLOR[item.priority] ?? 'default'}>
          {priorityLabel(item.priority)}
        </Tag>
      </div>
      <div className="kuaiai-ops-pulse-card-title">{item.title}</div>
      <div className="kuaiai-ops-pulse-card-fact">{item.fact}</div>
      <div className="kuaiai-ops-pulse-card-suggestion">{item.suggestion}</div>
      <div className="kuaiai-ops-pulse-card-foot">
        {item.route ? (
          <Button
            type="link"
            size="small"
            style={{ paddingInline: 0 }}
            onClick={() => navigate(item.route as string)}
          >
            {cardActionLabel(item)}
          </Button>
        ) : null}
      </div>
    </div>
  );

  return (
    <div className="kuaiai-ops-page">
      <div className="kuaiai-ops-inner">
        {header}
        {filters}

        {/* 刷新失败但已有数据：非阻塞错误 + 重试，保留上次结果 */}
        {status === 'error' && data ? (
          <Alert
            style={{ marginTop: 16 }}
            type="warning"
            showIcon
            message={t('app.kuaiai.ops.partialFailed', {
              defaultValue: '部分数据刷新失败，已保留上次结果',
            })}
            action={
              <Button size="small" onClick={retry}>
                {t('common.retry', { defaultValue: '重试' })}
              </Button>
            }
          />
        ) : null}

        {/* 局部失败：「部分数据」标识 + 逐领域错误 Alert + 重试 */}
        {data && !data.complete ? (
          <Alert
            style={{ marginTop: 16 }}
            type="warning"
            showIcon
            message={t('app.kuaiai.pulse.partialData', {
              defaultValue: '部分数据',
            })}
            description={domainErrors
              .map((e) => `${domainLabel(e.domain)}：${e.message}`)
              .join('；')}
            action={
              <Button size="small" onClick={retry}>
                {t('common.retry', { defaultValue: '重试' })}
              </Button>
            }
          />
        ) : null}

        {/* 尚未接入检测器的领域：信息提示，不计为异常也不伪装 0 正常 */}
        {notConnected.length ? (
          <Alert
            style={{ marginTop: 12 }}
            type="info"
            showIcon
            message={t('app.kuaiai.pulse.notConnected', {
              defaultValue: '以下领域尚未接入检测器：{{domains}}',
              domains: notConnected
                .map((e) => domainLabel(e.domain))
                .join('、'),
            })}
          />
        ) : null}

        {/* 五指标一行 */}
        <div className="kuaiai-ops-pulse-metrics">
          {metricCards.map((m) => (
            <MetricCard key={m.key} title={m.title} value={m.value} />
          ))}
        </div>

        {/* 领域分节：空领域不渲染分组 */}
        {groups.map((g) => (
          <section className="kuaiai-ops-pulse-section" key={g.domain}>
            <Typography.Title level={4} className="kuaiai-ops-pulse-section-title">
              {g.label}
              <span className="kuaiai-ops-pulse-section-count">
                {t('app.kuaiai.pulse.groupCount', {
                  defaultValue: '{{count}} 条',
                  count: g.count,
                })}
              </span>
            </Typography.Title>
            <div className="kuaiai-ops-pulse-grid">
              {g.items.map(renderCard)}
            </div>
          </section>
        ))}

        {/* 真实空态（与失败严格区分） */}
        {data && !groups.length ? (
          <Empty
            style={{ marginTop: 48 }}
            description={t('app.kuaiai.pulse.empty', {
              defaultValue: '暂无异常，系统运行正常',
            })}
          />
        ) : null}

        {summary && summary.total > PAGE_SIZE ? (
          <div className="kuaiai-ops-pulse-pagination">
            <Pagination
              current={page}
              pageSize={PAGE_SIZE}
              total={summary.total}
              showSizeChanger={false}
              onChange={setPage}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default PulsePage;
