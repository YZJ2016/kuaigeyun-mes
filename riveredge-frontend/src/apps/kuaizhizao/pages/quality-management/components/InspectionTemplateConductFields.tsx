import React, { useEffect, useMemo } from 'react';
import { Alert, Card, Checkbox, Col, Form, Input, InputNumber, Select, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  getInspectionTemplateSource,
  getTemplateStepItems,
  hasInspectionPlanSteps,
  isTypedInspectionStep,
} from './inspectionTemplateUtils';
import {
  defaultValueSpec,
  evaluateDerivedFormula,
  formatAcceptanceCriteriaPreview,
  formatSamplingCriteriaPreview,
  getCriteriaSupplement,
  getStepConductKey,
  normalizeValueType,
  resolveStepJudgmentClient,
  stepSpecAllowsNa,
  stepSpecIsCritical,
  stepSpecIsDerived,
  stepSpecRequiresPhoto,
  summarizeConductSteps,
  type InspectionTemplateStepItem,
  type StepConductEntry,
} from '../../../types/inspectionStepSpec';
import { valueTypeOptions } from '../../../components/InspectionStepValueSpecFields';
import InspectionStepConductPhotoField from '../../../components/InspectionStepConductPhotoField';
import { MarkerTag } from '../../../../../constants/statusBadges';
import { ThemedSegmented } from '../../../../../components/themed-segmented';
import {
  InspectionConductPlanSwitcher,
  type InspectionConductPlanSwitcherProps,
} from './InspectionConductPlanSwitcher';

const { Text } = Typography;

interface InspectionTemplateConductFieldsProps {
  inspection: Record<string, unknown> | null | undefined;
  photoCategory?: string;
  /** 为 false 时仍展示照片上传，但不强制校验（如来料检验） */
  stepPhotoRequired?: boolean;
  /** 待检验时在检验 Modal 内切换方案 */
  planSwitch?: Omit<InspectionConductPlanSwitcherProps, 'inspection'> | null;
}

function JudgmentTag({ judgment }: { judgment?: string | null }) {
  const { t } = useTranslation();
  if (!judgment) return null;
  const pass = judgment === 'pass';
  const label =
    judgment === 'na'
      ? t('app.kuaizhizao.quality.template.judgmentNa')
      : pass
        ? t('app.kuaizhizao.quality.common.result.qualified')
        : t('app.kuaizhizao.quality.common.result.unqualified');
  return (
    <MarkerTag color={pass ? 'success' : judgment === 'na' ? 'default' : 'error'}>
      {label}
    </MarkerTag>
  );
}

const InspectionConductStepSummary: React.FC<{
  inspection: Record<string, unknown> | null | undefined;
}> = ({ inspection }) => {
  const { t } = useTranslation();
  const template = getInspectionTemplateSource(inspection);
  const steps = useMemo(() => getTemplateStepItems(template), [template]);
  const stepResults = Form.useWatch('conduct_step_results') as Record<string, StepConductEntry> | undefined;
  const itemResults = Form.useWatch('item_results') as Record<string, unknown> | undefined;

  const summary = useMemo(
    () => summarizeConductSteps(steps, stepResults, itemResults, t),
    [steps, stepResults, itemResults, t],
  );

  if (summary.failCount === 0) return null;

  if (summary.criticalFailCount > 0) {
    return (
      <Alert
        type="error"
        showIcon
        style={{ marginBottom: 12 }}
        title={t('app.kuaizhizao.quality.template.criticalFailAlert', {
          items: summary.criticalFailLabels.join('、'),
        })}
      />
    );
  }

  return (
    <Alert
      type="warning"
      showIcon
      style={{ marginBottom: 12 }}
      title={t('app.kuaizhizao.quality.template.stepFailHint', {
        count: summary.failCount,
        items: summary.failLabels.join('、'),
      })}
    />
  );
};

const StepAutoJudgment: React.FC<{
  step: InspectionTemplateStepItem;
  stepKey: string;
}> = ({ step, stepKey }) => {
  const entry = Form.useWatch(['conduct_step_results', stepKey]) as StepConductEntry | undefined;
  if (entry?.judgment === 'na') {
    return <JudgmentTag judgment="na" />;
  }
  const judgment = resolveStepJudgmentClient(step, entry || {});
  return <JudgmentTag judgment={judgment} />;
};

const DerivedNumericValue: React.FC<{
  stepKey: string;
  spec: Record<string, unknown>;
  unitLabel: string;
}> = ({ stepKey, spec, unitLabel }) => {
  const { t } = useTranslation();
  const form = Form.useFormInstance();
  const allResults = Form.useWatch('conduct_step_results') as Record<string, StepConductEntry> | undefined;
  const computed = useMemo(
    () =>
      evaluateDerivedFormula(
        spec.formula as string | undefined,
        allResults,
        (spec.decimal_places as number) ?? 4,
      ),
    [allResults, spec.formula, spec.decimal_places],
  );

  useEffect(() => {
    if (computed == null) return;
    form.setFieldValue(['conduct_step_results', stepKey, 'value'], computed);
  }, [computed, form, stepKey]);

  return (
    <Form.Item
      name={['conduct_step_results', stepKey, 'value']}
      label={unitLabel}
      extra={t('app.kuaizhizao.quality.template.derivedValueHint')}
    >
      <InputNumber
        disabled
        precision={(spec.decimal_places as number) ?? 4}
        style={{ width: '100%' }}
      />
    </Form.Item>
  );
};

const STEP_META_LABEL_STYLE: React.CSSProperties = {
  display: 'inline',
  fontSize: 13,
  lineHeight: 1.55,
  color: 'rgba(0, 0, 0, 0.65)',
};

const STEP_META_VALUE_STYLE: React.CSSProperties = {
  fontSize: 13,
  lineHeight: 1.55,
  color: 'rgba(0, 0, 0, 0.88)',
  whiteSpace: 'pre-wrap',
};

const StepCriteriaBlocks: React.FC<{
  inspectionMethod?: string;
  acceptanceCriteria?: string;
  criteriaSupplement?: string;
}> = ({ inspectionMethod, acceptanceCriteria, criteriaSupplement }) => {
  const { t } = useTranslation();
  if (!inspectionMethod && !acceptanceCriteria && !criteriaSupplement) return null;
  return (
    <div style={{ marginBottom: 10, display: 'flex', flexDirection: 'column', gap: 4 }}>
      {inspectionMethod ? (
        <div>
          <Text style={STEP_META_LABEL_STYLE}>
            {t('app.kuaizhizao.quality.plans.step.inspectionMethod')}：
          </Text>
          <Text style={STEP_META_VALUE_STYLE}>{inspectionMethod}</Text>
        </div>
      ) : null}
      {acceptanceCriteria ? (
        <div>
          <Text style={STEP_META_LABEL_STYLE}>
            {t('app.kuaizhizao.quality.plans.step.acceptanceCriteria')}：
          </Text>
          <Text style={STEP_META_VALUE_STYLE}>{acceptanceCriteria}</Text>
        </div>
      ) : null}
      {criteriaSupplement ? (
        <div>
          <Text style={STEP_META_LABEL_STYLE}>
            {t('app.kuaizhizao.quality.plans.stepSpec.criteriaSupplement')}：
          </Text>
          <Text style={STEP_META_VALUE_STYLE}>{criteriaSupplement}</Text>
        </div>
      ) : null}
    </div>
  );
};

const TypedStepFields: React.FC<{
  step: InspectionTemplateStepItem;
  stepKey: string;
  label: string;
  inspectionMethod?: string;
  acceptanceCriteria?: string;
  criteriaSupplement?: string;
  photoCategory?: string;
  stepPhotoRequired?: boolean;
}> = ({
  step,
  stepKey,
  label,
  inspectionMethod,
  acceptanceCriteria,
  criteriaSupplement,
  photoCategory,
  stepPhotoRequired = true,
}) => {
  const { t } = useTranslation();
  const vt = normalizeValueType(step.value_type);
  const spec = { ...defaultValueSpec(vt, t), ...(step.value_spec || {}) };
  const passLabel = t('app.kuaizhizao.quality.common.result.qualified');
  const failLabel = t('app.kuaizhizao.quality.common.result.unqualified');
  const naLabel = t('app.kuaizhizao.quality.template.judgmentNa');
  const allowsNa = stepSpecAllowsNa(spec);
  const isCritical = stepSpecIsCritical(spec);
  const isDerived = vt === 'numeric' && stepSpecIsDerived(spec);
  const templateWantsPhoto = stepSpecRequiresPhoto(spec);
  const enforcePhoto = templateWantsPhoto && stepPhotoRequired;

  const basePath = ['conduct_step_results', stepKey];
  const judgment = Form.useWatch([...basePath, 'judgment']);
  const isNa = judgment === 'na';

  const skipValueRule = () => ({
    validator(_: unknown, value: unknown) {
      if (isNa || isDerived) return Promise.resolve();
      // 缺陷多选：未选缺陷项即为合格，允许空值/空数组
      if (vt === 'multi_select') {
        if (value === undefined || value === null) return Promise.resolve();
        if (Array.isArray(value)) return Promise.resolve();
        return Promise.reject(new Error(t('app.kuaizhizao.quality.template.valueRequired', { label })));
      }
      if (value === undefined || value === null || value === '') {
        return Promise.reject(new Error(t('app.kuaizhizao.quality.template.valueRequired', { label })));
      }
      return Promise.resolve();
    },
  });

  const photoRule = () => ({
    validator(_: unknown, value: unknown) {
      if (!enforcePhoto || isNa) return Promise.resolve();
      if (!Array.isArray(value) || value.length === 0) {
        return Promise.reject(new Error(t('app.kuaizhizao.quality.template.stepPhotoRequired', { label })));
      }
      return Promise.resolve();
    },
  });

  const typeLabels = Object.fromEntries(valueTypeOptions(t).map((o) => [o.value, o.label]));
  const typeLabel = typeLabels[vt] || t('app.kuaizhizao.quality.plans.stepSpec.typeBoolean');
  const form = Form.useFormInstance();

  const stepTitle = (
    <span>
      <Text strong>{label}</Text>
      {isCritical ? (
        <MarkerTag color="error" style={{ marginLeft: 8 }}>
          {t('app.kuaizhizao.quality.plans.stepSpec.critical')}
        </MarkerTag>
      ) : null}
      {isDerived ? (
        <MarkerTag color="processing" style={{ marginLeft: 8 }}>
          {t('app.kuaizhizao.quality.plans.stepSpec.derived')}
        </MarkerTag>
      ) : null}
    </span>
  );

  const stepExtra = (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <MarkerTag>{typeLabel}</MarkerTag>
      {isTypedInspectionStep(step) ? <StepAutoJudgment step={step} stepKey={stepKey} /> : null}
    </span>
  );

  if (!isTypedInspectionStep(step)) {
    return (
      <Card size="small" type="inner" style={{ marginBottom: 8 }} title={stepTitle} extra={stepExtra}>
        <StepCriteriaBlocks
          inspectionMethod={inspectionMethod}
          acceptanceCriteria={acceptanceCriteria}
          criteriaSupplement={criteriaSupplement}
        />
        <Form.Item
          name={['item_results', stepKey]}
          initialValue="pass"
          rules={[{ required: true, message: t('app.kuaizhizao.quality.template.judgmentRequired', { label }) }]}
        >
          <ThemedSegmented
            options={[
              { label: passLabel, value: 'pass' },
              { label: failLabel, value: 'fail' },
            ]}
          />
        </Form.Item>
      </Card>
    );
  }

  const unitLabel = t('app.kuaizhizao.quality.template.measurementValue', {
    unit: spec.unit ? ` (${spec.unit})` : '',
  });
  const selectOptions = ((spec.options as Array<{ value: string; label: string; defect?: boolean }>) || []).map((o) => ({
    value: o.value,
    label: o.defect ? `${o.label || o.value} (${t('app.kuaizhizao.quality.plans.stepSpec.defectOption')})` : o.label || o.value,
  }));

  return (
    <Card size="small" type="inner" style={{ marginBottom: 8 }} title={stepTitle} extra={stepExtra}>
      <StepCriteriaBlocks
        inspectionMethod={inspectionMethod}
        acceptanceCriteria={acceptanceCriteria}
        criteriaSupplement={criteriaSupplement}
      />

      {vt === 'boolean' ? (
        <Form.Item
          name={[...basePath, 'value']}
          initialValue={true}
          rules={[skipValueRule()]}
          getValueProps={(value) => ({
            value:
              value === true || value === 'true' || value === 1
                ? 'true'
                : value === false || value === 'false' || value === 0
                  ? 'false'
                  : value,
          })}
          getValueFromEvent={(next) => next === 'true'}
        >
          <ThemedSegmented
            options={[
              { label: t('common.yes'), value: 'true' },
              { label: t('common.no'), value: 'false' },
            ]}
          />
        </Form.Item>
      ) : null}

      {allowsNa && vt !== 'text' && vt !== 'boolean' ? (
        <Form.Item name={[...basePath, 'judgment']} style={{ marginBottom: 8 }}>
          <ThemedSegmented
            options={[
              { label: t('app.kuaizhizao.quality.plans.stepSpec.markNa'), value: 'na' },
            ]}
            value={isNa ? 'na' : undefined}
            onChange={(next) => {
              form.setFieldValue([...basePath, 'judgment'], next === 'na' ? 'na' : undefined);
            }}
          />
        </Form.Item>
      ) : null}

      {!isNa && vt === 'numeric' && isDerived ? (
        <DerivedNumericValue stepKey={stepKey} spec={spec} unitLabel={unitLabel} />
      ) : null}

      {!isNa && vt === 'numeric' && !isDerived ? (
        <Form.Item name={[...basePath, 'value']} label={unitLabel} rules={[skipValueRule()]}>
          <InputNumber
            precision={(spec.decimal_places as number) ?? 4}
            style={{ width: '100%' }}
          />
        </Form.Item>
      ) : null}

      {!isNa && vt === 'single_select' ? (
        selectOptions.length > 0 && selectOptions.length <= 4 ? (
          <Form.Item name={[...basePath, 'value']} rules={[skipValueRule()]}>
            <ThemedSegmented
              options={selectOptions}
            />
          </Form.Item>
        ) : (
          <Form.Item name={[...basePath, 'value']} rules={[skipValueRule()]}>
            <Select
              allowClear
              options={selectOptions}
              placeholder={t('app.kuaizhizao.quality.template.selectValue')}
            />
          </Form.Item>
        )
      ) : null}

      {!isNa && vt === 'multi_select' ? (
        <Form.Item name={[...basePath, 'value']} initialValue={[]} rules={[skipValueRule()]}>
          <Checkbox.Group options={selectOptions} />
        </Form.Item>
      ) : null}

      {vt === 'text' ? (
        <>
          {!isNa ? (
            spec.multiline ? (
              <Form.Item name={[...basePath, 'value']} rules={[skipValueRule()]}>
                <Input.TextArea maxLength={(spec.max_length as number) || 500} rows={3} />
              </Form.Item>
            ) : (
              <Form.Item name={[...basePath, 'value']} rules={[skipValueRule()]}>
                <Input maxLength={(spec.max_length as number) || 500} />
              </Form.Item>
            )
          ) : null}
          <Form.Item
            name={[...basePath, 'judgment']}
            initialValue="pass"
            rules={[{ required: true, message: t('app.kuaizhizao.quality.template.judgmentRequired', { label }) }]}
          >
            <ThemedSegmented
              options={[
                { label: passLabel, value: 'pass' },
                { label: failLabel, value: 'fail' },
                ...(allowsNa ? [{ label: naLabel, value: 'na' }] : []),
              ]}
            />
          </Form.Item>
        </>
      ) : null}

      {templateWantsPhoto && photoCategory && !isNa ? (
        <Form.Item
          name={[...basePath, 'photos']}
          label={t('app.kuaizhizao.quality.template.stepPhoto')}
          rules={enforcePhoto ? [photoRule()] : undefined}
        >
          <InspectionStepConductPhotoField
            category={photoCategory}
            required={enforcePhoto}
            label={label}
          />
        </Form.Item>
      ) : null}
    </Card>
  );
};

const InspectionTemplateConductFields: React.FC<InspectionTemplateConductFieldsProps> = ({
  inspection,
  photoCategory,
  stepPhotoRequired = true,
  planSwitch,
}) => {
  const { t } = useTranslation();
  const template = getInspectionTemplateSource(inspection);
  const steps = useMemo(() => getTemplateStepItems(template), [template]);

  const planCode = template?.plan_code as string | undefined;
  const planVersion = template?.plan_version as string | undefined;
  const planName =
    planCode && planVersion
      ? `${planCode} v${planVersion}`
      : planCode || (template?.standard_id ? t('app.kuaizhizao.quality.template.qualityStandard') : null);
  const passLabel = t('app.kuaizhizao.quality.common.result.qualified');
  const failLabel = t('app.kuaizhizao.quality.common.result.unqualified');

  const planCardExtra =
    planSwitch && inspection ? (
      <InspectionConductPlanSwitcher
        inspection={inspection}
        planType={planSwitch.planType}
        materialId={planSwitch.materialId}
        operationId={planSwitch.operationId}
        disabled={planSwitch.disabled}
        disabledTitle={planSwitch.disabledTitle}
        onApplyPlan={planSwitch.onApplyPlan}
      />
    ) : planName ? (
      <Text type="secondary">{planName}</Text>
    ) : null;

  if (template && hasInspectionPlanSteps(template)) {
    return (
      <Col span={24}>
        <Card
          size="small"
          title={t('app.kuaizhizao.quality.template.planItemsTitle')}
          extra={planCardExtra}
          style={{ marginBottom: 8 }}
        >
          <Text type="secondary" style={{ display: 'block', marginBottom: 12, fontSize: 12 }}>
            {t('app.kuaizhizao.quality.template.planModeHintTyped')}
          </Text>
          <InspectionConductStepSummary inspection={inspection} />
          {steps.map((step, idx) => {
            const stepKey = getStepConductKey(step, idx);
            const label = step.inspection_item || t('app.kuaizhizao.quality.template.inspectionItemFallback', { index: idx + 1 });
            const lotQty = Number(inspection?.inspection_quantity);
            const lotQuantity = Number.isFinite(lotQty) && lotQty > 0 ? lotQty : undefined;
            const samplingHint = formatSamplingCriteriaPreview(
              step.sampling_type,
              step.value_spec,
              t,
              lotQuantity,
              (step as { resolved_sampling?: { label?: string } }).resolved_sampling,
            );
            const criteriaSupplement = getCriteriaSupplement(step.value_spec);
            const typeCriteria = formatAcceptanceCriteriaPreview(
              step.value_type || 'boolean',
              step.value_spec,
              t,
            );
            const acceptanceCriteria =
              typeCriteria.trim() || String(step.acceptance_criteria || '').trim() || undefined;
            const method = String(step.inspection_method || '').trim();
            const inspectionMethod = [method && method !== label ? method : null, samplingHint]
              .filter(Boolean)
              .join(' / ');
            return (
              <TypedStepFields
                key={stepKey}
                step={step}
                stepKey={stepKey}
                label={label}
                inspectionMethod={inspectionMethod || undefined}
                acceptanceCriteria={acceptanceCriteria}
                criteriaSupplement={criteriaSupplement || undefined}
                photoCategory={photoCategory}
                stepPhotoRequired={stepPhotoRequired}
              />
            );
          })}
        </Card>
      </Col>
    );
  }

  const criteria = template?.acceptance_criteria as string | undefined;
  const standardItems = template?.inspection_items;
  if (criteria || standardItems) {
    return (
      <Col span={24}>
        <Card
          size="small"
          title={t('app.kuaizhizao.quality.template.standardTitle')}
          extra={planCardExtra}
          style={{ marginBottom: 8 }}
        >
          {criteria ? (
            <Text type="secondary" style={{ display: 'block', marginBottom: 12, fontSize: 12 }}>
              {t('app.kuaizhizao.quality.template.acceptanceCriteria', { criteria })}
            </Text>
          ) : null}
          {standardItems ? (
            <Text type="secondary" style={{ display: 'block', marginBottom: 12, fontSize: 12 }}>
              {t('app.kuaizhizao.quality.template.inspectionItems', {
                items: typeof standardItems === 'string' ? standardItems : JSON.stringify(standardItems),
              })}
            </Text>
          ) : null}
          <Form.Item
            name={['item_results', '0']}
            initialValue="pass"
            rules={[{ required: true, message: t('app.kuaizhizao.quality.template.overallJudgmentRequired') }]}
          >
            <ThemedSegmented
              options={[
                { label: passLabel, value: 'pass' },
                { label: failLabel, value: 'fail' },
              ]}
            />
          </Form.Item>
        </Card>
      </Col>
    );
  }

  // 简易质检且无标准项时，原先整块不渲染，切换方案入口也被藏掉；有 planSwitch 时仍露出切换条
  if (planCardExtra) {
    return (
      <Col span={24}>
        <Card
          size="small"
          title={t('app.kuaizhizao.quality.common.inspectionKind.simple')}
          extra={planCardExtra}
          style={{ marginBottom: 8 }}
        >
          <Text type="secondary" style={{ display: 'block', fontSize: 12 }}>
            {t('app.kuaizhizao.quality.template.simpleSwitchPlanHint')}
          </Text>
        </Card>
      </Col>
    );
  }

  return null;
};

export default InspectionTemplateConductFields;
