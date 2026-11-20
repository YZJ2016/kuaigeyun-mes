import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Modal, Radio, Space, Spin, Steps, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { visualSchedulingApi } from '../../../../services/production';

export type SchedulingStrategyCode = 'due_date' | 'changeover_min' | 'load_balance';

export interface SchedulingEngineProposalPayload {
  summary?: string | null;
  strategy?: string | null;
  strategy_name?: string | null;
  warnings: string[];
  reasons?: Array<{
    code: string;
    message: string;
    work_order_id?: number | null;
    operation_id?: number | null;
    changeover_hours?: number | null;
  }>;
  execution_log?: Array<{
    step: string;
    message: string;
    elapsed_ms?: number | null;
  }>;
  unfreezed?: number[];
  work_order_adjustments: Array<{
    work_order_id: number;
    planned_start_date: string;
    planned_end_date: string;
  }>;
  operation_adjustments: Array<{
    operation_id: number;
    planned_start_date: string;
    planned_end_date: string;
  }>;
  operation_station_adjustments?: Array<{
    operation_id: number;
    assigned_station_id: number;
  }>;
  operation_production_line_adjustments?: Array<{
    operation_id: number;
    assigned_production_line_id: number;
  }>;
}

interface SchedulingRescheduleWizardModalProps {
  open: boolean;
  workOrderIds: number[];
  planDate?: string;
  scope?: 'selected' | 'overdue' | 'unscheduled' | 'local';
  localWindowHours?: number;
  onCancel: () => void;
  onApply: (proposal: SchedulingEngineProposalPayload) => Promise<boolean> | boolean;
}

const SchedulingRescheduleWizardModal: React.FC<SchedulingRescheduleWizardModalProps> = ({
  open,
  workOrderIds,
  planDate,
  scope = 'selected',
  localWindowHours,
  onCancel,
  onApply,
}) => {
  const { t } = useTranslation();
  const [step, setStep] = useState(0);
  const [strategy, setStrategy] = useState<SchedulingStrategyCode>('due_date');
  const [strategies, setStrategies] = useState<
    Array<{ code: SchedulingStrategyCode; name: string; description: string }>
  >([]);
  const [strategiesLoading, setStrategiesLoading] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [applyLoading, setApplyLoading] = useState(false);
  const [proposal, setProposal] = useState<SchedulingEngineProposalPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setStep(0);
    setStrategy('due_date');
    setProposal(null);
    setError(null);
    setStrategies([]);
    setStrategiesLoading(true);
    void visualSchedulingApi
      .listStrategies()
      .then((res) => {
        const items = res.items ?? [];
        if (items.length === 0) {
          setError(t('app.kuaizhizao.scheduling.wizard.strategiesLoadFailed'));
          return;
        }
        setStrategies(
          items.map((item) => ({
            code: item.code as SchedulingStrategyCode,
            name: item.name,
            description: item.description,
          }))
        );
      })
      .catch((e: { message?: string }) => {
        setError(
          e?.message || t('app.kuaizhizao.scheduling.wizard.strategiesLoadFailed')
        );
      })
      .finally(() => {
        setStrategiesLoading(false);
      });
  }, [open, t]);

  const count = workOrderIds.length;
  const adjustmentCount = useMemo(() => {
    if (!proposal) return 0;
    return proposal.work_order_adjustments?.length ?? 0;
  }, [proposal]);

  const runPreview = useCallback(async () => {
    if (workOrderIds.length === 0) return;
    setPreviewLoading(true);
    setError(null);
    try {
      const res = await visualSchedulingApi.autoReschedule({
        work_order_ids: workOrderIds,
        scope,
        plan_date: planDate,
        local_window_hours: localWindowHours,
        strategy,
      });
      setProposal(res.proposal);
      setStep(1);
    } catch (e: any) {
      setError(e?.message || t('app.kuaizhizao.scheduling.msg.autoRescheduleFailed'));
    } finally {
      setPreviewLoading(false);
    }
  }, [localWindowHours, planDate, scope, strategy, t, workOrderIds]);

  const handleApply = useCallback(async () => {
    if (!proposal) return;
    setApplyLoading(true);
    setError(null);
    try {
      const ok = await onApply(proposal);
      if (ok) onCancel();
    } catch (e: unknown) {
      const detail =
        e && typeof e === 'object' && 'message' in e
          ? String((e as { message?: unknown }).message || '')
          : '';
      setError(detail || t('app.kuaizhizao.scheduling.wizard.applyFailed'));
    } finally {
      setApplyLoading(false);
    }
  }, [onApply, onCancel, proposal, t]);

  return (
    <Modal
      title={t('app.kuaizhizao.scheduling.wizard.title')}
      open={open}
      onCancel={onCancel}
      destroyOnHidden
      width={720}
      footer={
        <Space>
          <Button onClick={onCancel}>{t('common.cancel')}</Button>
          {step === 0 ? (
            <Button
              type="primary"
              loading={previewLoading || strategiesLoading}
              disabled={count === 0 || strategies.length === 0}
              onClick={() => void runPreview()}
            >
              {t('app.kuaizhizao.scheduling.wizard.generate')}
            </Button>
          ) : (
            <>
              <Button onClick={() => setStep(0)}>{t('app.kuaizhizao.scheduling.wizard.back')}</Button>
              <Button
                type="primary"
                loading={applyLoading}
                disabled={!proposal || adjustmentCount === 0}
                onClick={() => void handleApply()}
              >
                {t('app.kuaizhizao.scheduling.wizard.applyDraft')}
              </Button>
            </>
          )}
        </Space>
      }
    >
      <Steps
        size="small"
        current={step}
        style={{ marginBottom: 16 }}
        items={[
          { title: t('app.kuaizhizao.scheduling.wizard.stepStrategy') },
          { title: t('app.kuaizhizao.scheduling.wizard.stepPreview') },
        ]}
      />

      {step === 0 ? (
        <div>
          <Typography.Paragraph>
            {t('app.kuaizhizao.scheduling.wizard.selectedCount', { count })}
          </Typography.Paragraph>
          {strategiesLoading ? (
            <Spin description={t('common.loading')} />
          ) : strategies.length > 0 ? (
            <Radio.Group
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              style={{ width: '100%' }}
            >
              <Space orientation="vertical" style={{ width: '100%' }}>
                {strategies.map((item) => (
                  <Radio key={item.code} value={item.code} style={{ width: '100%' }}>
                    <div>
                      <Typography.Text strong>{item.name}</Typography.Text>
                      <div>
                        <Typography.Text type="secondary">{item.description}</Typography.Text>
                      </div>
                    </div>
                  </Radio>
                ))}
              </Space>
            </Radio.Group>
          ) : null}
          {error ? <Alert style={{ marginTop: 12 }} type="error" title={error} showIcon /> : null}
        </div>
      ) : (
        <div>
          {previewLoading ? (
            <Spin description={t('app.kuaizhizao.scheduling.wizard.generating')} />
          ) : (
            <>
              {proposal?.summary ? (
                <Alert
                  style={{ marginBottom: 12 }}
                  type="info"
                  showIcon
                  title={proposal.summary}
                />
              ) : null}
              {(proposal?.warnings?.length ?? 0) > 0 ? (
                <Alert
                  style={{ marginBottom: 12 }}
                  type="warning"
                  showIcon
                  title={t('app.kuaizhizao.scheduling.wizard.warningsTitle')}
                  description={
                    <ul style={{ margin: 0, paddingLeft: 18 }}>
                      {proposal!.warnings.slice(0, 8).map((w) => (
                        <li key={w}>{w}</li>
                      ))}
                    </ul>
                  }
                />
              ) : null}
              <Typography.Text strong>
                {t('app.kuaizhizao.scheduling.wizard.adjustmentCount', { count: adjustmentCount })}
              </Typography.Text>
              <div
                style={{
                  marginTop: 12,
                  maxHeight: 260,
                  overflow: 'auto',
                  border: '1px solid rgba(0,0,0,0.06)',
                  borderRadius: 6,
                  background: '#f7f8fa',
                  padding: '10px 12px',
                  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
                  fontSize: 12,
                  lineHeight: 1.6,
                }}
              >
                {(proposal?.execution_log ?? []).length === 0 ? (
                  <Typography.Text type="secondary">
                    {t('app.kuaizhizao.scheduling.wizard.emptyLog')}
                  </Typography.Text>
                ) : (
                  (proposal?.execution_log ?? []).map((row, idx) => (
                    <div key={`${row.step}-${idx}`}>
                      [{row.step}]
                      {row.elapsed_ms != null ? ` ${row.elapsed_ms}ms` : ''} — {row.message}
                    </div>
                  ))
                )}
              </div>
            </>
          )}
          {error ? <Alert style={{ marginTop: 12 }} type="error" title={error} showIcon /> : null}
        </div>
      )}
    </Modal>
  );
};

export default SchedulingRescheduleWizardModal;
