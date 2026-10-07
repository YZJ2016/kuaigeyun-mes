import type { SyncBinding, SyncSourceItem, SyncSourceType } from './types';
import { invertFieldMapping } from './syncSourceUtils';

export interface SyncSourceDraft {
  id: string;
  kind: SyncSourceType;
  api_uuid?: string;
  dataset_uuid?: string;
  /** 目标字段 -> 来源列 */
  targetToSource: Record<string, string>;
  request_body?: Record<string, unknown>;
  request_params?: Record<string, unknown>;
  persist_request_override?: boolean;
  batch_fill_path?: string;
  batch_fill_values?: string[];
}

let _draftSeq = 0;

export function newSyncSourceDraft(kind: SyncSourceType = 'api'): SyncSourceDraft {
  _draftSeq += 1;
  return { id: `src-${_draftSeq}`, kind, targetToSource: {} };
}

function cloneJsonObject(value: Record<string, unknown> | undefined): Record<string, unknown> | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  return structuredClone(value);
}

export function bindingToSourceDrafts(
  binding: SyncBinding,
  sanitizeMapping?: (targetToSource: Record<string, string>) => Record<string, string>,
): SyncSourceDraft[] {
  const sanitize = sanitizeMapping ?? ((mapping: Record<string, string>) => mapping);
  if (binding.sources?.length) {
    return binding.sources.map((src, index) => ({
      id: `src-${index + 1}`,
      kind: src.kind,
      api_uuid: src.api_uuid,
      dataset_uuid: src.dataset_uuid,
      targetToSource: sanitize(invertFieldMapping(src.field_mapping || {})),
      request_body: cloneJsonObject(src.request_body),
      request_params: cloneJsonObject(src.request_params),
      persist_request_override: Boolean(src.persist_request_override),
      batch_fill_path: src.batch_fill_path,
      batch_fill_values: src.batch_fill_values?.filter(Boolean),
    }));
  }
  const hasLegacy =
    Boolean(binding.api_uuid) ||
    Boolean(binding.dataset_uuid) ||
    Object.keys(binding.field_mapping || {}).length > 0;
  if (!hasLegacy) {
    return [];
  }
  const kind = (binding.source_type || 'api') as SyncSourceType;
  const draft = newSyncSourceDraft(kind);
  draft.targetToSource = sanitize(invertFieldMapping(binding.field_mapping || {}));
  if (kind === 'api' && binding.api_uuid) draft.api_uuid = binding.api_uuid;
  if (kind === 'dataset' && binding.dataset_uuid) draft.dataset_uuid = binding.dataset_uuid;
  return [draft];
}

export function draftsToPayloadSources(
  drafts: SyncSourceDraft[],
  sanitizeMapping?: (targetToSource: Record<string, string>) => Record<string, string>,
): SyncSourceItem[] {
  const sanitize = sanitizeMapping ?? ((mapping: Record<string, string>) => mapping);
  return drafts.map((draft) => ({
    kind: draft.kind,
    api_uuid: draft.kind === 'api' ? draft.api_uuid : undefined,
    dataset_uuid: draft.kind === 'dataset' ? draft.dataset_uuid : undefined,
    field_mapping: invertFieldMapping(sanitize(draft.targetToSource)),
    request_body: draft.kind === 'api' ? cloneJsonObject(draft.request_body) : undefined,
    request_params: draft.kind === 'api' ? cloneJsonObject(draft.request_params) : undefined,
    persist_request_override:
      draft.kind === 'api' ? Boolean(draft.persist_request_override) : undefined,
    batch_fill_path: draft.kind === 'api' ? draft.batch_fill_path : undefined,
    batch_fill_values: draft.kind === 'api' ? draft.batch_fill_values : undefined,
  }));
}
