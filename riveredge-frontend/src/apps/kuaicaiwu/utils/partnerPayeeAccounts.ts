import { apiRequest } from '../../../services/api';

export type PartnerPayeeAccount = {
  accountName: string;
  bankName: string;
  bankAccount: string;
  isDefault: boolean;
};

export function readPartnerPayeeAccounts(raw: unknown): PartnerPayeeAccount[] {
  if (!Array.isArray(raw)) return [];
  const rows: PartnerPayeeAccount[] = [];
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue;
    const row = item as Record<string, unknown>;
    const accountName = String(row.accountName ?? row.account_name ?? '').trim();
    const bankName = String(row.bankName ?? row.bank_name ?? '').trim();
    const bankAccount = String(row.bankAccount ?? row.bank_account ?? '').trim();
    if (!accountName && !bankName && !bankAccount) continue;
    rows.push({
      accountName,
      bankName,
      bankAccount,
      isDefault: Boolean(row.isDefault ?? row.is_default),
    });
  }
  return rows;
}

function unwrapSupplierList(res: unknown): Record<string, unknown>[] {
  if (Array.isArray(res)) return res as Record<string, unknown>[];
  if (res && typeof res === 'object') {
    const body = res as Record<string, unknown>;
    const list = body.data ?? body.items;
    if (Array.isArray(list)) return list as Record<string, unknown>[];
  }
  return [];
}

export function pickDefaultPartnerPayeeAccount(
  rows: PartnerPayeeAccount[],
): PartnerPayeeAccount | undefined {
  return rows.find((item) => item.isDefault) ?? rows[0];
}

export function partnerPayeeOptionLabel(account: PartnerPayeeAccount, defaultMark: string): string {
  const text = partnerPayeeAccountDisplayText(account);
  return account.isDefault ? `${text}（${defaultMark}）` : text;
}

/** 开户行及账号展示（户名、银行、账号） */
export function partnerPayeeAccountDisplayText(account: PartnerPayeeAccount): string {
  return formatPayeeAccountFields(account.accountName, account.bankName, account.bankAccount);
}

export function formatPayeeAccountFields(
  accountName?: string | null,
  bankName?: string | null,
  bankAccount?: string | null,
): string {
  return [accountName, bankName, bankAccount]
    .map((v) => String(v ?? '').trim())
    .filter(Boolean)
    .join(' ');
}

export function partnerPayeeAccountFromBankInfoText(
  text: unknown,
  accounts: PartnerPayeeAccount[],
): number | undefined {
  const raw = String(text || '').trim();
  if (!raw) return undefined;
  const idx = accounts.findIndex((item) => partnerPayeeAccountDisplayText(item) === raw);
  return idx >= 0 ? idx : undefined;
}

export function samePartnerPayeeAccount(
  account: PartnerPayeeAccount,
  name: unknown,
  bank: unknown,
  acct: unknown,
): boolean {
  return (
    account.accountName === String(name || '').trim() &&
    account.bankName === String(bank || '').trim() &&
    account.bankAccount === String(acct || '').trim()
  );
}

/** 按 numeric id 从供应商列表接口解析收款账户（与付款单对方账户同一数据源） */
export async function loadEmployeePayeeAccountsById(
  employeeId: number,
): Promise<{ found: boolean; accounts: PartnerPayeeAccount[] }> {
  const id = Number(employeeId);
  if (!Number.isFinite(id) || id <= 0) {
    return { found: false, accounts: [] };
  }
  const { loadOaEmployeeOptions } = await import('../../kuaioa/utils/oaEmployeeOptions');
  const emps = await loadOaEmployeeOptions({ activeOnly: false });
  const row = emps.find((item) => item.value === id);
  if (!row) {
    return { found: false, accounts: [] };
  }
  const accountName = String(row.full_name || row.label || '').trim();
  const bankName = String(row.bank_name || '').trim();
  const bankAccount = String(row.bank_account || '').trim();
  if (!accountName && !bankName && !bankAccount) {
    return { found: true, accounts: [] };
  }
  return {
    found: true,
    accounts: [
      {
        accountName,
        bankName,
        bankAccount,
        isDefault: true,
      },
    ],
  };
}

export async function loadCustomerPayeeAccountsById(
  customerId: number,
): Promise<{ found: boolean; accounts: PartnerPayeeAccount[] }> {
  const id = Number(customerId);
  if (!Number.isFinite(id) || id <= 0) {
    return { found: false, accounts: [] };
  }
  const res = await apiRequest<unknown>('/apps/master-data/supply-chain/customers', {
    params: { limit: 1000, is_active: true },
  });
  const row = unwrapSupplierList(res).find((item) => Number(item.id) === id);
  if (!row) {
    return { found: false, accounts: [] };
  }
  return {
    found: true,
    accounts: readPartnerPayeeAccounts(row.settlementAccounts ?? row.settlement_accounts),
  };
}

export async function loadSupplierPayeeAccountsById(
  supplierId: number,
): Promise<{ found: boolean; accounts: PartnerPayeeAccount[] }> {
  const id = Number(supplierId);
  if (!Number.isFinite(id) || id <= 0) {
    return { found: false, accounts: [] };
  }
  const res = await apiRequest<unknown>('/apps/master-data/supply-chain/suppliers', {
    params: { limit: 1000, is_active: true },
  });
  const row = unwrapSupplierList(res).find((item) => Number(item.id) === id);
  if (!row) {
    return { found: false, accounts: [] };
  }
  return {
    found: true,
    accounts: readPartnerPayeeAccounts(row.settlementAccounts ?? row.settlement_accounts),
  };
}
