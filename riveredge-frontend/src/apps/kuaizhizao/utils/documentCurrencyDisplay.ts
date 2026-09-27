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

export function resolveDocumentCurrencyInputPrefix(currencyCode: string | null | undefined): string {
  const code = (currencyCode ?? '').trim().toUpperCase();
  if (!code) {
    return CURRENCY_INPUT_PREFIX.CNY;
  }
  return CURRENCY_INPUT_PREFIX[code] ?? code;
}
