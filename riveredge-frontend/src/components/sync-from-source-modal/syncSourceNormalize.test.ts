import { describe, expect, it } from 'vitest';
import {
  extractKingdeeApiError,
  normalizeApiBodyToRows,
  suggestTargetToSourceMapping,
  SYNC_PREVIEW_ROW_LIMIT,
  withKingdeePreviewLimit,
} from './syncSourceUtils';
import {
  SALES_ORDER_SYNC_TARGET_ALIASES,
  SALES_ORDER_SYNC_TARGET_FIELDS,
} from '../../apps/kuaizhizao/pages/sales-management/sales-orders/salesOrderSyncFields';

describe('normalizeApiBodyToRows cosmic empty rows', () => {
  it('does not treat status envelope as a business row when rows is null', () => {
    const rows = normalizeApiBodyToRows({
      status: true,
      errorCode: '0',
      message: '',
      data: {
        filter: null,
        lastPage: true,
        pageNo: 1,
        pageSize: 10,
        rows: null,
        totalCount: '0',
      },
    });
    expect(rows).toEqual([]);
  });

  it('does not treat status envelope as a business row when rows is missing', () => {
    const rows = normalizeApiBodyToRows({
      status: true,
      errorCode: '0',
      data: { pageNo: 1, pageSize: 10, lastPage: true, totalCount: '0' },
    });
    expect(rows).toEqual([]);
  });

  it('surfaces DateTime NumberFormatException instead of empty rows', () => {
    const message =
      '参数【start_createtime】的类型为 DateTime，而传入值不能转换为该类型。java.lang.NumberFormatException,TraceId：fc19373c0eb4242a';
    expect(
      extractKingdeeApiError({
        status: false,
        errorCode: '400',
        message,
        data: null,
      }),
    ).toBe(message);

    expect(() =>
      normalizeApiBodyToRows({
        status: true,
        errorCode: '0',
        message,
        data: { pageNo: 1, pageSize: 10, rows: null },
      }),
    ).toThrow(/start_createtime/);
  });

  it('still expands real rows with billentry', () => {
    const rows = normalizeApiBodyToRows({
      status: true,
      errorCode: '0',
      data: {
        pageNo: 1,
        pageSize: 10,
        rows: [
          {
            billno: 'XSDD-1',
            bizdate: '2026-09-29',
            billstatus: 'C',
            customer_number: 'CUS-1',
            billentry: [{ qty: 2, material_masterid_number: 'M1' }],
          },
        ],
      },
    });
    expect(rows.length).toBe(1);
    expect(rows[0].billno).toBe('XSDD-1');
    expect(rows[0].billentryqty).toBe(2);

    const mapping = suggestTargetToSourceMapping(
      Object.keys(rows[0]),
      SALES_ORDER_SYNC_TARGET_FIELDS.map((f) => f.value),
      SALES_ORDER_SYNC_TARGET_ALIASES,
    );
    expect(mapping.order_code).toBe('billno');
    expect(mapping.order_date).toBe('bizdate');
    expect(Object.keys(mapping).length).toBeGreaterThan(1);
  });
});

describe('withKingdeePreviewLimit', () => {
  it('caps Cosmic getList pageSize for warehouse preview', () => {
    const limited = withKingdeePreviewLimit(
      { data: {}, pageNo: 3, pageSize: 1000 },
      SYNC_PREVIEW_ROW_LIMIT,
    );
    expect(limited?.pageNo).toBe(1);
    expect(limited?.pageSize).toBe(SYNC_PREVIEW_ROW_LIMIT);
    expect(limited?.data).toEqual({});
  });

  it('still caps Galaxy ExecuteBillQuery Limit', () => {
    const limited = withKingdeePreviewLimit({
      parameters: [
        JSON.stringify({ FormId: 'BD_MATERIAL', FieldKeys: 'FNumber', Limit: 2000, StartRow: 100 }),
      ],
    });
    const query = JSON.parse(String(limited?.parameters?.[0])) as Record<string, unknown>;
    expect(query.Limit).toBe(SYNC_PREVIEW_ROW_LIMIT);
    expect(query.StartRow).toBe(0);
  });
});
