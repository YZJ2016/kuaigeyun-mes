/**
 * 星AI 能力矩阵页（/apps/kuaiai/hub，spec 181 T7；spec 191 场景卡绑定；
 * spec 222 分类分组 + 收起记忆 + 检索）。
 *
 * - 数据：GET /apps/kuaiai/operations/hub?days=7（模型/四指标/能力卡，局部降级）；
 * - 能力卡入口：ask 卡打开既有 KU-Ask 抽屉（纯对话路径 A，capabilityMode=ask）；
 *   场景卡（带 scene_key）打开抽屉并写入 agentKey + agentId +
 *   capabilityMode=query（spec 191，服务端 guard_scene_agent_key 全量复核）；
 *   not_ready / 无路由 / 无目标权限一律禁用 + Tooltip，不跳 404；
 * - 指标卡点击进 /insights、/pulse、/corpus，缺 display 权限禁用；
 * - 指标为 null 显示「—」，绝不伪造 0；整页失败 Result + 重试，403 Result；
 * - 场景卡按 category 分组（组头=分类名+卡数+收起/展开，收起集合存
 *   localStorage 跨会话恢复，默认全展开）；ask 卡置顶不参与分组；
 * - 页头检索框即时过滤卡名/描述/分类名（大小写不敏感），命中分类强制
 *   展开，ask 卡始终显示，无命中显示「无匹配场景」空态而非加载失败。
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Empty,
  Input,
  Result,
  Skeleton,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import { ReloadOutlined, RightOutlined } from '@ant-design/icons';
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

/** spec 222：场景卡分类 key → 组头中文名（与后端 SCENE_CATEGORIES 闭集对齐） */
const CATEGORY_LABELS: Record<string, { key: string; fallback: string }> = {
  plan: { key: 'app.kuaiai.hub.category.plan', fallback: '计划' },
  production: { key: 'app.kuaiai.hub.category.production', fallback: '生产' },
  quality: { key: 'app.kuaiai.hub.category.quality', fallback: '质量' },
  inventory: { key: 'app.kuaiai.hub.category.inventory', fallback: '库存' },
  purchase: { key: 'app.kuaiai.hub.category.purchase', fallback: '采购' },
  equipment: { key: 'app.kuaiai.hub.category.equipment', fallback: '设备' },
  engineering: { key: 'app.kuaiai.hub.category.engineering', fallback: '工程' },
  management: { key: 'app.kuaiai.hub.category.management', fallback: '管理' },
  general: { key: 'app.kuaiai.hub.category.general', fallback: '通用' },
};

/** spec 222：已收起 category key 数组的 localStorage 键（默认全展开） */
const COLLAPSED_CATEGORIES_KEY = 'kuaiai.hub.collapsed_categories';

function readCollapsedCategories(): string[] {
  try {
    const raw = localStorage.getItem(COLLAPSED_CATEGORIES_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed)
      ? parsed.filter((v): v is string => typeof v === 'string')
      : [];
  } catch {
    return [];
  }
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
    (
      capabilityMode?: AiCapabilityMode,
      scene?: { agentKey: string; agentId?: string },
    ) => {
      setContext({
        screen: '/apps/kuaiai/hub',
        screenLabel: t('app.kuaiai.hub.title', { defaultValue: '能力矩阵' }),
        ...(capabilityMode ? { capabilityMode } : {}),
        ...(scene?.agentKey ? { agentKey: scene.agentKey } : {}),
        ...(scene?.agentId ? { agentId: scene.agentId } : {}),
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

  // spec 222：收起集合（localStorage 跨会话恢复）+ 页头检索
  const [collapsedCategories, setCollapsedCategories] = useState<string[]>(
    readCollapsedCategories,
  );
  const [keyword, setKeyword] = useState('');

  useEffect(() => {
    try {
      localStorage.setItem(
        COLLAPSED_CATEGORIES_KEY,
        JSON.stringify(collapsedCategories),
      );
    } catch {
      // localStorage 不可用时收起状态仅本次会话生效
    }
  }, [collapsedCategories]);

  const toggleCategory = useCallback((cat: string) => {
    setCollapsedCategories((prev) =>
      prev.includes(cat) ? prev.filter((k) => k !== cat) : [...prev, cat],
    );
  }, []);

  const categoryLabel = useCallback(
    (cat: string): string => {
      const conf = CATEGORY_LABELS[cat] ?? CATEGORY_LABELS.general;
      return t(conf.key, { defaultValue: conf.fallback });
    },
    [t],
  );

  const normalizedKeyword = keyword.trim().toLowerCase();

  // 分组渲染：ask 卡置顶不参与分组；分类组序/卡序均保持后端返回序
  // （SCENE_TEMPLATES 顺序，首次出现次序）；检索只显示命中卡且分类强制展开
  const hubGroups = useMemo(() => {
    const caps = data?.capabilities ?? [];
    const ask = caps.find((c) => c.key === 'ask') ?? null;
    const searching = normalizedKeyword.length > 0;
    const groups: { key: string; label: string; cards: HubCapabilityOut[] }[] = [];
    const byKey = new Map<string, (typeof groups)[number]>();
    for (const cap of caps) {
      if (cap.key === 'ask') continue;
      const cat = cap.category && cap.category.trim() ? cap.category.trim() : 'general';
      if (searching) {
        const haystack =
          `${cap.name ?? ''}\n${cap.description ?? ''}\n${cat}\n${categoryLabel(cat)}`.toLowerCase();
        if (!haystack.includes(normalizedKeyword)) continue;
      }
      let group = byKey.get(cat);
      if (!group) {
        group = { key: cat, label: categoryLabel(cat), cards: [] };
        byKey.set(cat, group);
        groups.push(group);
      }
      group.cards.push(cap);
    }
    return { ask, groups, searching };
  }, [data?.capabilities, normalizedKeyword, categoryLabel]);

  const renderCapabilityCard = (cap: HubCapabilityOut) => {
    const mode = ASSISTANT_CAP_MODE[cap.key];
    // spec 191：场景卡携带 scene_key，点击走档案装配（agentKey + agentId + query）
    const sceneKey = cap.scene_key ?? null;
    const isSceneCard = !mode && sceneKey != null;
    const usable = cap.status !== 'not_ready';
    const go = () => {
      if (isSceneCard) {
        openKuAsk('query', {
          agentKey: sceneKey as string,
          agentId:
            cap.agent_profile_id != null
              ? String(cap.agent_profile_id)
              : undefined,
        });
      } else if (mode) {
        openKuAsk(mode);
      } else if (cap.route) {
        navigate(cap.route);
      }
    };
    const opensAssistant = Boolean(mode) || isSceneCard;
    const disabled =
      !usable ||
      (opensAssistant ? !kuaiaiEntryAvailable : !canNavigateTo(cap.route));
    const reason = !usable
      ? cap.disabled_reason || t('app.kuaiai.ops.notReady', { defaultValue: '暂未就绪' })
      : disabled
        ? opensAssistant
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
          <Input.Search
            allowClear
            style={{ width: 240 }}
            placeholder={t('app.kuaiai.hub.searchPlaceholder', {
              defaultValue: '搜索场景名称、描述或分类',
            })}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            aria-label={t('app.kuaiai.hub.searchPlaceholder', {
              defaultValue: '搜索场景名称、描述或分类',
            })}
          />
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
            <div className="kuaiai-ops-cap-groups">
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
            title={t('app.kuaiai.ops.partialFailed', {
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
          <div className="kuaiai-ops-cap-groups">
            {/* ask 卡置顶，不参与分组与检索 */}
            {hubGroups.ask ? (
              <div className="kuaiai-ops-cap-grid">
                {renderCapabilityCard(hubGroups.ask)}
              </div>
            ) : null}
            {hubGroups.searching && hubGroups.groups.length === 0 ? (
              <div className="kuaiai-ops-hub-search-empty">
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('app.kuaiai.hub.searchEmpty', {
                    defaultValue: '无匹配场景',
                  })}
                />
              </div>
            ) : (
              hubGroups.groups.map((group) => {
                // 检索命中分类强制展开（不写入 localStorage）
                const isCollapsed =
                  !hubGroups.searching && collapsedCategories.includes(group.key);
                return (
                  <section className="kuaiai-ops-cap-group" key={group.key}>
                    <button
                      type="button"
                      className="kuaiai-ops-cap-group-head"
                      onClick={() => toggleCategory(group.key)}
                      aria-expanded={!isCollapsed}
                      aria-label={t('app.kuaiai.hub.category.groupAria', {
                        defaultValue: '{{name}}分类，{{count}} 个场景',
                        name: group.label,
                        count: group.cards.length,
                      })}
                    >
                      <RightOutlined
                        className="kuaiai-ops-cap-group-arrow"
                        rotate={isCollapsed ? 0 : 90}
                      />
                      <span className="kuaiai-ops-cap-group-name">{group.label}</span>
                      <span className="kuaiai-ops-cap-group-count">
                        {group.cards.length}
                      </span>
                      <span className="kuaiai-ops-cap-group-toggle">
                        {isCollapsed
                          ? t('app.kuaiai.hub.category.expand', {
                              defaultValue: '展开',
                            })
                          : t('common.collapse', { defaultValue: '收起' })}
                      </span>
                    </button>
                    {isCollapsed ? null : (
                      <div className="kuaiai-ops-cap-grid">
                        {group.cards.map(renderCapabilityCard)}
                      </div>
                    )}
                  </section>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default HubPage;
