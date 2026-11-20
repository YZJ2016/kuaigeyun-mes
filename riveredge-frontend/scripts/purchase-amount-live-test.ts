/**
 * 价税合计全场景实测：合并 purchaseOrderAmounts.test + derive-guard + 扩展矩阵。
 * 不装 E2E。运行: npx vite-node scripts/purchase-amount-live-test.ts
 */
import {
  computePurchaseOrderHeaderAmountsForSave,
  computePurchaseReceiptFormLineAmounts,
  computePurchaseReceiptFormGoodsTotals,
  purchaseOrderFormLineToStored,
  purchaseOrderTaxRateToPercent,
  purchaseStoredExclAsFormItemAmount,
  readPurchaseOrderEnteredUnitPrice,
  resolvePurchaseOrderDisplayAmount,
  resolvePurchaseOrderLineAmounts,
} from '../src/apps/kuaizhizao/pages/purchase-management/shared/purchaseOrderAmounts';
import {
  calcDocumentLineAmounts,
  documentLineExclMatchesDerived,
  documentLineInclMatchesDerived,
  syncFormListLineItemAmountAfterQuantityChange,
} from '../src/apps/kuaizhizao/utils/documentLineAmounts';

let pass = 0;
let fail = 0;

function ok(name: string, cond: boolean, detail?: string) {
  if (cond) {
    pass += 1;
    console.log('PASS', name);
  } else {
    fail += 1;
    console.log('FAIL', name, detail ?? '');
  }
}

function near(a: number, b: number, tol = 0.02) {
  return Math.abs(a - b) <= tol;
}

function lineEq(
  name: string,
  r: { excl: number; tax: number; incl: number },
  e: { excl: number; tax: number; incl: number },
  tol = 0.02,
) {
  ok(
    name,
    near(r.incl, e.incl, tol) && near(r.excl, e.excl, tol) && near(r.tax, e.tax, tol),
    `got incl=${r.incl} excl=${r.excl} tax=${r.tax}`,
  );
}

// --- purchaseStoredExclAsFormItemAmount.test ---
ok(
  'storedExcl 含税不映射 item_amount',
  purchaseStoredExclAsFormItemAmount(97.35, 'tax_inclusive') === undefined,
);
ok(
  'storedExcl 不含税映射',
  purchaseStoredExclAsFormItemAmount(97.35, 'tax_exclusive') === 97.35,
);

// --- purchaseOrderTaxRateToPercent ---
ok('税率 1% 保持', purchaseOrderTaxRateToPercent(1) === 1);
ok('税率 0.01→1%', purchaseOrderTaxRateToPercent(0.01) === 1);
ok('税率 0.13→13%', purchaseOrderTaxRateToPercent(0.13) === 13);
ok('税率 13→13%', purchaseOrderTaxRateToPercent(13) === 13);
{
  const line = resolvePurchaseOrderLineAmounts(
    { ordered_quantity: 1, unit_price: 100, tax_rate: 1 },
    'tax_exclusive',
  );
  ok('1% 不含税行', line.taxPct === 1 && line.excl === 100 && line.tax === 1 && line.incl === 101);
}

// --- purchaseOrderAmounts unified ---
{
  const stored = purchaseOrderFormLineToStored(800, 1, 13, 'tax_inclusive', 2);
  ok('PO 含税800落库 incl', stored.incl === 800);
  const header = computePurchaseOrderHeaderAmountsForSave(
    [{ ordered_quantity: 1, unit_price: 800, tax_rate: 13 }],
    'tax_inclusive',
  );
  ok('PO 头 net=价税', header.net_amount === 800);
  ok(
    'PO 列表展示',
    resolvePurchaseOrderDisplayAmount({ net_amount: header.net_amount }) === 800,
  );
}
{
  const stored = purchaseOrderFormLineToStored(600, 1, 13, 'tax_inclusive', 4);
  ok('PO display 600', stored.display_unit_price === 600 && stored.incl === 600);
  ok(
    'PO 回填单价',
    readPurchaseOrderEnteredUnitPrice(
      { display_unit_price: stored.display_unit_price, unit_price: stored.unit_price },
      'tax_inclusive',
    ) === 600,
  );
}
ok(
  '含税无 display 不从未税 unit 反推',
  readPurchaseOrderEnteredUnitPrice({ unit_price: 530.9735 }, 'tax_inclusive') === null,
);

lineEq(
  '入库 1×60 含税 display',
  computePurchaseReceiptFormLineAmounts(
    { receipt_quantity: 1, display_unit_price: 60, unit_price: 53.1, tax_rate: 13 },
    13,
    'tax_inclusive',
    null,
  ),
  { incl: 60, excl: 53.1, tax: 6.9 },
);

lineEq(
  '入库 3×55 含税 无 display（编辑场景）',
  computePurchaseReceiptFormLineAmounts(
    { receipt_quantity: 3, unit_price: 55, tax_rate: 13 },
    13,
    'tax_inclusive',
    null,
  ),
  { incl: 165, excl: 146.02, tax: 18.98 },
);

lineEq(
  '入库 API display=55',
  computePurchaseReceiptFormLineAmounts(
    { receipt_quantity: 2, display_unit_price: 55, unit_price: 48.6725, tax_rate: 13 },
    13,
    'tax_inclusive',
    null,
  ),
  { incl: 110, excl: 97.35, tax: 12.65 },
);

lineEq(
  '入库 PO含税 2×55',
  computePurchaseReceiptFormLineAmounts(
    {
      receipt_quantity: 2,
      display_unit_price: 55,
      unit_price: 48.6725,
      tax_rate: 13,
      purchase_order_item_id: 101,
    },
    13,
    'tax_inclusive',
    {
      priceType: 'tax_inclusive',
      headerTaxRate: 13,
      poiById: {
        101: {
          ordered_quantity: 2,
          total_price: 97.35,
          unit_price: 48.6725,
          display_unit_price: 55,
          tax_rate: 13,
        },
      },
    },
  ),
  { incl: 110, excl: 97.35, tax: 12.65 },
);

lineEq(
  '入库 不含税 1000×8.8496',
  computePurchaseReceiptFormLineAmounts(
    {
      receipt_quantity: 1000,
      unit_price: 8.8496,
      tax_rate: 13,
      purchase_order_item_id: 101,
      total_amount: 8849.56,
    },
    0.13,
    'tax_exclusive',
    {
      priceType: 'tax_exclusive',
      headerTaxRate: 0.13,
      poiById: {
        101: {
          ordered_quantity: 1000,
          total_price: 8849.56,
          unit_price: 8.84956,
          tax_rate: 13,
        },
      },
    },
  ),
  { incl: 10000.05, excl: 8849.6, tax: 1150.45 },
  0.1,
);

// --- documentLineAmounts derive-guard ---
{
  const line = calcDocumentLineAmounts(1, 600, 13, 'tax_inclusive');
  ok(
    'derive excl 600',
    documentLineExclMatchesDerived(line.excl, 1, 600, 13, 'tax_inclusive'),
  );
  ok(
    'derive incl 600',
    documentLineInclMatchesDerived(
      line.incl,
      { qty: 1, unit_price: 600, tax_rate: 13 },
      'tax_inclusive',
    ),
  );
}
ok(
  '用户改总价不匹配',
  !documentLineInclMatchesDerived(
    601,
    { qty: 1, unit_price: 600, tax_rate: 13 },
    'tax_inclusive',
  ),
);
{
  let items = [{ quote_quantity: 2, unit_price: 6, tax_rate: 13, item_amount: 6 }];
  const form = {
    getFieldValue: (name: string | (string | number)[]) => {
      if (name === 'items' || (Array.isArray(name) && name[0] === 'items')) return items;
      if (name === 'price_type') return 'tax_inclusive';
      return undefined;
    },
    setFieldsValue: (values: Record<string, unknown>) => {
      if (Array.isArray(values.items)) items = values.items as typeof items;
    },
  };
  ok(
    '改数量同步价税 item_amount',
    syncFormListLineItemAmountAfterQuantityChange(form, 0, 'quote_quantity', 2) === true &&
      items[0].item_amount === 12,
  );
}

// --- 扩展矩阵（销售同源公式 + 头表 + 错法对照）---
lineEq(
  '销售共用 含税 66750×1',
  calcDocumentLineAmounts(1, 66750, 13, 'tax_inclusive'),
  { incl: 66750, excl: 59070.8, tax: 7679.2 },
  0.5,
);
lineEq(
  '销售共用 不含税 59070.8×1',
  calcDocumentLineAmounts(1, 59070.8, 13, 'tax_exclusive'),
  { incl: 66750, excl: 59070.8, tax: 7679.2 },
  0.5,
);
lineEq(
  '销售 0.5×1950 不含税',
  calcDocumentLineAmounts(0.5, 1950, 13, 'tax_exclusive'),
  { incl: 1101.75, excl: 975, tax: 126.75 },
);
lineEq('旧 UI 错法 3×55', calcDocumentLineAmounts(3, 55, 13, 'tax_exclusive'), {
  incl: 186.45,
  excl: 165,
  tax: 21.45,
});
{
  const s = purchaseOrderFormLineToStored(55, 3, 13, 'tax_inclusive', 4);
  lineEq('落库 55×3', { excl: s.excl, tax: s.tax, incl: s.incl }, { incl: 165, excl: 146.02, tax: 18.98 });
}
{
  const t = computePurchaseReceiptFormGoodsTotals(
    [
      { receipt_quantity: 3, unit_price: 55, tax_rate: 13 },
      { receipt_quantity: 2, display_unit_price: 55, unit_price: 48.6725, tax_rate: 13 },
    ],
    13,
    'tax_inclusive',
    null,
  );
  ok('入库头汇总 incl=275', near(t.goodsIncl, 275, 0.05), `goodsIncl=${t.goodsIncl}`);
}
lineEq(
  '对账 8×22.566 不含税（BE receipt rollup 同源）',
  calcDocumentLineAmounts(8, 22.566, 13, 'tax_exclusive'),
  { incl: 204.0, excl: 180.53, tax: 23.47 },
  0.02,
);
lineEq(
  '对账 12×22.894 不含税（BE receipt rollup 同源）',
  calcDocumentLineAmounts(12, 22.894, 13, 'tax_exclusive'),
  { incl: 310.44, excl: 274.73, tax: 35.71 },
  0.02,
);

console.log('---');
console.log(`前端价税实测: ${pass} 通过, ${fail} 失败, 合计 ${pass + fail} 场景`);
process.exit(fail > 0 ? 1 : 0);