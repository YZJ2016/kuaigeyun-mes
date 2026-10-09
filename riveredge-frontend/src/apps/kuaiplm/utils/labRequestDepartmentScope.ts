/**
 * 实验委托：委托部门 / 检测部门可选范围（租户业务参数白名单）。
 * 空数组 = 不限制（全量启用部门）。
 */

import type { BusinessConfig } from '../../../services/businessConfig';
import type { DepartmentTreeItem } from '../../../services/department';

export type LabDeptOption = {
  label: string;
  /** 表单存部门名称（与现有 extension 快照契约一致） */
  value: string;
  uuid: string;
};

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function normalizeDeptUuidList(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  const out: string[] = [];
  const seen = new Set<string>();
  for (const item of raw) {
    if (typeof item !== 'string') continue;
    const value = item.trim();
    if (!value || !UUID_RE.test(value)) continue;
    const key = value.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(value);
  }
  return out;
}

export function resolveLabRequestDeptScopeFromConfig(
  config: BusinessConfig | null | undefined,
): { delegateUuids: string[]; testUuids: string[] } {
  const bucket = config?.parameters?.kuaiplm;
  return {
    delegateUuids: normalizeDeptUuidList(bucket?.lab_request_delegate_dept_uuids),
    testUuids: normalizeDeptUuidList(bucket?.lab_request_test_dept_uuids),
  };
}

export function flattenLabDeptOptions(
  items: DepartmentTreeItem[],
  prefix = '',
): LabDeptOption[] {
  const out: LabDeptOption[] = [];
  for (const item of items) {
    if (item.is_active === false) continue;
    const name = String(item.name ?? '').trim();
    const uuid = String(item.uuid ?? '').trim();
    if (!name || !uuid) continue;
    const label = prefix ? `${prefix} / ${name}` : name;
    out.push({ label, value: name, uuid });
    if (item.children?.length) {
      out.push(...flattenLabDeptOptions(item.children, label));
    }
  }
  return out;
}

/** 白名单为空则不限制；编辑时保留当前名称即使已移出白名单 */
export function filterLabDeptOptionsByWhitelist(
  options: LabDeptOption[],
  whitelistUuids: string[],
  preserveNames?: Array<string | null | undefined>,
): LabDeptOption[] {
  if (!whitelistUuids.length) return options;
  const allowed = new Set(whitelistUuids.map((u) => u.toLowerCase()));
  const preserve = new Set(
    (preserveNames ?? [])
      .map((n) => String(n ?? '').trim())
      .filter(Boolean),
  );
  return options.filter(
    (opt) => allowed.has(opt.uuid.toLowerCase()) || preserve.has(opt.value),
  );
}

export function labDeptSelectOptions(
  options: LabDeptOption[],
): { label: string; value: string }[] {
  return options.map(({ label, value }) => ({ label, value }));
}
