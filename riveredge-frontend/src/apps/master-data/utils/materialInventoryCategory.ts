import type { TFunction } from 'i18next';

/** 系统预置存货类别编码（与后端 material_inventory_category 一致） */
export const MATERIAL_INVENTORY_CATEGORY_VALUES = [
  'CHLB01_SYS',
  'CHLB02_SYS',
  'CHLB03_SYS',
  'CHLB04_SYS',
  'CHLB05_SYS',
  'CHLB06_SYS',
  'CHLB07_SYS',
  'CHLB08_SYS',
  'CHLB09_SYS',
  'CHLB10_SYS',
] as const;

export type MaterialInventoryCategoryValue = (typeof MATERIAL_INVENTORY_CATEGORY_VALUES)[number];

const INVENTORY_CATEGORY_I18N_KEY: Record<MaterialInventoryCategoryValue, string> = {
  CHLB01_SYS: 'app.master-data.materialForm.inventoryCategory.raw',
  CHLB02_SYS: 'app.master-data.materialForm.inventoryCategory.auxiliary',
  CHLB03_SYS: 'app.master-data.materialForm.inventoryCategory.selfSemi',
  CHLB04_SYS: 'app.master-data.materialForm.inventoryCategory.outsourceSemi',
  CHLB05_SYS: 'app.master-data.materialForm.inventoryCategory.finished',
  CHLB06_SYS: 'app.master-data.materialForm.inventoryCategory.tradingGoods',
  CHLB07_SYS: 'app.master-data.materialForm.inventoryCategory.service',
  CHLB08_SYS: 'app.master-data.materialForm.inventoryCategory.asset',
  CHLB09_SYS: 'app.master-data.materialForm.inventoryCategory.expense',
  CHLB10_SYS: 'app.master-data.materialForm.inventoryCategory.labor',
};

export function buildMaterialInventoryCategoryOptions(
  t: TFunction,
): Array<{ label: string; value: string }> {
  return MATERIAL_INVENTORY_CATEGORY_VALUES.map((value) => ({
    value,
    label: t(INVENTORY_CATEGORY_I18N_KEY[value]),
  }));
}

export function translateMaterialInventoryCategory(
  t: TFunction,
  code?: string | null,
): string {
  if (!code) return '';
  const key = INVENTORY_CATEGORY_I18N_KEY[code as MaterialInventoryCategoryValue];
  return key ? t(key) : code;
}
