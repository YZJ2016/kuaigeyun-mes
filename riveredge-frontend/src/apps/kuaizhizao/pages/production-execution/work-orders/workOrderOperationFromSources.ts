/**
 * 新建/编辑工单：将产品工艺行、工艺路线节点、工序主数据综合为工序明细表行
 */

import type { Operation } from '../../../../master-data/types/process'
import type { ProductProcessLine } from '../../../../master-data/types/productProcess'
import {
  enrichLineFromOperation,
  buildLineFromRowAndOperation,
  resourcesFromOperation,
} from '../../../../master-data/utils/productProcessLineUtils'
import {
  normalizeTimeUnit,
  productProcessLineFromApi,
  toSeconds,
} from '../../../../master-data/utils/manufacturingTimeUnits'
import { normalizeOperationSequenceInput } from '../../../../master-data/utils/processRouteSequenceUtils'
export type WorkOrderOperationFormRow = {
  key: string
  id?: number
  operation_id?: number
  operation_code?: string
  operation_name?: string
  sequence?: number
  reporting_type?: string
  over_report_mode?: string
  over_report_value?: number
  is_node_operation?: boolean
  allow_jump?: boolean
  workshop_id?: number
  workshop_name?: string
  assigned_equipment_id?: number
  assigned_equipment_ids?: number[]
  assigned_equipment_name?: string
  assigned_worker_id?: number
  assigned_worker_ids?: number[]
  assigned_worker_name?: string
  assigned_team_id?: number
  assigned_team_name?: string
  standard_time?: number
  setup_time?: number
  piece_rate?: number
  work_requirement?: string
  is_outsourced?: boolean
  outsource_supplier_name?: string
  has_reporting?: boolean
}

const SECONDS_PER_HOUR = 3600

export type WorkOrderOpListContext = {
  workshops?: Array<{ id?: number; name?: string; code?: string }>
  equipments?: Array<{ id?: number; name?: string; code?: string }>
  personnelOptions?: Array<{ value: string; label: string }>
}

function positiveIdList(raw: unknown): number[] {
  if (!Array.isArray(raw)) return []
  const out: number[] = []
  for (const item of raw) {
    const id = Number(item)
    if (Number.isInteger(id) && id > 0 && !out.includes(id)) out.push(id)
  }
  return out
}

function productProcessUiLineToWoStandardHours(line: ProductProcessLine): number | undefined {
  const qty = line.standardTimeQty != null && line.standardTimeQty >= 1 ? line.standardTimeQty : 1
  const unit = normalizeTimeUnit(line.standardTimeUnit)
  const seconds = toSeconds(line.standardTime, unit)
  if (seconds == null) return undefined
  return (seconds / qty) / SECONDS_PER_HOUR
}

function productProcessUiLineToWoSetupHours(line: ProductProcessLine): number | undefined {
  const unit = normalizeTimeUnit(line.setupTimeUnit ?? 'm')
  const seconds = toSeconds(line.setupTime, unit)
  if (seconds == null) return undefined
  return seconds / SECONDS_PER_HOUR
}

function normalizeOverReportMode(raw: unknown): string {
  const m = String(raw ?? '').trim().toLowerCase()
  if (m === 'fixed' || m === 'percent' || m === 'none') return m
  return 'none'
}

function resolveWorkRequirement(op: Record<string, unknown> | undefined): string | undefined {
  if (!op) return undefined
  const text = String(
    op.work_requirement ?? op.workRequirement ?? op.description ?? '',
  ).trim()
  return text || undefined
}

export function attachWorkOrderOpAssignmentLabels<
  T extends Record<string, unknown>,
>(row: T, ctx?: WorkOrderOpListContext): T {
  if (!ctx) return row
  const next = { ...row } as T & WorkOrderOperationFormRow
  const workshopId = Number(row.workshop_id)
  if (Number.isInteger(workshopId) && workshopId > 0 && !next.workshop_name) {
    const hit = ctx.workshops?.find((w) => Number(w.id) === workshopId)
    const label = String(hit?.name ?? hit?.code ?? '').trim()
    if (label) next.workshop_name = label
  }
  const equipmentIds = positiveIdList(row.assigned_equipment_ids ?? row.assigned_equipment_id)
  if (equipmentIds.length && !next.assigned_equipment_name) {
    const labels = equipmentIds
      .map((id) => {
        const hit = ctx.equipments?.find((e) => Number(e.id) === id)
        return String(hit?.name ?? hit?.code ?? '').trim() || String(id)
      })
      .filter(Boolean)
    if (labels.length) next.assigned_equipment_name = labels.join('、')
  }
  const workerIds = positiveIdList(row.assigned_worker_ids ?? row.assigned_worker_id)
  const workerNames: string[] = []
  for (const id of workerIds) {
    const opt = ctx.personnelOptions?.find((p) => p.value === `U_${id}`)
    if (opt?.label) {
      workerNames.push(opt.label.replace(/^\[人员\]\s*/, '').trim())
    }
  }
  const teamId = Number(row.assigned_team_id)
  let teamName: string | undefined
  if (Number.isInteger(teamId) && teamId > 0) {
    const opt = ctx.personnelOptions?.find((p) => p.value === `T_${teamId}`)
    teamName = opt?.label?.replace(/^\[小组\]\s*/, '').trim()
  }
  if (workerNames.length) next.assigned_worker_name = workerNames.join('、')
  if (teamName) next.assigned_team_name = teamName
  return next as T
}

/** 产品工艺行（UI 或 API 秒）→ 工单工序表行 */
export function workOrderOperationRowFromProductProcessLine(
  lineInput: ProductProcessLine,
  op: Operation | Record<string, unknown> | undefined,
  options: {
    sequence: number
    allowJump: boolean
    listContext?: WorkOrderOpListContext
    /** 产品工艺 API 的工时为秒；路线解析结果已是界面单位 */
    lineUsesApiSeconds?: boolean
  },
): WorkOrderOperationFormRow {
  const line =
  options.lineUsesApiSeconds === false
    ? lineInput
    : productProcessLineFromApi(lineInput)
  const enriched = op
    ? enrichLineFromOperation(line, op as Operation)
    : line
  const workshopIds = enriched.workshopIds ?? []
  const operatorIds = enriched.operatorIds ?? []
  const teamIds = enriched.teamIds ?? []
  const equipmentIds = enriched.equipmentIds ?? []
  const orm = normalizeOverReportMode(enriched.overReportMode)
  const orv = Number(enriched.overReportValue ?? 0) || 0
  const opRec = op as Record<string, unknown> | undefined

  const row: WorkOrderOperationFormRow = {
    key: '',
    operation_id: Number(enriched.operationId ?? opRec?.id) || undefined,
    operation_code: String(enriched.code ?? opRec?.code ?? '').trim() || undefined,
    operation_name: String(enriched.name ?? opRec?.name ?? '').trim() || undefined,
    sequence: options.sequence,
    is_node_operation: Boolean(enriched.isNodeOperation ?? false),
    reporting_type:
      String(enriched.reportingType ?? opRec?.reportingType ?? opRec?.reporting_type ?? 'quantity'),
    over_report_mode: orm,
    over_report_value: orv,
    standard_time: productProcessUiLineToWoStandardHours(enriched),
    setup_time: productProcessUiLineToWoSetupHours(enriched),
    piece_rate:
      enriched.pieceRate != null && Number.isFinite(Number(enriched.pieceRate))
        ? Number(enriched.pieceRate)
        : undefined,
    work_requirement: resolveWorkRequirement(opRec),
    workshop_id: workshopIds[0],
    assigned_worker_ids: operatorIds,
    assigned_worker_id: operatorIds[0],
    assigned_team_id: teamIds[0],
    assigned_equipment_ids: equipmentIds,
    assigned_equipment_id: equipmentIds[0],
    is_outsourced: Boolean(enriched.isOutsourced),
    outsource_supplier_name: enriched.outsourceSupplierName,
  } as WorkOrderOperationFormRow & {
    is_outsourced?: boolean
    outsource_supplier_name?: string
  }

  return attachWorkOrderOpAssignmentLabels(row, options.listContext)
}

/** 手工添加工序：从工序主数据默认资源与超报/报工类型补全 */
export function workOrderOperationRowFromOperationMaster(
  op: Record<string, unknown>,
  options: {
    sequence: number
    allowJump?: boolean
    listContext?: WorkOrderOpListContext
  },
): WorkOrderOperationFormRow {
  const resources = resourcesFromOperation(op as Operation)
  const line: ProductProcessLine = {
    operationUuid: String(op.uuid ?? ''),
    operationId: Number(op.id) || undefined,
    code: String(op.code ?? ''),
    name: String(op.name ?? ''),
    reportingType: String(op.reportingType ?? op.reporting_type ?? 'quantity'),
    overReportMode: String(op.overReportMode ?? op.over_report_mode ?? 'none'),
    overReportValue: Number(op.overReportValue ?? op.over_report_value ?? 0) || 0,
    workshopIds: resources.workshopIds,
    operatorIds: resources.operatorIds,
    teamIds: resources.teamIds,
    equipmentIds: resources.equipmentIds,
  }
  return workOrderOperationRowFromProductProcessLine(line, op, {
    sequence: options.sequence,
    allowJump: Boolean(options.allowJump),
    listContext: options.listContext,
    lineUsesApiSeconds: false,
  })
}

function extractRouteSequenceItems(seq: unknown, opList: Operation[]): Record<string, unknown>[] {
  const normalized = normalizeOperationSequenceInput(seq)
  if (!normalized || opList.length === 0) return []
  let items: unknown[] = []
  if (Array.isArray(normalized)) {
    items = normalized
  } else if (typeof normalized === 'object' && normalized !== null) {
    const seqObj = normalized as Record<string, unknown>
    if (Array.isArray(seqObj.operations)) {
      items = seqObj.operations
    } else if (Array.isArray(seqObj.sequence)) {
      for (const uuid of seqObj.sequence as string[]) {
        const op = opList.find((o) => o.uuid === uuid)
        if (op) {
          items.push({ uuid: op.uuid, code: op.code, name: op.name })
        }
      }
    } else if (seqObj.operation_ids || seqObj.operationIds) {
      const ids = (seqObj.operation_ids ?? seqObj.operationIds) as number[]
      items = ids.map((id, i) => ({ operation_id: id, sequence: i + 1 }))
    } else {
      const vals = Object.values(seqObj).filter(
        (v) => v && (typeof v === 'object' || typeof v === 'string'),
      )
      const arr = vals.find((v) => Array.isArray(v)) as unknown[] | undefined
      items = arr ?? vals
    }
  }
  const out: Record<string, unknown>[] = []
  items.forEach((item, index) => {
    if (!item || typeof item !== 'object') return
    const row = item as Record<string, unknown>
    let op: Operation | undefined
    if (row.operation_id != null || row.operationId != null) {
      const id = Number(row.operation_id ?? row.operationId)
      op = opList.find((o) => o.id === id)
    } else if (typeof item === 'string' || row.uuid) {
      const uuid = typeof item === 'string' ? item : String(row.uuid)
      op = opList.find((o) => o.uuid === uuid)
    }
    if (!op) return
    const merged = row.uuid || row.operation_id != null
      ? row
      : { ...row, uuid: op.uuid, operation_id: op.id, code: op.code, name: op.name }
    out.push({
      ...merged,
      sequence: Number(row.sequence ?? row._idx ?? index + 1) || index + 1,
    })
  })
  out.sort((a, b) => Number(a.sequence) - Number(b.sequence))
  return out
}

/** 工艺路线 operation_sequence → 工单工序明细行（含工时/工价/资源） */
export function parseWorkOrderOperationsFromRouteSequence(
  seq: unknown,
  opList: Operation[],
  allowJump: boolean,
  listContext?: WorkOrderOpListContext,
): WorkOrderOperationFormRow[] {
  const items = extractRouteSequenceItems(seq, opList)
  return items.map((item, index) => {
    const op =
      opList.find((o) => o.id === Number(item.operation_id ?? item.operationId)) ??
      opList.find((o) => o.uuid === String(item.uuid ?? ''))
    const line = buildLineFromRowAndOperation(item, op)
    const row = workOrderOperationRowFromProductProcessLine(line, op, {
      sequence: index + 1,
      allowJump,
      listContext,
      lineUsesApiSeconds: false,
    })
    return { ...row, allow_jump: allowJump } as WorkOrderOperationFormRow & { allow_jump?: boolean }
  })
}