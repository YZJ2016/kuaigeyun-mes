/**
 * KU-AI 运营层契约类型（spec 181；逐字对齐后端 schemas/operations.py）。
 *
 * - 状态闭集 ready|partial|not_ready；指标可为 null（数据源失败，不得显示为 0）；
 * - 写请求字段与后端 extra=forbid 模型一一对应，禁止夹带未声明字段。
 */

export type OperationalStatus = 'ready' | 'partial' | 'not_ready';

// ============================================================ hub

export interface HubModelOut {
  configured: boolean;
  name: string | null;
  connection_uuid: string | null;
}

export interface HubMetricsOut {
  total_calls: number | null;
  pulse_count: number | null;
  corpus_count: number | null;
  avg_latency_ms: number | null;
}

export interface HubCapabilityOut {
  key: string;
  name: string;
  status: OperationalStatus;
  description: string | null;
  route: string | null;
  disabled_reason: string | null;
}

export interface HubOut {
  days: number;
  model: HubModelOut;
  metrics: HubMetricsOut;
  capabilities: HubCapabilityOut[];
}

// ============================================================ 智能体库

export interface LibraryProvisioningOut {
  complete: boolean;
  missing_template_keys: string[];
  retryable: boolean;
}

export interface LibraryItemOut {
  /** 实例稳定 key（复制项为服务端生成的 key） */
  key: string;
  template_key: string;
  name: string;
  description: string | null;
  image_key: string | null;
  /** 实例单项开关（与模板总开关取与才是最终可发送条件） */
  enabled: boolean;
  status: OperationalStatus;
  capability_tags: string[];
  sample_prompt: string | null;
  /** 绑定的档案 ID；无使用权且无管理读权限时由后端脱敏为 null */
  agent_profile_id: number | null;
  scene_route: string | null;
  scene_available: boolean;
  disabled_reason: string | null;
}

export interface LibraryOut {
  provisioning: LibraryProvisioningOut;
  items: LibraryItemOut[];
}

// ============================================================ 写请求

/** PUT /instances/{key}：字段缺省=不动；显式 null 清覆盖/解绑 */
export interface SceneInstanceUpdatePayload {
  agent_profile_id?: number | null;
  enabled?: boolean;
  name?: string | null;
  description?: string | null;
  image_key?: string | null;
  sample_prompt?: string | null;
  capability_tags?: string[] | null;
  scene_route?: string | null;
}

export interface SceneCloneOverrides {
  name?: string | null;
  description?: string | null;
  image_key?: string | null;
  sample_prompt?: string | null;
  capability_tags?: string[] | null;
  scene_route?: string | null;
}

export interface SceneInstanceClonePayload {
  template_key: string;
  source_agent_id: number;
  overrides?: SceneCloneOverrides;
}

// ============================================================ Pulse（spec 182）
// 契约逐字对齐后端 schemas/pulse.py；errors[] 只含脱敏 code/message。

export type PulseDomain =
  | 'production'
  | 'inventory'
  | 'sales'
  | 'quality'
  | 'equipment';

export type PulseSeverity = 'info' | 'warning' | 'error' | 'critical';

export type PulsePriority = 'low' | 'medium' | 'high';

export type PulseErrorCode =
  | 'permission_denied'
  | 'timeout'
  | 'detector_error'
  | 'not_connected';

export interface PulseItemOut {
  id: string;
  domain: string;
  severity: PulseSeverity;
  priority: PulsePriority;
  title: string;
  fact: string;
  suggestion: string;
  resource_type: string;
  resource_id: string;
  resource_uuid: string | null;
  /** 服务端白名单业务路由；不可用为 null（不得在前端拼路由） */
  route: string | null;
  detected_at: string;
  rule_code: string;
}

export interface PulseSummaryOut {
  total: number;
  high_priority: number;
  critical: number;
  warning_or_error: number;
  domain_count: number;
}

export interface PulseGroupOut {
  domain: string;
  label: string;
  /** 该领域筛选后总条数（非本页条数） */
  count: number;
  items: PulseItemOut[];
}

export interface PulseErrorOut {
  domain: string;
  code: PulseErrorCode | string;
  message: string;
}

export interface PulseOut {
  summary: PulseSummaryOut;
  groups: PulseGroupOut[];
  errors: PulseErrorOut[];
  /** 任一已实现 detector 失败为 false；not_connected 不影响 */
  complete: boolean;
  generated_at: string;
}

export interface PulseQuery {
  /** 逗号分隔单参数，空=全部 */
  domain?: string;
  severity?: PulseSeverity;
  page?: number;
  page_size?: number;
}

// ============================================================ 设置（spec 185）

/** 连接候选：无 key/cipher，仅本租户启用且 model_role 匹配的连接 */
export interface SettingsOptionOut {
  uuid: string;
  name: string;
  provider: string;
  model: string | null;
  model_role: string | null;
  is_active: boolean;
  is_selected: boolean;
}

export interface SettingsOcrOut {
  configured: boolean;
  base_url_masked: string;
  model: string | null;
}

export interface SettingsCapabilitiesOut {
  tools_enabled: boolean;
  rag_enabled: boolean;
  rag_use_embedding: boolean;
  rag_backend: string;
  rag_top_k: number;
  stream_enabled: boolean;
  custom_system_prompt: string;
}

export interface SettingsOut {
  chat_connection_uuid: string | null;
  vision_connection_uuid: string | null;
  chat_options: SettingsOptionOut[];
  vision_options: SettingsOptionOut[];
  ocr: SettingsOcrOut;
  /** 六个出厂模板 key → 总开关（服务端闭集） */
  agent_switches: Record<string, boolean>;
  capabilities: SettingsCapabilitiesOut;
  /** 服务端派生的不透明版本，PUT 原样回传 */
  version: string;
}

/** PUT /operations/settings：字段与后端 extra=forbid 模型一一对应 */
export interface SettingsUpdatePayload {
  version: string;
  chat_connection_uuid: string;
  vision_connection_uuid?: string | null;
  agent_switches: Record<string, boolean>;
  capabilities: {
    tools_enabled: boolean;
    rag_enabled: boolean;
    rag_use_embedding: boolean;
    rag_backend: 'native';
    rag_top_k: number;
    stream_enabled: boolean;
    custom_system_prompt: string;
  };
}

// ============================================================ 知识语料（spec 183）
// 契约逐字对齐后端 schemas/corpus.py（设计 §11.4）；
// 列表项无 raw_content/tenant_id/file_uuid，error_summary 已脱敏。

export type CorpusDocType = 'faq' | 'text' | 'file';

export type CorpusDocStatus = 'pending' | 'parsing' | 'ready' | 'failed';

export interface CorpusItemOut {
  id: number;
  uuid: string;
  knowledge_id: number | null;
  knowledge_name: string | null;
  title: string;
  /** 服务端推导：faq|text|file */
  type: CorpusDocType | string;
  source_type: string;
  chunk_count: number;
  status: CorpusDocStatus | string;
  error_summary: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CorpusListOut {
  items: CorpusItemOut[];
  total: number;
  page: number;
  page_size: number;
}

/** GET /operations/corpus 查询参数（可分享，全部进 URL search params） */
export interface CorpusQuery {
  page?: number;
  page_size?: number;
  keyword?: string;
  knowledge_id?: number;
  type?: CorpusDocType;
  status?: CorpusDocStatus;
  /** YYYY-MM-DD，站点日历日闭区间 */
  created_from?: string;
  created_to?: string;
}

/** 语料页启用知识库下拉项（不要求 knowledge 权限） */
export interface CorpusKnowledgeOption {
  id: number;
  name: string;
}

/** POST /operations/corpus/faqs 请求体（extra=forbid，一一对应） */
export interface CorpusFaqCreatePayload {
  knowledge_id: number;
  question: string;
  answer: string;
  is_active?: boolean;
}

export interface CorpusSeedFaqsOut {
  created: number;
  skipped: number;
}

export interface CorpusBatchItemOut {
  id: number;
  success: boolean;
  error: string | null;
}

export interface CorpusBatchOut {
  items: CorpusBatchItemOut[];
}

// ============================================================ 信任中心（spec 184）
// 契约逐字对齐设计 §11.5 / 后端 TrustOut；只反映当前用户，无 user_id。

export interface TrustCardOut {
  key: string;
  title: string;
  status: OperationalStatus;
  description: string | null;
  evidence: string[];
}

export interface TrustPermissionOut {
  code: string;
  granted: boolean;
}

export interface TrustHitlOut {
  implemented: boolean;
  mode: string;
}

export interface TrustOut {
  cards: TrustCardOut[];
  permissions: TrustPermissionOut[];
  hitl: TrustHitlOut;
}

// ============================================================ Core AI 统计/审计复用（spec 184）
// 契约逐字对齐 core/ai/schemas/stats.py；URL/参数/响应形状不改。
// pulse_suggestion_count 在数据源缺失时为 null（spec 184 修复：不伪造 0）。

export interface AiCapabilityStatOut {
  capability: string | null;
  count: number;
}

export interface AiDayStatOut {
  day: string;
  count: number;
}

export interface AiStatsOverviewOut {
  days: number;
  total_calls: number;
  avg_latency_ms: number | null;
  pulse_suggestion_count: number | null;
  knowledge_document_count: number;
  by_capability: AiCapabilityStatOut[];
  by_day: AiDayStatOut[];
  empty_reason: string | null;
}

export interface AiAuditLogItemOut {
  uuid: string;
  route: string;
  capability: string | null;
  model: string | null;
  latency_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  status_code: number | null;
  /** 后端原样下发；页面默认不渲染，仅持管理级权限用户见脱敏摘要 */
  error_message: string | null;
  created_at: string;
  /** 仅展示用途，不得用作跨用户筛选 */
  user_id: number | null;
}

export interface AiAuditLogListOut {
  items: AiAuditLogItemOut[];
  total: number;
  page: number;
  page_size: number;
  empty_reason: string | null;
}
