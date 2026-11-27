/**
 * 物料健康助手抽屉与触发按钮（KU-AI 专业应用组件）。
 *
 * 调用既有 /api/v1/apps/master-data/materials/health-check，按物料聚合展示
 * 完备度/合理性与编码重复问题，支持按类别筛选与点击主编码直达编辑。
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Button,
  Empty,
  Progress,
  Result,
  Segmented,
  Space,
  Tag,
  Typography,
  theme,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import {
  DetailDrawerTemplate,
  DRAWER_CONFIG,
} from '../../../../components/layout-templates';
import { UniAiButton } from '../../../../components/uni-ai-button/UniAiButton';
import { UniAiLottieIcon } from '../../../../components/uni-ai-button/UniAiLottieIcon';
import { formatFastApiDetail } from '../../../../utils/errorHandler';
import { materialApi } from '../../../master-data/services/material';
import type {
  MaterialHealthCategory,
  MaterialHealthCheckResult,
  MaterialHealthIssue,
  MaterialHealthMaterialRef,
  MaterialHealthSeverity,
} from '../../../master-data/types/materialHealth';
import { useKuaiaiEntryAvailable } from '../../hooks/useKuaiaiEntryAvailable';
import './MaterialHealthAssistant.css';

const { Text, Paragraph } = Typography;

const I18N_PREFIX = 'app.kuaiai.materialHealth';

type HealthFilter = 'all' | 'completeness' | 'duplicate';

interface GroupedMaterialIssues {
  material: MaterialHealthMaterialRef;
  issues: MaterialHealthIssue[];
  maxSeverity: MaterialHealthSeverity;
}

const SEVERITY_RANK: Record<MaterialHealthSeverity, number> = {
  error: 0,
  warning: 1,
  info: 2,
};

function resolveMaxSeverity(issues: MaterialHealthIssue[]): MaterialHealthSeverity {
  return issues.reduce<MaterialHealthSeverity>(
    (best, issue) => (SEVERITY_RANK[issue.severity] < SEVERITY_RANK[best] ? issue.severity : best),
    'info',
  );
}

function groupIssuesByMaterial(issues: MaterialHealthIssue[]): GroupedMaterialIssues[] {
  const byUuid = new Map<string, GroupedMaterialIssues>();
  for (const issue of issues) {
    for (const mat of issue.materials) {
      let bucket = byUuid.get(mat.uuid);
      if (!bucket) {
        bucket = { material: mat, issues: [], maxSeverity: 'info' };
        byUuid.set(mat.uuid, bucket);
      }
      if (!bucket.issues.some((existing) => existing.id === issue.id)) {
        bucket.issues.push(issue);
      }
    }
  }
  return Array.from(byUuid.values())
    .map((bucket) => ({
      ...bucket,
      maxSeverity: resolveMaxSeverity(bucket.issues),
    }))
    .sort((a, b) => {
      const rankDiff = SEVERITY_RANK[a.maxSeverity] - SEVERITY_RANK[b.maxSeverity];
      if (rankDiff !== 0) return rankDiff;
      return a.material.mainCode.localeCompare(b.material.mainCode, undefined, { numeric: true });
    });
}

function renderSeverityTag(
  severity: MaterialHealthSeverity,
  t: (key: string) => string,
): React.ReactNode {
  const map: Record<
    MaterialHealthSeverity,
    { color: string; icon: React.ReactNode; label: string }
  > = {
    error: {
      color: 'error',
      icon: <CloseCircleOutlined />,
      label: t(`${I18N_PREFIX}.severityError`),
    },
    warning: {
      color: 'warning',
      icon: <ExclamationCircleOutlined />,
      label: t(`${I18N_PREFIX}.severityWarning`),
    },
    info: {
      color: 'default',
      icon: <InfoCircleOutlined />,
      label: t(`${I18N_PREFIX}.severityInfo`),
    },
  };
  const cfg = map[severity] ?? map.info;
  return (
    <Tag icon={cfg.icon} color={cfg.color}>
      {cfg.label}
    </Tag>
  );
}

function formatCategoryLabel(
  category: MaterialHealthCategory,
  t: (key: string) => string,
): string {
  return t(`${I18N_PREFIX}.category.${category}`);
}

export interface MaterialHealthAssistantDrawerProps {
  open: boolean;
  onClose: () => void;
  groupId?: number;
  onOpenMaterial?: (materialUuid: string) => void;
}

export const MaterialHealthAssistantDrawer: React.FC<MaterialHealthAssistantDrawerProps> = ({
  open,
  onClose,
  groupId,
  onOpenMaterial,
}) => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<MaterialHealthCheckResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [filter, setFilter] = useState<HealthFilter>('all');

  const runHealthCheck = useCallback(async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const data = await materialApi.healthCheck({
        groupId: groupId ?? undefined,
        mastersOnly: true,
      });
      setResult(data);
    } catch (err: unknown) {
      setResult(null);
      const responseDetail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data
        ?.detail;
      const msg =
        formatFastApiDetail(responseDetail) ||
        (err instanceof Error ? err.message : '') ||
        t(`${I18N_PREFIX}.checkFailed`);
      setErrorMessage(msg);
    } finally {
      setLoading(false);
    }
  }, [groupId, t]);

  useEffect(() => {
    if (open) {
      setFilter('all');
      void runHealthCheck();
    } else {
      setResult(null);
      setErrorMessage(null);
    }
  }, [open, runHealthCheck]);

  const filteredIssues = useMemo(() => {
    if (!result) return [];
    if (filter === 'all') return result.issues;
    if (filter === 'completeness') {
      return result.issues.filter(
        (item) => item.category === 'completeness' || item.category === 'reasonableness',
      );
    }
    return result.issues.filter((item) => item.category.startsWith('duplicate'));
  }, [result, filter]);

  const groupedIssues = useMemo(() => groupIssuesByMaterial(filteredIssues), [filteredIssues]);

  const healthScore = result?.summary.healthScore ?? 0;
  const scoreColor =
    healthScore >= 85
      ? token.colorSuccess
      : healthScore >= 60
        ? token.colorWarning
        : token.colorError;

  const handleOpenMaterial = useCallback(
    (uuid: string) => {
      onOpenMaterial?.(uuid);
      onClose();
    },
    [onOpenMaterial, onClose],
  );

  const hasResult = Boolean(result);
  const hasErrorOnly = Boolean(errorMessage) && !hasResult && !loading;
  const drawerLoading = loading || (!hasResult && !hasErrorOnly);

  return (
    <DetailDrawerTemplate
      title={
        <span className="material-health-drawer-title">
          <UniAiLottieIcon size={22} />
          <span>{t(`${I18N_PREFIX}.title`)}</span>
        </span>
      }
      open={open}
      onClose={onClose}
      size={DRAWER_CONFIG.STANDARD_WIDTH}
      loading={drawerLoading}
      extra={
        hasResult ? (
          <Button size="small" onClick={() => void runHealthCheck()} loading={loading}>
            {t('common.refresh')}
          </Button>
        ) : null
      }
      plainBody={
        hasErrorOnly ? (
          <Result
            status="error"
            title={errorMessage}
            extra={
              <Button type="primary" onClick={() => void runHealthCheck()} loading={loading}>
                {t(`${I18N_PREFIX}.retry`)}
              </Button>
            }
          />
        ) : result ? (
          <Space orientation="vertical" size="medium" style={{ width: '100%' }}>
            <div
              style={{
                padding: 16,
                borderRadius: token.borderRadiusLG,
                background: token.colorFillQuaternary,
                border: `1px solid ${token.colorBorderSecondary}`,
              }}
            >
              <Space align="center" style={{ width: '100%', justifyContent: 'space-between' }}>
                <div>
                  <Text type="secondary">{t(`${I18N_PREFIX}.scoreLabel`)}</Text>
                  <div
                    style={{
                      fontSize: 28,
                      fontWeight: 700,
                      color: scoreColor,
                      lineHeight: 1.2,
                    }}
                  >
                    {result.summary.healthScore}
                  </div>
                </div>
                <Progress
                  type="circle"
                  percent={result.summary.healthScore}
                  size={72}
                  strokeColor={scoreColor}
                  format={(percent) => `${percent}`}
                />
              </Space>
              <Paragraph
                type="secondary"
                style={{ marginBottom: 0, marginTop: 12, fontSize: 12 }}
              >
                {t(`${I18N_PREFIX}.summaryStats`, {
                  total: result.summary.totalMaterials,
                  issues: result.summary.issueCount,
                  completeness: result.summary.completenessCount,
                  duplicate: result.summary.duplicateCount,
                })}
              </Paragraph>
            </div>

            <Segmented
              block
              value={filter}
              onChange={(val) => setFilter(val as HealthFilter)}
              options={[
                { label: t(`${I18N_PREFIX}.filterAll`), value: 'all' },
                { label: t(`${I18N_PREFIX}.filterCompleteness`), value: 'completeness' },
                { label: t(`${I18N_PREFIX}.filterDuplicate`), value: 'duplicate' },
              ]}
            />

            {groupedIssues.length === 0 ? (
              <Empty
                image={
                  <CheckCircleOutlined style={{ fontSize: 48, color: token.colorSuccess }} />
                }
                description={t(`${I18N_PREFIX}.noIssues`)}
              />
            ) : (
              <div className="material-health-issue-list">
                {groupedIssues.map((group) => (
                  <div className="material-health-issue-row" key={group.material.uuid}>
                    <Space orientation="vertical" size={8} style={{ width: '100%' }}>
                      <div className="material-health-material-header">
                        {onOpenMaterial ? (
                          <Button
                            type="link"
                            className="material-health-issue-code-link"
                            onClick={() => handleOpenMaterial(group.material.uuid)}
                          >
                            {group.material.mainCode}
                          </Button>
                        ) : (
                          <Text strong>{group.material.mainCode}</Text>
                        )}
                        {group.material.name ? (
                          <Text
                            type="secondary"
                            ellipsis
                            className="material-health-material-name"
                          >
                            {group.material.name}
                          </Text>
                        ) : null}
                        <Tag>
                          {t(`${I18N_PREFIX}.issueCount`, { count: group.issues.length })}
                        </Tag>
                      </div>
                      <ul className="material-health-material-issues">
                        {group.issues.map((issue) => (
                          <li className="material-health-material-issue" key={issue.id}>
                            <Space wrap size={[4, 4]} align="start">
                              {renderSeverityTag(issue.severity, t)}
                              <Tag>{formatCategoryLabel(issue.category, t)}</Tag>
                              <Text type="secondary">{issue.title}</Text>
                            </Space>
                          </li>
                        ))}
                      </ul>
                    </Space>
                  </div>
                ))}
              </div>
            )}
          </Space>
        ) : (
          <Empty description={t(`${I18N_PREFIX}.empty`)} />
        )
      }
    />
  );
};

export interface MaterialHealthAssistantTriggerProps {
  groupId?: number;
  onOpenMaterial?: (materialUuid: string) => void;
  hideTrigger?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export const MaterialHealthAssistantTrigger: React.FC<MaterialHealthAssistantTriggerProps> = ({
  groupId,
  onOpenMaterial,
  hideTrigger = false,
  open,
  onOpenChange,
}) => {
  const { t } = useTranslation();
  const [innerOpen, setInnerOpen] = useState(false);
  const kuaiaiAvailable = useKuaiaiEntryAvailable();

  const isControlled = open !== undefined;
  const resolvedOpen = isControlled ? Boolean(open) : innerOpen;

  const setOpenState = useCallback(
    (next: boolean) => {
      if (!isControlled) {
        setInnerOpen(next);
      }
      onOpenChange?.(next);
    },
    [isControlled, onOpenChange],
  );

  if (!kuaiaiAvailable) return null;

  return (
    <>
      {!hideTrigger && (
        <UniAiButton onClick={() => setOpenState(true)}>
          {t(`${I18N_PREFIX}.trigger`)}
        </UniAiButton>
      )}
      <MaterialHealthAssistantDrawer
        open={resolvedOpen}
        onClose={() => setOpenState(false)}
        groupId={groupId}
        onOpenMaterial={onOpenMaterial}
      />
    </>
  );
};

export default MaterialHealthAssistantTrigger;
