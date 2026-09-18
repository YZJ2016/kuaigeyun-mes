/** 固定资产表单：折旧与净值计算（与后端 fa_core 一致） */

export type FaDepreciationMethod =
  | 'straight_line'
  | 'double_declining'
  | 'sum_of_years'
  | 'units_of_production'
  | 'none';

function lifeYearsFromMonths(usefulLifeMonths: number): number {
  const life = Number(usefulLifeMonths) || 0;
  if (life <= 0) return 0;
  return Math.max(1, Math.ceil(life / 12));
}

export function computePeriodDepreciation(params: {
  depreciationMethod?: string;
  originalValue: number;
  residualRate: number;
  usefulLifeMonths: number;
  depreciatedPeriods?: number;
  accumulatedDepreciation?: number;
  impairmentValue?: number;
  totalWorkload?: number;
  /** 工作量法当期工作量；不传时返回单位折旧额 */
  periodWorkload?: number | null;
}): number {
  const method = params.depreciationMethod || 'straight_line';
  if (method === 'none') return 0;

  const original = Number(params.originalValue) || 0;
  const rate = Number(params.residualRate) || 0;
  const life = Number(params.usefulLifeMonths) || 0;
  const used = Math.max(0, Number(params.depreciatedPeriods) || 0);
  const accumulated = Number(params.accumulatedDepreciation) || 0;
  const impairment = Number(params.impairmentValue) || 0;

  const residual = roundMoney(original * rate);
  const depreciable = roundMoney(original - residual);
  if (depreciable <= 0) return 0;

  const bookValue = roundMoney(original - accumulated - impairment);
  if (bookValue <= residual) return 0;

  const remainingDepreciable = roundMoney(bookValue - residual);

  if (method !== 'units_of_production') {
    if (life <= 0 || used >= life) return 0;
  }

  const remainingPeriods = life > 0 ? Math.max(1, life - used) : 1;
  let dep = 0;

  if (method === 'straight_line') {
    dep =
      impairment > 0
        ? roundMoney(remainingDepreciable / remainingPeriods)
        : roundMoney(depreciable / life);
  } else if (method === 'double_declining') {
    const ddb = roundMoney(bookValue * (2 / life));
    const sl = roundMoney(remainingDepreciable / remainingPeriods);
    dep = remainingPeriods <= 24 ? sl : ddb;
    if (dep < sl) dep = sl;
  } else if (method === 'sum_of_years') {
    const lifeYears = lifeYearsFromMonths(life);
    if (lifeYears <= 0) return 0;
    const yearIndex = Math.min(Math.floor(used / 12), lifeYears - 1);
    const remainingYears = lifeYears - yearIndex;
    if (remainingYears <= 0) return 0;
    let annual = 0;
    if (impairment > 0) {
      const sumRemaining = (remainingYears * (remainingYears + 1)) / 2;
      annual = roundMoney((remainingDepreciable * remainingYears) / sumRemaining);
    } else {
      const sumDigits = (lifeYears * (lifeYears + 1)) / 2;
      annual = roundMoney((depreciable * remainingYears) / sumDigits);
    }
    dep = roundMoney(annual / 12);
  } else if (method === 'units_of_production') {
    const workload = Number(params.totalWorkload) || 0;
    if (workload <= 0) return 0;
    const base = impairment > 0 ? remainingDepreciable : depreciable;
    const unitRate = roundMoney(base / workload);
    if (params.periodWorkload == null) {
      dep = unitRate;
    } else {
      const pw = Number(params.periodWorkload) || 0;
      if (pw <= 0) return 0;
      dep = roundMoney(unitRate * pw);
    }
  } else {
    dep =
      impairment > 0
        ? roundMoney(remainingDepreciable / remainingPeriods)
        : roundMoney(depreciable / life);
  }

  const maxDep = roundMoney(bookValue - residual);
  if (dep > maxDep) dep = maxDep;
  return dep > 0 ? dep : 0;
}

export function computeMonthlyDepreciation(
  originalValue: number,
  residualRate: number,
  usefulLifeMonths: number,
  options?: {
    depreciationMethod?: string;
    depreciatedPeriods?: number;
    accumulatedDepreciation?: number;
    impairmentValue?: number;
    totalWorkload?: number;
    periodWorkload?: number | null;
  },
): number {
  return computePeriodDepreciation({
    depreciationMethod: options?.depreciationMethod,
    originalValue,
    residualRate,
    usefulLifeMonths,
    depreciatedPeriods: options?.depreciatedPeriods,
    accumulatedDepreciation: options?.accumulatedDepreciation,
    impairmentValue: options?.impairmentValue,
    totalWorkload: options?.totalWorkload,
    periodWorkload: options?.periodWorkload,
  });
}

export function computeNetValue(
  originalValue: number,
  accumulatedDepreciation: number,
  impairmentValue: number,
): number {
  const original = Number(originalValue) || 0;
  const accumulated = Number(accumulatedDepreciation) || 0;
  const impairment = Number(impairmentValue) || 0;
  return roundMoney(original - accumulated - impairment);
}

export function computeExpectedResidual(originalValue: number, residualRate: number): number {
  const original = Number(originalValue) || 0;
  const rate = Number(residualRate) || 0;
  return roundMoney(original * rate);
}

export function computeRemainingPeriods(usefulLifeMonths: number, depreciatedPeriods: number): number {
  const life = Number(usefulLifeMonths) || 0;
  const used = Number(depreciatedPeriods) || 0;
  return Math.max(0, life - used);
}

function roundMoney(value: number): number {
  return Math.round(value * 10000) / 10000;
}

export function formatMoneyDisplay(value: number | undefined): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return '';
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export const FA_CHANGE_METHOD_OPTIONS = ['购入', '受捐', '盘盈', '自建', '导入', '其他'];

export const FA_UNIT_OPTIONS = ['台', '套', '个', '件', '辆', '张', '把', '米', '平方米'];
