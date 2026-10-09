import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Input, List } from 'antd';
import { TouchScreenTemplate } from '../../../../components/layout-templates/hmi';
import { TouchChip, TouchListItem, touchButtonProps } from '../../../../components/touch-terminal';
import { STATION_ENTRY_PATH } from '../../../../utils/clientChannel';
import { HMI_TOUCH } from '../../../../theme/hmi';
import { useStationWriteEnabled } from '../entry/session';
import {
  ANDON_CALL_TYPES,
  FAULT_LEVELS,
  MATERIAL_CALL_MODE,
  acknowledgeAndon,
  apiErrorText,
  cancelAndon,
  closeAndon,
  createAndonCall,
  listAndonCalls,
  listEquipment,
  listOpenAndonCalls,
  listOperationRows,
  listWorkOrders,
  searchSupervisors,
  type AndonCallType,
  type EquipmentChoice,
  type FaultLevel,
  type OperationChoice,
  type StationAndonCreateBody,
  type StationAndonRecord,
  type SupervisorChoice,
  type WorkOrderChoice,
} from './api';

export type StationAndonPageProps = {
  /** 157 入口已绑定的工位。缺省时不读 URL，也不发起安灯请求。 */
  workstationId?: number | null;
  /** 入口已绑定工位名称。有则随发起请求提交。 */
  workstationName?: string | null;
  /** 入口当前操作员，只用于展示。 */
  operatorId?: number | null;
  /** 入口当前操作员姓名，只用于展示。 */
  operatorName?: string | null;
};

const CALL_TYPE_LABEL: Record<string, string> = {
  quality: '质量',
  material: '物料',
  equipment: '设备',
  supervisor: '班长',
};

const STATUS_LABEL: Record<string, string> = {
  open: '已发起',
  acknowledged: '已响应',
  closed: '已关闭',
};

function boundWorkstationId(value: number | null | undefined): number | null {
  if (typeof value === 'number' && Number.isInteger(value) && value > 0) return value;
  return null;
}

function statusText(status: string): string {
  const label = STATUS_LABEL[status];
  return label ? `${label}（${status}）` : status || '—';
}

function callTypeText(callType: string): string {
  return CALL_TYPE_LABEL[callType] || callType || '—';
}

function timeText(value: string): string {
  if (!value) return '';
  return value.replace('T', ' ').replace(/\.\d+/, '').replace(/Z$/, '').replace(/\+.*/, '');
}

/** 返回工位入口；有已校验工位时保留 workstationId 查询参数。 */
function stationEntryPath(workstationId: number | null): string {
  return workstationId == null
    ? STATION_ENTRY_PATH
    : `${STATION_ENTRY_PATH}?workstationId=${workstationId}`;
}

export function StationAndonPage({
  workstationId = null,
  workstationName = null,
  operatorId = null,
  operatorName = null,
}: StationAndonPageProps) {
  const navigate = useNavigate();
  // 未确认操作员时可查看安灯列表，发起/响应/关闭/撤销禁用
  const writeEnabled = useStationWriteEnabled();
  const stationId = boundWorkstationId(workstationId);
  const stationName = typeof workstationName === 'string' ? workstationName.trim() : '';
  const operatorText = operatorName?.trim()
    ? operatorName.trim()
    : typeof operatorId === 'number' && Number.isInteger(operatorId)
      ? `操作员 ${operatorId}`
      : '入口未传入当前操作员';

  const [callType, setCallType] = useState<AndonCallType>('quality');
  const [remarks, setRemarks] = useState('');
  const [workOrders, setWorkOrders] = useState<WorkOrderChoice[]>([]);
  const [workOrderKeyword, setWorkOrderKeyword] = useState('');
  const [selectedWorkOrder, setSelectedWorkOrder] = useState<WorkOrderChoice | null>(null);
  const [operations, setOperations] = useState<OperationChoice[]>([]);
  const [selectedOperationId, setSelectedOperationId] = useState<number | null>(null);
  const [equipment, setEquipment] = useState<EquipmentChoice[]>([]);
  const [equipmentKeyword, setEquipmentKeyword] = useState('');
  const [selectedEquipmentUuid, setSelectedEquipmentUuid] = useState<string | null>(null);
  const [faultLevel, setFaultLevel] = useState<FaultLevel | null>(null);
  const [supervisors, setSupervisors] = useState<SupervisorChoice[]>([]);
  const [supervisorKeyword, setSupervisorKeyword] = useState('');
  const [selectedSupervisorId, setSelectedSupervisorId] = useState<number | null>(null);
  const [openRows, setOpenRows] = useState<StationAndonRecord[]>([]);
  const [allRows, setAllRows] = useState<StationAndonRecord[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [pickerLoading, setPickerLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(
    null,
  );
  const operationsRequestSeq = useRef(0);
  const listsRequestSeq = useRef(0);
  const pickerRequestSeq = useRef(0);

  const loadLists = useCallback(async (id: number) => {
    const requestSeq = ++listsRequestSeq.current;
    setListLoading(true);
    try {
      const [openList, allList] = await Promise.all([
        listOpenAndonCalls(id),
        listAndonCalls(id),
      ]);
      if (requestSeq !== listsRequestSeq.current) return;
      setOpenRows(openList);
      setAllRows(allList);
    } catch (error) {
      if (requestSeq === listsRequestSeq.current) {
        setNotice({ type: 'error', text: apiErrorText(error) });
      }
    } finally {
      if (requestSeq === listsRequestSeq.current) setListLoading(false);
    }
  }, []);

  useEffect(() => {
    if (stationId == null) return;
    void loadLists(stationId);
  }, [loadLists, stationId]);

  const loadWorkOrderChoices = useCallback(async (keyword: string) => {
    const requestSeq = ++pickerRequestSeq.current;
    setPickerLoading(true);
    try {
      const rows = await listWorkOrders(keyword);
      if (requestSeq !== pickerRequestSeq.current) return;
      setWorkOrders(rows);
    } catch (error) {
      if (requestSeq !== pickerRequestSeq.current) return;
      setWorkOrders([]);
      setNotice({ type: 'error', text: apiErrorText(error) });
    } finally {
      if (requestSeq === pickerRequestSeq.current) setPickerLoading(false);
    }
  }, []);

  const loadEquipmentChoices = useCallback(async (keyword: string) => {
    const requestSeq = ++pickerRequestSeq.current;
    setPickerLoading(true);
    try {
      const rows = await listEquipment(keyword);
      if (requestSeq !== pickerRequestSeq.current) return;
      setEquipment(rows);
    } catch (error) {
      if (requestSeq !== pickerRequestSeq.current) return;
      setEquipment([]);
      setNotice({ type: 'error', text: apiErrorText(error) });
    } finally {
      if (requestSeq === pickerRequestSeq.current) setPickerLoading(false);
    }
  }, []);

  const loadSupervisorChoices = useCallback(async (keyword: string) => {
    const requestSeq = ++pickerRequestSeq.current;
    setPickerLoading(true);
    try {
      const rows = await searchSupervisors(keyword);
      if (requestSeq !== pickerRequestSeq.current) return;
      setSupervisors(rows);
    } catch (error) {
      if (requestSeq !== pickerRequestSeq.current) return;
      setSupervisors([]);
      setNotice({ type: 'error', text: apiErrorText(error) });
    } finally {
      if (requestSeq === pickerRequestSeq.current) setPickerLoading(false);
    }
  }, []);

  useEffect(() => {
    if (stationId == null) return;
    if (callType === 'quality' || callType === 'material') {
      void loadWorkOrderChoices('');
    } else if (callType === 'equipment') {
      void loadEquipmentChoices('');
    } else {
      void loadSupervisorChoices('');
    }
  }, [callType, loadEquipmentChoices, loadSupervisorChoices, loadWorkOrderChoices, stationId]);

  const loadSelectedWorkOrderOperations = useCallback(async (row: WorkOrderChoice) => {
    const requestSeq = ++operationsRequestSeq.current;
    const pickerSeq = ++pickerRequestSeq.current;
    setPickerLoading(true);
    try {
      const rows = await listOperationRows(row.id);
      if (requestSeq !== operationsRequestSeq.current) return;
      setOperations(rows);
    } catch (error) {
      if (requestSeq === operationsRequestSeq.current) {
        setNotice({ type: 'error', text: apiErrorText(error) });
      }
    } finally {
      if (pickerSeq === pickerRequestSeq.current) setPickerLoading(false);
    }
  }, []);

  useEffect(() => {
    if (callType !== 'quality' || selectedWorkOrder == null) {
      operationsRequestSeq.current += 1;
      return;
    }
    void loadSelectedWorkOrderOperations(selectedWorkOrder);
  }, [callType, loadSelectedWorkOrderOperations, selectedWorkOrder]);

  const selectWorkOrder = (row: WorkOrderChoice) => {
    setSelectedWorkOrder(row);
    setSelectedOperationId(null);
    setOperations([]);
  };

  const submit = async () => {
    if (stationId == null || busy) return;
    const note = remarks.trim();
    const body: StationAndonCreateBody = {
      call_type: callType,
      workstation_id: stationId,
    };
    if (stationName) body.workstation_name = stationName;
    if (note) body.remarks = note;

    if (callType === 'quality') {
      if (selectedWorkOrder == null || selectedOperationId == null) {
        setNotice({ type: 'info', text: '质量安灯须选择工单与工序，未提交' });
        return;
      }
      body.work_order_id = selectedWorkOrder.id;
      if (selectedWorkOrder.code) body.work_order_code = selectedWorkOrder.code;
      body.operation_id = selectedOperationId;
    } else if (callType === 'material') {
      if (selectedWorkOrder == null) {
        setNotice({ type: 'info', text: '物料安灯须选择工单，未提交' });
        return;
      }
      body.work_order_id = selectedWorkOrder.id;
      if (selectedWorkOrder.code) body.work_order_code = selectedWorkOrder.code;
      body.material_call_mode = MATERIAL_CALL_MODE;
    } else if (callType === 'equipment') {
      if (!selectedEquipmentUuid || !faultLevel) {
        setNotice({ type: 'info', text: '设备安灯须选择设备与故障级别，未提交' });
        return;
      }
      body.equipment_uuid = selectedEquipmentUuid;
      body.fault_level = faultLevel;
    } else if (selectedSupervisorId == null) {
      setNotice({ type: 'info', text: '班长安灯须指定通知人，未提交' });
      return;
    } else {
      body.supervisor_user_id = selectedSupervisorId;
    }

    setBusy(true);
    try {
      const created = await createAndonCall(body);
      const status = created?.status ? statusText(created.status) : '已返回';
      const doc = created?.relatedDocCode ? `，关联 ${created.relatedDocCode}` : '';
      setNotice({ type: 'success', text: `已发起${callTypeText(callType)}安灯，状态 ${status}${doc}` });
      setRemarks('');
      await loadLists(stationId);
    } catch (error) {
      setNotice({ type: 'error', text: apiErrorText(error) });
    } finally {
      setBusy(false);
    }
  };

  const runAction = async (
    row: StationAndonRecord,
    action: 'acknowledge' | 'close' | 'cancel',
  ) => {
    if (stationId == null || busy) return;
    if (action === 'cancel') {
      if (row.status !== 'open' || operatorId == null || row.callerId !== operatorId) return;
    } else if (action === 'acknowledge') {
      if (row.status !== 'open') return;
    } else if (row.status !== 'open' && row.status !== 'acknowledged') {
      return;
    }
    setBusy(true);
    try {
      const updated =
        action === 'acknowledge'
          ? await acknowledgeAndon(row.id)
          : action === 'close'
            ? await closeAndon(row.id)
            : await cancelAndon(row.id);
      const label = action === 'acknowledge' ? '响应' : action === 'close' ? '关闭' : '撤销';
      setNotice({
        type: 'success',
        text: updated?.status
          ? `安灯 ${row.id} 已${label}，状态 ${statusText(updated.status)}`
          : `安灯 ${row.id} 已${label}`,
      });
      await loadLists(stationId);
    } catch (error) {
      setNotice({ type: 'error', text: apiErrorText(error) });
    } finally {
      setBusy(false);
    }
  };

  const renderRecord = (row: StationAndonRecord) => {
    const canAcknowledge = row.status === 'open';
    const canClose = row.status === 'open' || row.status === 'acknowledged';
    const canCancel = row.status === 'open' && operatorId != null && row.callerId === operatorId;
    return (
      <List.Item>
        <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 18 }}>
            <strong>{callTypeText(row.callType)}</strong>
            <span style={{ marginLeft: 12 }}>{statusText(row.status)}</span>
            <span style={{ marginLeft: 12 }}>发起人 {row.callerName || row.callerId}</span>
            {row.workOrderCode ? <span style={{ marginLeft: 12 }}>工单 {row.workOrderCode}</span> : null}
            {row.faultLevel ? <span style={{ marginLeft: 12 }}>级别 {row.faultLevel}</span> : null}
            {row.materialCallMode ? <span style={{ marginLeft: 12 }}>{row.materialCallMode}</span> : null}
          </div>
          {row.relatedDocCode ? (
            <div>
              关联单据 {row.relatedDocType || '—'} {row.relatedDocCode}
            </div>
          ) : null}
          {row.remarks ? <div>备注 {row.remarks}</div> : null}
          {row.createdAt ? <div>发起时间 {timeText(row.createdAt)}</div> : null}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {canAcknowledge ? (
              <Button
                size="large"
                {...touchButtonProps({ size: 'action' })}
                disabled={busy || !writeEnabled}
                onClick={() => void runAction(row, 'acknowledge')}
              >
                响应
              </Button>
            ) : null}
            {canClose ? (
              <Button
                size="large"
                {...touchButtonProps({ size: 'action' })}
                disabled={busy || !writeEnabled}
                onClick={() => void runAction(row, 'close')}
              >
                关闭
              </Button>
            ) : null}
            {canCancel ? (
              <Button
                size="large"
                {...touchButtonProps({ size: 'action' })}
                disabled={busy || !writeEnabled}
                onClick={() => void runAction(row, 'cancel')}
              >
                撤销
              </Button>
            ) : null}
          </div>
        </div>
      </List.Item>
    );
  };

  if (stationId == null) {
    return (
      <TouchScreenTemplate title="安灯">
        <Alert type="info" showIcon message="等待工位入口传入当前工位" />
        <div style={{ marginTop: 16 }}>
          <Button
            size="large"
            {...touchButtonProps({ size: 'action' })}
            onClick={() => navigate(stationEntryPath(stationId))}
          >
            返回工位入口
          </Button>
        </div>
      </TouchScreenTemplate>
    );
  }

  return (
    <TouchScreenTemplate title="安灯">
      <div className="hmi-station-pane" style={{ flex: 1 }}>
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 16,
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: 18,
          }}
        >
          <span>
            工位 {stationName || stationId}
            <span style={{ marginLeft: 16 }}>当前操作员 {operatorText}</span>
          </span>
          <Button
            size="large"
            {...touchButtonProps({ size: 'header', style: { height: HMI_TOUCH.HEADER_BTN_HEIGHT } })}
            onClick={() => navigate(stationEntryPath(stationId))}
          >
            返回工位入口
          </Button>
        </div>

        {notice ? <Alert type={notice.type} message={notice.text} showIcon /> : null}
        {!writeEnabled ? (
          <Alert
            type="info"
            showIcon
            message="未确认操作员：可查看安灯，发起、响应、关闭与撤销不可用"
          />
        ) : null}

        <div className="hmi-station-split hmi-station-split--balanced">
          <div className="hmi-station-pane">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {ANDON_CALL_TYPES.map((item) => (
            <TouchChip
              key={item.value}
              selected={callType === item.value}
              onClick={() => setCallType(item.value)}
            >
              {item.label}
            </TouchChip>
          ))}
        </div>

        {(callType === 'quality' || callType === 'material') && (
          <div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
              <Input
                size="large"
                value={workOrderKeyword}
                placeholder="工单编码或名称"
                onChange={(event) => setWorkOrderKeyword(event.target.value)}
                onPressEnter={() => void loadWorkOrderChoices(workOrderKeyword)}
              />
              <Button
                size="large"
                {...touchButtonProps({ size: 'action' })}
                loading={pickerLoading}
                onClick={() => void loadWorkOrderChoices(workOrderKeyword)}
              >
                查工单
              </Button>
            </div>
            <List
              loading={pickerLoading}
              dataSource={workOrders}
              locale={{ emptyText: '没有工单' }}
              renderItem={(row) => (
                <TouchListItem
                  selected={row.id === selectedWorkOrder?.id}
                  onClick={() => void selectWorkOrder(row)}
                  title={<strong>{row.code || `工单 ${row.id}`}</strong>}
                  subtitle={row.name}
                />
              )}
            />
          </div>
        )}

        {callType === 'quality' && selectedWorkOrder ? (
          <List
            dataSource={operations}
            locale={{ emptyText: '该工单没有工序' }}
            renderItem={(row) => (
              <TouchListItem
                selected={row.id === selectedOperationId}
                onClick={() => setSelectedOperationId(row.id)}
                title={`${row.sequence}. ${row.name || row.code || `工序 ${row.id}`}`}
              />
            )}
          />
        ) : null}

        {callType === 'material' ? (
          <div style={{ fontSize: 18 }}>叫料模式 {MATERIAL_CALL_MODE}</div>
        ) : null}

        {callType === 'equipment' && (
          <div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
              <Input
                size="large"
                value={equipmentKeyword}
                placeholder="设备编码或名称"
                onChange={(event) => setEquipmentKeyword(event.target.value)}
                onPressEnter={() => void loadEquipmentChoices(equipmentKeyword)}
              />
              <Button
                size="large"
                {...touchButtonProps({ size: 'action' })}
                loading={pickerLoading}
                onClick={() => void loadEquipmentChoices(equipmentKeyword)}
              >
                查设备
              </Button>
            </div>
            <List
              loading={pickerLoading}
              dataSource={equipment}
              locale={{ emptyText: '没有设备' }}
              renderItem={(row) => (
                <TouchListItem
                  selected={row.uuid === selectedEquipmentUuid}
                  onClick={() => setSelectedEquipmentUuid(row.uuid)}
                  title={<strong>{row.name || row.code || row.uuid}</strong>}
                  subtitle={row.name ? row.code : undefined}
                />
              )}
            />
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
              {FAULT_LEVELS.map((level) => (
                <TouchChip
                  key={level}
                  selected={faultLevel === level}
                  onClick={() => setFaultLevel(level)}
                >
                  {level}
                </TouchChip>
              ))}
            </div>
          </div>
        )}

        {callType === 'supervisor' && (
          <div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
              <Input
                size="large"
                value={supervisorKeyword}
                placeholder="姓名或账号"
                onChange={(event) => setSupervisorKeyword(event.target.value)}
                onPressEnter={() => void loadSupervisorChoices(supervisorKeyword)}
              />
              <Button
                size="large"
                {...touchButtonProps({ size: 'action' })}
                loading={pickerLoading}
                onClick={() => void loadSupervisorChoices(supervisorKeyword)}
              >
                查通知人
              </Button>
            </div>
            <List
              loading={pickerLoading}
              dataSource={supervisors}
              locale={{ emptyText: '没有可选通知人' }}
              renderItem={(row) => (
                <TouchListItem
                  selected={row.id === selectedSupervisorId}
                  onClick={() => setSelectedSupervisorId(row.id)}
                  title={row.label}
                />
              )}
            />
          </div>
        )}

        <Input.TextArea
          value={remarks}
          rows={2}
          placeholder="备注（可选）"
          onChange={(event) => setRemarks(event.target.value)}
        />
            <Button
              size="large"
              {...touchButtonProps({ variant: 'primary', size: 'primary' })}
              loading={busy}
              disabled={!writeEnabled}
              onClick={() => void submit()}
            >
              发起{callTypeText(callType)}安灯
            </Button>
          </div>

          <div className="hmi-station-pane hmi-station-pane--scroll">
            <h2 style={{ fontSize: 22, margin: '8px 0' }}>未响应</h2>
            <List
              loading={listLoading}
              dataSource={openRows}
              locale={{ emptyText: '没有未响应的安灯' }}
              renderItem={renderRecord}
            />
            <h2 style={{ fontSize: 22, margin: '8px 0' }}>安灯列表</h2>
            <Button
              {...touchButtonProps({ size: 'action' })}
              onClick={() => void loadLists(stationId)}
              loading={listLoading}
            >
              刷新
            </Button>
            <List
              loading={listLoading}
              dataSource={allRows}
              locale={{ emptyText: '没有安灯记录' }}
              renderItem={renderRecord}
            />
          </div>
        </div>
      </div>
    </TouchScreenTemplate>
  );
}
