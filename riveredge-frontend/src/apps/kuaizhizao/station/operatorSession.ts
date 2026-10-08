/**
 * 工位操作员会话：内存凭据 store 与确认/关闭/当前状态接口。
 *
 * 凭据只保存在页面内存（模块级变量）。绝不写入 localStorage/sessionStorage/cookie/Electron
 * 配置——刷新、Electron 重启、异常退出或断电恢复后天然丢失，必须重新刷脸或员工码确认。
 *
 * 本文件保持零静态运行时依赖（services/api 只在调用时动态引入），
 * 供 apiRequest、工位页面与 Node 纯函数测试共用。
 * 人脸特征、员工码明文与会话凭据不得写日志、toast 或持久存储。
 */

/** 工位业务请求显式 opt-in 后由 apiRequest 附加的业务凭据头。 */
export const STATION_OPERATOR_SESSION_HEADER = 'X-Station-Operator-Session';

const STATION_API = '/apps/kuaizhizao/station';

export type StationOperatorConfirmMethod = 'face' | 'employee_code';

export interface StationOperatorSessionInfo {
  id: number;
  uuid: string;
  workstation_id: number;
  workstation_name: string;
  operator_employee_id: number | null;
  operator_user_id: number;
  operator_name: string;
  confirm_method: StationOperatorConfirmMethod | string;
  status: string;
  issued_at: string;
  last_seen_at: string;
  closed_at: string | null;
  close_reason: string | null;
}

type Listener = () => void;

const listeners = new Set<Listener>();
let credential: string | null = null;
let session: StationOperatorSessionInfo | null = null;

function emit(): void {
  listeners.forEach((listener) => listener());
}

export function subscribeStationOperatorSession(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** 当前内存凭据；未确认或已清空时为 null。 */
export function getStationOperatorCredential(): string | null {
  return credential;
}

export function getStationOperatorSessionInfo(): StationOperatorSessionInfo | null {
  return session;
}

/** 是否已持有确认后的会话凭据。工位写动作以此判断可用性。 */
export function hasStationOperatorSession(): boolean {
  return credential != null && credential !== '';
}

/** 组装业务凭据头；无凭据返回空对象，调用方不附加也不报错（由服务端门禁拒绝）。 */
export function stationOperatorSessionHeaders(): Record<string, string> {
  return credential ? { [STATION_OPERATOR_SESSION_HEADER]: credential } : {};
}

/** 写方法判定（与 apiRequest 对齐：POST/PUT/PATCH/DELETE 算写）。 */
export function isWriteMethodForStationSession(method: string | undefined): boolean {
  const m = String(method || 'GET').toUpperCase();
  return m === 'POST' || m === 'PUT' || m === 'PATCH' || m === 'DELETE';
}

/**
 * apiRequest 的注入判定（纯函数，供 Node 测试直接覆盖）：
 * 仅调用方显式 opt-in 的请求附加凭据头（含需要操作员作用域的读取）；
 * 调用方已显式给同名头时不覆盖；无凭据不附加（由服务端门禁拒绝）。
 */
export function applyStationOperatorSessionHeader(
  headers: Record<string, string>,
  options?: { optIn?: boolean; method?: string },
): void {
  if (options?.optIn !== true) return;
  if (STATION_OPERATOR_SESSION_HEADER in headers) return;
  if (credential) {
    headers[STATION_OPERATOR_SESSION_HEADER] = credential;
  }
}

/** 确认接口签发凭据后登记到内存。凭据为空时忽略。 */
export function acceptStationOperatorSession(next: {
  credential: string;
  session: StationOperatorSessionInfo | null;
}): void {
  const value = typeof next.credential === 'string' ? next.credential.trim() : '';
  if (!value) return;
  credential = value;
  session = next.session ?? null;
  emit();
}

/** 清空内存凭据与会话信息（换人/退出/换工位/失败兜底）。 */
export function clearStationOperatorSession(): void {
  if (credential == null && session == null) return;
  credential = null;
  session = null;
  emit();
}

export type ConfirmStationOperatorInput = {
  workstationId: number;
  candidateUserId: number;
  confirmMethod: StationOperatorConfirmMethod;
  faceDescriptor?: number[];
  employeeCode?: string;
};

type ApiRequestOptions = {
  method?: string;
  data?: unknown;
  params?: Record<string, unknown>;
  headers?: Record<string, string>;
};

async function request<T>(url: string, options?: ApiRequestOptions): Promise<T> {
  // 动态引入避免与 services/api 形成静态循环，也让本文件可被 Node 纯函数测试直接加载。
  const { apiRequest } = await import('../../../services/api');
  return apiRequest<T>(url, options);
}

/**
 * 确认操作员：候选人与刷脸/员工码一致时服务端才签发会话。
 * 成功才写入内存凭据；失败原样抛出，由调用方统一给通用失败文案（不回显细节）。
 */
export async function confirmStationOperatorSession(
  input: ConfirmStationOperatorInput,
): Promise<StationOperatorSessionInfo> {
  const data: Record<string, unknown> = {
    workstation_id: input.workstationId,
    candidate_user_id: input.candidateUserId,
    confirm_method: input.confirmMethod,
  };
  if (Array.isArray(input.faceDescriptor) && input.faceDescriptor.length > 0) {
    data.face_descriptor = input.faceDescriptor;
  }
  const employeeCode = input.employeeCode?.trim();
  if (employeeCode) data.employee_code = employeeCode;
  const res = await request<{ credential?: string; session?: StationOperatorSessionInfo }>(
    `${STATION_API}/operator-session/confirm`,
    { method: 'POST', data },
  );
  const nextCredential = typeof res?.credential === 'string' ? res.credential.trim() : '';
  if (!nextCredential || !res.session) {
    throw new Error('operator session confirm failed');
  }
  acceptStationOperatorSession({ credential: nextCredential, session: res.session });
  return res.session;
}

/** 查询当前会话状态（GET，凭据经显式业务头携带）。无凭据直接返回 invalid。 */
export async function fetchCurrentStationOperatorSession(
  workstationId: number,
): Promise<{ valid: boolean; session: StationOperatorSessionInfo | null }> {
  const current = credential;
  if (!current) return { valid: false, session: null };
  const res = await request<{ valid?: boolean; session?: StationOperatorSessionInfo }>(
    `${STATION_API}/operator-session/current`,
    {
      method: 'GET',
      params: { workstation_id: workstationId },
      headers: { [STATION_OPERATOR_SESSION_HEADER]: current },
    },
  );
  return { valid: res?.valid === true, session: res?.session ?? null };
}

/** 显式换人/退出：通知服务端关闭；无论成败本地凭据都清空。reason 仅作为服务端关闭原因记录。 */
export async function closeStationOperatorSession(reason?: string): Promise<void> {
  const current = credential;
  if (!current) {
    clearStationOperatorSession();
    return;
  }
  try {
    await request<{ closed?: boolean }>(`${STATION_API}/operator-session/close`, {
      method: 'POST',
      headers: { [STATION_OPERATOR_SESSION_HEADER]: current },
      ...(reason ? { data: { reason } } : {}),
    });
  } finally {
    clearStationOperatorSession();
  }
}
