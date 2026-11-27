/**
 * 流程造数：按销售订单/销售预测生成制造全流程数据
 */

import { apiRequest } from '../../../services/api';

export type FlowSourceType = 'sales_order' | 'sales_forecast';

export type StepOperatorMode =
  | 'fixed'
  | 'random_role'
  | 'random_department'
  | 'random_team'
  | 'operation_assigned'
  | 'current';

export interface FlowEligibleOrder {
  id: number;
  order_code: string;
  order_name?: string | null;
  customer_name?: string | null;
  status?: string;
  order_date?: string | null;
  planning_pushed_to_computation?: boolean;
  procurement_fulfillment_mode?: string | null;
  eligible?: boolean;
  block_reason?: string | null;
}

export interface FlowEligibleForecast {
  id: number;
  forecast_code: string;
  forecast_name?: string | null;
  forecast_period?: string | null;
  status?: string;
  start_date?: string | null;
  end_date?: string | null;
  planning_pushed_to_computation?: boolean;
  eligible?: boolean;
  block_reason?: string | null;
}

export interface FlowInterval {
  min_seconds: number;
  max_seconds: number;
}

export interface FlowWorkSchedule {
  weekdays: number[];
  start_time: string;
  end_time: string;
  lookback_days?: number;
}

export interface StepOperatorPayload {
  mode: StepOperatorMode;
  user_id?: number | null;
  role_code?: string | null;
  department_id?: number | null;
  work_group_id?: number | null;
}

export interface ReportingBatchConfig {
  min_batches: number;
  max_batches: number;
}

export interface FlowGeneratePayload {
  source_type: FlowSourceType;
  sales_order_id?: number | null;
  sales_forecast_id?: number | null;
  warehouse_id?: number | null;
  anchor_at?: string | null;
  default_interval?: FlowInterval;
  intervals?: Record<string, FlowInterval>;
  steps?: Record<string, boolean>;
  step_operators?: Record<string, StepOperatorPayload>;
  reporting_batches?: ReportingBatchConfig;
  work_schedule?: FlowWorkSchedule | null;
  use_work_schedule?: boolean;
  /** 自选完工物料；不传/空=全部下推工单走生产链 */
  selected_material_ids?: number[] | null;
  /** 多工单生产链并行推进 */
  parallel_work_orders?: boolean;
  /** 数量并行组每组最小件数（如 1） */
  parallel_group_size_min?: number | null;
  /** 数量并行组每组最大件数（如 3） */
  parallel_group_size_max?: number | null;
  /** 流程结束锚点；仅填数模式与 anchor_at 组成时间窗均摊间隔 */
  flow_end_at?: string | null;
  /** 来料检建单失败时允许直推入库（仅填数模式；真实模式强制关） */
  allow_skip_iqc?: boolean;
  /** 续跑：失败轮次 run_id，按检查点跳过已完成阶段 */
  resume_run_id?: string | null;
  /** real=验收级真实仿真（默认）；fill=快速填数 */
  sim_mode?: 'real' | 'fill';
  /** 场景段；空=全链路串联 */
  scenarios?: string[] | null;
}

export type FlowSimMode = 'real' | 'fill';

export const DEFAULT_FULL_CHAIN_SCENARIOS = [
  'mrp_push',
  'purchase_inbound',
  'owo_fulfill',
  'wo_complete',
  'ship',
  'finance_settlement',
] as const;

export const FLOW_SCENARIO_OPTIONS = [
  {
    key: 'mrp_push',
    labelKey: 'app.kuaizhizao.flowDataGenerate.scenario.mrp_push',
    stepKeys: ['demand_computation'] as const,
  },
  {
    key: 'direct_purchase',
    labelKey: 'app.kuaizhizao.flowDataGenerate.scenario.direct_purchase',
    stepKeys: ['direct_purchase'] as const,
  },
  {
    key: 'purchase_inbound',
    labelKey: 'app.kuaizhizao.flowDataGenerate.scenario.purchase_inbound',
    stepKeys: ['purchase', 'incoming_inspection'] as const,
  },
  {
    key: 'owo_fulfill',
    labelKey: 'app.kuaizhizao.flowDataGenerate.scenario.owo_fulfill',
    stepKeys: ['outsource'] as const,
  },
  {
    key: 'wo_complete',
    labelKey: 'app.kuaizhizao.flowDataGenerate.scenario.wo_complete',
    stepKeys: [
      'inventory_topup',
      'production_picking',
      'reporting',
      'process_outsource',
      'process_inspection',
      'finished_goods_inspection',
      'finished_goods_receipt',
    ] as const,
  },
  {
    key: 'ship',
    labelKey: 'app.kuaizhizao.flowDataGenerate.scenario.ship',
    stepKeys: ['shipment_delivery'] as const,
  },
  {
    key: 'finance_settlement',
    labelKey: 'app.kuaizhizao.flowDataGenerate.scenario.finance_settlement',
    stepKeys: ['finance_settlement'] as const,
  },
] as const;

/** 场景 → 步骤开关（前端真源，与后端 SCENARIO_DEFS 对齐） */
export function stepsFromScenarios(scenarioKeys: string[]): Record<string, boolean> {
  const all = [
    'demand_computation',
    'direct_purchase',
    'purchase',
    'incoming_inspection',
    'outsource',
    'inventory_topup',
    'production_picking',
    'reporting',
    'process_outsource',
    'process_inspection',
    'finished_goods_inspection',
    'finished_goods_receipt',
    'shipment_delivery',
    'finance_settlement',
  ] as const;
  const enabled = new Set<string>();
  for (const key of scenarioKeys) {
    const def = FLOW_SCENARIO_OPTIONS.find((s) => s.key === key);
    if (def) {
      for (const sk of def.stepKeys) enabled.add(sk);
    }
  }
  return Object.fromEntries(all.map((k) => [k, enabled.has(k)]));
}

export interface FlowWorkOrderCandidate {
  material_id: number;
  material_code: string;
  material_name?: string;
  source_type?: string;
  quantity?: number;
  has_process?: boolean;
  process_operation_count?: number;
  has_bom?: boolean;
  /** 0=订单行成品；>0=BOM 下级自制件 */
  bom_level?: number;
  parent_material_id?: number | null;
  ready?: boolean;
  blockers?: string[];
}

export interface FlowMaterialIdIssue {
  line_id: number;
  stale_material_id?: number | null;
  material_code?: string | null;
  material_name?: string | null;
  issue?: string;
  message?: string;
}

export interface FlowPrecheckResult {
  ok: boolean;
  source_type?: FlowSourceType;
  sales_order_id?: number | null;
  sales_forecast_id?: number | null;
  order_code: string;
  warehouse_id: number;
  warehouse_name: string;
  errors: string[];
  warnings: string[];
  blocking_codes?: string[];
  work_order_candidates: FlowWorkOrderCandidate[];
  material_id_issues?: FlowMaterialIdIssue[];
  can_repair_material_ids?: boolean;
  parallel_work_orders_default?: boolean;
}

export interface FlowRepairMaterialIdsResult {
  success: boolean;
  source_type?: FlowSourceType;
  sales_order_id?: number | null;
  sales_forecast_id?: number | null;
  order_code: string;
  repaired_count: number;
  failed_count: number;
  skipped_count: number;
  repaired: Array<{
    line_id: number;
    stale_material_id?: number | null;
    material_id: number;
    material_code?: string;
    material_name?: string;
    message?: string;
  }>;
  failed: Array<{
    line_id: number;
    stale_material_id?: number | null;
    material_code?: string | null;
    material_name?: string | null;
    message?: string;
  }>;
}

export interface FlowOperatorDefaultStep {
  step_key: string;
  default_role_codes: string[];
}

export interface FlowOperatorDefaultsResult {
  steps: FlowOperatorDefaultStep[];
}

export interface FlowPreviewStep {
  step_key: string;
  label: string;
  issued_at: string;
  operation_sequence?: number;
  operation_code?: string | null;
  operation_name?: string | null;
  flow_mode?: string | null;
  note?: string | null;
}

export interface FlowPreviewResult {
  source_type?: FlowSourceType;
  sales_order_id?: number | null;
  sales_forecast_id?: number | null;
  order_code: string;
  warehouse_id: number;
  warehouse_name: string;
  anchor_at: string;
  /** 预估整流程完成时刻（末步 issued_at） */
  estimated_finish_at?: string | null;
  /** 按起止时间窗推算的步骤间隔（秒）；前端可回填表单 */
  suggested_intervals?: Record<string, FlowInterval> | null;
  steps: FlowPreviewStep[];
  process_operations?: Array<{
    code?: string | null;
    name?: string | null;
    sequence?: number;
    allow_jump?: boolean;
    standard_time?: number | null;
    setup_time?: number | null;
  }>;
  process_material_code?: string | null;
  /** 成品 + BOM 下级自制件工序明细 */
  process_materials?: Array<{
    material_id?: number;
    material_code?: string;
    material_name?: string;
    bom_level?: number;
    parent_material_id?: number | null;
    quantity?: number;
    process_operation_count?: number;
    has_process?: boolean;
    operations?: Array<Record<string, unknown>>;
  }>;
  warnings?: string[];
}

export interface FlowRevertResult {
  success: boolean;
  run_id: string;
  reverted_count: number;
  demand_id?: number | null;
  notes?: string[];
}

export interface FlowStepResult {
  step_key: string;
  status: string;
  doc_type?: string;
  doc_id?: number;
  doc_code?: string;
  label?: string;
  issued_at?: string;
  operation_log_id?: number | null;
  note?: string | null;
  message?: string;
}

export interface FlowExecuteResult {
  success: boolean;
  run_id: string;
  resumed?: boolean;
  resumable?: boolean;
  source_type?: FlowSourceType;
  sales_order_id?: number | null;
  sales_forecast_id?: number | null;
  order_code: string;
  warehouse_id: number;
  warehouse_name: string;
  steps: FlowStepResult[];
  timeline: FlowStepResult[];
  outsource_notes?: string[];
  operators?: Record<string, number>;
  errors?: string[];
  skipped_count?: number;
  completed_work_order_count?: number;
  error?: string;
}

export class FlowGenerateExecuteError extends Error {
  run_id?: string;
  resumable?: boolean;

  constructor(message: string, opts?: { run_id?: string; resumable?: boolean }) {
    super(message);
    this.name = 'FlowGenerateExecuteError';
    this.run_id = opts?.run_id;
    this.resumable = opts?.resumable;
  }
}

export type FlowJobStatus = 'queued' | 'running' | 'succeeded' | 'failed';

export interface FlowGenerateJob {
  job_id: string;
  status: FlowJobStatus;
  progress: number;
  message?: string | null;
  result?: FlowExecuteResult | null;
  error?: string | null;
  created_at?: string;
  updated_at?: string;
}

const BASE = '/apps/kuaizhizao/management/flow-generate';

export async function getFlowOperatorDefaults(): Promise<FlowOperatorDefaultsResult> {
  return apiRequest(BASE + '/operator-defaults', {
    method: 'GET',
  });
}

export async function previewFlowGenerate(
  body: FlowGeneratePayload,
): Promise<FlowPreviewResult> {
  return apiRequest(BASE + '/preview', {
    method: 'POST',
    data: body,
    // BOM 展开 + 工艺解析在大树下可达数十秒；与后端上限对齐
    timeoutMs: 180_000,
  });
}

export async function precheckFlowGenerate(
  body: FlowGeneratePayload,
): Promise<FlowPrecheckResult> {
  return apiRequest(BASE + '/precheck', {
    method: 'POST',
    data: body,
    timeoutMs: 180_000,
  });
}

/** 按行物料编码+名称回写失效 material_id */
export async function repairFlowMaterialIds(
  body: FlowGeneratePayload,
): Promise<FlowRepairMaterialIdsResult> {
  return apiRequest(BASE + '/repair-material-ids', {
    method: 'POST',
    data: body,
    timeoutMs: 60_000,
  });
}

/** 启动异步造数任务（立即返回 job_id，避免网关 504） */
export async function startFlowGenerate(
  body: FlowGeneratePayload,
): Promise<FlowGenerateJob> {
  return apiRequest(BASE, {
    method: 'POST',
    data: body,
    timeoutMs: 60_000,
  });
}

export async function getFlowGenerateJob(jobId: string): Promise<FlowGenerateJob> {
  return apiRequest(`${BASE}/jobs/${encodeURIComponent(jobId)}`, {
    method: 'GET',
    timeoutMs: 30_000,
  });
}

/** 按 run_id 撤回本轮已写入单据 */
export async function revertFlowGenerate(runId: string): Promise<FlowRevertResult> {
  return apiRequest(BASE + '/revert', {
    method: 'POST',
    data: { run_id: runId },
    timeoutMs: 120_000,
  });
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** 启动并轮询至完成；onProgress 用于进度条 */
export async function executeFlowGenerate(
  body: FlowGeneratePayload,
  onProgress?: (job: FlowGenerateJob) => void,
): Promise<FlowExecuteResult> {
  const started = await startFlowGenerate(body);
  onProgress?.(started);
  let job = started;
  const deadline = Date.now() + 30 * 60_000;
  while (job.status === 'queued' || job.status === 'running') {
    if (Date.now() > deadline) {
      throw new Error('造数任务超时，请稍后在业务单据中核对是否已生成');
    }
    await sleep(1200);
    job = await getFlowGenerateJob(job.job_id);
    onProgress?.(job);
  }
  if (job.status === 'failed') {
    const partial = job.result;
    throw new FlowGenerateExecuteError(
      job.error || job.message || '造数未通过，请修改后重试',
      {
        run_id: partial?.run_id || undefined,
        resumable: Boolean(partial?.resumable && partial?.run_id),
      },
    );
  }
  if (!job.result) {
    throw new Error('造数任务已完成但未返回结果');
  }
  return job.result;
}
