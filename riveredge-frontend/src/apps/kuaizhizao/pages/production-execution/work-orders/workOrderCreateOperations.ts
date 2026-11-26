/** 新建工单：将表单工序选择转为创建 API 载荷 */

function positiveIdList(raw: unknown): number[] {
  if (!Array.isArray(raw)) return []
  const out: number[] = []
  for (const item of raw) {
    const id = Number(item)
    if (Number.isInteger(id) && id > 0 && !out.includes(id)) out.push(id)
  }
  return out
}

function optionalPositiveId(raw: unknown): number | null {
  const id = Number(raw)
  return Number.isInteger(id) && id > 0 ? id : null
}

export function workOrderOperationAssignmentPayload(op: Record<string, unknown> | null | undefined) {
  const workerIds = positiveIdList(op?.assigned_worker_ids)
  const singularWorker = optionalPositiveId(op?.assigned_worker_id)
  const workers = workerIds.length ? workerIds : (singularWorker ? [singularWorker] : [])
  const equipmentIds = positiveIdList(op?.assigned_equipment_ids)
  const singularEquipment = optionalPositiveId(op?.assigned_equipment_id)
  const equipment = equipmentIds.length ? equipmentIds : (singularEquipment ? [singularEquipment] : [])
  return {
    assigned_worker_ids: workers,
    assigned_worker_id: workers[0] ?? null,
    assigned_team_id: optionalPositiveId(op?.assigned_team_id),
    assigned_equipment_ids: equipment,
    assigned_equipment_id: equipment[0] ?? null,
  }
}

export function assignmentFromProductProcessLine(line: {
  operatorIds?: unknown
  teamIds?: unknown
  equipmentIds?: unknown
}) {
  const operatorIds = positiveIdList(line.operatorIds)
  const teamIds = positiveIdList(line.teamIds)
  const equipmentIds = positiveIdList(line.equipmentIds)
  return {
    assigned_worker_ids: operatorIds,
    assigned_worker_id: operatorIds[0],
    assigned_team_id: teamIds[0],
    assigned_equipment_ids: equipmentIds,
    assigned_equipment_id: equipmentIds[0],
  }
}

/** 工单行已有人员或设备时保留；空的一侧用产品工艺行补上。 */
export function mergeMissingAssignmentFromProductProcess<T extends Record<string, unknown>>(
  ops: T[],
  lines: Array<{
    operationId?: number
    operatorIds?: unknown
    teamIds?: unknown
    equipmentIds?: unknown
  }>,
): T[] {
  const byOperationId = new Map<number, (typeof lines)[number]>()
  for (const line of lines) {
    const operationId = Number(line.operationId)
    if (Number.isInteger(operationId) && operationId > 0 && !byOperationId.has(operationId)) {
      byOperationId.set(operationId, line)
    }
  }
  return ops.map((op) => {
    const line = byOperationId.get(Number(op.operation_id))
    if (!line) return op
    const fromLine = assignmentFromProductProcessLine(line)
    const hasWorkers = positiveIdList(op.assigned_worker_ids).length > 0
      || optionalPositiveId(op.assigned_worker_id) != null
      || optionalPositiveId(op.assigned_team_id) != null
    const hasEquipment = positiveIdList(op.assigned_equipment_ids).length > 0
      || optionalPositiveId(op.assigned_equipment_id) != null
    return {
      ...op,
      ...(hasWorkers
        ? {}
        : {
            assigned_worker_ids: fromLine.assigned_worker_ids,
            assigned_worker_id: fromLine.assigned_worker_id,
            assigned_team_id: fromLine.assigned_team_id,
          }),
      ...(hasEquipment
        ? {}
        : {
            assigned_equipment_ids: fromLine.assigned_equipment_ids,
            assigned_equipment_id: fromLine.assigned_equipment_id,
          }),
    }
  })
}

function normalizeOverReportMode(raw: unknown): string {
  const m = String(raw ?? '').trim().toLowerCase()
  if (m === 'fixed' || m === 'percent' || m === 'none') return m
  return 'none'
}

function resolveLineOverReport(
  headerExplicit: boolean,
  headerOrm: string,
  headerOrv: number,
  so?: Record<string, unknown> | null,
): { over_report_mode: string; over_report_value: number } {
  if (headerExplicit) {
    return { over_report_mode: headerOrm, over_report_value: headerOrv }
  }
  // 头未配超报：保留选路线时展开的节点超报；勿塞工序档案（档案由后端 merge）
  const soMode = normalizeOverReportMode(so?.over_report_mode ?? so?.overReportMode)
  if (soMode !== 'none') {
    return {
      over_report_mode: soMode,
      over_report_value: Number(so?.over_report_value ?? so?.overReportValue ?? 0) || 0,
    }
  }
  return { over_report_mode: 'none', over_report_value: 0 }
}

/**
 * 创建弹窗仅有「工单默认超报」，无按行编辑。
 * 头上配了 fixed/percent → 写入每道工序行，保证开单设置生效；
 * 头为 none → 行优先带选路线节点超报，否则传 none，由后端 merge（物料→档案→路线默认→节点→头）。
 */
export function buildOperationsForCreatePayload(
  values: {
    operations?: number[]
    allow_operation_jump?: boolean
    over_report_mode?: string
    over_report_value?: number
  },
  selectedOperations: Array<Record<string, unknown>>,
  operationList: Array<{
    id: number
    code: string
    name: string
    reportingType?: string
    reporting_type?: string
    overReportMode?: string
    over_report_mode?: string
    overReportValue?: number
    over_report_value?: number
  }>,
): Array<Record<string, unknown>> | undefined {
  const woAllowJump = Boolean(values.allow_operation_jump)
  const headerOrm = normalizeOverReportMode(values.over_report_mode)
  const headerOrv = Number(values.over_report_value ?? 0) || 0
  const headerExplicit = headerOrm !== 'none'

  if (values.operations && Array.isArray(values.operations) && values.operations.length > 0) {
    return values.operations.map((opId: number, index: number) => {
      const operationDetail = operationList.find((op) => op.id === opId)
      if (!operationDetail) {
        throw new Error(`工序ID ${opId} 不存在`)
      }
      const so = selectedOperations.find((o) => o.operation_id === opId)
      const lineOr = resolveLineOverReport(headerExplicit, headerOrm, headerOrv, so)
      return {
        operation_id: opId,
        operation_code: operationDetail.code,
        operation_name: operationDetail.name,
        sequence: index + 1,
        reporting_type:
          so?.reporting_type ??
          operationDetail.reportingType ??
          operationDetail.reporting_type ??
          'quantity',
        // 跳转唯一控制源：工单头 allow_operation_jump；行仅镜像
        allow_jump: woAllowJump,
        is_node_operation: false,
        over_report_mode: lineOr.over_report_mode,
        over_report_value: lineOr.over_report_value,
        ...(so ? workOrderOperationAssignmentPayload(so) : {}),
      }
    })
  }
  if (selectedOperations.length > 0) {
    return selectedOperations.map((op, i) => {
      const lineOr = resolveLineOverReport(headerExplicit, headerOrm, headerOrv, op)
      return {
        operation_id: op.operation_id,
        operation_code: op.operation_code,
        operation_name: op.operation_name,
        sequence: op.sequence ?? i + 1,
        reporting_type: op.reporting_type ?? 'quantity',
        allow_jump: woAllowJump,
        is_node_operation: false,
        over_report_mode: lineOr.over_report_mode,
        over_report_value: lineOr.over_report_value,
        ...workOrderOperationAssignmentPayload(op),
        ...(op.workshop_id != null ? { workshop_id: op.workshop_id } : {}),
        ...(op.workshop_name != null ? { workshop_name: op.workshop_name } : {}),
        ...(op.standard_time != null ? { standard_time: op.standard_time } : {}),
        ...(op.setup_time != null ? { setup_time: op.setup_time } : {}),
        ...(op.piece_rate != null ? { piece_rate: op.piece_rate } : {}),
        ...(op.work_requirement != null ? { work_requirement: op.work_requirement } : {}),
        ...(op.assigned_equipment_name != null
          ? { assigned_equipment_name: op.assigned_equipment_name }
          : {}),
        ...(op.assigned_worker_name != null ? { assigned_worker_name: op.assigned_worker_name } : {}),
      }
    })
  }
  return undefined
}
