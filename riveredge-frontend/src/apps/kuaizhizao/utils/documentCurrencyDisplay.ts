import type { TFunction } from 'i18next';
import { getLocalizedCurrencyLabel } from '../../../utils/systemDictionaryLabels';

/** 单据金额输入框前缀：常见币种符号，否则回退币种代码 */
const CURRENCY_INPUT_PREFIX: Record<string, string> = {
  CNY: '¥',
  JPY: '¥',
  USD: '$',
  EUR: '€',
  GBP: '£',
  HKD: 'HK$',
  AUD: 'A$',
  CAD: 'C$',
  SGD: 'S$',
};

/** 列标题兜底：无 i18n 时用中文币种名 */
const CURRENCY_UNIT_NAME_FALLBACK: Record<string, string> = {
  CNY: '元',
  USD: '美元',
  EUR: '欧元',
  GBP: '英镑',
  JPY: '日元',
  HKD: '港币',
  AUD: '澳元',
  CAD: '加元',
  SGD: '新加坡元',
};

export function resolveDocumentCurrencyInputPrefix(currencyCode: string | null | undefined): string {
  const code = (currencyCode ?? '').trim().toUpperCase();
  if (!code) {
    return CURRENCY_INPUT_PREFIX.CNY;
  }
  return CURRENCY_INPUT_PREFIX[code] ?? code;
}

/** 去掉字典文案末尾的「 (USD)」类代码，得到「美元」「欧元」等名称 */
function stripCurrencyCodeSuffix(label: string): string {
  return label.replace(/\s*\([A-Za-z]{3}\)\s*$/u, '').trim();
}

/**
 * 列标题用币种名称（如「美元」「欧元」）；人民币习惯写「元」。
 * 金额输入前缀仍用 {@link resolveDocumentCurrencyInputPrefix} 的符号。
 */
export function resolveDocumentCurrencyUnitLabel(
  currencyCode: string | null | undefined,
  t?: TFunction,
): string {
  const code = (currencyCode ?? '').trim().toUpperCase();
  if (!code || code === 'CNY') {
    return CURRENCY_UNIT_NAME_FALLBACK.CNY;
  }
  if (t) {
    const name = stripCurrencyCodeSuffix(getLocalizedCurrencyLabel(code, t));
    if (name) return name;
  }
  return CURRENCY_UNIT_NAME_FALLBACK[code] ?? code;
}

export function documentCurrencyTitleVars(currencyCode?: string | null, t?: TFunction) {
  return { currency: resolveDocumentCurrencyUnitLabel(currencyCode, t) };
}
