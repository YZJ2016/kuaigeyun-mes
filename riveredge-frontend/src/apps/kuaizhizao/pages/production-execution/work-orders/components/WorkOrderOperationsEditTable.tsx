import React, { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Button, Input, InputNumber, Select, Table, theme } from 'antd'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import type { FormListFieldData } from 'antd/es/form/FormList'
import { DOCUMENT_DETAIL_CONTROL_SIZE } from '../../../../components/document-detail-table/documentDetailTable'
import {
  UniTableDetailHeader,
} from '../../../../../../components/uni-table-detail/UniTableDetail'
import {
  UNI_TABLE_DETAIL_DRAG_INDEX_COL_WIDTH,
  UniTableDetailSortableTable,
  buildUniTableDetailDragIndexColumn,
  uniTableDetailSortableComponents,
} from '../../../../../../components/uni-table-detail/sortableFormListTable'
import { UniTableStackedPrimaryCell } from '../../../../../../components/uni-table/stackedPrimaryColumn'
import { MarkerTag } from '../../../../../../constants/statusBadges'

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

export type WorkOrderWorkshopSelectOption = { value: number; label: string }
export type WorkOrderEquipmentSelectOption = { value: number; label: string }
export type WorkOrderPersonnelSelectOption = { value: string; label: string }

export interface WorkOrderOperationsEditTableProps {
  rows: WorkOrderOperationFormRow[]
  onChange: (rows: WorkOrderOperationFormRow[]) => void
  workshopOptions?: WorkOrderWorkshopSelectOption[]
  equipmentOptions?: WorkOrderEquipmentSelectOption[]
  personnelOptions?: WorkOrderPersonnelSelectOption[]
  disabled?: boolean
  /** 外层已用页签标出分组时不再重复标题 */
  hideSectionTitle?: boolean
  /** 表头右侧「添加工序」，与物料清单「添加子物料」同一位置 */
  onAdd?: () => void
  /** 表头左侧：工单默认超报、超报数值、允许跳转工序 */
  headerLeft?: React.ReactNode
}

const patchRows = (
  rows: WorkOrderOperationFormRow[],
  key: string,
  patch: Partial<WorkOrderOperationFormRow>,
): WorkOrderOperationFormRow[] => rows.map((r) => (r.key === key ? { ...r, ...patch } : r))

const positiveIds = (raw: unknown): number[] => {
  if (!Array.isArray(raw)) return []
  const out: number[] = []
  for (const item of raw) {
    const id = Number(item)
    if (Number.isInteger(id) && id > 0 && !out.includes(id)) out.push(id)
  }
  return out
}

const equipmentIdsOf = (row: WorkOrderOperationFormRow): number[] => {
  const ids = positiveIds(row.assigned_equipment_ids)
  if (ids.length) return ids
  const one = Number(row.assigned_equipment_id)
  return Number.isInteger(one) && one > 0 ? [one] : []
}

const personnelValuesOf = (row: WorkOrderOperationFormRow): string[] => {
  const workerIds = positiveIds(row.assigned_worker_ids)
  const ids = workerIds.length
    ? workerIds
    : (Number.isInteger(Number(row.assigned_worker_id)) && Number(row.assigned_worker_id) > 0
      ? [Number(row.assigned_worker_id)]
      : [])
  const values = ids.map((id) => `U_${id}`)
  const teamId = Number(row.assigned_team_id)
  if (Number.isInteger(teamId) && teamId > 0) values.push(`T_${teamId}`)
  return values
}

/** 工单只存一个工作小组：多选里后选的小组替换先前的小组。 */
const normalizePersonnelValues = (values: string[]): string[] => {
  const workers: string[] = []
  let team: string | undefined
  for (const value of values) {
    if (value.startsWith('U_')) workers.push(value)
    else if (value.startsWith('T_')) team = value
  }
  return team ? [...workers, team] : workers
}

const personnelOptionsForRow = (
  options: WorkOrderPersonnelSelectOption[],
  row: WorkOrderOperationFormRow,
): WorkOrderPersonnelSelectOption[] => {
  const values = personnelValuesOf(row)
  const known = new Set(options.map((item) => item.value))
  const missing = values.filter((value) => !known.has(value))
  if (!missing.length) return options
  const workerName = String(row.assigned_worker_name ?? '').trim()
  const teamName = String(row.assigned_team_name ?? '').trim()
  const extra = missing.map((value) => {
    if (value.startsWith('U_') && missing.filter((item) => item.startsWith('U_')).length === 1 && workerName) {
      return { value, label: `[人员] ${workerName}` }
    }
    if (value.startsWith('T_') && teamName) {
      return { value, label: `[小组] ${teamName}` }
    }
    return { value, label: value }
  })
  return [...options, ...extra]
}

const equipmentOptionsForRow = (
  options: WorkOrderEquipmentSelectOption[],
  row: WorkOrderOperationFormRow,
): WorkOrderEquipmentSelectOption[] => {
  const ids = equipmentIdsOf(row)
  const known = new Set(options.map((item) => item.value))
  const missing = ids.filter((id) => !known.has(id))
  if (!missing.length) return options
  const storedName = String(row.assigned_equipment_name ?? '').trim()
  const extra = missing.map((id) => ({
    value: id,
    label: missing.length === 1 && storedName ? storedName : String(id),
  }))
  return [...options, ...extra]
}

const workshopOptionsForRow = (
  options: WorkOrderWorkshopSelectOption[],
  row: WorkOrderOperationFormRow,
): WorkOrderWorkshopSelectOption[] => {
  const id = Number(row.workshop_id)
  if (!Number.isInteger(id) || id <= 0) return options
  if (options.some((item) => item.value === id)) return options
  const storedName = String(row.workshop_name ?? '').trim()
  return [{ value: id, label: storedName || String(id) }, ...options]
}

const withSequence = (rows: WorkOrderOperationFormRow[]) =>
  rows.map((row, index) => ({ ...row, sequence: index + 1 }))

const moveRows = (rows: WorkOrderOperationFormRow[], from: number, to: number) => {
  if (from === to || from < 0 || to < 0 || from >= rows.length || to >= rows.length) return rows
  const next = rows.slice()
  const [item] = next.splice(from, 1)
  if (!item) return rows
  next.splice(to, 0, item)
  return withSequence(next)
}

export const WorkOrderOperationsEditTable: React.FC<WorkOrderOperationsEditTableProps> = ({
  rows,
  onChange,
  workshopOptions = [],
  equipmentOptions = [],
  personnelOptions = [],
  disabled = false,
  hideSectionTitle = false,
  onAdd,
  headerLeft,
}) => {
  const { t } = useTranslation()
  const { token } = theme.useToken()
  const dragActive = !disabled && rows.length > 0

  const formatOverReportDisplay = (mode?: string, value?: number) => {
    const m = String(mode ?? 'none').trim().toLowerCase()
    if (m === 'none') return '—'
    const v = Number(value ?? 0) || 0
    if (m === 'percent') return `${v}%`
    return String(v)
  }
  const fields = useMemo(
    () =>
      rows.map((row, name) => ({
        key: row.key,
        name,
      })) as unknown as FormListFieldData[],
    [rows],
  )

  const columns = [
    ...(dragActive ? [buildUniTableDetailDragIndexColumn(t, token)] : [{
      title: t('app.kuaizhizao.workOrder.opColSequence'),
      width: 56,
      render: (_: unknown, __: WorkOrderOperationFormRow, index: number) => index + 1,
    }]),
    {
      title: t('app.kuaizhizao.workOrder.opColOperation'),
      width: 156,
      render: (_: unknown, row: WorkOrderOperationFormRow) => (
        <UniTableStackedPrimaryCell
          primary={row.operation_name?.trim() || row.operation_code?.trim() || '—'}
          secondary={[
            row.operation_code?.trim(),
            row.is_outsourced
              ? row.outsource_supplier_name?.trim()
                ? `${t('app.kuaizhizao.workOrder.opOutsourcedTag')} ${row.outsource_supplier_name.trim()}`
                : t('app.kuaizhizao.workOrder.opOutsourcedTag')
              : undefined,
          ]
            .filter(Boolean)
            .join(' / ')}
          secondaryCopyable={Boolean(row.operation_code?.trim())}
        />
      ),
    },
    {
      title: t('field.operation.reportingType'),
      dataIndex: 'reporting_type',
      width: 100,
      render: (v: string) => {
        const isStatus = String(v ?? '') === 'status'
        return (
          <MarkerTag variant="filled" color={isStatus ? 'geekblue' : 'default'}>
            {isStatus
              ? t('field.operation.reportingTypeStatus')
              : t('field.operation.reportingTypeQuantity')}
          </MarkerTag>
        )
      },
    },
    {
      title: t('app.kuaizhizao.workOrder.opColWorkshop'),
      dataIndex: 'workshop_id',
      width: 140,
      render: (_: unknown, row: WorkOrderOperationFormRow) => {
        const selectedId = Number(row.workshop_id)
        const value = Number.isInteger(selectedId) && selectedId > 0 ? selectedId : undefined
        if (disabled) {
          return row.workshop_name || (value != null ? String(value) : '—')
        }
        return (
          <Select
            size={DOCUMENT_DETAIL_CONTROL_SIZE}
            style={{ width: '100%' }}
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder={t('app.kuaizhizao.workOrder.opWorkshopPlaceholder')}
            options={workshopOptionsForRow(workshopOptions, row)}
            value={value}
            onChange={(nextId: number | null | undefined) => {
              const id = Number(nextId)
              if (!Number.isInteger(id) || id <= 0) {
                onChange(patchRows(rows, row.key, {
                  workshop_id: undefined,
                  workshop_name: undefined,
                }))
                return
              }
              const label =
                workshopOptions.find((item) => item.value === id)?.label ||
                String(row.workshop_name ?? '').trim() ||
                String(id)
              onChange(patchRows(rows, row.key, {
                workshop_id: id,
                workshop_name: label,
              }))
            }}
          />
        )
      },
    },
    {
      title: t('app.kuaizhizao.workOrder.opColEquipment'),
      dataIndex: 'assigned_equipment_ids',
      width: 200,
      render: (_: unknown, row: WorkOrderOperationFormRow) => {
        const selected = equipmentIdsOf(row)
        return (
          <Select
            mode="multiple"
            size={DOCUMENT_DETAIL_CONTROL_SIZE}
            style={{ width: '100%' }}
            disabled={disabled || row.has_reporting}
            allowClear
            showSearch
            optionFilterProp="label"
            maxTagCount="responsive"
            placeholder={t('field.operation.defaultEquipmentIdsPlaceholder')}
            options={equipmentOptionsForRow(equipmentOptions, row)}
            value={selected}
            onChange={(values: number[]) => {
              const ids = positiveIds(values)
              const labels = ids
                .map((id) => equipmentOptions.find((item) => item.value === id)?.label)
                .filter((label): label is string => Boolean(label))
              onChange(patchRows(rows, row.key, {
                assigned_equipment_ids: ids,
                assigned_equipment_id: ids[0],
                assigned_equipment_name: labels.length ? labels.join('、') : undefined,
              }))
            }}
          />
        )
      },
    },
    {
      title: t('app.kuaizhizao.workOrder.opColWorkers'),
      dataIndex: 'assigned_worker_ids',
      width: 220,
      render: (_: unknown, row: WorkOrderOperationFormRow) => (
        <Select
          mode="multiple"
          size={DOCUMENT_DETAIL_CONTROL_SIZE}
          style={{ width: '100%' }}
          disabled={disabled || row.has_reporting}
          allowClear
          showSearch
          optionFilterProp="label"
          maxTagCount="responsive"
          placeholder={t('field.operation.defaultPersonnelConfigsPlaceholder')}
          options={personnelOptionsForRow(personnelOptions, row)}
          value={personnelValuesOf(row)}
          onChange={(values: string[]) => {
            const normalized = normalizePersonnelValues(values)
            const workerIds: number[] = []
            const workerNames: string[] = []
            let teamId: number | undefined
            let teamName: string | undefined
            for (const value of normalized) {
              if (value.startsWith('U_')) {
                const id = Number(value.slice(2))
                if (!Number.isInteger(id) || id <= 0) continue
                workerIds.push(id)
                const label = personnelOptions.find((item) => item.value === value)?.label ?? ''
                const name = label.replace(/^\[人员\]\s*/, '').trim()
                if (name) workerNames.push(name)
              } else if (value.startsWith('T_')) {
                const id = Number(value.slice(2))
                if (!Number.isInteger(id) || id <= 0) continue
                teamId = id
                const label = personnelOptions.find((item) => item.value === value)?.label ?? ''
                teamName = label.replace(/^\[小组\]\s*/, '').trim() || undefined
              }
            }
            onChange(patchRows(rows, row.key, {
              assigned_worker_ids: workerIds,
              assigned_worker_id: workerIds[0],
              assigned_worker_name: workerNames.length ? workerNames.join('、') : undefined,
              assigned_team_id: teamId,
              assigned_team_name: teamName,
            }))
          }}
        />
      ),
    },
    {
      title: t('app.kuaizhizao.workOrder.opColOverReport'),
      dataIndex: 'over_report_value',
      width: 88,
      render: (_: unknown, row: WorkOrderOperationFormRow) => {
        const mode = String(row.over_report_mode ?? 'none')
        if (mode === 'none') return '—'
        const text = formatOverReportDisplay(mode, row.over_report_value)
        return (
          <MarkerTag variant="filled" color="gold">
            {mode === 'percent'
              ? `${t('field.operation.overReportModePercent')} ${text}`
              : `${t('field.operation.overReportModeFixed')} ${text}`}
          </MarkerTag>
        )
      },
    },
    {
      title: t('app.kuaizhizao.workOrder.opColStandardTime'),
      dataIndex: 'standard_time',
      width: 110,
      render: (v: number, row: WorkOrderOperationFormRow) =>
        disabled ? (
          v ?? '—'
        ) : (
          <InputNumber
            size={DOCUMENT_DETAIL_CONTROL_SIZE}
            style={{ width: '100%' }}
            min={0}
            value={v}
            onChange={(n) => onChange(patchRows(rows, row.key, { standard_time: Number(n) || 0 }))}
          />
        ),
    },
    {
      title: t('app.kuaizhizao.workOrder.opColSetupTime'),
      dataIndex: 'setup_time',
      width: 100,
      render: (v: number, row: WorkOrderOperationFormRow) =>
        disabled ? (
          v ?? '—'
        ) : (
          <InputNumber
            size={DOCUMENT_DETAIL_CONTROL_SIZE}
            style={{ width: '100%' }}
            min={0}
            value={v}
            onChange={(n) => onChange(patchRows(rows, row.key, { setup_time: Number(n) || 0 }))}
          />
        ),
    },
    {
      title: t('app.kuaizhizao.workOrder.opColPieceRate'),
      dataIndex: 'piece_rate',
      width: 100,
      render: (v: number, row: WorkOrderOperationFormRow) =>
        disabled ? (
          v ?? '—'
        ) : (
          <InputNumber
            size={DOCUMENT_DETAIL_CONTROL_SIZE}
            style={{ width: '100%' }}
            min={0}
            value={v}
            onChange={(n) => onChange(patchRows(rows, row.key, { piece_rate: Number(n) || 0 }))}
          />
        ),
    },
    {
      title: t('app.kuaizhizao.workOrder.opColWorkRequirement'),
      dataIndex: 'work_requirement',
      width: 180,
      render: (v: string, row: WorkOrderOperationFormRow) =>
        disabled ? (
          v || '—'
        ) : (
          <Input
            size={DOCUMENT_DETAIL_CONTROL_SIZE}
            value={v}
            onChange={(e) => onChange(patchRows(rows, row.key, { work_requirement: e.target.value }))}
          />
        ),
    },
    ...(!disabled
      ? [{
          title: t('common.actions'),
          key: 'operation',
          width: 48,
          align: 'center' as const,
          fixed: 'right' as const,
          onHeaderCell: () => ({ className: 'uni-detail-fixed-op-header' }),
          render: (_: unknown, row: WorkOrderOperationFormRow) => (
            <Button
              type="link"
              danger
              size="small"
              icon={<DeleteOutlined />}
              disabled={row.has_reporting}
              aria-label={t('common.delete')}
              onClick={() => onChange(withSequence(rows.filter((item) => item.key !== row.key)))}
            />
          ),
        }]
      : []),
  ]

  const totalWidth = columns.reduce((sum, col) => sum + (Number(col.width) || 0), 0)

  const table = (
    <Table<WorkOrderOperationFormRow>
      className="uni-detail-table"
      size="small"
      pagination={false}
      rowKey="key"
      dataSource={rows}
      scroll={{ x: Math.max(totalWidth, UNI_TABLE_DETAIL_DRAG_INDEX_COL_WIDTH) }}
      columns={columns}
      components={dragActive ? uniTableDetailSortableComponents : undefined}
    />
  )

  return (
    <div className="uni-table-detail wo-ops-table" style={{ marginBottom: 0 }}>
      <UniTableDetailHeader
        title={hideSectionTitle ? undefined : t('app.kuaizhizao.workOrder.formOperationsSection')}
        required={false}
        leftExtra={headerLeft}
        actions={
          !disabled && onAdd
            ? [{
                key: 'add',
                label: t('app.kuaizhizao.workOrder.modalAddOperation'),
                icon: <PlusOutlined />,
                color: 'primary',
                className: 'uni-detail-action-add',
                onClick: onAdd,
              }]
            : undefined
        }
      />
      <div className="uni-table-detail-body">
        {dragActive ? (
          <UniTableDetailSortableTable
            fields={fields}
            move={(from, to) => onChange(moveRows(rows, from, to))}
          >
            {table}
          </UniTableDetailSortableTable>
        ) : (
          table
        )}
      </div>
    </div>
  )
}

export default WorkOrderOperationsEditTable
