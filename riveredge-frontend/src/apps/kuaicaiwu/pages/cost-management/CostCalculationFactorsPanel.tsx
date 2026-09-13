import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Collapse, Divider, List, Space, Spin, Steps, Tag, Typography } from 'antd';

export interface CostCalculationFactorAction {
  code: string;
  work_center_id?: number;
  cost_item_type?: string;
  work_order_id?: number;
  material_id?: number;
  operation_name?: string;
}

export interface CostCalculationFactor {
  key: string;
  category: string;
  status: 'ready' | 'missing' | 'warning';
  message: string;
  hint?: string;
  action?: CostCalculationFactorAction;
}

export interface CostCalculationReadiness {
  target_type?: string;
  target_id?: number;
  target_label?: string;
  work_order_id?: number;
  work_order_code?: string;
  ready: boolean;
  blocking_count: number;
  warning_count: number;
  factors: CostCalculationFactor[];
}

const STATUS_TAG: Record<CostCalculationFactor['status'], { color: string; labelKey: string }> = {
  ready: { color: 'success', labelKey: 'app.kuaicaiwu.costCalculation.factorStatus.ready' },
  missing: { color: 'error', labelKey: 'app.kuaicaiwu.costCalculation.factorStatus.missing' },
  warning: { color: 'warning', labelKey: 'app.kuaicaiwu.costCalculation.factorStatus.warning' },
};

const CATEGORY_ORDER = ['material', 'labor', 'manufacturing'] as const;

function buildActionPath(action: CostCalculationFactorAction, readiness: CostCalculationReadiness): string | null {
  const woId = action.work_order_id ?? readiness.work_order_id ?? readiness.target_id;
  switch (action.code) {
    case 'standard_cost_work_center_rate':
      if (!action.work_center_id || !action.cost_item_type) return null;
      return (
        `/apps/kuaicaiwu/cost-management/standard-costs?prefill=1&target_type=work_center` +
        `&target_id=${action.work_center_id}&cost_item_type=${encodeURIComponent(action.cost_item_type)}`
      );
    case 'standard_cost_material':
      if (!action.material_id) return null;
      return (
        `/apps/kuaicaiwu/cost-management/standard-costs?prefill=1&target_type=material` +
        `&target_id=${action.material_id}&cost_item_type=material_cost`
      );
    case 'work_order_operations':
      if (!woId) return null;
      return `/apps/kuaizhizao/production-execution/work-orders?highlight=${woId}`;
    case 'cost_rules':
      return '/apps/kuaicaiwu/cost-management/cost-rules';
    case 'master_operations':
      return '/apps/master-data/process/operations';
    default:
      return null;
  }
}

export interface CostCalculationFactorsPanelProps {
  readiness: CostCalculationReadiness | null;
  loading?: boolean;
  targetKind?: 'work_order' | 'product';
}

export const CostCalculationFactorsPanel: React.FC<CostCalculationFactorsPanelProps> = ({
  readiness,
  loading = false,
  targetKind = 'work_order',
}) => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const categoryLabel = useMemo(
    () =>
      ({
        material: t('app.kuaicaiwu.costCalculation.factorCategory.material'),
        labor: t('app.kuaicaiwu.costCalculation.factorCategory.labor'),
        manufacturing: t('app.kuaicaiwu.costCalculation.factorCategory.manufacturing'),
      }) as Record<string, string>,
    [t],
  );

  const guideSteps = useMemo(
    () =>
      targetKind === 'product'
        ? [
            { title: t('app.kuaicaiwu.costCalculation.guideProductStep1Title') },
            { title: t('app.kuaicaiwu.costCalculation.guideProductStep2Title') },
            { title: t('app.kuaicaiwu.costCalculation.guideProductStep3Title') },
          ]
        : [
            { title: t('app.kuaicaiwu.costCalculation.guideWorkOrderStep1Title') },
            { title: t('app.kuaicaiwu.costCalculation.guideWorkOrderStep2Title') },
            { title: t('app.kuaicaiwu.costCalculation.guideWorkOrderStep3Title') },
          ],
    [t, targetKind],
  );

  const groupedFactors = useMemo(() => {
    if (!readiness?.factors?.length) return [];
    const buckets = new Map<string, CostCalculationFactor[]>();
    for (const item of readiness.factors) {
      const list = buckets.get(item.category) ?? [];
      list.push(item);
      buckets.set(item.category, list);
    }
    return CATEGORY_ORDER.filter((cat) => buckets.has(cat)).map((cat) => ({
      category: cat,
      items: buckets.get(cat) ?? [],
    }));
  }, [readiness?.factors]);

  const actionLabel = (action: CostCalculationFactorAction): string => {
    switch (action.code) {
      case 'standard_cost_work_center_rate':
      case 'standard_cost_material':
        return t('app.kuaicaiwu.costCalculation.actionGoStandardCost');
      case 'work_order_operations':
        return t('app.kuaicaiwu.costCalculation.actionGoWorkOrder');
      case 'cost_rules':
        return t('app.kuaicaiwu.costCalculation.actionGoCostRules');
      case 'master_operations':
        return t('app.kuaicaiwu.costCalculation.actionGoMasterOperations');
      default:
        return t('app.kuaicaiwu.costCalculation.actionGoConfigure');
    }
  };

  if (loading) {
    return (
      <div style={{ marginBottom: 16, textAlign: 'center', padding: '12px 0' }}>
        <Spin size="small" />
        <Typography.Text type="secondary" style={{ marginLeft: 8 }}>
          {t('app.kuaicaiwu.costCalculation.factorsLoading')}
        </Typography.Text>
      </div>
    );
  }

  return (
    <div style={{ marginBottom: 16 }}>
      <Collapse
        size="small"
        style={{ marginBottom: 12 }}
        items={[
          {
            key: 'guide',
            label: t('app.kuaicaiwu.costCalculation.guideTitle'),
            children: (
              <div>
                <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
                  {targetKind === 'product'
                    ? t('app.kuaicaiwu.costCalculation.guideProductIntro')
                    : t('app.kuaicaiwu.costCalculation.guideWorkOrderIntro')}
                </Typography.Paragraph>
                <Steps direction="vertical" size="small" current={-1} items={guideSteps} />
                <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0, fontSize: 12 }}>
                  {t('app.kuaicaiwu.costCalculation.guideFooter')}
                </Typography.Paragraph>
              </div>
            ),
          },
        ]}
      />

      {!readiness ? (
        <Alert type="info" showIcon title={t('app.kuaicaiwu.costCalculation.factorsSelectTarget')} />
      ) : (
        <>
          <Alert
            type={readiness.ready ? 'success' : readiness.blocking_count > 0 ? 'error' : 'warning'}
            showIcon
            title={
              readiness.ready
                ? t('app.kuaicaiwu.costCalculation.factorsAllReady')
                : t('app.kuaicaiwu.costCalculation.factorsBlockingSummary', {
                    blocking: readiness.blocking_count,
                    warning: readiness.warning_count,
                  })
            }
            description={
              readiness.target_label ? (
                <Typography.Text type="secondary">{readiness.target_label}</Typography.Text>
              ) : undefined
            }
            style={{ marginBottom: 12 }}
          />
          {!readiness.ready ? (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 12 }}
              title={t('app.kuaicaiwu.costCalculation.factorsFixBeforeCalculate')}
            />
          ) : null}
          {groupedFactors.length === 0 ? (
            <List
              size="small"
              bordered
              locale={{ emptyText: t('app.kuaicaiwu.costCalculation.factorsEmpty') }}
              dataSource={[]}
              renderItem={() => null}
            />
          ) : (
            groupedFactors.map(({ category, items }) => (
              <div key={category} style={{ marginBottom: 12 }}>
                <Divider orientation="left" style={{ margin: '0 0 8px' }}>
                  {categoryLabel[category] ?? category}
                </Divider>
                <List
                  size="small"
                  bordered
                  dataSource={items}
                  renderItem={(item) => {
                    const statusMeta = STATUS_TAG[item.status];
                    const actionPath =
                      item.action && readiness ? buildActionPath(item.action, readiness) : null;
                    return (
                      <List.Item
                        actions={
                          actionPath && item.status !== 'ready'
                            ? [
                                <Button
                                  key="action"
                                  type="link"
                                  size="small"
                                  onClick={() => navigate(actionPath)}
                                >
                                  {item.action ? actionLabel(item.action) : t('common.configure')}
                                </Button>,
                              ]
                            : undefined
                        }
                      >
                        <div style={{ width: '100%' }}>
                          <Space wrap align="start">
                            <Tag color={statusMeta.color}>{t(statusMeta.labelKey)}</Tag>
                            <Typography.Text>{item.message}</Typography.Text>
                          </Space>
                          {item.hint ? (
                            <Typography.Text
                              type="secondary"
                              style={{ display: 'block', marginTop: 4, fontSize: 12 }}
                            >
                              {item.hint}
                            </Typography.Text>
                          ) : null}
                        </div>
                      </List.Item>
                    );
                  }}
                />
              </div>
            ))
          )}
        </>
      )}
    </div>
  );
};
