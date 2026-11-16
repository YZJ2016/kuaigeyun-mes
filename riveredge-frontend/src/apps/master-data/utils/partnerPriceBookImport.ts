/**
 * 客户/供应商价格本 Excel 导入（标准价 + 数量阶梯，走 bulk API）
 */

import type { TFunction } from 'i18next';
import {
  buildFactoryImportTemplate,
  resolveFactoryImportHeaderIndexMap,
} from '../../../utils/spreadsheetImportTemplate';
import type { Material } from '../types/material';
import type { Customer, Supplier } from '../types/supply-chain';
import type {
  PartnerPriceBookBulkCreate,
  PartnerPriceBookBulkConflictPolicy,
  PartnerPriceBookType,
  PartnerPriceTierLine,
} from '../types/partner-price-book';
import { normalizeTierPricesForSubmit } from '../components/PartnerPriceTierLinesEditor';
import { createPartnerPriceBookApi } from '../services/partner-price-book';
import type { UniImportCommitContext } from '../../../components/uni-import';

export function buildPartnerPriceBookImportTemplate(
  t: TFunction,
  partnerType: PartnerPriceBookType,
) {
  const isCustomer = partnerType === 'customer';
  const partnerCodeLabel = isCustomer
    ? t('field.customer.code', '客户编号')
    : t('field.supplier.code', '供应商编号');
  const partnerNameLabel = isCustomer
    ? t('field.customer.name', '客户名称')
    : t('field.supplier.name', '供应商名称');

  return buildFactoryImportTemplate(
    t,
    [
      { field: 'partnerCode', required: true, labelKey: 'app.master-data.priceBook.import.partnerCode', aliases: [partnerCodeLabel, '*客户编号', '*供应商编号'] },
      { field: 'partnerName', labelKey: 'app.master-data.priceBook.import.partnerName', aliases: [partnerNameLabel] },
      { field: 'materialCode', required: true, labelKey: 'app.master-data.priceBook.import.materialCode', aliases: ['物料主编号', '物料编码'] },
      { field: 'unitPrice', labelKey: 'app.master-data.priceBook.standardUnitPrice', aliases: ['标准价', 'unit_price'] },
      { field: 'tierMinQty', labelKey: 'app.master-data.priceBook.import.tierMinQty', aliases: ['tier_min_qty', '阶梯起订量'] },
      { field: 'tierMaxQty', labelKey: 'app.master-data.priceBook.import.tierMaxQty', aliases: ['tier_max_qty', '阶梯上限量'] },
      { field: 'tierUnitPrice', labelKey: 'app.master-data.priceBook.import.tierUnitPrice', aliases: ['tier_unit_price', '阶梯单价'] },
      { field: 'unit', labelKey: 'app.master-data.materialForm.baseUnit', aliases: ['单位'] },
      { field: 'taxRate', labelKey: 'app.master-data.defaults.defaultTaxRate', aliases: ['税率'] },
      {
        field: 'priceType',
        labelKey: 'app.kuaizhizao.salesOrder.priceType',
        options: [t('app.kuaizhizao.salesOrder.taxInclusive'), t('app.kuaizhizao.salesOrder.taxExclusive')],
      },
      { field: 'partnerMaterialCode', labelKey: isCustomer ? 'app.master-data.priceBook.customerMaterialCode' : 'app.master-data.priceBook.supplierMaterialCode' },
      { field: 'partnerMaterialName', labelKey: isCustomer ? 'app.master-data.priceBook.customerMaterialName' : 'app.master-data.priceBook.supplierMaterialName' },
      { field: 'effectiveFrom', labelKey: 'app.master-data.priceBook.effectiveFrom' },
      { field: 'effectiveTo', labelKey: 'app.master-data.priceBook.effectiveTo' },
      { field: 'remark', labelKey: 'common.remark' },
    ],
    [
      isCustomer ? 'C001' : 'S001',
      isCustomer ? t('app.master-data.priceBook.import.examplePartnerName', '示例伙伴') : t('app.master-data.priceBook.import.examplePartnerName', '示例伙伴'),
      'MAT-001',
      '100',
      '1',
      '99',
      '105',
      'PCS',
      '13',
      t('app.kuaizhizao.salesOrder.taxInclusive'),
      '',
      '',
      '2026-01-01',
      '',
      '',
    ],
  );
}

type ParsedGroup = {
  rowNums: number[];
  partnerId: number;
  materialId: number;
  unitPrice?: number;
  tierLines: PartnerPriceTierLine[];
  unit?: string;
  taxRate?: number;
  priceType?: 'tax_inclusive' | 'tax_exclusive';
  partnerMaterialCode?: string;
  partnerMaterialName?: string;
  effectiveFrom?: string;
  effectiveTo?: string;
  remark?: string;
};

function cell(row: unknown[], index: number): string {
  if (index < 0) return '';
  return String(row[index] ?? '').trim();
}

function parseNumber(raw: string): number | undefined {
  if (!raw) return undefined;
  const n = Number(raw.replace(/,/g, ''));
  return Number.isFinite(n) ? n : undefined;
}

function parsePriceType(raw: string, t: TFunction): 'tax_inclusive' | 'tax_exclusive' | undefined {
  const s = raw.trim();
  if (!s) return undefined;
  const inclusive = t('app.kuaizhizao.salesOrder.taxInclusive');
  const exclusive = t('app.kuaizhizao.salesOrder.taxExclusive');
  if (s === inclusive || s === '含税' || s.toLowerCase() === 'tax_inclusive') return 'tax_inclusive';
  if (s === exclusive || s === '不含税' || s.toLowerCase() === 'tax_exclusive') return 'tax_exclusive';
  return undefined;
}

function groupKey(partnerId: number, materialId: number): string {
  return `${partnerId}:${materialId}`;
}

export async function commitPartnerPriceBookImport(
  partnerType: PartnerPriceBookType,
  data: unknown[][],
  options: {
    t: TFunction;
    importHeaderMap: Record<string, string>;
    partners: Array<Customer | Supplier>;
    materials: Material[];
    context?: UniImportCommitContext;
  },
): Promise<{ created: number; updated: number; skipped: number; errors: string[] }> {
  const { t, importHeaderMap, partners, materials, context } = options;
  const result = { created: 0, updated: 0, skipped: 0, errors: [] as string[] };
  if (!data || data.length < 2) {
    result.errors.push(t('app.master-data.importEmpty'));
    return result;
  }

  const headers = (data[0] as unknown[]).map((h) => String(h ?? '').trim());
  const headerIndexMap = resolveFactoryImportHeaderIndexMap(headers, importHeaderMap);
  const idx = (field: string) => headerIndexMap[field] ?? -1;

  if (idx('partnerCode') < 0) {
    result.errors.push(
      t('app.master-data.importMissingField', {
        field: t('app.master-data.priceBook.import.partnerCode'),
        headers: headers.join(', '),
      }),
    );
    return result;
  }
  if (idx('materialCode') < 0) {
    result.errors.push(
      t('app.master-data.importMissingField', {
        field: t('app.master-data.priceBook.import.materialCode'),
        headers: headers.join(', '),
      }),
    );
    return result;
  }

  const partnerByCode = new Map<string, Customer | Supplier>();
  const partnerByName = new Map<string, Customer | Supplier>();
  for (const p of partners) {
    const code = String(p.code ?? '').trim();
    const name = String(p.name ?? '').trim();
    if (code) partnerByCode.set(code, p);
    if (name) partnerByName.set(name, p);
  }

  const materialByCode = new Map<string, Material>();
  for (const m of materials) {
    const code = String(m.mainCode ?? (m as { code?: string }).code ?? '').trim();
    if (code) materialByCode.set(code, m);
  }

  const groups = new Map<string, ParsedGroup>();
  const rows = data.slice(2) as unknown[][];

  rows.forEach((row, rowIndex) => {
    const isEmpty = !row?.some((c) => c != null && String(c).trim() !== '');
    if (isEmpty) return;
    const rowNum = rowIndex + 3;

    const partnerCode = cell(row, idx('partnerCode'));
    const partnerName = cell(row, idx('partnerName'));
    const materialCode = cell(row, idx('materialCode'));
    if (!partnerCode && !partnerName) {
      result.errors.push(
        t('app.master-data.priceBook.import.rowPartnerRequired', { row: rowNum }),
      );
      return;
    }
    if (!materialCode) {
      result.errors.push(
        t('app.master-data.priceBook.import.rowMaterialRequired', { row: rowNum }),
      );
      return;
    }

    const partner =
      (partnerCode ? partnerByCode.get(partnerCode) : undefined) ??
      (partnerName ? partnerByName.get(partnerName) : undefined);
    if (!partner?.id) {
      result.errors.push(
        t('app.master-data.priceBook.import.rowPartnerNotFound', { row: rowNum, code: partnerCode || partnerName }),
      );
      return;
    }

    const material = materialByCode.get(materialCode);
    const materialId = Number(material?.id);
    if (!Number.isFinite(materialId) || materialId <= 0) {
      result.errors.push(
        t('app.master-data.priceBook.import.rowMaterialNotFound', { row: rowNum, code: materialCode }),
      );
      return;
    }

    const key = groupKey(Number(partner.id), materialId);
    let group = groups.get(key);
    if (!group) {
      group = {
        rowNums: [],
        partnerId: Number(partner.id),
        materialId,
        tierLines: [],
      };
      groups.set(key, group);
    }
    group.rowNums.push(rowNum);

    const unitPrice = parseNumber(cell(row, idx('unitPrice')));
    if (unitPrice != null && unitPrice > 0) {
      group.unitPrice = unitPrice;
    }

    const tierMin = parseNumber(cell(row, idx('tierMinQty')));
    const tierMax = parseNumber(cell(row, idx('tierMaxQty')));
    const tierPrice = parseNumber(cell(row, idx('tierUnitPrice')));
    if (tierMin != null && tierMin > 0 && tierPrice != null && tierPrice > 0) {
      group.tierLines.push({
        minQuantity: tierMin,
        maxQuantity: tierMax != null && tierMax > 0 ? tierMax : undefined,
        unitPrice: tierPrice,
      });
    }

    const unit = cell(row, idx('unit'));
    if (unit) group.unit = unit;
    const taxRate = parseNumber(cell(row, idx('taxRate')));
    if (taxRate != null) group.taxRate = taxRate;
    const pt = parsePriceType(cell(row, idx('priceType')), t);
    if (pt) group.priceType = pt;

    const pmc = cell(row, idx('partnerMaterialCode'));
    if (pmc) group.partnerMaterialCode = pmc;
    const pmn = cell(row, idx('partnerMaterialName'));
    if (pmn) group.partnerMaterialName = pmn;

    const ef = cell(row, idx('effectiveFrom'));
    if (ef) group.effectiveFrom = ef.slice(0, 10);
    const et = cell(row, idx('effectiveTo'));
    if (et) group.effectiveTo = et.slice(0, 10);
    const remark = cell(row, idx('remark'));
    if (remark) group.remark = remark;
  });

  if (groups.size === 0) {
    if (result.errors.length === 0) {
      result.errors.push(t('app.master-data.importNoRows'));
    }
    return result;
  }

  for (const group of groups.values()) {
    const tierPrices = normalizeTierPricesForSubmit(group.tierLines);
    const hasStandard = group.unitPrice != null && group.unitPrice > 0;
    const hasTier = tierPrices != null && tierPrices.length > 0;
    if (!hasStandard && !hasTier) {
      result.errors.push(
        t('app.master-data.priceBook.import.rowPriceRequired', {
          row: group.rowNums[0],
        }),
      );
    }
  }

  if (result.errors.length > 0) {
    return result;
  }

  const byPartner = new Map<number, ParsedGroup[]>();
  for (const g of groups.values()) {
    const list = byPartner.get(g.partnerId) ?? [];
    list.push(g);
    byPartner.set(g.partnerId, list);
  }

  const duplicateStrategy = context?.duplicateStrategy ?? 'overwrite';
  const conflictPolicy: PartnerPriceBookBulkConflictPolicy =
    duplicateStrategy === 'skip' ? 'skip' : 'overwrite';

  const api = createPartnerPriceBookApi(partnerType);

  for (const [partnerId, partnerGroups] of byPartner) {
    const header = partnerGroups[0];
    const payload: PartnerPriceBookBulkCreate = {
      partnerIds: [partnerId],
      conflictPolicy,
      priceType: header.priceType ?? 'tax_inclusive',
      taxRate: header.taxRate,
      effectiveFrom: header.effectiveFrom,
      effectiveTo: header.effectiveTo,
      remark: header.remark,
      isActive: true,
      syncPartnerAlias: false,
      lines: partnerGroups.map((g) => {
        const tierPrices = normalizeTierPricesForSubmit(g.tierLines);
        return {
          materialId: g.materialId,
          unitPrice: g.unitPrice != null && g.unitPrice > 0 ? g.unitPrice : undefined,
          tierPrices: tierPrices ?? undefined,
          unit: g.unit,
          partnerMaterialCode: g.partnerMaterialCode,
          partnerMaterialName: g.partnerMaterialName,
        };
      }),
    };

    try {
      const res = await api.bulkCreate(payload);
      result.created += res.createdCount ?? 0;
      result.updated += res.overwrittenCount ?? 0;
      result.skipped += res.skippedCount ?? 0;
    } catch (e: unknown) {
      const msg =
        (e as { message?: string })?.message ??
        t('app.master-data.priceBook.import.bulkFailed', { partnerId });
      result.errors.push(msg);
    }
  }

  return result;
}
