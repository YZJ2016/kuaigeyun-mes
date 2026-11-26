/** 入库明细 — 库位/批号/序列号行字段与物料属性同步 */

import { materialApi } from '../../../../master-data/services/material';
import type { Material, MaterialListResponse } from '../../../../master-data/types/material';

function firstMaterialFromListResponse(
  res: MaterialListResponse | Material[] | null | undefined,
): Material | null {
  if (!res) return null;
  if (Array.isArray(res)) return res[0] ?? null;
  return res.items?.[0] ?? null;
}

export const INBOUND_ITEM_TRACKING_FIELDS = {
  material_uuid: undefined as string | undefined,
  batch_managed: false,
  serial_managed: false,
  batch_rule_id: undefined as number | undefined,
  default_batch_rule_id: undefined as number | undefined,
  serial_rule_id: undefined as number | undefined,
  default_serial_rule_id: undefined as number | undefined,
  location_code: undefined as string | undefined,
  batch_number: undefined as string | undefined,
  serial_numbers: undefined as string[] | undefined,
};

export type InboundMaterialTrackingMeta = {
  uuid: string;
  batchManaged: boolean;
  serialManaged: boolean;
  defaultBatchRuleId: number | null;
  defaultSerialRuleId: number | null;
};

export function readMaterialTrackingFromPicker(material: Record<string, unknown> | undefined): InboundMaterialTrackingMeta | null {
  if (!material) return null;
  const uuid = String(material.uuid ?? material.UUID ?? '').trim();
  if (!uuid) return null;
  const defaultBatchRuleId = material.defaultBatchRuleId ?? material.default_batch_rule_id;
  const defaultSerialRuleId = material.defaultSerialRuleId ?? material.default_serial_rule_id;
  return {
    uuid,
    batchManaged: !!(material.batchManaged ?? material.batch_managed),
    serialManaged: !!(material.serialManaged ?? material.serial_managed),
    defaultBatchRuleId:
      defaultBatchRuleId != null && Number(defaultBatchRuleId) > 0 ? Number(defaultBatchRuleId) : null,
    defaultSerialRuleId:
      defaultSerialRuleId != null && Number(defaultSerialRuleId) > 0 ? Number(defaultSerialRuleId) : null,
  };
}

export function applyMaterialTrackingToFormRow(
  setFieldValue: (name: (string | number)[], value: unknown) => void,
  listName: string,
  index: number,
  meta: InboundMaterialTrackingMeta,
): void {
  setFieldValue([listName, index, 'material_uuid'], meta.uuid);
  setFieldValue([listName, index, 'batch_managed'], meta.batchManaged);
  setFieldValue([listName, index, 'serial_managed'], meta.serialManaged);
  setFieldValue([listName, index, 'default_batch_rule_id'], meta.defaultBatchRuleId ?? undefined);
  setFieldValue([listName, index, 'default_serial_rule_id'], meta.defaultSerialRuleId ?? undefined);
}

export function pickInboundItemTrackingPayload(it: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  const loc = String(it.location_code ?? '').trim();
  if (loc) out.location_code = loc;
  const batch = String(it.batch_number ?? '').trim();
  if (batch) out.batch_number = batch;
  if (Array.isArray(it.serial_numbers) && it.serial_numbers.length > 0) {
    out.serial_numbers = it.serial_numbers;
  }
  return out;
}

/** 为已载入明细行补全批号/序列号管理标记（按物料编码查主数据） */
export async function enrichInboundFormItemsTracking(
  items: Record<string, unknown>[],
): Promise<Record<string, unknown>[]> {
  if (!items.length) return items;
  const codes = [...new Set(items.map((it) => String(it.material_code ?? '').trim()).filter(Boolean))];
  const metaByCode = new Map<string, InboundMaterialTrackingMeta>();
  await Promise.all(
    codes.map(async (code) => {
      try {
        const list = await materialApi.list({ code, limit: 1 });
        const m = firstMaterialFromListResponse(list);
        const fromPicker = readMaterialTrackingFromPicker(m as unknown as Record<string, unknown> | undefined);
        if (!fromPicker) return;
        if (m?.uuid) {
          try {
            const full = await materialApi.get(m.uuid);
            metaByCode.set(code, {
              uuid: m.uuid,
              batchManaged: !!full.batchManaged,
              serialManaged: !!full.serialManaged,
              defaultBatchRuleId:
                full.defaultBatchRuleId != null && Number(full.defaultBatchRuleId) > 0
                  ? Number(full.defaultBatchRuleId)
                  : null,
              defaultSerialRuleId:
                full.defaultSerialRuleId != null && Number(full.defaultSerialRuleId) > 0
                  ? Number(full.defaultSerialRuleId)
                  : null,
            });
            return;
          } catch {
            /* 使用列表字段 */
          }
        }
        metaByCode.set(code, fromPicker);
      } catch {
        /* 跳过 */
      }
    }),
  );
  return items.map((row) => {
    const code = String(row.material_code ?? '').trim();
    const meta = metaByCode.get(code);
    if (!meta) return row;
    return {
      ...row,
      material_uuid: meta.uuid,
      batch_managed: meta.batchManaged,
      serial_managed: meta.serialManaged,
      default_batch_rule_id: meta.defaultBatchRuleId ?? undefined,
      default_serial_rule_id: meta.defaultSerialRuleId ?? undefined,
    };
  });
}

export type ConfirmPreviewMaterialMeta = {
  batchManaged: boolean;
  serialManaged: boolean;
  materialUuid: string;
  defaultBatchRuleId: number | null;
  defaultSerialRuleId: number | null;
};

function confirmPreviewMetaFromMaterial(m: Material): ConfirmPreviewMaterialMeta | null {
  const uuid = String(m?.uuid ?? '').trim();
  if (!uuid) return null;
  const defaultBatchRuleId = (m.defaultBatchRuleId ??
    (m as { default_batch_rule_id?: number | null }).default_batch_rule_id ??
    null) as number | null;
  const defaultSerialRuleId = (m.defaultSerialRuleId ?? (m as { default_serial_rule_id?: number | null }).default_serial_rule_id ?? null) as
    | number
    | null;
  return {
    batchManaged: !!(m.batchManaged ?? (m as { batch_managed?: boolean }).batch_managed),
    serialManaged: !!(m.serialManaged ?? (m as { serial_managed?: boolean }).serial_managed),
    materialUuid: uuid,
    defaultBatchRuleId:
      defaultBatchRuleId != null && Number(defaultBatchRuleId) > 0 ? Number(defaultBatchRuleId) : null,
    defaultSerialRuleId:
      defaultSerialRuleId != null && Number(defaultSerialRuleId) > 0 ? Number(defaultSerialRuleId) : null,
  };
}

/** 确认预览：按明细行加载物料批号/序列号管理属性（列表/预取真源，禁止每行 GET 详情） */
export async function loadConfirmPreviewMaterialMeta(
  items: { id?: number; material_code?: string; material_id?: number; serial_numbers?: string[] | null }[],
  materialById?: Map<string, Material>,
): Promise<Record<number, ConfirmPreviewMaterialMeta>> {
  const out: Record<number, ConfirmPreviewMaterialMeta> = {};
  const rows = items.filter((it) => it?.id != null);
  const mergedByMaterialId = new Map<string, Material>();
  if (materialById) {
    for (const [key, m] of materialById) {
      if (m.id != null) mergedByMaterialId.set(String(m.id), m);
      if (m.uuid) mergedByMaterialId.set(String(m.uuid), m);
      mergedByMaterialId.set(key, m);
    }
  }

  const missingNumericIds: number[] = [];
  const missingCodes: string[] = [];
  for (const it of rows) {
    const materialId = it.material_id;
    if (materialId != null && Number(materialId) > 0 && !mergedByMaterialId.has(String(materialId))) {
      missingNumericIds.push(Number(materialId));
    }
    const code = String(it.material_code || '').trim();
    if (!code) continue;
    const resolvedById =
      materialId != null &&
      Number(materialId) > 0 &&
      mergedByMaterialId.has(String(materialId));
    if (!resolvedById) {
      missingCodes.push(code);
    }
  }

  const uniqueMissingIds = [...new Set(missingNumericIds)];
  if (uniqueMissingIds.length > 0) {
    try {
      const res = await materialApi.list({ ids: uniqueMissingIds, limit: uniqueMissingIds.length });
      for (const m of res.items ?? []) {
        if (m.id != null) mergedByMaterialId.set(String(m.id), m);
        if (m.uuid) mergedByMaterialId.set(String(m.uuid), m);
      }
    } catch {
      /* 主数据不可用时跳过自动批号/序列号 */
    }
  }

  await Promise.all(
    [...new Set(missingCodes)].map(async (code) => {
      try {
        const res = await materialApi.list({ code, limit: 1 });
        const m = firstMaterialFromListResponse(res);
        if (m?.id != null) mergedByMaterialId.set(String(m.id), m);
      } catch {
        /* 跳过 */
      }
    }),
  );

  for (const it of rows) {
    const id = Number(it.id);
    const materialId = it.material_id;
    let m: Material | null = null;
    if (materialId != null && mergedByMaterialId.has(String(materialId))) {
      m = mergedByMaterialId.get(String(materialId)) ?? null;
    }
    if (!m) {
      const code = String(it.material_code || '').trim();
      if (!code) continue;
      m = [...mergedByMaterialId.values()].find((row) => String((row as { main_code?: string }).main_code ?? row.code ?? '').trim() === code) ?? null;
    }
    const meta = m ? confirmPreviewMetaFromMaterial(m) : null;
    if (meta) out[id] = meta;
  }

  return out;
}
