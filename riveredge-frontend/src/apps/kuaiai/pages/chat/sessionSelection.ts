/**
 * 星AI 对话页：会话记住右上角模型 / 档案，以及 ?session= 解析。
 *
 * 模型存在会话字段 model（不新增列）：`#id:<目录行 id>`。
 * 没有此前缀的旧会话只按 model_name 回显，且必须在当前启用 chat 选项里恰好一条。
 */

const CATALOG_MODEL_REF_PREFIX = '#id:';
const CATALOG_MODEL_REF = /^#id:(\d+)$/;

export interface SessionModelOption {
  id: number;
  model_name: string;
}

export interface SessionSelectionFields {
  agent_id?: number | null;
  model?: string | null;
}

export function formatCatalogModelRef(modelId: number): string {
  return `${CATALOG_MODEL_REF_PREFIX}${modelId}`;
}

/**
 * 会话 model → 下拉目录行 id。
 * `#id:N` 且 N 在选项中才选中；否则按模型名，0 条或重名则空。
 */
export function resolveSessionModelId(
  model: string | null | undefined,
  options: readonly SessionModelOption[],
): number | undefined {
  const raw = (model ?? '').trim();
  if (!raw) return undefined;
  if (raw.startsWith(CATALOG_MODEL_REF_PREFIX)) {
    const matched = CATALOG_MODEL_REF.exec(raw);
    if (!matched) return undefined;
    const id = Number(matched[1]);
    if (!Number.isSafeInteger(id) || id <= 0) return undefined;
    return options.some((option) => option.id === id) ? id : undefined;
  }
  const hits = options.filter((option) => option.model_name === raw);
  return hits.length === 1 ? hits[0].id : undefined;
}

/** `?session=` 只接受正整数；无法解析时返回 null（调用方去掉无效 query）。 */
export function parseSessionQueryId(raw: string | null): number | null {
  if (raw == null || raw === '') return null;
  if (!/^[1-9]\d*$/.test(raw)) return null;
  const id = Number(raw);
  return Number.isSafeInteger(id) ? id : null;
}

/**
 * 新建会话时的选择：有档案只写 agent_id 并清空 model；
 * 有模型写 `#id:` 并清空档案；都没有则不带这两个字段。
 */
export function sessionSelectionPayload(
  agentId: number | undefined,
  modelId: number | undefined,
): SessionSelectionFields {
  if (agentId != null) {
    return { agent_id: agentId, model: null };
  }
  if (modelId != null) {
    return { agent_id: null, model: formatCatalogModelRef(modelId) };
  }
  return {};
}
