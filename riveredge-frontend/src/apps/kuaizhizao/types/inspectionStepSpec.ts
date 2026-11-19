import type { TFunction } from 'i18next';

export const INSPECTION_STEP_VALUE_TYPES = [
  'boolean',
  'single_select',
  'multi_select',
  'text',
  'numeric',
] as const;

export type InspectionStepValueType = (typeof INSPECTION_STEP_VALUE_TYPES)[number];

export type InspectionStepValueSpec = Record<string, unknown>;

export type SamplingMode = 'fixed' | 'lot_ratio' | 'gb2828_single';

export type Gb2828Strictness = 'normal' | 'tightened' | 'reduced';

export type Gb2828InspectionLevel = 'S-1' | 'S-2' | 'S-3' | 'S-4' | 'I' | 'II' | 'III';

export interface SamplingSpec {
  mode?: SamplingMode;
  sample_size: number;
  accept_num: number;
  reject_num: number;
  /** 按批量比例抽检时的百分比（1–100） */
  lot_sample_ratio?: number;
  level?: Gb2828InspectionLevel;
  aql?: number;
  strictness?: Gb2828Strictness;
  transfer_enabled?: boolean;
}

export type ResolvedSampling = {
  mode?: string;
  sample_size?: number;
  accept_num?: number;
  reject_num?: number;
  strictness?: string;
  level?: string;
  aql?: number;
  transfer_enabled?: boolean;
  label?: string;
  gb2828?: Record<string, unknown>;
};

export function normalizeSamplingSpec(raw?: unknown): SamplingSpec {
  const base: SamplingSpec = {
    mode: 'fixed',
    sample_size: 1,
    accept_num: 0,
    reject_num: 1,
    lot_sample_ratio: 10,
  };
  if (!raw || typeof raw !== 'object') return base;
  const src = raw as Record<string, unknown>;
  const out = { ...base };
  const modeRaw = String(src.mode || 'fixed').trim();
  if (modeRaw === 'gb2828_single') {
    out.mode = 'gb2828_single';
    if (src.level != null) out.level = String(src.level) as Gb2828InspectionLevel;
    if (src.aql != null) {
      const aql = Number(src.aql);
      if (!Number.isNaN(aql)) out.aql = aql;
    }
    if (src.strictness != null) out.strictness = String(src.strictness) as Gb2828Strictness;
    if (src.transfer_enabled != null) out.transfer_enabled = Boolean(src.transfer_enabled);
    if (out.level == null) out.level = 'II';
    if (out.aql == null) out.aql = 2.5;
    if (out.strictness == null) out.strictness = 'normal';
    if (out.transfer_enabled == null) out.transfer_enabled = false;
    return out;
  }
  out.mode = modeRaw === 'lot_ratio' ? 'lot_ratio' : 'fixed';
  for (const key of ['sample_size', 'accept_num', 'reject_num'] as const) {
    if (src[key] == null) continue;
    const n = Number(src[key]);
    if (!Number.isNaN(n)) out[key] = Math.max(0, Math.floor(n));
  }
  if (src.lot_sample_ratio != null) {
    const ratio = Number(src.lot_sample_ratio);
    if (!Number.isNaN(ratio)) {
      out.lot_sample_ratio = Math.min(100, Math.max(0.01, ratio));
    }
  }
  if (out.sample_size < 1) out.sample_size = 1;
  return out;
}

/** 执行检验时按报检数量解析有效 n（固定 n 或批量比例） */
export function resolveEffectiveSamplingSpec(
  spec: SamplingSpec,
  lotQuantity?: number,
): SamplingSpec {
  const normalized = normalizeSamplingSpec(spec);
  if (normalized.mode !== 'lot_ratio') return normalized;
  const lot = Number(lotQuantity);
  if (!Number.isFinite(lot) || lot <= 0) return normalized;
  const ratio = normalized.lot_sample_ratio ?? 10;
  const n = Math.max(1, Math.ceil((lot * ratio) / 100));
  return { ...normalized, sample_size: n };
}

export function getCriteriaSupplement(valueSpec?: InspectionStepValueSpec): string {
  return typeof valueSpec?.criteria_supplement === 'string'
    ? valueSpec.criteria_supplement.trim()
    : '';
}

export function appendCriteriaSupplement(
  autoCriteria: string,
  valueSpec?: InspectionStepValueSpec,
): string {
  const sup = getCriteriaSupplement(valueSpec);
  if (!sup) return autoCriteria;
  return autoCriteria ? `${autoCriteria} / ${sup}` : sup;
}

/** 仅类型规格 + 抽检（不含补充说明；执行页补充说明单独成块展示） */
export function formatStepAutoCriteriaDisplay(
  step: Pick<InspectionPlanStepItem, 'value_type' | 'value_spec' | 'sampling_type'>,
  t?: TFunction,
  lotQuantity?: number,
  resolvedSampling?: ResolvedSampling,
): string {
  const typeHint = formatAcceptanceCriteriaPreview(
    step.value_type || 'boolean',
    step.value_spec,
    t,
  );
  const samplingHint = formatSamplingCriteriaPreview(
    step.sampling_type,
    step.value_spec,
    t,
    lotQuantity,
    resolvedSampling,
  );
  return [typeHint, samplingHint].filter(Boolean).join(' / ');
}

/** 方案列表：类型规格 + 抽检 + 合格标准补充说明 */
export function formatStepCriteriaDisplay(
  step: Pick<
    InspectionPlanStepItem,
    'value_type' | 'value_spec' | 'sampling_type' | 'acceptance_criteria'
  >,
  t?: TFunction,
  lotQuantity?: number,
  resolvedSampling?: ResolvedSampling,
): string {
  const auto = formatStepAutoCriteriaDisplay(step, t, lotQuantity, resolvedSampling);
  return appendCriteriaSupplement(auto, step.value_spec) || step.acceptance_criteria || '';
}

export function getSamplingSpec(
  step: Pick<InspectionPlanStepItem, 'value_spec' | 'sampling_type'>,
): SamplingSpec | undefined {
  if (step.sampling_type !== 'sampling') return undefined;
  const nested = step.value_spec?.sampling;
  return normalizeSamplingSpec(nested);
}

export function formatSamplingCriteriaPreview(
  samplingType: string | undefined,
  valueSpec: InspectionStepValueSpec | undefined,
  t?: TFunction,
  lotQuantity?: number,
  resolvedSampling?: ResolvedSampling,
): string {
  if (samplingType !== 'sampling') return '';
  if (resolvedSampling?.label) {
    return resolvedSampling.label;
  }
  const normalized = normalizeSamplingSpec(valueSpec?.sampling);
  if (normalized.mode === 'gb2828_single') {
    if (!t) {
      return `GB/T 2828.1 水平 ${normalized.level}，${normalized.strictness}，AQL ${normalized.aql}（报检批量查表）`;
    }
    return t('app.kuaizhizao.quality.plans.stepSpec.samplingCriteriaGb2828Pending', {
      level: normalized.level,
      strictness: normalized.strictness,
      aql: normalized.aql,
    });
  }
  const s = resolveEffectiveSamplingSpec(normalized, lotQuantity);
  if (s.mode === 'lot_ratio') {
    const ratio = s.lot_sample_ratio ?? 10;
    if (!t) {
      const lotHint =
        lotQuantity != null && Number(lotQuantity) > 0
          ? `，n=${s.sample_size}（批量 ${lotQuantity}）`
          : '';
      return `抽检 批量 ${ratio}%${lotHint}，Ac=${s.accept_num}，Re=${s.reject_num}`;
    }
    const lotHint =
      lotQuantity != null && Number(lotQuantity) > 0
        ? `，n=${s.sample_size}（批量 ${lotQuantity}）`
        : '';
    return t('app.kuaizhizao.quality.plans.stepSpec.samplingCriteriaLotRatio', {
      ratio,
      lotHint,
      ac: s.accept_num,
      re: s.reject_num,
    });
  }
  if (!t) {
    return `抽检 n=${s.sample_size}，Ac=${s.accept_num}，Re=${s.reject_num}`;
  }
  return t('app.kuaizhizao.quality.plans.stepSpec.samplingCriteria', {
    n: s.sample_size,
    ac: s.accept_num,
    re: s.reject_num,
  });
}

export function applySamplingToValueSpec(
  valueSpec: InspectionStepValueSpec,
  samplingType: 'full' | 'sampling',
  samplingSpec?: SamplingSpec,
): InspectionStepValueSpec {
  const next = { ...valueSpec };
  if (samplingType === 'sampling') {
    next.sampling = normalizeSamplingSpec(samplingSpec ?? next.sampling);
  } else {
    delete next.sampling;
  }
  return next;
}

export interface InspectionPlanStepItem {
  sequence: number;
  step_key?: string;
  inspection_item: string;
  inspection_method?: string;
  acceptance_criteria?: string;
  value_type?: InspectionStepValueType | string;
  value_spec?: InspectionStepValueSpec;
  sampling_type: 'full' | 'sampling';
  quality_standard_id?: number;
  remarks?: string;
}

export type InspectionTemplateStepItem = InspectionPlanStepItem & {
  step_key?: string;
};

export function normalizeValueType(raw?: string | null): InspectionStepValueType {
  const s = (raw || 'boolean').toLowerCase();
  if (INSPECTION_STEP_VALUE_TYPES.includes(s as InspectionStepValueType)) {
    return s as InspectionStepValueType;
  }
  return 'boolean';
}

export function defaultValueSpec(
  valueType: InspectionStepValueType,
  t?: TFunction,
): InspectionStepValueSpec {
  const passLabel = t
    ? t('app.kuaizhizao.quality.common.result.qualified')
    : '合格';
  const failLabel = t
    ? t('app.kuaizhizao.quality.common.result.unqualified')
    : '不合格';

  const base = { required: true, allow_na: false, critical: false, require_photo: false };

  switch (valueType) {
    case 'boolean':
      return { ...base, pass_when: true };
    case 'single_select':
      return {
        ...base,
        options: [
          { value: 'pass', label: passLabel, result: 'pass' },
          { value: 'fail', label: failLabel, result: 'fail' },
        ],
      };
    case 'multi_select':
      return { ...base, options: [], pass_rule: 'no_defect_selected' };
    case 'text':
      return { ...base, multiline: false, max_length: 500, judgment: 'manual' };
    case 'numeric':
      return { ...base, decimal_places: 4, derived: false, formula: '' };
    default:
      return { ...base, pass_when: true };
  }
}

export type StepConductEntry = {
  value?: unknown;
  judgment?: string;
  judgment_source?: string;
  photos?: Array<{ uid?: string; name?: string; url?: string; status?: string }>;
};

export function stepSpecAllowsNa(valueSpec?: InspectionStepValueSpec): boolean {
  return valueSpec?.allow_na === true;
}

export function stepSpecIsCritical(valueSpec?: InspectionStepValueSpec): boolean {
  return valueSpec?.critical === true;
}

export function stepSpecRequiresPhoto(valueSpec?: InspectionStepValueSpec): boolean {
  return valueSpec?.require_photo === true;
}

export function stepSpecIsDerived(valueSpec?: InspectionStepValueSpec): boolean {
  return valueSpec?.derived === true;
}

const FORMULA_REF_PATTERN = /\{([^}]+)\}/g;

export function extractFormulaRefs(formula?: string): string[] {
  if (!formula) return [];
  const refs: string[] = [];
  let m: RegExpExecArray | null;
  const re = new RegExp(FORMULA_REF_PATTERN.source, 'g');
  while ((m = re.exec(formula)) !== null) {
    const ref = m[1]?.trim();
    if (ref) refs.push(ref);
  }
  return refs;
}

function safeEvalNumeric(expr: string): number | null {
  const sanitized = expr.replace(/\s+/g, '');
  if (!/^[\d.+\-*/()]+$/.test(sanitized)) return null;
  try {
    // eslint-disable-next-line no-new-func
    const result = new Function(`return (${sanitized})`)();
    const num = Number(result);
    return Number.isFinite(num) ? num : null;
  } catch {
    return null;
  }
}

export function evaluateDerivedFormula(
  formula: string | undefined,
  stepResults: Record<string, StepConductEntry> | undefined,
  decimalPlaces = 4,
): number | null {
  if (!formula || !stepResults) return null;
  let expr = formula;
  const refs = extractFormulaRefs(formula);
  for (const ref of refs) {
    const entry = stepResults[ref];
    if (!entry || entry.judgment === 'na') return null;
    const num = Number(entry.value);
    if (Number.isNaN(num)) return null;
    expr = expr.split(`{${ref}}`).join(String(num));
  }
  if (/\{[^}]+\}/.test(expr)) return null;
  const raw = safeEvalNumeric(expr);
  if (raw == null) return null;
  return Number(raw.toFixed(decimalPlaces));
}

export function bumpPlanVersion(version?: string): string {
  const v = (version || '1.0').trim();
  const m = v.match(/^(\d+)(?:\.(\d+))?$/);
  if (!m) return `${v}.1`;
  const major = Number(m[1]);
  const minor = Number(m[2] ?? 0) + 1;
  return `${major}.${minor}`;
}

export function stepsFingerprint(steps: InspectionPlanStepItem[]): string {
  return JSON.stringify(
    steps.map((s, i) => ({
      sequence: i,
      step_key: s.step_key,
      inspection_item: s.inspection_item,
      value_type: s.value_type,
      value_spec: s.value_spec,
      sampling_type: s.sampling_type,
    })),
  );
}

export function resolveStepJudgmentClient(
  step: InspectionTemplateStepItem,
  entry: StepConductEntry,
): 'pass' | 'fail' | 'na' | null {
  const manual = entry.judgment;
  if (manual === 'pass' || manual === 'fail' || manual === 'na') return manual;
  return judgeStepValueClient(step.value_type || 'boolean', step.value_spec, entry.value);
}

export function formatConductStepValue(
  valueType: string,
  valueSpec: InspectionStepValueSpec | undefined,
  entry: StepConductEntry,
  t: TFunction,
): string {
  if (entry.judgment === 'na') {
    return t('app.kuaizhizao.quality.template.judgmentNa');
  }
  const vt = normalizeValueType(valueType);
  const spec = { ...defaultValueSpec(vt, t), ...(valueSpec || {}) };
  const value = entry.value;
  if (value === undefined || value === null || value === '') return '-';

  if (vt === 'boolean') {
    const actual = value === true || value === 'true' || value === 1;
    return actual
      ? t('common.yes')
      : t('common.no');
  }
  if (vt === 'single_select') {
    const opts = (spec.options as Array<{ value: string; label: string }>) || [];
    const hit = opts.find((o) => String(o.value) === String(value));
    return hit?.label || String(value);
  }
  if (vt === 'multi_select') {
    const opts = (spec.options as Array<{ value: string; label: string }>) || [];
    const selected = Array.isArray(value) ? value.map(String) : [];
    return (
      selected.map((v) => opts.find((o) => o.value === v)?.label || v).join('、') || '-'
    );
  }
  return String(value);
}

export interface ConductStepsSummary {
  failCount: number;
  criticalFailCount: number;
  failLabels: string[];
  criticalFailLabels: string[];
}

export function summarizeConductSteps(
  steps: InspectionTemplateStepItem[],
  stepResults: Record<string, StepConductEntry> | undefined,
  itemResults: Record<string, unknown> | undefined,
  t: TFunction,
): ConductStepsSummary {
  const summary: ConductStepsSummary = {
    failCount: 0,
    criticalFailCount: 0,
    failLabels: [],
    criticalFailLabels: [],
  };
  if (!stepResults && !itemResults) return summary;

  steps.forEach((step, idx) => {
    const key = getStepConductKey(step, idx);
    const spec = { ...defaultValueSpec(normalizeValueType(step.value_type), t), ...(step.value_spec || {}) };
    const label = step.inspection_item || t('app.kuaizhizao.quality.template.inspectionItemFallback', { index: idx + 1 });

    let judgment: 'pass' | 'fail' | 'na' | null = null;
    if (step.value_type) {
      const entry = stepResults?.[key];
      if (entry) judgment = resolveStepJudgmentClient(step, entry);
    } else {
      const legacy = itemResults?.[key] ?? itemResults?.[String(idx)];
      if (legacy === 'pass' || legacy === 'fail') judgment = legacy;
    }

    if (judgment === 'fail') {
      summary.failCount += 1;
      summary.failLabels.push(label);
      if (stepSpecIsCritical(spec)) {
        summary.criticalFailCount += 1;
        summary.criticalFailLabels.push(label);
      }
    }
  });
  return summary;
}

export function getStepConductKey(step: InspectionTemplateStepItem, index: number): string {
  return step.step_key || String(index);
}

/**
 * 解析数值项有效合格上下限。
 * - 无目标值，或目标值落在 [下限, 上限] 内：按绝对合格限
 * - 有目标值且目标不在 [下限, 上限] 内：按相对目标公差
 *   （下限≥0 表示负向公差幅度，如目标 12、上下限 0.5 → 11.5 ~ 12.5；
 *    下限<0 则按 signed 偏差 target+lower）
 */
export function resolveNumericEffectiveLimits(spec: InspectionStepValueSpec | undefined): {
  lower?: number;
  upper?: number;
  target?: number;
  mode: 'absolute' | 'deviation';
} {
  const rawLo = spec?.lower_limit;
  const rawHi = spec?.upper_limit;
  const rawTarget = spec?.target;
  const lo = rawLo == null || rawLo === '' ? undefined : Number(rawLo);
  const hi = rawHi == null || rawHi === '' ? undefined : Number(rawHi);
  const target = rawTarget == null || rawTarget === '' ? undefined : Number(rawTarget);
  const hasLo = lo != null && !Number.isNaN(lo);
  const hasHi = hi != null && !Number.isNaN(hi);
  const hasTarget = target != null && !Number.isNaN(target);

  if (!hasTarget || (!hasLo && !hasHi)) {
    return {
      lower: hasLo ? lo : undefined,
      upper: hasHi ? hi : undefined,
      target: hasTarget ? target : undefined,
      mode: 'absolute',
    };
  }

  if (hasLo && hasHi && lo! <= target! && target! <= hi!) {
    return { lower: lo, upper: hi, target, mode: 'absolute' };
  }

  return {
    lower: hasLo ? (lo! < 0 ? target! + lo! : target! - lo!) : undefined,
    upper: hasHi ? target! + hi! : undefined,
    target,
    mode: 'deviation',
  };
}

export function judgeStepValueClient(
  valueType: string,
  valueSpec: InspectionStepValueSpec | undefined,
  value: unknown,
): 'pass' | 'fail' | null {
  const vt = normalizeValueType(valueType);
  const spec = { ...defaultValueSpec(vt), ...(valueSpec || {}) };

  // 缺陷多选：未选/空选即无缺陷 → 合格
  if (vt === 'multi_select') {
    const selected = new Set((Array.isArray(value) ? value : []).map(String));
    const defectValues = new Set(
      ((spec.options as Array<{ value: string; defect?: boolean }>) || [])
        .filter((o) => o.defect)
        .map((o) => String(o.value)),
    );
    for (const v of selected) {
      if (defectValues.has(v)) return 'fail';
    }
    return 'pass';
  }

  if (value === undefined || value === null || value === '') {
    return null;
  }

  if (vt === 'boolean') {
    const actual = value === true || value === 'true' || value === 1;
    const passWhen = spec.pass_when !== false;
    return actual === passWhen ? 'pass' : 'fail';
  }

  if (vt === 'single_select') {
    const opts = (spec.options as Array<{ value: string; result?: string }>) || [];
    const hit = opts.find((o) => String(o.value) === String(value));
    if (!hit) return null;
    return hit.result === 'fail' ? 'fail' : 'pass';
  }

  if (vt === 'numeric') {
    const num = Number(value);
    if (Number.isNaN(num)) return null;
    const { lower: lo, upper: hi } = resolveNumericEffectiveLimits(spec);
    if (lo != null && num < lo) return 'fail';
    if (hi != null && num > hi) return 'fail';
    if (lo == null && hi == null) return null;
    return 'pass';
  }

  return null;
}

export function formatAcceptanceCriteriaPreview(
  valueType: string,
  valueSpec?: InspectionStepValueSpec,
  t?: TFunction,
): string {
  const vt = normalizeValueType(valueType);
  const spec = { ...defaultValueSpec(vt, t), ...(valueSpec || {}) };
  const unit = spec.unit ? ` ${spec.unit}` : '';

  if (vt === 'boolean') {
    if (!t) {
      return spec.pass_when === false ? '合格：否' : '合格：是';
    }
    return spec.pass_when === false
      ? t('app.kuaizhizao.quality.plans.stepSpec.criteriaPassWhenNo')
      : t('app.kuaizhizao.quality.plans.stepSpec.criteriaPassWhenYes');
  }

  if (vt === 'numeric') {
    if (spec.derived && spec.formula) {
      return t
        ? t('app.kuaizhizao.quality.plans.stepSpec.criteriaDerived', { formula: spec.formula })
        : `派生：${spec.formula}`;
    }
    const bounds = resolveNumericEffectiveLimits(spec);
    const lo = bounds.lower;
    const hi = bounds.upper;
    if (lo != null && hi != null) {
      if (bounds.mode === 'deviation' && bounds.target != null) {
        return t
          ? t('app.kuaizhizao.quality.plans.stepSpec.criteriaRangeWithTarget', {
              lo,
              hi,
              target: bounds.target,
              unit,
            })
          : `${lo} ~ ${hi}${unit}（目标 ${bounds.target}）`;
      }
      return t
        ? t('app.kuaizhizao.quality.plans.stepSpec.criteriaRange', { lo, hi, unit })
        : `${lo} ~ ${hi}${unit}`;
    }
    if (lo != null) {
      return t
        ? t('app.kuaizhizao.quality.plans.stepSpec.criteriaGte', { lo, unit })
        : `≥ ${lo}${unit}`;
    }
    if (hi != null) {
      return t
        ? t('app.kuaizhizao.quality.plans.stepSpec.criteriaLte', { hi, unit })
        : `≤ ${hi}${unit}`;
    }
    if (bounds.target != null) {
      return t
        ? t('app.kuaizhizao.quality.plans.stepSpec.criteriaTarget', { target: bounds.target, unit })
        : `目标 ${bounds.target}${unit}`;
    }
    return '';
  }

  if (vt === 'text' || vt === 'multi_select') return '';
  return '';
}
