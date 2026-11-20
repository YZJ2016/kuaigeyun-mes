import React, { useMemo, useRef, useState, useCallback } from 'react';
import { App, Typography, Alert } from 'antd';
import { ProFormDateTimePicker, ProFormSelect } from '@ant-design/pro-components';
import type { ProFormInstance } from '@ant-design/pro-components';
import dayjs, { type Dayjs } from 'dayjs';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { FormModalTemplate } from '../../../../../../components/layout-templates';
import { MODAL_CONFIG } from '../../../../../../components/layout-templates/constants';
import type { WorkOrderForGantt, WorkstationResource } from '../../../../components/GanttSchedulingChart/types';
import { visualSchedulingApi } from '../../../../services/production';
import type {
  OperationNeedingStation,
  WorkOrderSchedulingMissingField,
} from '../schedulingDropUtils';
import {
  cascadeOperationPrepScheduleFromIndex,
  durationHoursFromTakt,
  operationPrepEndFieldName,
  operationPrepScheduleDatesToFormValues,
  operationPrepStartFieldName,
  resolveOperationPrepScheduleDates,
} from '../schedulingDropUtils';
import '../scheduling-prep-modal.less';
import { buildFutureDateShortcutFieldProps } from '../../../../../../utils/futureDatePickerShortcuts';

export interface SchedulingWorkOrderPrepValues {
  planned_start_date?: string;
  planned_end_date?: string;
  operationStations: Array<{ operation_id: number; assigned_station_id: number }>;
  operationDates: Array<{ operation_id: number; planned_start_date: string; planned_end_date: string }>;
  operationAssignments: Array<{
    operation_id: number;
    assigned_worker_id?: number | null;
    assigned_equipment_id?: number | null;
    assigned_mold_id?: number | null;
  }>;
}

interface SchedulingResourceOption {
  id: number;
  name: string;
  code?: string;
}

interface SchedulingWorkOrderPrepModalProps {
  open: boolean;
  workOrder: WorkOrderForGantt | null;
  missingFields: WorkOrderSchedulingMissingField[];
  operationsNeedingStation: OperationNeedingStation[];
  workstations: WorkstationResource[];
  workCenters: SchedulingWorkCenterOption[];
  workers?: SchedulingResourceOption[];
  equipments?: SchedulingResourceOption[];
  molds?: SchedulingResourceOption[];
  /** 产线模式：泳道资源为产线；工位模式下为工位（仅 production_line 改行业包路径） */
  resourceMode?: 'workstation' | 'production_line';
  /** 产线模式：缺少节拍/日产能配置的产线 ID */
  linesMissingTakt?: number[];
  /** 产线模式：已配节拍 ∩ 绑定含本工单自制件的产线 ID */
  eligibleProductionLineIds?: number[];
  /** 产线模式：节拍秒，用于自动推算工序时长 */
  taktSecondsByLineId?: Map<number, number>;
  lineCapacityPath?: string;
  loading?: boolean;
  onCancel: () => void;
  onSubmit: (values: SchedulingWorkOrderPrepValues) => Promise<void>;
}

function defaultStart(): Dayjs {
  return dayjs().startOf('hour').add(1, 'hour');
}

function stationOptionsForOperation(
  op: OperationNeedingStation,
  workstations: WorkstationResource[],
  workCenters: SchedulingWorkCenterOption[]
) {
  const wcId = op.workCenterId != null && Number(op.workCenterId) > 0 ? Number(op.workCenterId) : null;
  let candidates = workstations;
  if (wcId != null) {
    const wc = workCenters.find((item) => item.id === wcId);
    const allowedIds = new Set((wc?.workstationIds ?? []).filter((id) => id > 0));
    if (allowedIds.size > 0) {
      candidates = workstations.filter((station) => allowedIds.has(station.id));
    }
  }
  return candidates.map((station) => ({
    value: station.id,
    label: station.code ? `${station.code} ${station.name}` : station.name,
  }));
}

function operationFieldName(operationId: number): string {
  return `station_${operationId}`;
}

function workerFieldName(operationId: number): string {
  return `worker_${operationId}`;
}

function equipmentFieldName(operationId: number): string {
  return `equipment_${operationId}`;
}

function moldFieldName(operationId: number): string {
  return `mold_${operationId}`;
}

interface SchedulingWorkCenterOption {
  id: number;
  name: string;
  code?: string;
  workstationIds?: number[];
}

const SchedulingWorkOrderPrepModal: React.FC<SchedulingWorkOrderPrepModalProps> = ({
  open,
  workOrder,
  missingFields,
  operationsNeedingStation,
  workstations,
  workCenters,
  workers = [],
  equipments = [],
  molds = [],
  resourceMode = 'workstation',
  linesMissingTakt = [],
  eligibleProductionLineIds,
  taktSecondsByLineId,
  lineCapacityPath = '/apps/ind-relay/line-capacity',
  loading = false,
  onCancel,
  onSubmit,
}) => {
  const isProductionLineMode = resourceMode === 'production_line';
  const eligibleLineIdSet = useMemo(() => {
    if (!isProductionLineMode) return null;
    // 未传入时仍按节拍缺口过滤，避免误显无节拍产线
    if (eligibleProductionLineIds != null) {
      return new Set(eligibleProductionLineIds.filter((id) => id > 0));
    }
    return new Set(
      workstations.map((line) => line.id).filter((id) => id > 0 && !linesMissingTakt.includes(id))
    );
  }, [
    eligibleProductionLineIds,
    isProductionLineMode,
    linesMissingTakt,
    workstations,
  ]);
  const workOrderQty = Number(workOrder?.quantity ?? 0);
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const formRef = useRef<ProFormInstance>();
  const cascadingRef = useRef(false);
  const [rateWarnings, setRateWarnings] = useState<string[]>([]);
  const sortedOperations = useMemo(
    () => [...operationsNeedingStation].sort((a, b) => a.sequence - b.sequence),
    [operationsNeedingStation]
  );

  const workerOptions = useMemo(
    () =>
      workers.map((item) => ({
        value: item.id,
        label: item.code ? `${item.code} ${item.name}` : item.name,
      })),
    [workers]
  );
  const equipmentOptions = useMemo(
    () =>
      equipments.map((item) => ({
        value: item.id,
        label: item.code ? `${item.code} ${item.name}` : item.name,
      })),
    [equipments]
  );
  const moldOptions = useMemo(
    () =>
      molds.map((item) => ({
        value: item.id,
        label: item.code ? `${item.code} ${item.name}` : item.name,
      })),
    [molds]
  );

  const checkRateCoverage = useCallback(
    async (operationId: number, workerId: number) => {
      if (!workOrder || workerId <= 0) {
        setRateWarnings([]);
        return;
      }
      try {
        const res = await visualSchedulingApi.rateCoverage([
          {
            worker_id: workerId,
            operation_id: operationId,
            material_id: workOrder.product_id ?? null,
          },
        ]);
        const item = res.items?.[0];
        if (!item?.missing?.length) {
          setRateWarnings([]);
          return;
        }
        const labels = item.missing.map((key) =>
          key === 'piece_rate'
            ? t('app.kuaizhizao.scheduling.prep.missingPieceRate')
            : t('app.kuaizhizao.scheduling.prep.missingHourlyRate')
        );
        setRateWarnings(labels);
      } catch (e: unknown) {
        setRateWarnings([]);
        const detail =
          e && typeof e === 'object' && 'message' in e
            ? String((e as { message?: unknown }).message || '')
            : '';
        messageApi.warning(
          detail || t('app.kuaizhizao.scheduling.prep.rateCoverageLoadFailed')
        );
      }
    },
    [messageApi, t, workOrder]
  );

  const initialValues = useMemo(() => {
    if (!workOrder) return undefined;
    const start = workOrder.planned_start_date ? dayjs(workOrder.planned_start_date) : defaultStart();
    const end = workOrder.planned_end_date
      ? dayjs(workOrder.planned_end_date)
      : start.add(7, 'day');
    const stationValues = Object.fromEntries(
      operationsNeedingStation.map((op) => {
        const resourceId =
          resourceMode === 'production_line'
            ? op.assignedProductionLineId
            : op.assignedStationId;
        return [
          operationFieldName(op.operationId),
          resourceId && resourceId > 0 ? resourceId : undefined,
        ];
      })
    );
    const workerValues = Object.fromEntries(
      operationsNeedingStation.map((op) => [
        workerFieldName(op.operationId),
        op.assignedWorkerId && op.assignedWorkerId > 0 ? op.assignedWorkerId : undefined,
      ])
    );
    const equipmentValues = Object.fromEntries(
      operationsNeedingStation.map((op) => [
        equipmentFieldName(op.operationId),
        op.assignedEquipmentId && op.assignedEquipmentId > 0 ? op.assignedEquipmentId : undefined,
      ])
    );
    const moldValues = Object.fromEntries(
      operationsNeedingStation.map((op) => [
        moldFieldName(op.operationId),
        op.assignedMoldId && op.assignedMoldId > 0 ? op.assignedMoldId : undefined,
      ])
    );
    const durationHoursByOperationId = new Map<number, number>();
    if (isProductionLineMode) {
      for (const op of operationsNeedingStation) {
        const lineId = op.assignedProductionLineId;
        if (lineId == null || lineId <= 0) continue;
        const hours = durationHoursFromTakt(workOrderQty, taktSecondsByLineId?.get(lineId) ?? 0);
        if (hours != null) durationHoursByOperationId.set(op.operationId, hours);
      }
    }
    const rawDateValues = Object.fromEntries(
      operationsNeedingStation.flatMap((op) => {
        const entries: Array<[string, Dayjs]> = [];
        if (op.plannedStartDate) {
          entries.push([operationPrepStartFieldName(op.operationId), dayjs(op.plannedStartDate)]);
        }
        if (op.plannedEndDate) {
          entries.push([operationPrepEndFieldName(op.operationId), dayjs(op.plannedEndDate)]);
        }
        return entries;
      })
    );
    const normalizedDates = operationPrepScheduleDatesToFormValues(
      resolveOperationPrepScheduleDates(operationsNeedingStation, rawDateValues, {
        workOrderStart: workOrder.planned_start_date,
        durationHoursByOperationId:
          durationHoursByOperationId.size > 0 ? durationHoursByOperationId : undefined,
        sharedWindow: isProductionLineMode,
      })
    );
    return {
      planned_start_date: start,
      planned_end_date: end,
      ...stationValues,
      ...workerValues,
      ...equipmentValues,
      ...moldValues,
      ...normalizedDates,
    };
  }, [
    isProductionLineMode,
    operationsNeedingStation,
    resourceMode,
    taktSecondsByLineId,
    workOrder,
    workOrderQty,
  ]);

  const buildTaktDurationByOperationId = useCallback(
    (allValues: Record<string, unknown>) => {
      const map = new Map<number, number>();
      if (!isProductionLineMode) return map;
      for (const op of sortedOperations) {
        const lineId = Number(allValues[operationFieldName(op.operationId)]);
        if (!(lineId > 0)) continue;
        const hours = durationHoursFromTakt(workOrderQty, taktSecondsByLineId?.get(lineId) ?? 0);
        if (hours != null) map.set(op.operationId, hours);
      }
      return map;
    },
    [isProductionLineMode, sortedOperations, taktSecondsByLineId, workOrderQty]
  );

  const handleAssignmentValuesChange = (changedValues: Record<string, unknown>) => {
    const changedKey = Object.keys(changedValues)[0];
    if (!changedKey?.startsWith('worker_') || !workOrder) return;
    const opId = Number(changedKey.replace(/^worker_/, ''));
    const workerId = Number(changedValues[changedKey]);
    if (Number.isInteger(opId) && Number.isInteger(workerId)) {
      void checkRateCoverage(opId, workerId);
    }
  };

  const handleFormValuesChange = (
    changedValues: Record<string, unknown>,
    allValues: Record<string, unknown>
  ) => {
    handleAssignmentValuesChange(changedValues);
    handleLineTaktCascade(changedValues, allValues);
    handleScheduleValuesChange(changedValues, allValues);
  };

  const scheduleCascadeOptions = useMemo(
    () => ({
      workOrderStart: workOrder?.planned_start_date ?? undefined,
    }),
    [workOrder?.planned_start_date]
  );

  const handleLineTaktCascade = (
    changedValues: Record<string, unknown>,
    allValues: Record<string, unknown>
  ) => {
    if (!isProductionLineMode || cascadingRef.current) return;
    const changedKey = Object.keys(changedValues)[0];
    if (!changedKey?.startsWith('station_')) return;
    const durationHoursByOperationId = buildTaktDurationByOperationId(allValues);
    if (durationHoursByOperationId.size === 0) return;
    const patches = cascadeOperationPrepScheduleFromIndex(
      sortedOperations,
      allValues,
      0,
      {
        ...scheduleCascadeOptions,
        durationHoursByOperationId,
        sharedWindow: true,
      }
    );
    cascadingRef.current = true;
    formRef.current?.setFieldsValue(patches);
    cascadingRef.current = false;
  };

  const handleScheduleValuesChange = (changedValues: Record<string, unknown>, allValues: Record<string, unknown>) => {
    if (cascadingRef.current) return;
    const changedKey = Object.keys(changedValues)[0];
    if (!changedKey?.startsWith('op_start_') && !changedKey?.startsWith('op_end_')) return;

    const opId = Number(changedKey.replace(/^op_(start|end)_/, ''));
    const fromIndex = sortedOperations.findIndex((op) => op.operationId === opId);
    if (fromIndex < 0) return;

    const durationHoursByOperationId = buildTaktDurationByOperationId(allValues);
    const patches = cascadeOperationPrepScheduleFromIndex(
      sortedOperations,
      allValues,
      fromIndex,
      {
        ...scheduleCascadeOptions,
        durationHoursByOperationId:
          durationHoursByOperationId.size > 0 ? durationHoursByOperationId : undefined,
        sharedWindow: isProductionLineMode,
      }
    );
    const changedPatches = Object.fromEntries(
      Object.entries(patches).filter(([key, value]) => {
        const current = allValues[key];
        if (current == null || current === '') return true;
        return !dayjs.isDayjs(current) || !current.isSame(value);
      })
    );
    if (Object.keys(changedPatches).length === 0) return;

    cascadingRef.current = true;
    formRef.current?.setFieldsValue(changedPatches);
    cascadingRef.current = false;
  };

  const needsStart = missingFields.includes('planned_start_date');
  const needsEnd = missingFields.includes('planned_end_date');
  const needsStations = operationsNeedingStation.length > 0;

  const submitPrepForm = async (rawValues: Record<string, unknown>) => {
    if (!workOrder) return;
    if (operationsNeedingStation.length === 0) {
      messageApi.error(t('app.kuaizhizao.scheduling.prep.noOperations'));
      return;
    }

    const values = {
      ...rawValues,
      ...(formRef.current?.getFieldsValue(true) ?? {}),
    };

    const operationStations: SchedulingWorkOrderPrepValues['operationStations'] = [];
    const operationAssignments: SchedulingWorkOrderPrepValues['operationAssignments'] = [];
    for (const op of operationsNeedingStation) {
      const stationId = Number(values[operationFieldName(op.operationId)]);
      if (!Number.isInteger(stationId) || stationId <= 0) {
        messageApi.error(
          t(
            isProductionLineMode
              ? 'app.kuaizhizao.scheduling.prep.selectProductionLineForOp'
              : 'app.kuaizhizao.scheduling.prep.selectStationForOp',
            { name: op.operationName }
          )
        );
        return;
      }
      if (isProductionLineMode && linesMissingTakt.includes(stationId)) {
        messageApi.error(t('app.kuaizhizao.scheduling.prep.missingTaktCapacity'));
        return;
      }
      if (
        isProductionLineMode &&
        eligibleLineIdSet != null &&
        !eligibleLineIdSet.has(stationId)
      ) {
        messageApi.error(t('app.kuaizhizao.scheduling.msg.lineProductNotAllowed'));
        return;
      }
      operationStations.push({
        operation_id: op.operationId,
        assigned_station_id: stationId,
      });
      if (!isProductionLineMode) {
        const workerId = Number(values[workerFieldName(op.operationId)]);
        const equipmentId = Number(values[equipmentFieldName(op.operationId)]);
        const moldId = Number(values[moldFieldName(op.operationId)]);
        if (
          (Number.isInteger(workerId) && workerId > 0) ||
          (Number.isInteger(equipmentId) && equipmentId > 0) ||
          (Number.isInteger(moldId) && moldId > 0)
        ) {
          operationAssignments.push({
            operation_id: op.operationId,
            assigned_worker_id: Number.isInteger(workerId) && workerId > 0 ? workerId : null,
            assigned_equipment_id:
              Number.isInteger(equipmentId) && equipmentId > 0 ? equipmentId : null,
            assigned_mold_id: Number.isInteger(moldId) && moldId > 0 ? moldId : null,
          });
        }
      }
    }

    const startRaw = values.planned_start_date as Dayjs | undefined;
    const anchorStart = needsStart
      ? startRaw
      : workOrder.planned_start_date
        ? dayjs(workOrder.planned_start_date)
        : startRaw;
    if (needsStart && !anchorStart) {
      messageApi.error(t('app.kuaizhizao.scheduling.prep.selectStartRequired'));
      return;
    }

    const durationHoursByOperationId = new Map<number, number>();
    if (isProductionLineMode) {
      for (const item of operationStations) {
        const hours = durationHoursFromTakt(
          workOrderQty,
          taktSecondsByLineId?.get(item.assigned_station_id) ?? 0
        );
        if (hours == null) {
          messageApi.error(t('app.kuaizhizao.scheduling.prep.missingTaktCapacity'));
          return;
        }
        durationHoursByOperationId.set(item.operation_id, hours);
      }
    }
    const scheduleResult = resolveOperationPrepScheduleDates(operationsNeedingStation, values, {
      workOrderStart: anchorStart ? anchorStart.toISOString() : workOrder.planned_start_date,
      durationHoursByOperationId:
        durationHoursByOperationId.size > 0 ? durationHoursByOperationId : undefined,
      sharedWindow: isProductionLineMode,
    });
    if (isProductionLineMode && scheduleResult.dates.length === 0) {
      messageApi.error(t('app.kuaizhizao.scheduling.prep.missingTaktCapacity'));
      return;
    }
    if (scheduleResult.adjustedOperationNames.length > 0) {
      formRef.current?.setFieldsValue(operationPrepScheduleDatesToFormValues(scheduleResult));
      messageApi.info(
        t('app.kuaizhizao.scheduling.prep.scheduleAdjusted', {
          names: scheduleResult.adjustedOperationNames.join('、'),
        })
      );
    }

    let planned_start_date: string | undefined;
    let planned_end_date: string | undefined;
    if (scheduleResult.dates.length > 0) {
      const starts = scheduleResult.dates.map((d) => d.planned_start_date).sort();
      const ends = scheduleResult.dates.map((d) => d.planned_end_date).sort();
      planned_start_date = starts[0];
      planned_end_date = ends[ends.length - 1];
    } else {
      const endRaw = values.planned_end_date as Dayjs | undefined;
      planned_start_date = anchorStart?.toISOString() ?? workOrder.planned_start_date ?? undefined;
      planned_end_date = (
        needsEnd ? endRaw : workOrder.planned_end_date ? dayjs(workOrder.planned_end_date) : endRaw
      )?.toISOString();
    }

    // 产线模式：工序时间可由节拍生成；不强制头表日期
    if (!isProductionLineMode && (!planned_start_date || !planned_end_date)) {
      messageApi.error(t('app.kuaizhizao.scheduling.prep.fillDatesRequired'));
      return;
    }

    await onSubmit({
      planned_start_date,
      planned_end_date,
      operationStations,
      operationDates: scheduleResult.dates,
      operationAssignments,
    });
  };

  return (
    <FormModalTemplate
      title={t('app.kuaizhizao.scheduling.prep.title')}
      open={open}
      onClose={onCancel}
      loading={loading}
      isEdit
      width={MODAL_CONFIG.LARGE_WIDTH}
      initialValues={initialValues}
      formRef={formRef}
      onValuesChange={handleFormValuesChange}
      onFinish={submitPrepForm}
    >
      <Typography.Paragraph type="secondary" style={{ marginBottom: 16 }}>
        {t(
          isProductionLineMode
            ? 'app.kuaizhizao.scheduling.prep.descriptionProductionLine'
            : 'app.kuaizhizao.scheduling.prep.description',
          {
            code: workOrder?.code || workOrder?.id,
          }
        )}
      </Typography.Paragraph>
      {!isProductionLineMode && rateWarnings.length > 0 ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          title={t('app.kuaizhizao.scheduling.prep.rateWarningTitle', { items: rateWarnings.join('、') })}
          description={
            <Link to="/apps/kuaioa/hr/employee-configs">
              {t('app.kuaizhizao.scheduling.prep.gotoPerformanceConfig')}
            </Link>
          }
        />
      ) : null}
      {isProductionLineMode && linesMissingTakt.length > 0 ? (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 12 }}
          title={t('app.kuaizhizao.scheduling.prep.missingTaktCapacity')}
          description={
            <Link to={lineCapacityPath}>{t('app.kuaizhizao.scheduling.prep.gotoLineCapacity')}</Link>
          }
        />
      ) : null}
      {needsStations ? (
        <>
          <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>
            {t('app.kuaizhizao.scheduling.prep.operationScheduling')}
          </Typography.Text>
          <div
            className={`scheduling-prep-station-grid${
              isProductionLineMode ? ' scheduling-prep-station-grid--production-line' : ''
            }`}
          >
            <div className="scheduling-prep-station-grid__head">
              <span>{t('app.kuaizhizao.scheduling.prep.colOperation')}</span>
              <span>
                {t(
                  isProductionLineMode
                    ? 'app.kuaizhizao.scheduling.prep.colProductionLine'
                    : 'app.kuaizhizao.scheduling.prep.colStation'
                )}
              </span>
              {!isProductionLineMode ? (
                <>
                  <span>{t('app.kuaizhizao.scheduling.prep.colWorker')}</span>
                  <span>{t('app.kuaizhizao.scheduling.prep.colEquipment')}</span>
                  <span>{t('app.kuaizhizao.scheduling.prep.colMold')}</span>
                </>
              ) : null}
              <span>{t('app.kuaizhizao.scheduling.prep.colStart')}</span>
              <span>{t('app.kuaizhizao.scheduling.prep.colEnd')}</span>
            </div>
            {sortedOperations.map((op, index) => {
              const stationOptions = isProductionLineMode
                ? workstations
                    .filter((line) => eligibleLineIdSet == null || eligibleLineIdSet.has(line.id))
                    .map((line) => ({
                      value: line.id,
                      label: line.code ? `${line.code} ${line.name}` : line.name,
                    }))
                : stationOptionsForOperation(op, workstations, workCenters);
              return (
                <div key={op.operationId} className="scheduling-prep-station-grid__row">
                  <div className="scheduling-prep-station-grid__op" title={op.operationName}>
                    {op.sequence > 0 ? `${op.sequence}. ${op.operationName}` : op.operationName}
                  </div>
                  <ProFormSelect
                    name={operationFieldName(op.operationId)}
                    rules={[
                      {
                        required: true,
                        message: t(
                          isProductionLineMode
                            ? 'app.kuaizhizao.scheduling.prep.selectProductionLineRequired'
                            : 'app.kuaizhizao.scheduling.prep.selectStationRequired'
                        ),
                      },
                    ]}
                    formItemProps={{ style: { marginBottom: 0 } }}
                    options={stationOptions}
                    fieldProps={{
                      size: 'small',
                      showSearch: true,
                      optionFilterProp: 'label',
                      placeholder:
                        stationOptions.length > 0
                          ? t(
                              isProductionLineMode
                                ? 'app.kuaizhizao.scheduling.prep.selectProductionLine'
                                : 'app.kuaizhizao.scheduling.prep.selectStation'
                            )
                          : t(
                              isProductionLineMode
                                ? 'app.kuaizhizao.scheduling.msg.lineProductNoEligible'
                                : 'app.kuaizhizao.scheduling.prep.noStationsAvailable'
                            ),
                      disabled: stationOptions.length === 0 || loading,
                      style: { width: '100%' },
                    }}
                  />
                  {!isProductionLineMode ? (
                    <>
                      <ProFormSelect
                        name={workerFieldName(op.operationId)}
                        formItemProps={{ style: { marginBottom: 0 } }}
                        options={workerOptions}
                        fieldProps={{
                          size: 'small',
                          allowClear: true,
                          showSearch: true,
                          optionFilterProp: 'label',
                          placeholder: t('app.kuaizhizao.scheduling.prep.selectWorker'),
                          style: { width: '100%' },
                        }}
                      />
                      <ProFormSelect
                        name={equipmentFieldName(op.operationId)}
                        formItemProps={{ style: { marginBottom: 0 } }}
                        options={equipmentOptions}
                        fieldProps={{
                          size: 'small',
                          allowClear: true,
                          showSearch: true,
                          optionFilterProp: 'label',
                          placeholder: t('app.kuaizhizao.scheduling.prep.selectEquipment'),
                          style: { width: '100%' },
                        }}
                      />
                      <ProFormSelect
                        name={moldFieldName(op.operationId)}
                        formItemProps={{ style: { marginBottom: 0 } }}
                        options={moldOptions}
                        fieldProps={{
                          size: 'small',
                          allowClear: true,
                          showSearch: true,
                          optionFilterProp: 'label',
                          placeholder: t('app.kuaizhizao.scheduling.prep.selectMold'),
                          style: { width: '100%' },
                        }}
                      />
                    </>
                  ) : null}
                  <ProFormDateTimePicker
                    name={operationPrepStartFieldName(op.operationId)}
                    formItemProps={{ style: { marginBottom: 0 } }}
                    fieldProps={{
                      size: 'small',
                      showTime: { format: 'HH:mm' },
                      format: 'YYYY-MM-DD HH:mm',
                      allowClear: true,
                      style: { width: '100%' },
                      placeholder:
                        index > 0
                          ? t('app.kuaizhizao.scheduling.prep.placeholderAfterPrevOp')
                          : t('app.kuaizhizao.scheduling.prep.placeholderCurrentTime'),
                    }}
                  />
                  <ProFormDateTimePicker
                    name={operationPrepEndFieldName(op.operationId)}
                    formItemProps={{ style: { marginBottom: 0 } }}
                    fieldProps={{
                      size: 'small',
                      showTime: { format: 'HH:mm' },
                      format: 'YYYY-MM-DD HH:mm',
                      allowClear: true,
                      style: { width: '100%' },
                      placeholder: isProductionLineMode
                        ? t('app.kuaizhizao.scheduling.prep.placeholderTaktDuration')
                        : t('app.kuaizhizao.scheduling.prep.placeholderStartPlus8h'),
                    }}
                  />
                </div>
              );
            })}
          </div>
        </>
      ) : workOrder && !loading ? (
        <Typography.Paragraph type="warning" style={{ marginBottom: 16 }}>
          {t('app.kuaizhizao.scheduling.prep.noRouteWarning')}
        </Typography.Paragraph>
      ) : null}
      {needsStart ? (
        <ProFormDateTimePicker
          name="planned_start_date"
          label={t('app.kuaizhizao.scheduling.prep.plannedStart')}
          rules={[{ required: true, message: t('app.kuaizhizao.scheduling.prep.selectStartRequired') }]}
          fieldProps={{ style: { width: '100%' } }}
        />
      ) : null}
      {needsEnd ? (
        <ProFormDateTimePicker
          name="planned_end_date"
          label={t('app.kuaizhizao.scheduling.prep.plannedEnd')}
          rules={[{ required: true, message: t('app.kuaizhizao.scheduling.prep.selectEndRequired') }]}
          fieldProps={buildFutureDateShortcutFieldProps({
            getForm: () => formRef.current,
            fieldName: 'planned_end_date',
            baseFieldName: 'planned_start_date',
            t,
            fieldProps: { style: { width: '100%' } },
          }) as React.ComponentProps<typeof ProFormDateTimePicker>['fieldProps']}
        />
      ) : null}
    </FormModalTemplate>
  );
};

export default SchedulingWorkOrderPrepModal;
