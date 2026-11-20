/**
 * 销售订单列表批量导入：按订单编号（或缺省时客户+订单日期）合并多行产品明细。
 */
import type { TFunction } from 'i18next';

import type { Material } from '../../../../master-data/types/material';
import {
  findMaterialByImportCode,
  normalizeImportMaterialCode,
} from '../../../../master-data/utils/materialImportResolve';
import {
  parsePartnerDefaultPaymentMethodImport,
  parsePartnerSettlementTermsImport,
  buildPartnerDefaultPaymentMethodImportOptions,
  buildPartnerSettlementTermsImportOptions,
} from '../../../../master-data/utils/partner-static-labels';
import {
  buildFactoryImportTemplate,
  resolveFactoryImportHeaderIndexMap,
} from '../../../../../utils/spreadsheetImportTemplate';
import { pickImportExampleValue } from '../../../../../utils/loadImportDictionaryValues';
import {
  buildImportPriceTypeOptions,
  DEFAULT_SALES_PRICE_TYPE,
  parseImportPriceType,
} from '../shared/salesPriceType';
import {
  calcDocumentLineAmounts,
  computeSalesDocumentTotals,
  resolveSalesDocumentStoredLineAmount,
  resolveSalesDocumentStoredTotalAmount,
} from '../../../utils/documentLineAmounts';
import type { SalesOrder, SalesOrderItem } from '../../../services/sales-order';
import { ReviewStatus, SalesOrderStatus } from '../../../services/sales-order';

export type SalesOrderListImportDict = {
  MATERIAL_UNIT?: string[];
  CURRENCY?: string[];
  SHIPPING_METHOD?: string[];
  parseDict?: (dictionaryCode: string, raw?: string | null) => string | undefined;
  parseShippingMethod?: (raw?: string | null) => string | undefined;
};

export function buildSalesOrderListImportTemplate(
  t: TFunction,
  dict: SalesOrderListImportDict,
) {
  const unitOpts = dict.MATERIAL_UNIT ?? [];
  const priceTypeOpts = buildImportPriceTypeOptions(t);
  const paymentMethodOpts = buildPartnerDefaultPaymentMethodImportOptions(t);
  const settlementTermsOpts = buildPartnerSettlementTermsImportOptions(t);
  return buildFactoryImportTemplate(
    t,
    [
      {
        field: 'code',
        labelKey: 'app.kuaizhizao.salesOrder.orderCode',
        aliases: ['订单编号', '销售订单号', '单号'],
      },
      {
        field: 'date',
        required: true,
        labelKey: 'app.kuaizhizao.salesOrder.orderDate',
        aliases: ['订单日期', '日期'],
      },
      {
        field: 'delivery',
        labelKey: 'app.kuaizhizao.salesOrder.deliveryDate',
        aliases: ['交货日期', '交期'],
      },
      {
        field: 'customer',
        required: true,
        labelKey: 'app.kuaizhizao.salesOrder.customerName',
        aliases: ['客户', '客户名称', '客户编码'],
      },
      {
        field: 'customerContact',
        labelKey: 'app.kuaizhizao.salesOrder.customerContact',
        aliases: ['联系人'],
      },
      {
        field: 'customerPhone',
        labelKey: 'app.kuaizhizao.salesOrder.customerPhone',
        aliases: ['联系电话', '电话'],
      },
      {
        field: 'salesman',
        labelKey: 'app.kuaizhizao.salesOrder.salesman',
        aliases: ['销售员', '业务员'],
      },
      {
        field: 'shippingAddress',
        labelKey: 'app.kuaizhizao.salesOrder.shippingAddress',
        aliases: ['收货地址', '送货地址'],
      },
      {
        field: 'shippingMethod',
        labelKey: 'app.kuaizhizao.salesOrder.shippingMethod',
        aliases: ['发货方式'],
        options: dict.SHIPPING_METHOD,
      },
      {
        field: 'paymentMethod',
        labelKey: 'app.kuaizhizao.salesOrder.paymentMethod',
        aliases: ['付款方式'],
        options: paymentMethodOpts,
      },
      {
        field: 'settlementTerms',
        labelKey: 'app.kuaizhizao.salesOrder.settlementTerms',
        aliases: ['结算条款'],
        options: settlementTermsOpts,
      },
      {
        field: 'paymentCycle',
        labelKey: 'app.kuaizhizao.salesOrder.paymentCycle',
        aliases: ['付款周期', '账期'],
      },
      {
        field: 'currency',
        labelKey: 'app.kuaizhizao.quotation.form.currency',
        aliases: ['币种'],
        options: dict.CURRENCY,
      },
      {
        field: 'priceType',
        labelKey: 'app.kuaizhizao.salesOrder.priceType',
        aliases: ['价格类型'],
        options: priceTypeOpts,
      },
      {
        field: 'material',
        required: true,
        labelKey: 'app.kuaizhizao.salesContract.importHeaders.materialCode',
        aliases: ['产品编号', '物料编号', '物料编码'],
      },
      {
        field: 'quantity',
        required: true,
        labelKey: 'common.quantity',
        aliases: ['数量', '订购数量'],
      },
      {
        field: 'unitPrice',
        labelKey: 'app.kuaizhizao.salesContract.importHeaders.unitPrice',
        aliases: ['单价'],
      },
      {
        field: 'unit',
        labelKey: 'common.unit',
        aliases: ['单位'],
        options: unitOpts,
      },
      {
        field: 'notes',
        labelKey: 'common.remark',
        aliases: ['备注'],
      },
    ],
    [
      '',
      '2026-01-01',
      '2026-01-31',
      t('app.kuaizhizao.salesOrder.importExampleCustomer'),
      '',
      '',
      '',
      '',
      '',
      '',
      '',
      '',
      pickImportExampleValue(dict.CURRENCY, 'CNY'),
      pickImportExampleValue(
        priceTypeOpts,
        t('app.kuaizhizao.salesContract.priceTypeTaxInclusive'),
      ),
      t('app.kuaizhizao.quotation.importExample.materialCode'),
      '100',
      '1.5',
      pickImportExampleValue(unitOpts, t('app.kuaizhizao.salesContract.defaultUnit')),
      t('app.kuaizhizao.salesOrder.importExampleNotes'),
    ],
  );
}

type CustomerLike = {
  id?: number;
  customer_id?: number;
  name?: string;
  customer_name?: string;
  code?: string;
};

export type SalesOrderListImportPayload = Partial<SalesOrder> & {
  customer_id: number;
  customer_name: string;
  order_date: string;
  items: Array<
    Pick<
      SalesOrderItem,
      | 'material_id'
      | 'material_code'
      | 'material_name'
      | 'material_spec'
      | 'material_unit'
      | 'required_quantity'
      | 'unit_price'
      | 'tax_rate'
      | 'item_amount'
      | 'delivery_date'
      | 'notes'
    >
  >;
};

export function parseSalesOrderListImport(
  data: unknown[][],
  opts: {
    t: TFunction;
    importHeaderMap: Record<string, string>;
    customers: CustomerLike[];
    materials: Material[];
    parseDict?: (dictionaryCode: string, raw?: string | null) => string | undefined;
    parseShippingMethod?: (raw?: string | null) => string | undefined;
  },
): {
  errors: Array<{ row: number; message: string }>;
  items: SalesOrderListImportPayload[];
} {
  const { t, importHeaderMap, customers, materials, parseDict, parseShippingMethod } = opts;
  const parse = (code: string, raw?: string | null) =>
    parseDict ? parseDict(code, raw) : String(raw ?? '').trim() || undefined;
  const headers = (data[0] || []).map((h) => String(h || '').trim());
  const rows = (data.slice(2) as unknown[][]).filter((row) =>
    row?.some((c) => c != null && String(c).trim() !== ''),
  );
  const headerIndexMap = resolveFactoryImportHeaderIndexMap(headers, importHeaderMap);
  const idx = {
    code: headerIndexMap.code ?? -1,
    date: headerIndexMap.date ?? -1,
    delivery: headerIndexMap.delivery ?? -1,
    customer: headerIndexMap.customer ?? -1,
    customerContact: headerIndexMap.customerContact ?? -1,
    customerPhone: headerIndexMap.customerPhone ?? -1,
    salesman: headerIndexMap.salesman ?? -1,
    shippingAddress: headerIndexMap.shippingAddress ?? -1,
    shippingMethod: headerIndexMap.shippingMethod ?? -1,
    paymentMethod: headerIndexMap.paymentMethod ?? -1,
    settlementTerms: headerIndexMap.settlementTerms ?? -1,
    paymentCycle: headerIndexMap.paymentCycle ?? -1,
    currency: headerIndexMap.currency ?? -1,
    priceType: headerIndexMap.priceType ?? -1,
    material: headerIndexMap.material ?? -1,
    qty: headerIndexMap.quantity ?? -1,
    price: headerIndexMap.unitPrice ?? -1,
    unit: headerIndexMap.unit ?? -1,
    notes: headerIndexMap.notes ?? -1,
  };

  const errors: Array<{ row: number; message: string }> = [];
  if (idx.customer < 0 || idx.date < 0 || idx.material < 0 || idx.qty < 0) {
    return {
      errors: [
        {
          row: 1,
          message: t('app.kuaizhizao.salesOrder.listImport.missingRequiredColumns'),
        },
      ],
      items: [],
    };
  }

  const cell = (row: unknown[], i: number) => (i >= 0 ? String(row[i] ?? '').trim() : '');
  type GroupAcc = {
    code?: string;
    customer: string;
    date: string;
    delivery?: string;
    customerContact?: string;
    customerPhone?: string;
    salesman?: string;
    shippingAddress?: string;
    shippingMethod?: string;
    paymentMethod?: string;
    settlementTerms?: string;
    paymentTermsDays?: number;
    currency: string;
    priceType: string;
    notes?: string;
    items: SalesOrderListImportPayload['items'];
  };
  const groupMap = new Map<string, GroupAcc>();

  rows.forEach((row, i) => {
    const rowNum = i + 3;
    const customerName = cell(row, idx.customer);
    const dateVal = cell(row, idx.date);
    const materialCode = normalizeImportMaterialCode(cell(row, idx.material));
    const qty = Number(row[idx.qty]);
    if (!customerName) {
      errors.push({
        row: rowNum,
        message: t('app.kuaizhizao.quotation.validation.customerRequired'),
      });
      return;
    }
    if (!dateVal) {
      errors.push({
        row: rowNum,
        message: t('app.kuaizhizao.salesOrder.listImport.orderDateRequired'),
      });
      return;
    }
    if (!materialCode) {
      errors.push({
        row: rowNum,
        message: t('app.kuaizhizao.quotation.validation.materialRequired'),
      });
      return;
    }
    if (Number.isNaN(qty) || qty <= 0) {
      errors.push({
        row: rowNum,
        message: t('app.kuaizhizao.quotation.validation.qtyPositive'),
      });
      return;
    }
    const mat = findMaterialByImportCode(materials, materialCode);
    if (!mat) {
      errors.push({
        row: rowNum,
        message: t('app.kuaizhizao.quotation.validation.materialNotFound', {
          code: materialCode,
        }),
      });
      return;
    }

    const code = cell(row, idx.code);
    const priceType = parseImportPriceType(cell(row, idx.priceType) || undefined, t);
    const unitPriceRaw = idx.price >= 0 ? Number(row[idx.price]) : NaN;
    const unitPrice = Number.isFinite(unitPriceRaw)
      ? unitPriceRaw
      : Number(
          (mat as any)?.defaults?.defaultSalePrice ??
            (mat as any)?.defaults?.default_sale_price ??
            (mat as any)?.defaultSalePrice ??
            (mat as any)?.default_sale_price,
        ) || 0;
    const taxRate =
      Number(
        (mat as any)?.defaults?.defaultTaxRate ?? (mat as any)?.defaults?.default_tax_rate,
      ) || 0;
    const groupKey = code || `${customerName}|${dateVal}`;
    if (!groupMap.has(groupKey)) {
      const cycleRaw = cell(row, idx.paymentCycle);
      const cycleDigits = cycleRaw.replace(/\D/g, '');
      const shippingRaw = cell(row, idx.shippingMethod);
      groupMap.set(groupKey, {
        code: code || undefined,
        customer: customerName,
        date: dateVal,
        delivery: cell(row, idx.delivery) || undefined,
        customerContact: cell(row, idx.customerContact) || undefined,
        customerPhone: cell(row, idx.customerPhone) || undefined,
        salesman: cell(row, idx.salesman) || undefined,
        shippingAddress: cell(row, idx.shippingAddress) || undefined,
        shippingMethod:
          (parseShippingMethod ? parseShippingMethod(shippingRaw) : undefined) ||
          parse('SHIPPING_METHOD', shippingRaw),
        paymentMethod: parsePartnerDefaultPaymentMethodImport(
          cell(row, idx.paymentMethod) || undefined,
          t,
        ),
        settlementTerms: parsePartnerSettlementTermsImport(
          cell(row, idx.settlementTerms) || undefined,
          t,
        ),
        paymentTermsDays: cycleDigits ? parseInt(cycleDigits, 10) : undefined,
        currency: parse('CURRENCY', cell(row, idx.currency)) || 'CNY',
        priceType,
        notes: cell(row, idx.notes) || undefined,
        items: [],
      });
    }
    const g = groupMap.get(groupKey)!;
    const unit =
      parse('MATERIAL_UNIT', cell(row, idx.unit)) ||
      (mat as any).baseUnit ||
      (mat as any).base_unit ||
      'PCS';
    const rowDelivery = cell(row, idx.delivery) || undefined;
    if (rowDelivery && !g.delivery) {
      g.delivery = rowDelivery;
    }
    const amounts = calcDocumentLineAmounts(qty, unitPrice, taxRate, g.priceType);
    g.items.push({
      material_id: Number(mat.id),
      material_code: (mat as any).mainCode || (mat as any).code || materialCode,
      material_name: mat.name || '',
      material_spec: (mat as any).specification || '',
      material_unit: unit,
      required_quantity: qty,
      unit_price: unitPrice,
      tax_rate: taxRate,
      item_amount: resolveSalesDocumentStoredLineAmount(amounts, g.priceType),
      delivery_date: rowDelivery || g.delivery || undefined,
      notes: cell(row, idx.notes) || undefined,
    });
  });

  if (errors.length) return { errors, items: [] };

  const items: SalesOrderListImportPayload[] = [];
  for (const g of groupMap.values()) {
    const cust = customers.find(
      (c) =>
        (c.name || '').trim() === g.customer.trim() ||
        (c.customer_name || '').trim() === g.customer.trim() ||
        (c.code || '').trim() === g.customer.trim(),
    );
    const customerId = Number(cust?.id ?? cust?.customer_id);
    if (!Number.isFinite(customerId) || customerId <= 0) {
      errors.push({
        row: 0,
        message: t('app.kuaizhizao.salesOrder.listImport.customerNotFound', {
          name: g.customer,
        }),
      });
      continue;
    }
    const priceType = g.priceType || DEFAULT_SALES_PRICE_TYPE;
    const sums = computeSalesDocumentTotals(
      g.items,
      [],
      priceType,
      'required_quantity',
      0,
    );
    const salesmanRaw = g.salesman?.trim();
    const salesmanAsId = salesmanRaw && /^\d+$/.test(salesmanRaw)
      ? parseInt(salesmanRaw, 10)
      : undefined;
    items.push({
      order_code: g.code,
      order_date: g.date,
      delivery_date: g.delivery,
      customer_id: customerId,
      customer_name: (cust?.name || cust?.customer_name || g.customer).trim(),
      customer_contact: g.customerContact,
      customer_phone: g.customerPhone,
      salesman_id: salesmanAsId,
      salesman_name: salesmanAsId == null ? salesmanRaw : undefined,
      shipping_address: g.shippingAddress,
      shipping_method: g.shippingMethod,
      payment_method_code: g.paymentMethod,
      settlement_terms_code: g.settlementTerms,
      payment_terms_days: g.paymentTermsDays,
      currency_code: g.currency,
      price_type: priceType,
      notes: g.notes,
      discount_amount: 0,
      total_amount: resolveSalesDocumentStoredTotalAmount(sums, priceType),
      status: SalesOrderStatus.DRAFT,
      review_status: ReviewStatus.PENDING,
      items: g.items,
    });
  }

  return { errors, items };
}
