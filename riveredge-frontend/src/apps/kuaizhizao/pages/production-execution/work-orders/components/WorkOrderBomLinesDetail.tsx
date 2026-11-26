import React, { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { App, Button, Input, InputNumber, Select, Table } from 'antd'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import { DOCUMENT_DETAIL_CONTROL_SIZE } from '../../../../components/document-detail-table/documentDetailTable'
import { UniTableDetailHeader } from '../../../../../../components/uni-table-detail/UniTableDetail'
import {
  DocumentLineTotalStockCell,
  DocumentLineTotalStockProvider,
} from '../../../../components/DocumentLineTotalStock'
import { KUAIZHIZAO_DOC_HOST } from '../../../../../../utils/documentFormReferenceLoad'
import {
  ReferenceDisplayAccessError,
  searchReferenceDisplay,
} from '../../../../../../utils/referenceDisplay'

export type WorkOrderBomLineRow = {
  key: string
  material_id?: number
  material_code?: string
  material_name?: string
  material_spec?: string
  warehouse_id?: number
  warehouse_name?: string
  unit?: string
  required_quantity?: number
  issued_quantity?: number
  current_stock?: number
  batch_no?: string
  bom_version?: string
  line_remarks?: string
}

export type WorkOrderWarehouseSelectOption = {
  value: number
  label: string
}

export interface WorkOrderBomLinesDetailProps {
  rows: WorkOrderBomLineRow[]
  onChange: (rows: WorkOrderBomLineRow[]) => void
  readOnly?: boolean
  /** 外层已用页签标出分组时不再重复标题 */
  hideSectionTitle?: boolean
  /** 无 BOM 时手工加行 */
  onAdd?: () => void
  /** 宿主 {app}:{module}，供引用展示鉴权；默认工单宿主 */
  hostResource?: string
}

export const mapApiBomLineToFormRow = (line: Record<string, unknown>, idx: number): WorkOrderBomLineRow => ({
  key: `bom-${line.material_id ?? idx}`,
  material_id: Number(line.material_id),
  material_code: String(line.material_code ?? ''),
  material_name: String(line.material_name ?? ''),
  material_spec: line.material_spec != null ? String(line.material_spec) : undefined,
  warehouse_id: line.warehouse_id != null ? Number(line.warehouse_id) : undefined,
  warehouse_name: line.warehouse_name != null ? String(line.warehouse_name) : undefined,
  unit: line.unit != null ? String(line.unit) : undefined,
  required_quantity: Number(line.required_quantity ?? 0),
  issued_quantity: line.issued_quantity != null ? Number(line.issued_quantity) : undefined,
  current_stock: line.current_stock != null ? Number(line.current_stock) : undefined,
  batch_no: line.batch_no != null ? String(line.batch_no) : undefined,
  bom_version: line.bom_version != null ? String(line.bom_version) : undefined,
  line_remarks: line.line_remarks != null ? String(line.line_remarks) : undefined,
})

export const bomFormRowsToPreviewPayload = (rows: WorkOrderBomLineRow[]) =>
  rows
    .filter((line) => line.material_id != null && Number(line.material_id) > 0)
    .map((line, idx) => ({
      material_id: Number(line.material_id),
      material_code: line.material_code,
      material_name: line.material_name,
      material_spec: line.material_spec,
      warehouse_id: line.warehouse_id,
      warehouse_name: line.warehouse_name,
      unit: line.unit,
      required_quantity: line.required_quantity ?? 0,
      batch_no: line.batch_no,
      bom_version: line.bom_version,
      line_remarks: line.line_remarks,
      sequence: idx + 1,
    }))

const patchRows = (
  rows: WorkOrderBomLineRow[],
  key: string,
  patch: Partial<WorkOrderBomLineRow>,
): WorkOrderBomLineRow[] => rows.map((r) => (r.key === key ? { ...r, ...patch } : r))

const warehouseOptionsForRow = (
  options: WorkOrderWarehouseSelectOption[],
  row: WorkOrderBomLineRow,
): WorkOrderWarehouseSelectOption[] => {
  const id = Number(row.warehouse_id)
  if (!Number.isInteger(id) || id <= 0) return options
  if (options.some((item) => item.value === id)) return options
  const storedName = String(row.warehouse_name ?? '').trim()
  return [{ value: id, label: storedName || String(id) }, ...options]
}

export const WorkOrderBomLinesDetail: React.FC<WorkOrderBomLinesDetailProps> = ({
  rows,
  onChange,
  readOnly = false,
  hideSectionTitle = false,
  onAdd,
  hostResource = KUAIZHIZAO_DOC_HOST.workOrder,
}) => {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [warehouseOptions, setWarehouseOptions] = useState<WorkOrderWarehouseSelectOption[]>([])
  const [warehouseLoading, setWarehouseLoading] = useState(false)

  const stockMaterialIds = useMemo(
    () =>
      rows
        .map((row) => Number(row.material_id))
        .filter((id) => Number.isFinite(id) && id > 0),
    [rows],
  )

  useEffect(() => {
    if (readOnly) return
    let cancelled = false
    const load = async () => {
      setWarehouseLoading(true)
      try {
        const response = await searchReferenceDisplay({
          resource: 'master-data:warehouse:warehouse',
          hostResource,
          isActive: true,
          pageSize: 200,
        })
        if (cancelled) return
        setWarehouseOptions(
          (response.items || []).map((item) => {
            const id = Number(item.id)
            const label = `${item.code ?? ''} ${item.name ?? ''}`.trim() || String(id)
            return { value: id, label }
          }).filter((item) => Number.isInteger(item.value) && item.value > 0),
        )
      } catch (error) {
        if (cancelled) return
        console.error(error)
        if (error instanceof ReferenceDisplayAccessError) {
          message.error(error.message)
        } else {
          message.error(t('app.kuaizhizao.workOrder.bomLineWarehouseLoadFailed'))
        }
        setWarehouseOptions([])
      } finally {
        if (!cancelled) setWarehouseLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [hostResource, message, readOnly, t])

  return (
    <div className="uni-table-detail" style={{ marginBottom: 0 }}>
      {hideSectionTitle && !onAdd ? null : (
        <UniTableDetailHeader
          title={hideSectionTitle ? undefined : t('app.kuaizhizao.workOrder.formBomLinesSection')}
          required={false}
          actions={
            !readOnly && onAdd
              ? [{
                  key: 'add',
                  label: t('app.kuaizhizao.workOrder.modalAddBomLine'),
                  icon: <PlusOutlined />,
                  color: 'primary',
                  className: 'uni-detail-action-add',
                  onClick: onAdd,
                }]
              : undefined
          }
        />
      )}
      <DocumentLineTotalStockProvider materialIds={stockMaterialIds}>
        <div className="uni-table-detail-body">
          <Table<WorkOrderBomLineRow>
            className="uni-detail-table"
            size="small"
            pagination={false}
            rowKey="key"
            dataSource={rows}
            scroll={{ x: 1280 }}
            columns={[
              { title: t('app.kuaizhizao.workOrder.bomLineMaterialCode'), dataIndex: 'material_code', width: 120 },
              { title: t('app.kuaizhizao.workOrder.bomLineMaterialName'), dataIndex: 'material_name', width: 140 },
              {
                title: t('app.kuaizhizao.workOrder.bomLineSpec'),
                dataIndex: 'material_spec',
                width: 120,
                render: (v) => v || '—',
              },
              {
                title: t('app.kuaizhizao.workOrder.bomLineWarehouse'),
                dataIndex: 'warehouse_id',
                width: 160,
                render: (_v, row) => {
                  const selectedId = Number(row.warehouse_id)
                  const value = Number.isInteger(selectedId) && selectedId > 0 ? selectedId : undefined
                  if (readOnly) {
                    return row.warehouse_name || (value != null ? String(value) : '—')
                  }
                  return (
                    <Select
                      size={DOCUMENT_DETAIL_CONTROL_SIZE}
                      style={{ width: '100%' }}
                      allowClear
                      showSearch
                      optionFilterProp="label"
                      loading={warehouseLoading}
                      placeholder={t('app.kuaizhizao.workOrder.bomLineWarehousePlaceholder')}
                      options={warehouseOptionsForRow(warehouseOptions, row)}
                      value={value}
                      onChange={(nextId: number | null | undefined) => {
                        const id = Number(nextId)
                        if (!Number.isInteger(id) || id <= 0) {
                          onChange(patchRows(rows, row.key, {
                            warehouse_id: undefined,
                            warehouse_name: undefined,
                          }))
                          return
                        }
                        const label =
                          warehouseOptions.find((item) => item.value === id)?.label ||
                          String(row.warehouse_name ?? '').trim() ||
                          String(id)
                        onChange(patchRows(rows, row.key, {
                          warehouse_id: id,
                          warehouse_name: label,
                        }))
                      }}
                    />
                  )
                },
              },
              { title: t('common.unit'), dataIndex: 'unit', width: 72 },
              {
                title: t('app.kuaizhizao.workOrder.bomLineRequiredQty'),
                dataIndex: 'required_quantity',
                width: 110,
                render: (v, row) =>
                  readOnly ? (
                    v
                  ) : (
                    <InputNumber
                      size={DOCUMENT_DETAIL_CONTROL_SIZE}
                      style={{ width: '100%' }}
                      min={0}
                      value={v as number}
                      onChange={(n) => onChange(patchRows(rows, row.key, { required_quantity: Number(n) || 0 }))}
                    />
                  ),
              },
              {
                title: t('app.kuaizhizao.workOrder.bomLineIssuedQty'),
                dataIndex: 'issued_quantity',
                width: 96,
                render: (v) => v ?? 0,
              },
              {
                title: t('app.kuaizhizao.workOrder.bomLineCurrentStock'),
                dataIndex: 'current_stock',
                width: 112,
                align: 'right',
                render: (_v, row) => <DocumentLineTotalStockCell materialId={row.material_id} />,
              },
              {
                title: t('app.kuaizhizao.workOrder.bomLineBatchNo'),
                dataIndex: 'batch_no',
                width: 120,
                render: (v, row) =>
                  readOnly ? (
                    v || '—'
                  ) : (
                    <Input
                      size={DOCUMENT_DETAIL_CONTROL_SIZE}
                      value={v}
                      onChange={(e) => onChange(patchRows(rows, row.key, { batch_no: e.target.value }))}
                    />
                  ),
              },
              {
                title: t('app.kuaizhizao.workOrder.bomLineBomVersion'),
                dataIndex: 'bom_version',
                width: 100,
                render: (v, row) =>
                  readOnly ? (
                    v || '—'
                  ) : (
                    <Input
                      size={DOCUMENT_DETAIL_CONTROL_SIZE}
                      value={v}
                      onChange={(e) => onChange(patchRows(rows, row.key, { bom_version: e.target.value }))}
                    />
                  ),
              },
              {
                title: t('app.kuaizhizao.workOrder.bomLineRemarks'),
                dataIndex: 'line_remarks',
                width: 160,
                render: (v, row) =>
                  readOnly ? (
                    v || '—'
                  ) : (
                    <Input
                      size={DOCUMENT_DETAIL_CONTROL_SIZE}
                      value={v}
                      onChange={(e) => onChange(patchRows(rows, row.key, { line_remarks: e.target.value }))}
                    />
                  ),
              },
              ...(!readOnly
                ? [{
                    title: t('common.actions'),
                    key: 'operation',
                    width: 48,
                    align: 'center' as const,
                    fixed: 'right' as const,
                    onHeaderCell: () => ({ className: 'uni-detail-fixed-op-header' }),
                    render: (_: unknown, row: WorkOrderBomLineRow) => (
                      <Button
                        type="link"
                        danger
                        size="small"
                        icon={<DeleteOutlined />}
                        disabled={Number(row.issued_quantity ?? 0) > 0}
                        aria-label={t('common.delete')}
                        onClick={() => onChange(rows.filter((item) => item.key !== row.key))}
                      />
                    ),
                  }]
                : []),
            ]}
          />
        </div>
      </DocumentLineTotalStockProvider>
    </div>
  )
}

export default WorkOrderBomLinesDetail
