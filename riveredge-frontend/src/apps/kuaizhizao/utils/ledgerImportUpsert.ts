import { fetchAllListItems } from '../../../utils/fetchAllListPages';

type LedgerRow = { code?: string | null; uuid?: string | null };

/** 预取台账编号 → uuid，用于导入时按编码更新而非重复创建。 */
export async function buildLedgerCodeUuidMap(
  listFn: (params: Record<string, unknown>) => Promise<unknown>,
  listParams?: Record<string, unknown>,
): Promise<Map<string, string>> {
  const rows = (await fetchAllListItems((p) =>
    listFn({ ...(listParams ?? {}), ...p }),
  )) as LedgerRow[];
  const map = new Map<string, string>();
  for (const row of rows) {
    const code = String(row.code ?? '').trim();
    const uuid = row.uuid ? String(row.uuid) : '';
    if (code && uuid) {
      map.set(code, uuid);
    }
  }
  return map;
}

/** 有编号且库内已有则 update，否则 create；新建成功后写入 map 供同批后续行使用。 */
export async function upsertLedgerImportItem<T extends { code?: string }>(
  item: T,
  codeToUuid: Map<string, string>,
  create: (payload: T) => Promise<unknown>,
  update: (uuid: string, payload: T) => Promise<unknown>,
): Promise<void> {
  const code = item.code?.trim();
  if (code) {
    const existingUuid = codeToUuid.get(code);
    if (existingUuid) {
      await update(existingUuid, item);
      return;
    }
  }
  const created = (await create(item)) as LedgerRow | undefined;
  const newUuid = created?.uuid ? String(created.uuid) : '';
  const newCode = String(created?.code ?? code ?? '').trim();
  if (newCode && newUuid) {
    codeToUuid.set(newCode, newUuid);
  }
}
