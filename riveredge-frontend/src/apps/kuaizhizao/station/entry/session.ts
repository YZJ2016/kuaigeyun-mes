/**
 * 工位入口的页面状态：已绑定工位、候选操作员与当前（已确认）操作员。
 * 不签发登录。终端账号会话仍是进入页面前的那一次登录。
 * 点选姓名只产生候选人；刷脸或员工码经服务端确认后才写入 operator
 * 并在 operatorSession 内存中登记凭据。
 */
import { useEffect, useState } from 'react';
import type { StationInfo } from '../../components/StationBinder';
import {
  clearStationOperatorSession,
  closeStationOperatorSession,
  hasStationOperatorSession,
  subscribeStationOperatorSession,
} from '../operatorSession';

export type StationOperator = {
  id: number;
  name: string;
};

type Listener = () => void;

const listeners = new Set<Listener>();
let workstation: StationInfo | null = null;
let operator: StationOperator | null = null;
let operatorCandidate: StationOperator | null = null;
let terminalAccountName = '';
let workOrderId: number | null = null;
let operationId: number | null = null;

function emit(): void {
  listeners.forEach((listener) => listener());
}

// 凭据变化（确认成功/清空）同样触发入口订阅，让 useStationEntrySnapshot
// 与 useStationWriteEnabled 及时刷新。
subscribeStationOperatorSession(emit);

export function subscribeStationEntry(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getStationWorkstation(): StationInfo | null {
  return workstation;
}

export function getStationOperator(): StationOperator | null {
  return operator;
}

export function getStationOperatorCandidate(): StationOperator | null {
  return operatorCandidate;
}

/** 点选姓名只置候选人，不产生业务归属；确认成功后由调用方清空。 */
export function setStationOperatorCandidate(next: StationOperator | null): void {
  operatorCandidate = next;
  emit();
}

export function getTerminalAccountName(): string {
  return terminalAccountName;
}

export function setTerminalAccountName(name: string): void {
  terminalAccountName = name;
  emit();
}

/**
 * 写入当前操作员。仅应在服务端确认成功后调用，不调用登录接口、不换令牌。
 * 置 null（显式换人/退出）时同步清空内存凭据。
 */
export function setStationOperator(next: StationOperator | null): void {
  operator = next;
  if (next == null) {
    clearStationOperatorSession();
  }
  emit();
}

export function getStationWorkOrderId(): number | null {
  return workOrderId;
}

export function getStationOperationId(): number | null {
  return operationId;
}

/** 执行页选中的工单与工序行。刷脸页只通过入口 props 读取。 */
export function setStationExecutionSelection(next: {
  workOrderId: number | null;
  operationId: number | null;
}): void {
  workOrderId = next.workOrderId;
  operationId = next.operationId;
  emit();
}

type StationShell = {
  setWorkstationId?: (workstationId: number) => void;
  getWorkstationId?: () => Promise<unknown>;
};

/** 壳已保存的工位 ID。没有窄接口或值不是正整数时返回 null。 */
export async function readShellWorkstationId(): Promise<number | null> {
  const shell = (window as Window & { stationShell?: StationShell }).stationShell;
  if (typeof shell?.getWorkstationId !== 'function') return null;
  try {
    const raw = await shell.getWorkstationId();
    const text = typeof raw === 'number' ? String(raw) : typeof raw === 'string' ? raw.trim() : '';
    if (!/^[1-9]\d*$/.test(text)) return null;
    const id = Number(text);
    return Number.isSafeInteger(id) ? id : null;
  } catch {
    return null;
  }
}

function notifyStationShell(workstationId: number): void {
  const shell = (window as Window & { stationShell?: StationShell }).stationShell;
  if (typeof shell?.setWorkstationId === 'function') {
    shell.setWorkstationId(workstationId);
  }
}

export function setStationWorkstation(
  next: StationInfo | null,
  options?: { notifyShell?: boolean },
): void {
  const changed = next?.stationId !== workstation?.stationId;
  workstation = next;
  // 会话绑定工位：换绑/解绑后旧凭据不再适用，候选人一并清掉
  if (changed) {
    // 清本地状态前先通知服务端关闭会话（不带 reason 记 explicit_close），
    // 避免遗留孤儿 active 行。无凭据时 closeStationOperatorSession 内部不发请求；
    // 失败不阻断重绑——本地凭据随后一律清空。
    void closeStationOperatorSession().catch(() => {});
    operator = null;
    operatorCandidate = null;
    workOrderId = null;
    operationId = null;
    clearStationOperatorSession();
  }
  if (options?.notifyShell && next && Number.isFinite(next.stationId)) {
    notifyStationShell(next.stationId);
  }
  emit();
}

export function useStationEntrySnapshot(): {
  workstation: StationInfo | null;
  operator: StationOperator | null;
  candidate: StationOperator | null;
  terminalAccountName: string;
  workOrderId: number | null;
  operationId: number | null;
} {
  const [, setTick] = useState(0);
  useEffect(() => subscribeStationEntry(() => setTick((n) => n + 1)), []);
  return {
    workstation: getStationWorkstation(),
    operator: getStationOperator(),
    candidate: getStationOperatorCandidate(),
    terminalAccountName: getTerminalAccountName(),
    workOrderId: getStationWorkOrderId(),
    operationId: getStationOperationId(),
  };
}

/**
 * 工位写动作可用性：已持有服务端确认的操作员会话凭据。
 * 未确认操作员时页面可读，写按钮禁用。
 */
export function useStationWriteEnabled(): boolean {
  const [, setTick] = useState(0);
  useEffect(() => subscribeStationEntry(() => setTick((n) => n + 1)), []);
  return hasStationOperatorSession();
}
