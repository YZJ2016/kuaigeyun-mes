/**
 * 导入单元格文本保全：禁止对编码/名称等非数值格全局去逗号。
 * 仅当符合「千分位数字」形态时才去掉逗号，供数量/金额解析。
 */

/** 美式千分位：1,234 / 1,234.56 / -12,345.6 */
const US_THOUSANDS_RE = /^-?\d{1,3}(,\d{3})+(\.\d+)?([eE][+-]?\d+)?$/;

/**
 * 保留编码、名称中的逗号与特殊字符；仅剥离千分位数字里的逗号。
 */
export function spreadsheetPlainCellText(raw: unknown): string {
  const s = String(raw ?? '').trim();
  if (!s) return '';
  if (!s.includes(',')) return s;
  if (US_THOUSANDS_RE.test(s)) {
    return s.replace(/,/g, '');
  }
  return s;
}

/**
 * 数值比较用：在已确认两侧为数字展示时去掉逗号。
 * 不要用于物料编码 / 名称列。
 */
export function spreadsheetNumericCompareText(raw: unknown): string {
  return String(raw ?? '')
    .trim()
    .replace(/,/g, '');
}
