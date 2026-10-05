/**
 * 检验 Modal：待检验切换检验方案（Card 标题栏右侧）。
 */

import React, { useEffect, useMemo, useState } from 'react';
import { App, Button, Popconfirm, Select, Space, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { inspectionPlanApi, unwrapInspectionPlanList } from '../../../services/production';
import {
  getInspectionPlanNameAndCode,
  getInspectionTemplateSource,
} from './inspectionTemplateUtils';
import type { InspectionPlanType } from './QualityInspectionDetailSupplement';

function resolveInspectionPlanId(
  template: Record<string, unknown> | null,
  inspection: Record<string, unknown>,
): number | undefined {
  const raw = template?.plan_id ?? inspection.inspection_plan_id;
  if (raw == null || raw === '') return undefined;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : undefined;
}

function formatPlanOptionLabel(planName: string, planCode: string): string {
  const name = planName.trim();
  const code = planCode.trim();
  if (name && code) return `${name} (${code})`;
  return name || code;
}

function snapshotPlanOption(
  template: Record<string, unknown> | null,
  inspection: Record<string, unknown>,
): { value: number; label: string } | null {
  const id = resolveInspectionPlanId(template, inspection);
  if (!id) return null;
  const nameFromSnap = String(template?.plan_name ?? '').trim();
  const codeFromSnap = String(template?.plan_code ?? '').trim();
  const { name, code } = getInspectionPlanNameAndCode(inspection);
  const label = formatPlanOptionLabel(nameFromSnap || name, codeFromSnap || code);
  return { value: id, label: label || String(id) };
}

export type InspectionConductPlanSwitcherProps = {
  inspection: Record<string, unknown>;
  planType: InspectionPlanType;
  materialId?: number | null;
  operationId?: number | null;
  disabled?: boolean;
  disabledTitle?: string;
  onApplyPlan: (inspectionPlanId: number) => Promise<void>;
};

function mapPlanListToOptions(items: unknown[]): Array<{ label: string; value: number }> {
  return items
    .map((row) => row as Record<string, unknown>)
    .filter((p) => p.id != null && Number(p.id) > 0)
    .map((p) => ({
      value: Number(p.id),
      label: formatPlanOptionLabel(String(p.plan_name ?? ''), String(p.plan_code ?? '')),
    }));
}

function mergePlanOptions(
  fromList: Array<{ label: string; value: number }>,
  snap: { label: string; value: number } | null,
): Array<{ label: string; value: number }> {
  const options = [...fromList];
  if (snap && !options.some((o) => o.value === snap.value)) {
    options.unshift(snap);
  }
  return options;
}

export function InspectionConductPlanSwitcher({
  inspection,
  planType,
  materialId: _materialId,
  operationId: _operationId,
  disabled,
  disabledTitle,
  onApplyPlan,
}: InspectionConductPlanSwitcherProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const template = getInspectionTemplateSource(inspection);
  const currentPlanId = resolveInspectionPlanId(template, inspection);
  const snapOption = useMemo(
    () => snapshotPlanOption(getInspectionTemplateSource(inspection), inspection),
    [inspection],
  );

  const [planOptions, setPlanOptions] = useState<Array<{ label: string; value: number }>>([]);
  const [selectedPlanId, setSelectedPlanId] = useState<number | undefined>();
  const [planApplying, setPlanApplying] = useState(false);
  const [plansLoading, setPlansLoading] = useState(false);
  const [planSearchText, setPlanSearchText] = useState('');

  const inspectionIdentity = `${String(inspection.id ?? '')}:${currentPlanId ?? ''}`;

  useEffect(() => {
    let cancelled = false;
    setPlansLoading(true);
    void (async () => {
      try {
        // 与已入库补检一致：按环节类型列出启用方案，不按物料/工序收窄（否则常为空）
        const res = await inspectionPlanApi.list({
          plan_type: planType,
          is_active: true,
          skip: 0,
          limit: 200,
          include_steps: false,
        });
        const items = unwrapInspectionPlanList(res);
        if (cancelled) return;
        const options = mergePlanOptions(mapPlanListToOptions(items), snapOption);
        setPlanOptions(options);
        setSelectedPlanId(currentPlanId ?? snapOption?.value);
      } catch (e: unknown) {
        if (!cancelled) {
          if (snapOption) {
            setPlanOptions([snapOption]);
            setSelectedPlanId(snapOption.value);
          } else {
            setPlanOptions([]);
          }
          message.error((e as Error)?.message || t('common.loadFailed'));
        }
      } finally {
        if (!cancelled) setPlansLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [planType, currentPlanId, inspectionIdentity, snapOption, message, t]);

  const handleApply = async () => {
    if (!selectedPlanId) {
      message.warning(t('app.kuaizhizao.quality.common.messages.selectInspectionPlan'));
      return;
    }
    if (currentPlanId && selectedPlanId === currentPlanId) {
      message.info(t('app.kuaizhizao.quality.common.messages.inspectionPlanUnchanged'));
      return;
    }
    try {
      setPlanApplying(true);
      await onApplyPlan(selectedPlanId);
      message.success(t('app.kuaizhizao.quality.common.messages.applyInspectionPlanSuccess'));
    } catch (e: unknown) {
      message.error((e as Error)?.message || t('common.saveFailed'));
    } finally {
      setPlanApplying(false);
    }
  };

  if (disabled) {
    const { name, code } = getInspectionPlanNameAndCode(inspection);
    const planVersion = String(template?.plan_version ?? '').trim();
    let label = formatPlanOptionLabel(name, code);
    if (label && planVersion) {
      label = `${label} v${planVersion}`;
    }
    return label ? (
      <Typography.Text type="secondary" title={disabledTitle}>
        {label}
      </Typography.Text>
    ) : null;
  }

  return (
    <Space wrap size={8} align="center">
      <Select
        size="small"
        style={{ minWidth: 280 }}
        placeholder={t('app.kuaizhizao.quality.incoming.form.inspectionPlan')}
        loading={plansLoading}
        options={planOptions}
        value={planOptions.length ? selectedPlanId : undefined}
        onChange={(v) => setSelectedPlanId(v)}
        showSearch
        searchValue={planSearchText}
        onSearch={setPlanSearchText}
        onOpenChange={(open) => {
          if (open) setPlanSearchText('');
        }}
        filterOption={(input, option) =>
          String(option?.label ?? '')
            .toLowerCase()
            .includes(input.trim().toLowerCase())
        }
        optionLabelProp="label"
        notFoundContent={plansLoading ? null : t('common.noData')}
      />
      <Popconfirm
        title={t('app.kuaizhizao.quality.common.confirm.applyInspectionPlanTitle')}
        description={t('app.kuaizhizao.quality.common.confirm.applyInspectionPlanDescription')}
        onConfirm={() => void handleApply()}
        disabled={!selectedPlanId || planApplying}
      >
        <Button size="small" type="link" loading={planApplying}>
          {t('app.kuaizhizao.quality.common.actions.switchInspectionPlan')}
        </Button>
      </Popconfirm>
    </Space>
  );
}
