import React, { useMemo, useState } from 'react';

import { useTranslation } from 'react-i18next';

import { Alert, Button, Checkbox, Empty, Input, Row, Col, Select, Skeleton, Spin, Typography, theme } from 'antd';

import { SearchOutlined } from '@ant-design/icons';

import { MarkerTag } from '../../../../../../constants/statusBadges';

import { renderMasterActiveTag } from '../../../../../master-data/utils/masterListPresentation';

import { formatBusinessDateOnly, formatDateTimeBySiteSetting } from '../../../../../../utils/format';



export type EquipmentDispatchSnapshot = {

  equipment_id: number;

  equipment_uuid: string;

  code: string;

  name: string;

  status: string;

  is_active: boolean;

  monitor_status?: string | null;

  monitor_is_online?: boolean | null;

  assigned_operation_count: number;

  assigned_work_order_codes: string[];

  has_in_process_work_order?: boolean;

  open_fault_count: number;

  open_maintenance_plan_count: number;

  spot_check_abnormality_count: number;

  latest_spot_check_date?: string | null;

  latest_spot_check_document_no?: string | null;

  latest_spot_check_has_abnormality?: boolean | null;

  latest_repair_date?: string | null;

  latest_repair_no?: string | null;

  latest_repair_status?: string | null;

};



type EquipmentListRow = {

  id: number;

  uuid?: string;

  code?: string;

  name?: string;

  status?: string;

  is_active?: boolean;

  capable_operation_ids?: number[] | null;

};



const LEDGER_STATUS_OPTIONS = [

  '正常',

  '运行中',

  '待机',

  '故障',

  '维修中',

  '停用',

  '校验中',

  '报废',

] as const;



type OccupancyFilterKey = 'noAssigned' | 'hasAssigned' | 'hasFault' | 'hasMaintenance' | 'hasSpotAbnormal';



export interface EquipmentDispatchCardPickerProps {

  value?: number[];

  onChange?: (equipmentIds: number[]) => void;

  equipmentList: EquipmentListRow[];

  snapshotsById: Record<number, EquipmentDispatchSnapshot>;

  loading?: boolean;

  snapshotsLoading?: boolean;

  canReadSnapshots: boolean;

  onOpenDetail?: (snapshot: EquipmentDispatchSnapshot) => void;

  dispatchOperationPlannedStart?: string | null;

  dispatchOperationPlannedEnd?: string | null;

  dispatchOperationId?: number;

}



function equipmentStatusTagColor(status: string): 'success' | 'processing' | 'error' | 'warning' | 'default' {

  const map: Record<string, 'success' | 'processing' | 'error' | 'warning' | 'default'> = {

    正常: 'success',

    运行中: 'processing',

    待机: 'default',

    故障: 'error',

    维修中: 'warning',

    停用: 'default',

    校验中: 'processing',

    报废: 'error',

  };

  return map[status] ?? 'default';

}



function resolveRowId(row: EquipmentListRow): number {

  return Number(row.id ?? (row as { ID?: number }).ID ?? 0);

}

function resolveCapableOperationIds(row: EquipmentListRow): number[] | null {

  const raw = row.capable_operation_ids;

  if (raw == null) {

    return null;

  }

  if (!Array.isArray(raw)) {

    return null;

  }

  return raw.map((id) => Number(id)).filter((id) => Number.isInteger(id) && id > 0);

}

function equipmentCapableSortRank(row: EquipmentListRow, operationId: number): number {

  if (!Number.isInteger(operationId) || operationId <= 0) {

    return 0;

  }

  const ids = resolveCapableOperationIds(row);

  if (ids === null || ids.length === 0) {

    return 1;

  }

  if (ids.includes(operationId)) {

    return 0;

  }

  return 2;

}

function compareEquipmentByOperationCapability(

  a: EquipmentListRow,

  b: EquipmentListRow,

  operationId: number,

): number {

  const rankDiff = equipmentCapableSortRank(a, operationId) - equipmentCapableSortRank(b, operationId);

  if (rankDiff !== 0) {

    return rankDiff;

  }

  const codeA = String(a.code ?? '').toLowerCase();

  const codeB = String(b.code ?? '').toLowerCase();

  return codeA.localeCompare(codeB, 'zh-CN');

}

function equipmentMatchesDispatchOperation(row: EquipmentListRow, operationId: number): boolean {

  if (!Number.isInteger(operationId) || operationId <= 0) {

    return false;

  }

  const ids = resolveCapableOperationIds(row);

  return ids !== null && ids.length > 0 && ids.includes(operationId);

}



function formatDispatchOperationPeriod(start?: string | null, end?: string | null): string | null {

  const startText = start ? formatDateTimeBySiteSetting(start) : '';

  const endText = end ? formatDateTimeBySiteSetting(end) : '';

  if (startText && endText) {

    return `${startText} 至 ${endText}`;

  }

  if (startText) {

    return startText;

  }

  if (endText) {

    return endText;

  }

  return null;

}



const EquipmentDispatchCardPicker: React.FC<EquipmentDispatchCardPickerProps> = ({

  value,

  onChange,

  equipmentList,

  snapshotsById,

  loading = false,

  snapshotsLoading = false,

  canReadSnapshots,

  onOpenDetail,

  dispatchOperationPlannedStart,

  dispatchOperationPlannedEnd,

  dispatchOperationId,

}) => {

  const { t } = useTranslation();
  const { token } = theme.useToken();

  const [keyword, setKeyword] = useState('');

  const [statusFilter, setStatusFilter] = useState<string[]>([]);

  const [activeFilter, setActiveFilter] = useState<'all' | 'active' | 'inactive'>('all');

  const [occupancyFilters, setOccupancyFilters] = useState<OccupancyFilterKey[]>([]);



  const dispatchPeriodText = useMemo(

    () => formatDispatchOperationPeriod(dispatchOperationPlannedStart, dispatchOperationPlannedEnd),

    [dispatchOperationPlannedEnd, dispatchOperationPlannedStart],

  );



  const selectedIds = useMemo(() => {

    const raw = value ?? [];

    return raw.filter((id) => Number.isInteger(id) && id > 0);

  }, [value]);



  const statusOptions = useMemo(() => {

    const fromList = new Set<string>();

    for (const row of equipmentList) {

      const st = String(row.status ?? snapshotsById[resolveRowId(row)]?.status ?? '').trim();

      if (st) {

        fromList.add(st);

      }

    }

    const ordered = LEDGER_STATUS_OPTIONS.filter((s) => fromList.has(s));

    for (const st of fromList) {

      if (!ordered.includes(st as (typeof LEDGER_STATUS_OPTIONS)[number])) {

        ordered.push(st);

      }

    }

    return ordered.map((s) => ({ label: s, value: s }));

  }, [equipmentList, snapshotsById]);



  const filtered = useMemo(() => {

    const q = keyword.trim().toLowerCase();

    const rows = equipmentList.filter((row) => {

      const id = resolveRowId(row);

      if (!Number.isInteger(id) || id <= 0) {

        return false;

      }

      const snap = snapshotsById[id];

      const code = String(row.code ?? snap?.code ?? '').toLowerCase();

      const name = String(row.name ?? snap?.name ?? '').toLowerCase();

      if (q && !code.includes(q) && !name.includes(q)) {

        return false;

      }

      const ledgerStatus = String(snap?.status ?? row.status ?? '').trim();

      if (statusFilter.length > 0 && !statusFilter.includes(ledgerStatus)) {

        return false;

      }

      const isActive = snap?.is_active ?? row.is_active;

      if (activeFilter === 'active' && isActive !== true) {

        return false;

      }

      if (activeFilter === 'inactive' && isActive !== false) {

        return false;

      }

      if (canReadSnapshots && occupancyFilters.length > 0 && snap) {

        const inProcess =

          snap.has_in_process_work_order === true ||

          (snap.has_in_process_work_order == null && snap.assigned_operation_count > 0);

        const spotAbnormal =

          snap.latest_spot_check_has_abnormality === true || snap.spot_check_abnormality_count > 0;

        const match = occupancyFilters.some((key) => {

          if (key === 'noAssigned') {

            return !inProcess;

          }

          if (key === 'hasAssigned') {

            return inProcess;

          }

          if (key === 'hasFault') {

            return snap.open_fault_count > 0;

          }

          if (key === 'hasMaintenance') {

            return snap.open_maintenance_plan_count > 0;

          }

          if (key === 'hasSpotAbnormal') {

            return spotAbnormal;

          }

          return false;

        });

        if (!match) {

          return false;

        }

      }

      return true;

    });

    const operationId = Number(dispatchOperationId ?? 0);

    if (!Number.isInteger(operationId) || operationId <= 0) {

      return rows;

    }

    return [...rows].sort((a, b) => compareEquipmentByOperationCapability(a, b, operationId));

  }, [

    activeFilter,

    canReadSnapshots,

    dispatchOperationId,

    equipmentList,

    keyword,

    occupancyFilters,

    snapshotsById,

    statusFilter,

  ]);



  const toggleSelect = (id: number) => {

    const next = selectedIds.includes(id) ? selectedIds.filter((x) => x !== id) : [...selectedIds, id];

    onChange?.(next);

  };



  if (loading) {

    return (

      <div style={{ padding: 24, textAlign: 'center' }}>

        <Spin />

      </div>

    );

  }



  if (!equipmentList.length) {

    return <Empty description={t('app.kuaizhizao.workOrder.equipmentDispatchPreview.noCapableEquipment')} />;

  }



  return (

    <div style={{ width: '100%' }}>

      <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>

        {t('app.kuaizhizao.workOrder.equipmentDispatchPreview.dispatchOperationPeriodHeader')}{' '}

        {dispatchPeriodText ?? t('app.kuaizhizao.workOrder.equipmentDispatchPreview.cardNoPlannedPeriod')}

      </Typography.Paragraph>

      {!canReadSnapshots ? (

        <Alert

          type="info"

          showIcon

          style={{ marginBottom: 12 }}

          title={t('app.kuaizhizao.workOrder.equipmentDispatchPreview.snapshotReadonlyBasic')}

        />

      ) : null}

      <Row gutter={[8, 8]} wrap={false} style={{ marginBottom: 12 }}>

        <Col flex="1 1 0" style={{ minWidth: 140 }}>

          <Input

            allowClear

            prefix={<SearchOutlined />}

            placeholder={t('app.kuaizhizao.workOrder.equipmentDispatchPreview.cardSearchPlaceholder')}

            value={keyword}

            onChange={(e) => setKeyword(e.target.value)}

          />

        </Col>

        <Col flex="1 1 0" style={{ minWidth: 120 }}>

          <Select

            mode="multiple"

            allowClear

            style={{ width: '100%' }}

            placeholder={t('app.kuaizhizao.workOrder.equipmentDispatchPreview.filterStatus')}

            value={statusFilter}

            onChange={setStatusFilter}

            options={statusOptions}

            maxTagCount="responsive"

          />

        </Col>

        {canReadSnapshots ? (

          <Col flex="1 1 0" style={{ minWidth: 120 }}>

            <Select

              mode="multiple"

              allowClear

              style={{ width: '100%' }}

              placeholder={t('app.kuaizhizao.workOrder.equipmentDispatchPreview.filterOccupancy')}

              value={occupancyFilters}

              onChange={(vals) => setOccupancyFilters(vals as OccupancyFilterKey[])}

              options={[

                {

                  label: t('app.kuaizhizao.workOrder.equipmentDispatchPreview.filterNoAssigned'),

                  value: 'noAssigned',

                },

                {

                  label: t('app.kuaizhizao.workOrder.equipmentDispatchPreview.filterHasAssigned'),

                  value: 'hasAssigned',

                },

                {

                  label: t('app.kuaizhizao.workOrder.equipmentDispatchPreview.filterHasFault'),

                  value: 'hasFault',

                },

                {

                  label: t('app.kuaizhizao.workOrder.equipmentDispatchPreview.filterHasMaintenance'),

                  value: 'hasMaintenance',

                },

                {

                  label: t('app.kuaizhizao.workOrder.equipmentDispatchPreview.filterHasSpotAbnormal'),

                  value: 'hasSpotAbnormal',

                },

              ]}

              maxTagCount="responsive"

            />

          </Col>

        ) : null}

        <Col flex="1 1 0" style={{ minWidth: 120 }}>

          <Select

            style={{ width: '100%' }}

            value={activeFilter}

            onChange={setActiveFilter}

            options={[

              { label: t('app.kuaizhizao.workOrder.equipmentDispatchPreview.filterActiveAll'), value: 'all' },

              { label: t('common.enabled'), value: 'active' },

              { label: t('common.disabled'), value: 'inactive' },

            ]}

          />

        </Col>

      </Row>

      {selectedIds.length > 0 ? (

        <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>

          {t('app.kuaizhizao.workOrder.equipmentDispatchPreview.selectedCount', { count: selectedIds.length })}

        </Typography.Text>

      ) : null}

      <Spin spinning={snapshotsLoading}>

        <div

          style={{

            display: 'grid',

            gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',

            gap: 12,

            maxHeight: 420,

            overflowY: 'auto',

            padding: 2,

          }}

        >

          {filtered.map((row) => {

            const id = resolveRowId(row);

            const selected = selectedIds.includes(id);

            const snap = snapshotsById[id];

            const ledgerStatus = snap?.status ?? row.status ?? '-';

            const isActive = snap?.is_active ?? row.is_active;

            const inProcess =

              snap &&

              (snap.has_in_process_work_order === true ||

                (snap.has_in_process_work_order == null && snap.assigned_operation_count > 0));

            const operationId = Number(dispatchOperationId ?? 0);

            const capableForOperation = equipmentMatchesDispatchOperation(row, operationId);

            return (

              <div

                key={id}

                role="checkbox"

                aria-checked={selected}

                tabIndex={0}

                onClick={() => toggleSelect(id)}

                onKeyDown={(e) => {

                  if (e.key === 'Enter' || e.key === ' ') {

                    e.preventDefault();

                    toggleSelect(id);

                  }

                }}

                style={{

                  border: selected ? '2px solid var(--ant-color-primary)' : '1px solid rgba(0, 0, 0, 0.08)',

                  borderRadius: token.borderRadiusLG,

                  padding: '10px 12px',

                  cursor: 'pointer',

                  background: selected ? 'var(--ant-color-primary-bg)' : '#fafafa',

                }}

              >

                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>

                  <Checkbox checked={selected} tabIndex={-1} style={{ marginTop: 2 }} />

                  <div style={{ flex: 1, minWidth: 0 }}>

                    <Typography.Text strong ellipsis style={{ display: 'block' }}>

                      {row.code} {row.name}

                    </Typography.Text>

                    <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>

                      {(() => {

                        const operationalStatus = String(snap?.status ?? row.status ?? '').trim();

                        if (!operationalStatus || operationalStatus === '-') {

                          return null;

                        }

                        const statusColor = equipmentStatusTagColor(operationalStatus);

                        return (

                          <MarkerTag color={statusColor === 'default' ? undefined : statusColor}>

                            {operationalStatus}

                          </MarkerTag>

                        );

                      })()}

                      {renderMasterActiveTag(t, isActive, 'common.enabled', 'common.disabled')}

                      {capableForOperation ? (

                        <MarkerTag color="blue">

                          {t('app.kuaizhizao.workOrder.equipmentDispatchPreview.cardCapableOperationMatch')}

                        </MarkerTag>

                      ) : null}

                    </div>

                    {canReadSnapshots ? (

                      <div style={{ marginTop: 10, fontSize: 12, color: 'rgba(0,0,0,0.65)', lineHeight: 1.6 }}>

                        {snapshotsLoading && !snap ? (

                          <Skeleton active paragraph={{ rows: 2, width: '100%' }} title={false} />

                        ) : snap ? (

                          <>

                            <div>

                              {t('app.kuaizhizao.workOrder.equipmentDispatchPreview.cardLatestSpotCheck')}{' '}

                              {snap.latest_spot_check_date

                                ? t('app.kuaizhizao.workOrder.equipmentDispatchPreview.cardLatestSpotCheckValue', {

                                    date: formatBusinessDateOnly(snap.latest_spot_check_date),

                                    result:

                                      snap.latest_spot_check_has_abnormality === true

                                        ? t(

                                            'app.kuaizhizao.workOrder.equipmentDispatchPreview.cardSpotCheckResultAbnormal',

                                          )

                                        : t(

                                            'app.kuaizhizao.workOrder.equipmentDispatchPreview.cardSpotCheckResultNormal',

                                          ),

                                  })

                                : t('app.kuaizhizao.workOrder.equipmentDispatchPreview.cardNoRecord')}

                            </div>

                            <div>

                              {t('app.kuaizhizao.workOrder.equipmentDispatchPreview.cardLatestRepair')}{' '}

                              {snap.latest_repair_date

                                ? t('app.kuaizhizao.workOrder.equipmentDispatchPreview.cardLatestRepairValue', {

                                    date: formatDateTimeBySiteSetting(snap.latest_repair_date),

                                    status: snap.latest_repair_status ?? '',

                                  })

                                : t('app.kuaizhizao.workOrder.equipmentDispatchPreview.cardNoRecord')}

                            </div>

                            <div>

                              {t('app.kuaizhizao.workOrder.equipmentDispatchPreview.cardInProcessWorkOrder')}{' '}

                              {inProcess

                                ? t('app.kuaizhizao.workOrder.equipmentDispatchPreview.cardInProcessYes', {

                                    codes:

                                      snap.assigned_work_order_codes.length > 0

                                        ? snap.assigned_work_order_codes.join(' ')

                                        : '',

                                  })

                                : t('app.kuaizhizao.workOrder.equipmentDispatchPreview.cardInProcessNo')}

                            </div>

                          </>

                        ) : (

                          <div>{t('app.kuaizhizao.workOrder.equipmentDispatchPreview.cardSnapshotUnavailable')}</div>

                        )}

                      </div>

                    ) : null}

                    {canReadSnapshots && snap && onOpenDetail ? (

                      <Button

                        type="link"

                        size="small"

                        style={{ padding: 0, marginTop: 6, height: 'auto' }}

                        onClick={(e) => {

                          e.stopPropagation();

                          onOpenDetail(snap);

                        }}

                      >

                        {t('app.kuaizhizao.workOrder.equipmentDispatchPreview.openDetail')}

                      </Button>

                    ) : null}

                  </div>

                </div>

              </div>

            );

          })}

        </div>

        {!filtered.length ? (

          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common.noData')} style={{ marginTop: 16 }} />

        ) : null}

      </Spin>

    </div>

  );

};



export default EquipmentDispatchCardPicker;

