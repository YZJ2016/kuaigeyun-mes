import type { TFunction } from 'i18next';

export type SyncSourceType = 'api' | 'dataset';

export interface SyncSourceItem {
  kind: SyncSourceType;
  api_uuid?: string;
  dataset_uuid?: string;
  field_mapping: Record<string, string>;
  label?: string;
  /** 仅覆盖本同步来源调用，不改接口管理模板 */
  request_body?: Record<string, unknown>;
  request_params?: Record<string, unknown>;
  persist_request_override?: boolean;
  batch_fill_path?: string;
  batch_fill_values?: string[];
}

export interface SyncTargetField {
  value: string;
  /** i18n key；与 label 二选一，优先 label */
  labelKey?: string;
  /** 直接展示名（自定义字段等无 i18n 时） */
  label?: string;
  required?: boolean;
  kind?: 'system' | 'custom' | 'helper';
}

/** 自定义字段映射目标键前缀：custom:{field_code} */
export const SYNC_CUSTOM_FIELD_TARGET_PREFIX = 'custom:';

export function syncCustomFieldTargetKey(code: string): string {
  return `${SYNC_CUSTOM_FIELD_TARGET_PREFIX}${code}`;
}

export function isSyncCustomFieldTarget(value: string): boolean {
  return value.startsWith(SYNC_CUSTOM_FIELD_TARGET_PREFIX);
}

export function syncCustomFieldCodeFromTarget(value: string): string {
  return value.slice(SYNC_CUSTOM_FIELD_TARGET_PREFIX.length);
}

export interface SyncBinding {
  sources?: SyncSourceItem[];
  source_type?: SyncSourceType | null;
  api_uuid?: string | null;
  dataset_uuid?: string | null;
  field_mapping: Record<string, string>;
  match_key_field?: string;
  sync_mode?: string;
  schedule_interval_minutes?: number;
  schedule_window_start?: string | null;
  schedule_window_end?: string | null;
  last_success_at?: string | null;
  last_attempt_at?: string | null;
  last_error?: string | null;
}

export interface SyncFromSourcePayload {
  sources?: SyncSourceItem[];
  source_type?: SyncSourceType;
  api_uuid?: string;
  dataset_uuid?: string;
  field_mapping?: Record<string, string>;
  save_binding?: boolean;
  skip_prerequisite_syncs?: boolean;
  sync_mode?: string;
  schedule_interval_minutes?: number;
  schedule_window_start?: string | null;
  schedule_window_end?: string | null;
  incremental?: boolean;
  /** 仅同步有效主数据或未完成单据，默认 true */
  active_only?: boolean;
  /** 物料分组：按编码段智能推断父级（如 06.01→06） */
  infer_parent_by_code?: boolean;
}

export type SyncProgressHandler = (message: string) => void;

export interface SyncPrerequisiteStep {
  id: string;
  titleKey: string;
  getBinding: () => Promise<SyncBinding>;
  syncFromSource: (
    payload: SyncFromSourcePayload,
    onProgress?: SyncProgressHandler,
  ) => Promise<SyncFromSourceResult>;
}

export type SyncProgressStatus = 'wait' | 'process' | 'finish' | 'error' | 'skip';

export interface SyncProgressItem {
  id: string;
  titleKey: string;
  status: SyncProgressStatus;
  description?: string;
}

export interface SyncFromSourceResult {
  created: number;
  updated: number;
  skipped: number;
  failed: number;
  /** 源端本轮拉取行数 */
  fetched?: number;
  /** 全量且无写入时的空结果原因：source_empty | filtered_all | mapping_empty */
  empty_reason?: string;
  /** full | incremental */
  mode?: string;
  errors: string[];
}

export interface SyncFromSourceConfig {
  titleKey: string;
  hintKey?: string;
  apiRealtimeHintKey?: string;
  datasetBatchHintKey?: string;
  targetFieldLabelKey?: string;
  /** 默认展示的常用目标字段 */
  targetFields: SyncTargetField[];
  /**
   * 可通过「添加更多字段」追加的系统/辅助字段（不含 targetFields）。
   * 与 loadAvailableTargetFields / customFieldTableName 合并去重。
   */
  availableTargetFields?: SyncTargetField[];
  /** 异步加载额外目标字段（如自定义字段）；打开弹窗时调用 */
  loadAvailableTargetFields?: () => Promise<SyncTargetField[]>;
  /** 便捷：按表名拉取启用中的自定义字段并转为 custom:{code} 目标 */
  customFieldTableName?: string;
  requiredTargets: string[];
  /** 匹配键目标字段；BOM 等可为派生键（如 line_key），不必出现在 requiredTargets */
  matchKeyField?: string;
  validateMapping?: (targetToSource: Record<string, string>, t: TFunction) => string | null;
  /** 保存/回填前清理错误映射（如把苍穹 warehouse 内码当成本地仓库ID） */
  sanitizeMapping?: (targetToSource: Record<string, string>) => Record<string, string>;
  getBinding: () => Promise<SyncBinding>;
  syncFromSource: (
    payload: SyncFromSourcePayload,
    onProgress?: SyncProgressHandler,
  ) => Promise<SyncFromSourceResult>;
  completeSuccessKey: string;
  completePartialKey: string;
  failedKey: string;
  /** 主同步前先逐步执行的关联同步（界面展示进度） */
  prerequisiteSteps?: SyncPrerequisiteStep[];
  /** 主同步请求跳过服务端内置关联同步（由前端 prerequisiteSteps 负责时设为 true） */
  skipBackendPrerequisites?: boolean;
  /** 主同步步骤标题（有 prerequisiteSteps 时在进度条中展示） */
  mainStepTitleKey?: string;
  /** 拉取预览时优先展示的源列（单位同步等只关心编码/名称） */
  previewPreferredSourceKeys?: string[];
  /**
   * 预览时按基础单位编码去重（仅单位同步）。
   * 物料同步也会在 preferredKeys 里带 baseunit.*，绝不能据此推断去重。
   */
  collapsePreviewToUniqueUnits?: boolean;
  /**
   * 本页同步目标字段的源列别名（覆盖全局 KINGDEE_TARGET_ALIASES）。
   * 单位/物料等同源接口必须各自声明，禁止共用一套 code←number 顺序。
   */
  targetAliases?: Record<string, string[]>;
  /**
   * 添加来源时优先排到前面的接口 code 后缀（如 query_measureunits / query_material）。
   * 只排序不隐藏，避免误绑其它业务接口时仍可选手动项。
   * 星空/苍穹常共用同一后缀：须配合 preferredApiPathTokens / preferredConnectorTypes，
   * 禁止只靠后缀在两套产品间猜默认项。
   */
  preferredApiCodeSuffixes?: string[];
  /** 与 SyncRunLog entity_type 一致；设置后弹窗展示「同步记录」Tab */
  historySourceType?: string;
  /** 主数据页走 master-data sync-run-history 等；缺省走 document-push/run-history */
  listSyncRunHistory?: import('../../apps/kuaizhizao/services/document-push').ListSyncRunHistoryFn;
  /**
   * path 子串优先序（越前越优先）。例：物料页 `['executebillquery', 'bd_material/batchquery']`
   * 先星空 ExecuteBillQuery，再苍穹 batchQuery。
   */
  preferredApiPathTokens?: string[];
  /**
   * 连接器 type 优先序（越前越优先）。例：`['kingdee_galaxy', 'kingdee_cosmic']`。
   */
  preferredConnectorTypes?: string[];
  /**
   * 展示「按编码智能归类」开关：开启后请求体带 infer_parent_by_code。
   * 仅物料分组等需要时配置；文案 key 由业务页提供，避免弹窗壳绑死 master-data i18n。
   */
  inferParentByCodeOption?: {
    labelKey: string;
    onKey: string;
    offKey: string;
    hintOnKey: string;
    hintOffKey: string;
  };
}
