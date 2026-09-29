/**
 * 工位入口的页面状态：已绑定工位与当前操作员。
 * 不签发登录。终端账号会话仍是进入页面前的那一次登录。
 */
import { useEffect, useState } from 'react';
import type { StationInfo } from '../../components/StationBinder';

export type StationOperator = {
  id: number;
  name: string;
};

type Listener = () => void;

const listeners = new Set<Listener>();
let workstation: StationInfo | null = null;
let operator: StationOperator | null = null;
let terminalAccountName = '';
let workOrderId: number | null = null;
let operationId: number | null = null;

function emit(): void {
  listeners.forEach((listener) => listener());
}

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

export function getTerminalAccountName(): string {
  return terminalAccountName;
}

export function setTerminalAccountName(name: string): void {
  terminalAccountName = name;
  emit();
}

/** 点选或刷脸比对只改当前操作员，不调用登录接口，不换令牌。 */
export function setStationOperator(next: StationOperator | null): void {
  operator = next;
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
  workstation = next;
  if (options?.notifyShell && next && Number.isFinite(next.stationId)) {
    notifyStationShell(next.stationId);
  }
  emit();
}

export function useStationEntrySnapshot(): {
  workstation: StationInfo | null;
  operator: StationOperator | null;
  terminalAccountName: string;
  workOrderId: number | null;
  operationId: number | null;
} {
  const [, setTick] = useState(0);
  useEffect(() => subscribeStationEntry(() => setTick((n) => n + 1)), []);
  return {
    workstation: getStationWorkstation(),
    operator: getStationOperator(),
    terminalAccountName: getTerminalAccountName(),
    workOrderId: getStationWorkOrderId(),
    operationId: getStationOperationId(),
  };
}
