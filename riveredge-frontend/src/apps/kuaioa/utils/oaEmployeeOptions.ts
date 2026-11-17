import { listEmployees } from '../services/employees';

export type OaEmployeeOption = {
  label: string;
  value: number;
  full_name?: string;
  bank_name?: string;
  bank_account?: string;
};

/** 员工下拉选项（含收款账户字段，供财务付款对象解析使用） */
export async function loadOaEmployeeOptions(options?: {
  activeOnly?: boolean;
}): Promise<OaEmployeeOption[]> {
  const params: Record<string, unknown> = { limit: 1000 };
  if (options?.activeOnly !== false) {
    params.is_active = true;
  }
  const res = await listEmployees(params);
  const items = Array.isArray(res?.items) ? res.items : [];
  return items
    .map((row) => {
      const id = Number(row.id);
      if (!Number.isFinite(id) || id <= 0) return null;
      const name = String(row.full_name ?? row.name ?? '').trim();
      return {
        label: name || String(id),
        value: id,
        full_name: name,
        bank_name: String(row.bank_name ?? '').trim(),
        bank_account: String(row.bank_account ?? '').trim(),
      } as OaEmployeeOption;
    })
    .filter((row): row is OaEmployeeOption => row !== null);
}
