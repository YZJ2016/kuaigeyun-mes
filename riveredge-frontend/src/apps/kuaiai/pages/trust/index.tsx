/**
 * KU-Trust 信任中心（/apps/kuaiai/trust，spec 184 T3；设计 §8/§11.5）。
 *
 * - 门控：entry:read + trust:display 双码缺一即 403，不发任何请求；
 * - 数据：GET /apps/kuaiai/operations/trust（只反映当前用户，无 user_id）；
 *   审计表直接请求既有 /core/ai/audit/logs（entry:read，不改契约）；
 * - 三张等宽卡（约 140px/16px 间距）：RBAC/HITL/审计，状态只
 *   ready|partial|not_ready；HITL 未接入时固定 not_ready + 未完成时态文案；
 * - 权限 chip：权限码 + 拥有/未拥有（文字非仅颜色）；只展示当前用户持有情况；
 * - 审计表：时间180/能力120/路由自适应/耗时100/状态90；
 *   2xx 绿、4xx 橙、5xx 红并显示数值状态码；
 *   error_message 无专门高权限入口，本页一律不渲染（服务端已留字段）。
 */

import React, { useState } from 'react';
import {
  Button,
  Empty,
  Result,
  Skeleton,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  FileSearchOutlined,
  InfoCircleOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  UserSwitchOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import type { ColumnsType } from 'antd/es/table';
import { useCurrentUser } from '../../../../hooks/useCurrentUser';
import { hasAllPermissions } from '../../../../utils/permission';
import OperationalPageHeader from '../../components/OperationalPageHeader';
import { getTrust, listAiAuditLogs } from '../../services/operations';
import { auditStatusTone, capabilityLabel } from '../../opsData';
import type {
  AiAuditLogItemOut,
  OperationalStatus,
  TrustCardOut,
} from '../../types/operations';
import '../../ops.less';

const REQUIRED_PERMISSIONS = ['kuaiai:entry:read', 'kuaiai:trust:display'];
const AUDIT_PAGE_SIZE = 20;

const STATUS_TAG: Record<OperationalStatus, { color: string; key: string; fallback: string }> = {
  ready: { color: 'success', key: 'app.kuaiai.catalog.status.ready', fallback: '已就绪' },
  partial: { color: 'warning', key: 'app.kuaiai.catalog.status.degraded', fallback: '降级可用' },
  not_ready: { color: 'default', key: 'app.kuaiai.catalog.status.blocked', fallback: '不可用' },
};

const CARD_ICON: Record<string, React.ReactNode> = {
  rbac: <SafetyCertificateOutlined />,
  hitl: <UserSwitchOutlined />,
  audit: <FileSearchOutlined />,
};

function statusTag(status: OperationalStatus, t: (k: string, o?: any) => string) {
  const conf = STATUS_TAG[status] ?? STATUS_TAG.not_ready;
  return <Tag color={conf.color}>{t(conf.key, { defaultValue: conf.fallback })}</Tag>;
}

const TrustPage: React.FC = () => {
  const { t } = useTranslation();
  const currentUser = useCurrentUser();
  // 双码门控：缺任一码 → 403 视图，enabled=false 保证不发任何请求
  const allowed = hasAllPermissions(currentUser, REQUIRED_PERMISSIONS);
  const [page, setPage] = useState(1);

  const trustQuery = useQuery({
    queryKey: ['kuaiai', 'operations', 'trust'],
    queryFn: ({ signal }) => getTrust(signal),
    enabled: allowed,
    staleTime: 30_000,
  });

  const auditQuery = useQuery({
    queryKey: ['kuaiai', 'core-ai', 'audit-logs', { page }],
    queryFn: ({ signal }) =>
      listAiAuditLogs({ page, page_size: AUDIT_PAGE_SIZE }, signal),
    enabled: allowed,
    placeholderData: (prev) => prev,
  });

  const refresh = () => {
    void trustQuery.refetch();
    void auditQuery.refetch();
  };

  const header = (
    <OperationalPageHeader
      title={t('app.kuaiai.trust.title', { defaultValue: '信任中心' })}
      subtitle={t('app.kuaiai.trust.subtitle', {
        defaultValue: '权限边界、人审门控与全链路审计',
      })}
      extra={
        <Button
          icon={<ReloadOutlined />}
          loading={trustQuery.isFetching || auditQuery.isFetching}
          onClick={refresh}
          aria-label={t('common.refresh', { defaultValue: '刷新' })}
        >
          {t('common.refresh', { defaultValue: '刷新' })}
        </Button>
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

  const trustError = trustQuery.error as any;
  const trustFailed = trustQuery.isError && !trustQuery.data;
  const trust403 = trustError?.response?.status === 403;

  const auditError = auditQuery.error as any;
  const auditFailed = auditQuery.isError && !auditQuery.data;
  const audit403 = auditError?.response?.status === 403;

  const renderCard = (card: TrustCardOut) => {
    const tag = statusTag(card.status, t);
    return (
      <div className="kuaiai-ops-trust-card" key={card.key}>
        <div className="kuaiai-ops-trust-card-head">
          <span className="kuaiai-ops-trust-card-icon" aria-hidden="true">
            {CARD_ICON[card.key] ?? <InfoCircleOutlined />}
          </span>
          <span className="kuaiai-ops-trust-card-name">{card.title}</span>
          {card.evidence?.length ? (
            <Tooltip
              title={
                <ul className="kuaiai-ops-trust-evidence">
                  {card.evidence.map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
              }
            >
              {tag}
            </Tooltip>
          ) : (
            tag
          )}
        </div>
        <div className="kuaiai-ops-trust-card-desc">{card.description || '—'}</div>
      </div>
    );
  };

  const auditColumns: ColumnsType<AiAuditLogItemOut> = [
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
      render: (v: string | null) =>
        capabilityLabel(
          v,
          t('app.kuaiai.insights.unknownCap', { defaultValue: '未分类' }),
        ),
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
      render: (v: number | null) => (v === null || v === undefined ? '—' : `${v} ms`),
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

  const auditSection = auditFailed ? (
    <Result
      status={audit403 ? '403' : 'error'}
      title={
        audit403
          ? t('app.kuaiai.ops.forbidden', { defaultValue: '缺少功能权限' })
          : t('app.kuaiai.trust.loadFailed', { defaultValue: '加载审计日志失败' })
      }
      subTitle={
        audit403
          ? t('app.kuaiai.trust.auditForbidden', {
              defaultValue: '当前账号缺少 kuaiai:entry:read，无法读取审计日志',
            })
          : auditError?.message
      }
      extra={
        !audit403 ? (
          <Button type="primary" onClick={() => void auditQuery.refetch()}>
            {t('common.retry', { defaultValue: '重试' })}
          </Button>
        ) : undefined
      }
    />
  ) : (
    <Table<AiAuditLogItemOut>
      rowKey="uuid"
      size="middle"
      loading={auditQuery.isPending || auditQuery.isFetching}
      columns={auditColumns}
      dataSource={auditQuery.data?.items ?? []}
      locale={{
        emptyText: (
          <Empty
            description={
              auditQuery.data?.empty_reason ||
              t('app.kuaiai.trust.auditEmpty', { defaultValue: '暂无审计记录' })
            }
          />
        ),
      }}
      pagination={{
        current: page,
        pageSize: AUDIT_PAGE_SIZE,
        total: auditQuery.data?.total ?? 0,
        showSizeChanger: false,
        showTotal: (total) =>
          t('app.kuaiai.trust.auditTotal', { defaultValue: '共 {{total}} 条', total }),
        onChange: setPage,
      }}
      scroll={{ x: 720 }}
    />
  );

  return (
    <div className="kuaiai-ops-page">
      <div className="kuaiai-ops-inner">
        {header}

        {trustQuery.isPending ? (
          <div className="kuaiai-ops-trust-grid">
            {[0, 1, 2].map((i) => (
              <div className="kuaiai-ops-trust-card" key={i}>
                <Skeleton active paragraph={{ rows: 2 }} title={{ width: '50%' }} />
              </div>
            ))}
          </div>
        ) : trustFailed ? (
          <Result
            status={trust403 ? '403' : 'error'}
            title={
              trust403
                ? t('app.kuaiai.ops.forbidden', { defaultValue: '缺少功能权限' })
                : t('app.kuaiai.trust.loadFailed', {
                    defaultValue: '加载审计日志失败',
                  })
            }
            subTitle={
              trust403
                ? t('app.kuaiai.ops.forbiddenHint', {
                    defaultValue: '当前账号缺少对应页面权限，请联系管理员授权',
                  })
                : trustError?.message
            }
            extra={
              !trust403 ? (
                <Button type="primary" onClick={() => void trustQuery.refetch()}>
                  {t('common.retry', { defaultValue: '重试' })}
                </Button>
              ) : undefined
            }
          />
        ) : (
          <>
            <div className="kuaiai-ops-trust-grid">
              {(trustQuery.data?.cards ?? []).map(renderCard)}
            </div>

            <Typography.Title level={4} className="kuaiai-ops-section-title">
              {t('app.kuaiai.trust.permissionsTitle', {
                defaultValue: '相关权限码',
              })}
            </Typography.Title>
            <div className="kuaiai-ops-trust-chips">
              {(trustQuery.data?.permissions ?? []).map((p) => (
                <Tag
                  key={p.code}
                  className="kuaiai-ops-trust-chip"
                  color={p.granted ? 'success' : 'default'}
                  icon={
                    p.granted ? <CheckCircleOutlined /> : <CloseCircleOutlined />
                  }
                >
                  {p.code}
                  <span className="kuaiai-ops-trust-chip-state">
                    {p.granted
                      ? t('app.kuaiai.trust.permGranted', { defaultValue: '拥有' })
                      : t('app.kuaiai.trust.permMissing', { defaultValue: '未拥有' })}
                  </span>
                </Tag>
              ))}
            </div>
          </>
        )}

        <Typography.Title level={4} className="kuaiai-ops-section-title">
          {t('app.kuaiai.trust.auditTitle', { defaultValue: '审计日志' })}
        </Typography.Title>
        <div className="kuaiai-ops-trust-audit">{auditSection}</div>

        <Typography.Paragraph className="kuaiai-ops-trust-note" type="secondary">
          {t('app.kuaiai.trust.actHint', {
            defaultValue:
              '写操作仍受业务单据原权限与服务校验约束；人工确认闸尚未接入，接入后本页同步更新状态。',
          })}
        </Typography.Paragraph>
      </div>
    </div>
  );
};

export default TrustPage;
