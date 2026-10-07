/** 键值对行（表单模式） */
export interface JsonKeyValuePair {
  key: string;
  value: string;
}

/** 可嵌套的 JSON 键值对节点（支持对象子字段） */
export interface JsonTreeNode {
  id: string;
  key: string;
  enabled: boolean;
  kind: 'value' | 'object';
  value: string;
  children: JsonTreeNode[];
}

const PRIMITIVE_JSON_TYPES = new Set(['string', 'number', 'boolean']);

let jsonTreeNodeSeq = 0;

export function createJsonTreeNodeId(): string {
  jsonTreeNodeSeq += 1;
  return `json-node-${jsonTreeNodeSeq}`;
}

export function createEmptyJsonTreeNode(): JsonTreeNode {
  return {
    id: createJsonTreeNodeId(),
    key: '',
    enabled: true,
    kind: 'value',
    value: '',
    children: [],
  };
}

/** 是否为普通 JSON 对象（可键值对编辑，允许嵌套） */
export function isJsonObject(value: unknown): value is Record<string, unknown> {
  return value != null && typeof value === 'object' && !Array.isArray(value);
}

/** 是否为可用扁平键值对模式编辑的对象 */
export function isFlatJsonObject(value: unknown): value is Record<string, string | number | boolean | null> {
  if (!isJsonObject(value)) return false;
  return Object.values(value).every(
    (v) => v == null || PRIMITIVE_JSON_TYPES.has(typeof v),
  );
}

export function canEditAsJsonTree(value: unknown): boolean {
  return value == null || value === '' || isJsonObject(value);
}

export function parseJsonScalar(raw: string): string | number | boolean | null {
  const trimmed = raw.trim();
  if (trimmed === '') return null;
  if (trimmed === 'true') return true;
  if (trimmed === 'false') return false;
  if (/^-?\d+(\.\d+)?$/.test(trimmed)) return Number(trimmed);
  return raw;
}

function formatJsonScalar(val: unknown): string {
  if (val == null) return '';
  if (typeof val === 'string') return val;
  if (typeof val === 'number' || typeof val === 'boolean') return String(val);
  try {
    return JSON.stringify(val);
  } catch {
    return String(val);
  }
}

function jsonEntryToTreeNode(key: string, val: unknown): JsonTreeNode {
  if (isJsonObject(val)) {
    const entries = Object.entries(val);
    return {
      id: createJsonTreeNodeId(),
      key,
      enabled: true,
      kind: 'object',
      value: '',
      children: entries.length ? entries.map(([k, v]) => jsonEntryToTreeNode(k, v)) : [createEmptyJsonTreeNode()],
    };
  }
  return {
    id: createJsonTreeNodeId(),
    key,
    enabled: true,
    kind: 'value',
    value: formatJsonScalar(val),
    children: [],
  };
}

export function jsonValueToTree(value: unknown): JsonTreeNode[] {
  if (!isJsonObject(value) || Object.keys(value).length === 0) {
    return [createEmptyJsonTreeNode()];
  }
  return Object.entries(value).map(([key, val]) => jsonEntryToTreeNode(key, val));
}

export function jsonTreeToValue(nodes: JsonTreeNode[]): Record<string, unknown> | null {
  const result: Record<string, unknown> = {};
  let hasEntry = false;
  for (const node of nodes) {
    if (!node.enabled) continue;
    const key = node.key.trim();
    if (!key) continue;
    if (node.kind === 'object') {
      result[key] = jsonTreeToValue(node.children) ?? {};
      hasEntry = true;
    } else {
      result[key] = node.value.trim() === '' ? '' : parseJsonScalar(node.value);
      hasEntry = true;
    }
  }
  return hasEntry ? result : null;
}

export function updateJsonTreeNode(
  nodes: JsonTreeNode[],
  id: string,
  mapper: (node: JsonTreeNode) => JsonTreeNode,
): JsonTreeNode[] {
  return nodes.map((node) => {
    if (node.id === id) return mapper(node);
    if (node.children.length) {
      return { ...node, children: updateJsonTreeNode(node.children, id, mapper) };
    }
    return node;
  });
}

export function removeJsonTreeNode(nodes: JsonTreeNode[], id: string): JsonTreeNode[] {
  return nodes
    .filter((node) => node.id !== id)
    .map((node) => ({
      ...node,
      children: node.children.length ? removeJsonTreeNode(node.children, id) : node.children,
    }));
}

export function addJsonTreeChild(nodes: JsonTreeNode[], parentId: string | null): JsonTreeNode[] {
  const next = createEmptyJsonTreeNode();
  if (parentId == null) return [...nodes, next];
  return updateJsonTreeNode(nodes, parentId, (node) => ({
    ...node,
    kind: 'object',
    value: '',
    children: [...node.children, next],
  }));
}

export function jsonValueToKeyValuePairs(value: unknown): JsonKeyValuePair[] {
  if (!isFlatJsonObject(value) || Object.keys(value).length === 0) {
    return [{ key: '', value: '' }];
  }
  return Object.entries(value).map(([key, val]) => ({
    key,
    value: val == null ? '' : String(val),
  }));
}

export function keyValuePairsToJsonObject(pairs: JsonKeyValuePair[]): Record<string, string | number | boolean | null> | null {
  const result: Record<string, string | number | boolean | null> = {};
  let hasEntry = false;
  for (const pair of pairs) {
    const key = pair.key.trim();
    if (!key) continue;
    hasEntry = true;
    result[key] = parseJsonScalar(pair.value);
  }
  return hasEntry ? result : null;
}

export function formatJsonText(value: unknown): string {
  if (value == null || value === '') return '';
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) return '';
    try {
      return JSON.stringify(JSON.parse(trimmed), null, 2);
    } catch {
      return trimmed;
    }
  }
  return JSON.stringify(value, null, 2);
}

export function parseJsonText(text: string): { ok: true; value: unknown } | { ok: false; error: string } {
  const trimmed = text.trim();
  if (!trimmed) return { ok: true, value: null };
  try {
    return { ok: true, value: JSON.parse(trimmed) };
  } catch {
    return { ok: false, error: 'JSON 格式不正确，请检查括号、引号或逗号' };
  }
}

export function normalizeJsonFieldValue(value: unknown): unknown {
  if (value == null || value === '') return null;
  if (typeof value === 'string') {
    const parsed = parseJsonText(value);
    return parsed.ok ? parsed.value : value;
  }
  return value;
}

export function isEmptyJsonValue(value: unknown): boolean {
  if (value == null || value === '') return true;
  if (typeof value === 'object' && !Array.isArray(value) && Object.keys(value as object).length === 0) {
    return true;
  }
  return false;
}
