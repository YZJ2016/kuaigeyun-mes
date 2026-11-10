/**
 * 自定义字段源字段（系统 / 自定义）解析工具
 */

export type CustomFieldSourceScope = 'custom' | 'system';

const CUSTOM_PREFIX = 'custom_';

export function encodeSourceFieldKey(scope: CustomFieldSourceScope, name: string): string {
  return `${scope}:${name}`;
}

export function parseSourceFieldKey(
  value?: string | null,
): { scope: CustomFieldSourceScope; name: string } | null {
  if (!value) return null;
  const idx = value.indexOf(':');
  if (idx <= 0) {
    return { scope: 'custom', name: value };
  }
  const scope = value.slice(0, idx) as CustomFieldSourceScope;
  const name = value.slice(idx + 1);
  if ((scope !== 'custom' && scope !== 'system') || !name) {
    return { scope: 'custom', name: value };
  }
  return { scope, name };
}

/**
 * 关联对象源字段变更后，匹配字段默认值：
 * - 已知外键 / 名称以 Id 结尾 / 清单外系统字段 → id
 * - 已知标量系统字段 → code
 * - 其余（含自定义文本源）→ code
 */
export function resolveSourceMatchFieldDefault(
  sourceKey: string | undefined,
  options: {
    linkFieldKeys: ReadonlySet<string>;
    scalarFieldKeys: ReadonlySet<string>;
  },
): 'id' | 'code' {
  if (!sourceKey) return 'code';
  if (options.linkFieldKeys.has(sourceKey)) return 'id';
  if (options.scalarFieldKeys.has(sourceKey)) return 'code';
  const parsed = parseSourceFieldKey(sourceKey);
  if (parsed?.scope === 'system' && /Id$/i.test(parsed.name)) return 'id';
  if (parsed?.scope === 'system' && !options.scalarFieldKeys.has(sourceKey)) return 'id';
  return 'code';
}

/** 将搜索词或已保存值规范为可追加的源字段选项（默认按系统表单字段） */
export function normalizeManualSourceFieldOption(
  raw: string,
  customLabelPrefix: string,
): { value: string; label: string; scope: CustomFieldSourceScope } | null {
  const text = raw.trim();
  if (!text) return null;
  const parsed = parseSourceFieldKey(text.includes(':') ? text : null);
  const name = (parsed?.name || text.replace(/^(system|custom):/i, '')).trim();
  if (!name) return null;
  const scope: CustomFieldSourceScope = parsed?.scope === 'custom' ? 'custom' : 'system';
  return {
    value: encodeSourceFieldKey(scope, name),
    label: `${customLabelPrefix} (${name})`,
    scope,
  };
}

export function resolveSourceFormFieldName(
  sourceField?: string,
  sourceFieldType?: CustomFieldSourceScope,
): string | null {
  if (!sourceField) return null;
  const scope = sourceFieldType || 'custom';
  return scope === 'system' ? sourceField : `${CUSTOM_PREFIX}${sourceField}`;
}

export function buildSourceFieldKeyFromConfig(config?: {
  sourceField?: string;
  sourceFieldType?: CustomFieldSourceScope;
}): string | undefined {
  if (!config?.sourceField) return undefined;
  return encodeSourceFieldKey(config.sourceFieldType || 'custom', config.sourceField);
}

export function buildLinkFieldKeyFromConfig(config?: {
  linkField?: string;
  linkFieldType?: CustomFieldSourceScope;
}): string | undefined {
  if (!config?.linkField) return undefined;
  return encodeSourceFieldKey(config.linkFieldType || 'custom', config.linkField);
}

export function resolveLinkFormFieldName(
  linkField?: string,
  linkFieldType?: CustomFieldSourceScope,
): string | null {
  return resolveSourceFormFieldName(linkField, linkFieldType);
}
