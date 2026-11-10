import { describe, expect, it } from 'vitest';
import { spreadsheetNumericCompareText, spreadsheetPlainCellText } from './spreadsheetPreserveText';
import { isExportTextColumnKey } from './exportRecordsXlsx';

describe('spreadsheetPlainCellText', () => {
  it('keeps commas inside material names/codes', () => {
    expect(spreadsheetPlainCellText('Widget, large')).toBe('Widget, large');
    expect(spreadsheetPlainCellText('A,B-1')).toBe('A,B-1');
  });

  it('strips US thousands separators only', () => {
    expect(spreadsheetPlainCellText('1,234')).toBe('1234');
    expect(spreadsheetPlainCellText('1,234.56')).toBe('1234.56');
    expect(spreadsheetPlainCellText('-12,345.6')).toBe('-12345.6');
  });

  it('does not treat European-looking decimals as thousands', () => {
    expect(spreadsheetPlainCellText('12,34')).toBe('12,34');
  });
});

describe('spreadsheetNumericCompareText', () => {
  it('strips all commas for numeric compare', () => {
    expect(spreadsheetNumericCompareText('1,234.5')).toBe('1234.5');
  });
});

describe('isExportTextColumnKey', () => {
  it('marks identity columns as text', () => {
    expect(isExportTextColumnKey('material_code')).toBe(true);
    expect(isExportTextColumnKey('order_code')).toBe(true);
    expect(isExportTextColumnKey('customer_name')).toBe(true);
    expect(isExportTextColumnKey('customer_phone')).toBe(true);
    expect(isExportTextColumnKey('shipping_address')).toBe(true);
  });

  it('leaves quantity/amount keys as non-text by default', () => {
    expect(isExportTextColumnKey('required_quantity')).toBe(false);
    expect(isExportTextColumnKey('total_amount')).toBe(false);
    expect(isExportTextColumnKey('unit_price')).toBe(false);
  });
});
