/**
 * Ant Design Form.List 明细行的唯一读取规范。
 * Form.List 在 setFieldsValue / 嵌套字段更新后，items 可能为数组或 { 0: row, 1: row } 对象形态；
 * 禁止在各单据页用 `values.items ?? []` 或 `Array.isArray` 单独判断。
 */
export function normalizeFormListItems<T>(raw: unknown): T[] {
  if (Array.isArray(raw)) {
    return raw.filter((row) => row != null);
  }
  if (raw && typeof raw === 'object') {
    return Object.values(raw as Record<string, T>).filter((row) => row != null);
  }
  return [];
}

/** Form.List 必填校验：至少一行明细（含对象形态） */
export function hasFormListItems(raw: unknown): boolean {
  return normalizeFormListItems(raw).length > 0;
}

/** ProForm 提交时 Form.List 字段优先读 form 实例（onFinish 的 values 可能缺嵌套列表） */
export function resolveFormListFieldForSubmit(
  formRef: { current?: { getFieldValue?: (name: string) => unknown } | null } | null,
  values: Record<string, unknown>,
  fieldName: string,
): unknown {
  const fromRef = formRef?.current?.getFieldValue?.(fieldName);
  const refRows = normalizeFormListItems(fromRef);
  const valRows = normalizeFormListItems(values[fieldName]);
  if (refRows.length > 0) {
    return fromRef;
  }
  if (valRows.length > 0) {
    return values[fieldName];
  }
  return fromRef ?? values[fieldName];
}
