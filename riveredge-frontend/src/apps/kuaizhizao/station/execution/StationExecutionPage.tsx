import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Button, List, Switch } from 'antd';
import {
  DOWNTIME_REASONS,
  acknowledgeSop,
  apiErrorText,
  checkOperatorSkill,
  checkSopAcknowledgment,
  completeOperation,
  getStationOperationDocuments,
  listExecutableWorkOrders,
  listOperations,
  pauseOperation,
  readSkillCheck,
  readSopAcknowledged,
  readSopRef,
  resumeOperation,
  setMachineSession,
  startOperation,
  withdrawOperationStart,
  type StationOperation,
  type StationWorkOrder,
} from './api';

export type StationExecutionOperator = {
  id: number;
  name?: string;
};

export type StationExecutionSelection = {
  workOrderId: number | null;
  operationId: number | null;
};

export type StationExecutionPageProps = {
  /** 157 入口已绑定的工位。有值时暂停请求带 workstation_id。 */
  workstationId?: number | null;
  /** 157 入口当前操作员。SOP 确认与资质检查使用该 id。 */
  operator?: StationExecutionOperator | null;
  /** 把选中的工单与工序行交回入口。本页不另建工单列表。 */
  onSelectionChange?: (selection: StationExecutionSelection) => void;
};

type PendingSop = {
  workOrderId: number;
  operationId: number;
  sopUuid: string;
  revision: string;
};

const OPERATION_STATUS_LABEL: Record<string, string> = {
  pending: '待开工',
  in_progress: '进行中',
  processing: '进行中',
  paused: '已暂停',
  completed: '已完成',
};

const WORK_ORDER_STATUS_LABEL: Record<string, string> = {
  released: '已下达',
  in_progress: '执行中',
};

function statusText(status: string, labels: Record<string, string>): string {
  if (!status) return '—';
  const label = labels[status];
  return label ? `${label}（${status}）` : status;
}

function boundWorkstationId(value: number | null | undefined): number | null {
  if (typeof value === 'number' && Number.isInteger(value) && value > 0) return value;
  return null;
}

export function StationExecutionPage({
  workstationId = null,
  operator = null,
  onSelectionChange,
}: StationExecutionPageProps) {
  const [sopEnabled, setSopEnabled] = useState(false);
  const [skillEnabled, setSkillEnabled] = useState(false);
  const [workOrders, setWorkOrders] = useState<StationWorkOrder[]>([]);
  const [skip, setSkip] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [listLoading, setListLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedOperationId, setSelectedOperationId] = useState<number | null>(null);
  const [operations, setOperations] = useState<StationOperation[]>([]);
  const [opsLoading, setOpsLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pauseFor, setPauseFor] = useState<number | null>(null);
  const [pendingSop, setPendingSop] = useState<PendingSop | null>(null);
  const [notice, setNotice] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(
    null,
  );

  const stationId = boundWorkstationId(workstationId);

  const loadWorkOrders = useCallback(async (nextSkip: number, append: boolean) => {
    setListLoading(true);
    try {
      const page = await listExecutableWorkOrders(nextSkip);
      setWorkOrders((prev) => {
        const merged = append ? [...prev, ...page.rows] : page.rows;
        const byId = new Map<number, StationWorkOrder>();
        for (const row of merged) byId.set(row.id, row);
        return [...byId.values()].sort((a, b) => a.code.localeCompare(b.code));
      });
      setSkip(nextSkip);
      setHasMore(page.hasMore);
    } catch (error) {
      setNotice({ type: 'error', text: apiErrorText(error) });
    } finally {
      setListLoading(false);
    }
  }, []);

  const loadOperations = useCallback(async (workOrderId: number) => {
    setOpsLoading(true);
    try {
      setOperations(await listOperations(workOrderId));
    } catch (error) {
      setOperations([]);
      setNotice({ type: 'error', text: apiErrorText(error) });
    } finally {
      setOpsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadWorkOrders(0, false);
  }, [loadWorkOrders]);

  const refreshSelected = useCallback(
    async (workOrderId: number) => {
      await Promise.all([loadWorkOrders(0, false), loadOperations(workOrderId)]);
    },
    [loadOperations, loadWorkOrders],
  );

  const ensureOperator = (): StationExecutionOperator | null => {
    if (operator?.id != null && Number.isInteger(operator.id)) return operator;
    setNotice({ type: 'info', text: '入口未提供当前操作员，未调用开工' });
    return null;
  };

  const runSkillGate = async (
    workOrderId: number,
    operationId: number,
  ): Promise<{ ok: true; message: string } | { ok: false }> => {
    if (!skillEnabled) return { ok: true, message: '' };
    const current = ensureOperator();
    if (!current) return { ok: false };
    const result = readSkillCheck(
      await checkOperatorSkill({
        userId: current.id,
        operationId,
        workOrderId,
      }),
    );
    if (!result.qualified) {
      setNotice({
        type: 'error',
        text: result.message || '上岗资质未通过，未调用开工',
      });
      return { ok: false };
    }
    return { ok: true, message: result.message };
  };

  const runStart = async (operation: StationOperation, sopAlreadyConfirmed: boolean) => {
    if (selectedId == null) return;
    setBusy(true);
    setPauseFor(null);
    try {
      if (sopEnabled && !sopAlreadyConfirmed) {
        const docs = await getStationOperationDocuments(selectedId, operation.id);
        const sop = readSopRef(docs);
        if (sop) {
          const current = ensureOperator();
          if (!current) return;
          const checked = await checkSopAcknowledgment({
            workOrderId: selectedId,
            operationId: operation.id,
            sopUuid: sop.uuid,
            workerId: current.id,
          });
          if (!readSopAcknowledged(checked)) {
            setPendingSop({
              workOrderId: selectedId,
              operationId: operation.id,
              sopUuid: sop.uuid,
              revision: sop.revision,
            });
            setNotice({ type: 'info', text: 'SOP 尚未确认，未调用开工' });
            return;
          }
        }
        setPendingSop(null);
      }

      const skill = await runSkillGate(selectedId, operation.id);
      if (!skill.ok) return;

      await startOperation(selectedId, operation.id);
      const started = skill.message ? `${skill.message}。已开工` : '已开工';
      setPendingSop(null);
      try {
        await refreshSelected(selectedId);
        setNotice({ type: 'success', text: started });
      } catch (error) {
        setNotice({ type: 'error', text: `${started}。刷新失败：${apiErrorText(error)}` });
      }
    } catch (error) {
      setNotice({ type: 'error', text: apiErrorText(error) });
    } finally {
      setBusy(false);
    }
  };

  const confirmSopAndStart = async (operation: StationOperation) => {
    if (!pendingSop || pendingSop.operationId !== operation.id || selectedId == null) return;
    const current = ensureOperator();
    if (!current) return;
    setBusy(true);
    try {
      const acked = await acknowledgeSop({
        sopUuid: pendingSop.sopUuid,
        revision: pendingSop.revision,
        workOrderId: pendingSop.workOrderId,
        operationId: pendingSop.operationId,
        workerId: current.id,
        workerName: current.name || '',
      });
      if (!readSopAcknowledged(acked)) {
        setNotice({ type: 'error', text: 'SOP 确认未成功，未调用开工' });
        return;
      }
    } catch (error) {
      setNotice({ type: 'error', text: apiErrorText(error) });
      return;
    } finally {
      setBusy(false);
    }
    await runStart(operation, true);
  };

  const runAction = async (action: () => Promise<unknown>, successText: string) => {
    if (selectedId == null) return;
    setBusy(true);
    setPauseFor(null);
    try {
      await action();
      try {
        await refreshSelected(selectedId);
        setNotice({ type: 'success', text: successText });
      } catch (error) {
        setNotice({ type: 'error', text: `${successText}。刷新失败：${apiErrorText(error)}` });
      }
    } catch (error) {
      setNotice({ type: 'error', text: apiErrorText(error) });
    } finally {
      setBusy(false);
    }
  };

  const selected = workOrders.find((row) => row.id === selectedId) ?? null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: 16 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 24, alignItems: 'center' }}>
        <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 18 }}>
          <Switch
            checked={sopEnabled}
            onChange={(checked) => {
              setSopEnabled(checked);
              if (!checked) setPendingSop(null);
            }}
          />
          SOP 确认
        </label>
        <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 18 }}>
          <Switch checked={skillEnabled} onChange={setSkillEnabled} />
          上岗资质
        </label>
        <Button size="large" onClick={() => void loadWorkOrders(0, false)} loading={listLoading}>
          刷新工单
        </Button>
      </div>

      {notice ? (
        <Alert type={notice.type} message={notice.text} showIcon />
      ) : null}

      <List
        loading={listLoading}
        dataSource={workOrders}
        locale={{ emptyText: '没有已下达或执行中的工单' }}
        renderItem={(row) => (
          <List.Item
            style={{
              cursor: 'pointer',
              background: row.id === selectedId ? '#e6f4ff' : undefined,
              padding: 12,
            }}
          >
            <div
              style={{ fontSize: 18, width: '100%' }}
              onClick={() => {
                setSelectedId(row.id);
                setSelectedOperationId(null);
                setPauseFor(null);
                setPendingSop(null);
                onSelectionChange?.({ workOrderId: row.id, operationId: null });
                void loadOperations(row.id);
              }}
            >
              <strong>{row.code || `工单 ${row.id}`}</strong>
              <span style={{ marginLeft: 12 }}>{row.productName}</span>
              {row.productCode ? <span style={{ marginLeft: 8 }}>{row.productCode}</span> : null}
              <span style={{ marginLeft: 12 }}>数量 {row.quantity || '—'}</span>
              <span style={{ marginLeft: 12 }}>{statusText(row.status, WORK_ORDER_STATUS_LABEL)}</span>
            </div>
          </List.Item>
        )}
      />
      {hasMore ? (
        <Button size="large" onClick={() => void loadWorkOrders(skip + 50, true)} loading={listLoading}>
          加载更多
        </Button>
      ) : null}

      {selected ? (
        <div>
          <h2 style={{ fontSize: 22, margin: '8px 0' }}>
            {selected.code} 的工序
          </h2>
          <List
            loading={opsLoading}
            dataSource={operations}
            locale={{ emptyText: '该工单没有工序' }}
            renderItem={(operation) => {
              const waitingSop =
                pendingSop?.workOrderId === selected.id && pendingSop.operationId === operation.id;
              const selectedRow = operation.id === selectedOperationId;
              return (
                <List.Item
                  style={{
                    cursor: 'pointer',
                    background: selectedRow ? '#e6f4ff' : undefined,
                  }}
                  onClick={() => {
                    setSelectedOperationId(operation.id);
                    onSelectionChange?.({ workOrderId: selected.id, operationId: operation.id });
                  }}
                >
                  <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <div style={{ fontSize: 18 }}>
                      {operation.sequence}. {operation.name || operation.code || `工序 ${operation.id}`}
                      <span style={{ marginLeft: 12 }}>
                        {statusText(operation.status, OPERATION_STATUS_LABEL)}
                      </span>
                      <span style={{ marginLeft: 12 }}>
                        上下机 {operation.machineSessionState || 'none'}
                      </span>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                      <Button
                        size="large"
                        type="primary"
                        disabled={busy}
                        onClick={() => void runStart(operation, false)}
                      >
                        开工
                      </Button>
                      {waitingSop ? (
                        <Button
                          size="large"
                          type="primary"
                          disabled={busy}
                          onClick={() => void confirmSopAndStart(operation)}
                        >
                          确认 SOP 并开工
                        </Button>
                      ) : null}
                      <Button
                        size="large"
                        disabled={busy}
                        onClick={() =>
                          void runAction(
                            () => withdrawOperationStart(selected.id, operation.id),
                            '已撤回开工',
                          )
                        }
                    >
                      撤回开工
                    </Button>
                    <Button size="large" disabled={busy} onClick={() => setPauseFor(operation.id)}>
                      暂停
                    </Button>
                    <Button
                      size="large"
                      disabled={busy}
                      onClick={() =>
                        void runAction(
                          () => resumeOperation(selected.id, operation.id),
                          '已恢复',
                        )
                      }
                    >
                      恢复
                    </Button>
                    <Button
                      size="large"
                      disabled={busy}
                      onClick={() =>
                        void runAction(
                          () => completeOperation(selected.id, operation.id),
                          '已结束',
                        )
                      }
                    >
                      结束
                    </Button>
                    <Button
                      size="large"
                      disabled={busy}
                      onClick={() =>
                        void runAction(
                          () => setMachineSession(selected.id, operation.id, 'on'),
                          '已上机',
                        )
                      }
                    >
                      上机
                    </Button>
                    <Button
                      size="large"
                      disabled={busy}
                      onClick={() =>
                        void runAction(
                          () => setMachineSession(selected.id, operation.id, 'off'),
                          '已下机',
                        )
                      }
                    >
                        下机
                      </Button>
                    </div>
                    {pauseFor === operation.id ? (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                        {DOWNTIME_REASONS.map((reason) => (
                          <Button
                            key={reason.code}
                            size="large"
                            disabled={busy}
                            onClick={() =>
                              void runAction(
                                () =>
                                  pauseOperation(selected.id, operation.id, reason.code, stationId),
                                stationId == null
                                  ? `已暂停（${reason.label}）。入口未绑定工位，请求未带 workstation_id`
                                  : `已暂停（${reason.label}）`,
                              )
                            }
                          >
                            {reason.label}
                          </Button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </List.Item>
              );
            }}
          />
        </div>
      ) : null}
    </div>
  );
}
