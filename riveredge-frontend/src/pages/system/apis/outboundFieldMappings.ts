/** 出站字段映射行（接口管理 ↔ 推送组报文） */
export interface OutboundFieldMappingRow {
  enabled?: boolean;
  level?: 'header' | 'entry';
  source_table?: string;
  local_field?: string;
  remote_field?: string;
  default_value?: string | number | boolean | null;
}

const PR_HEADER = 'apps_kuaizhizao_purchase_receipts';
const PR_ENTRY = 'apps_kuaizhizao_purchase_receipt_items';

/** 采购入库 → 苍穹 im_purinbill 默认映射（与后端 default_purchase_receipt_outbound_mappings 对齐） */
export function defaultPurchaseReceiptOutboundMappings(): OutboundFieldMappingRow[] {
  return [
    { enabled: true, level: 'header', source_table: PR_HEADER, local_field: 'receipt_code', remote_field: 'trdbillno', default_value: '' },
    { enabled: true, level: 'header', source_table: PR_HEADER, local_field: 'biztime', remote_field: 'biztime', default_value: '' },
    { enabled: true, level: 'header', source_table: PR_HEADER, local_field: 'biztime', remote_field: 'exratedate', default_value: '' },
    { enabled: true, level: 'header', source_table: PR_HEADER, local_field: 'biztime', remote_field: 'bookdate', default_value: '' },
    { enabled: true, level: 'header', source_table: PR_HEADER, local_field: 'pay_mode', remote_field: 'paymode', default_value: 'CREDIT' },
    { enabled: true, level: 'header', source_table: PR_HEADER, local_field: '', remote_field: 'istax', default_value: 'true' },
    { enabled: true, level: 'header', source_table: PR_HEADER, local_field: 'org_number', remote_field: 'org_number', default_value: '' },
    { enabled: true, level: 'header', source_table: PR_HEADER, local_field: 'bizorg_number', remote_field: 'bizorg_number', default_value: '' },
    { enabled: true, level: 'header', source_table: PR_HEADER, local_field: 'billtype_number', remote_field: 'billtype_number', default_value: 'im_PurInBill_STD_BT_S' },
    { enabled: true, level: 'header', source_table: PR_HEADER, local_field: 'biztype_number', remote_field: 'biztype_number', default_value: '110' },
    { enabled: true, level: 'header', source_table: PR_HEADER, local_field: 'invscheme_number', remote_field: 'invscheme_number', default_value: '110' },
    { enabled: true, level: 'header', source_table: PR_HEADER, local_field: 'supplier_number', remote_field: 'supplier_number', default_value: '' },
    { enabled: true, level: 'header', source_table: PR_HEADER, local_field: 'comment', remote_field: 'comment', default_value: '' },
    { enabled: true, level: 'header', source_table: PR_HEADER, local_field: 'buyer_operator_number', remote_field: 'bizoperator_operatornumber', default_value: '' },
    { enabled: true, level: 'entry', source_table: PR_ENTRY, local_field: 'material_code', remote_field: 'material_number', default_value: '' },
    { enabled: true, level: 'entry', source_table: PR_ENTRY, local_field: 'receipt_quantity', remote_field: 'qty', default_value: '' },
    { enabled: true, level: 'entry', source_table: PR_ENTRY, local_field: 'material_unit', remote_field: 'unit_number', default_value: '' },
    { enabled: true, level: 'entry', source_table: PR_ENTRY, local_field: 'warehouse_number', remote_field: 'warehouse_number', default_value: '' },
    { enabled: true, level: 'entry', source_table: PR_ENTRY, local_field: 'batch_number', remote_field: 'lotnumber', default_value: '' },
    { enabled: true, level: 'entry', source_table: PR_ENTRY, local_field: '', remote_field: 'linetype_number', default_value: '010' },
    { enabled: true, level: 'entry', source_table: PR_ENTRY, local_field: '', remote_field: 'invtype_number', default_value: '110' },
    { enabled: true, level: 'entry', source_table: PR_ENTRY, local_field: '', remote_field: 'invstatus_number', default_value: '110' },
    { enabled: true, level: 'entry', source_table: PR_ENTRY, local_field: '', remote_field: 'outinvtype_number', default_value: '110' },
    { enabled: true, level: 'entry', source_table: PR_ENTRY, local_field: '', remote_field: 'outinvstatus_number', default_value: '110' },
    { enabled: true, level: 'entry', source_table: PR_ENTRY, local_field: '', remote_field: 'ownertype', default_value: 'bos_org' },
    { enabled: true, level: 'entry', source_table: PR_ENTRY, local_field: '', remote_field: 'keepertype', default_value: 'bos_org' },
    { enabled: true, level: 'entry', source_table: PR_ENTRY, local_field: 'org_number', remote_field: 'owner_number', default_value: '' },
    { enabled: true, level: 'entry', source_table: PR_ENTRY, local_field: 'org_number', remote_field: 'keeper_number', default_value: '' },
    { enabled: true, level: 'entry', source_table: PR_ENTRY, local_field: 'org_number', remote_field: 'entryreqorg_number', default_value: '' },
    { enabled: true, level: 'entry', source_table: PR_ENTRY, local_field: 'org_number', remote_field: 'entrysettleorg_number', default_value: '' },
  ];
}

export function normalizeOutboundFieldMappings(
  rows: OutboundFieldMappingRow[] | null | undefined,
): OutboundFieldMappingRow[] | null {
  if (!Array.isArray(rows)) return null;
  const cleaned = rows
    .filter((r) => String(r?.remote_field || '').trim())
    .map((r) => ({
      enabled: r.enabled !== false,
      level: (r.level === 'entry' ? 'entry' : 'header') as 'header' | 'entry',
      source_table: String(r.source_table || '').trim(),
      local_field: String(r.local_field || '').trim(),
      remote_field: String(r.remote_field || '').trim(),
      default_value: r.default_value ?? '',
    }));
  return cleaned.length ? cleaned : null;
}

const ENTRY_ARRAY_KEYS = new Set(['billentry', 'billEntry', 'entry', 'entries', 'FEntity']);

function asPlainObject(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function scalarDefault(value: unknown): string | number | boolean | '' {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return value;
  }
  return '';
}

/**
 * 从出站请求体样例抽出对方字段：
 * - data / data[0] 下标量键 → 单据头
 * - billentry[0] 下标量键 → 明细
 */
export function extractRemoteFieldsFromRequestBody(
  body: unknown,
): Array<{
  level: 'header' | 'entry';
  remote_field: string;
  default_value: string | number | boolean | '';
}> {
  const root = asPlainObject(body);
  if (!root) return [];

  let headerObj: Record<string, unknown> | null = null;
  const data = root.data;
  if (Array.isArray(data) && data.length && asPlainObject(data[0])) {
    headerObj = asPlainObject(data[0]);
  } else if (asPlainObject(data)) {
    headerObj = asPlainObject(data);
  } else if ('billentry' in root || 'billno' in root || 'org_number' in root) {
    headerObj = root;
  }

  const out: Array<{
    level: 'header' | 'entry';
    remote_field: string;
    default_value: string | number | boolean | '';
  }> = [];
  const seen = new Set<string>();

  const pushField = (
    level: 'header' | 'entry',
    key: string,
    value: unknown,
  ) => {
    const remote = String(key || '').trim();
    if (!remote || ENTRY_ARRAY_KEYS.has(remote)) return;
    const dedupe = `${level}:${remote}`;
    if (seen.has(dedupe)) return;
    seen.add(dedupe);
    out.push({ level, remote_field: remote, default_value: scalarDefault(value) });
  };

  if (headerObj) {
    for (const [key, value] of Object.entries(headerObj)) {
      if (ENTRY_ARRAY_KEYS.has(key) && Array.isArray(value)) {
        const first = value.find((row) => asPlainObject(row));
        const entryObj = asPlainObject(first);
        if (entryObj) {
          for (const [ek, ev] of Object.entries(entryObj)) {
            pushField('entry', ek, ev);
          }
        }
        continue;
      }
      if (value !== null && typeof value === 'object') continue;
      pushField('header', key, value);
    }
  }

  return out;
}

/** 用请求体对方字段补齐映射行：已有 remote_field 保留；空对方字段先填；其余追加新行 */
export function mergeRequestBodyFieldsIntoMappings(
  existing: OutboundFieldMappingRow[] | null | undefined,
  body: unknown,
  opts?: { headerTable?: string; entryTable?: string },
): OutboundFieldMappingRow[] {
  const extracted = extractRemoteFieldsFromRequestBody(body);
  const rows = Array.isArray(existing)
    ? existing.map((r) => ({ ...r }))
    : [];
  const usedRemotes = new Set(
    rows
      .map((r) => String(r.remote_field || '').trim())
      .filter(Boolean),
  );

  const takeNext = (preferLevel?: 'header' | 'entry') => {
    const idx = extracted.findIndex((e) => {
      if (usedRemotes.has(e.remote_field)) return false;
      if (preferLevel && e.level !== preferLevel) return false;
      return true;
    });
    if (idx < 0 && preferLevel) {
      return extracted.findIndex((e) => !usedRemotes.has(e.remote_field));
    }
    return idx;
  };

  // 对方字段为空的行：按层级优先填入请求体键名
  for (const row of rows) {
    if (String(row.remote_field || '').trim()) continue;
    const level = row.level === 'entry' ? 'entry' : 'header';
    const idx = takeNext(level);
    if (idx < 0) break;
    const item = extracted[idx];
    row.remote_field = item.remote_field;
    if (row.default_value === undefined || row.default_value === null || row.default_value === '') {
      row.default_value = item.default_value;
    }
    usedRemotes.add(item.remote_field);
  }

  // 请求体里还有未出现在映射中的键 → 追加行，本地字段留给用户选
  for (const item of extracted) {
    if (usedRemotes.has(item.remote_field)) continue;
    const source_table =
      item.level === 'entry'
        ? opts?.entryTable || opts?.headerTable || ''
        : opts?.headerTable || opts?.entryTable || '';
    rows.push({
      enabled: true,
      level: item.level,
      source_table,
      local_field: '',
      remote_field: item.remote_field,
      default_value: item.default_value,
    });
    usedRemotes.add(item.remote_field);
  }

  return rows;
}

/** 采购入库新增样例请求体（出站 JSON 源码用） */
export function defaultPurchaseReceiptRequestBody(): Record<string, unknown> {
  return {
    data: {
      biztime: '2026-11-02',
      exratedate: '2026-11-02',
      bookdate: '2026-11-02',
      paymode: 'CREDIT',
      istax: true,
      org_number: '',
      bizorg_number: '',
      billtype_number: 'im_PurInBill_STD_BT_S',
      biztype_number: '110',
      invscheme_number: '110',
      supplier_number: '',
      trdbillno: 'LOCAL-PR-SAMPLE',
      comment: '快格云采购入库出站样例',
      billentry: [
        {
          linetype_number: '010',
          material_number: '',
          qty: 1,
          unit_number: '',
          warehouse_number: '',
          invtype_number: '110',
          invstatus_number: '110',
          outinvtype_number: '110',
          outinvstatus_number: '110',
          ownertype: 'bos_org',
          keepertype: 'bos_org',
          owner_number: '',
          keeper_number: '',
          entryreqorg_number: '',
          entrysettleorg_number: '',
        },
      ],
    },
  };
}
