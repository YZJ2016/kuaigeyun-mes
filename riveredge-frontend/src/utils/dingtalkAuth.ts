/** 钉钉 OAuth state 本地校验与解码（与后端 encode_dingtalk_oauth_state 对齐）。 */

const STORAGE_KEY = 'dingtalk_oauth_state';

export function saveDingtalkOAuthState(state: string): void {
  sessionStorage.setItem(STORAGE_KEY, state);
}

export function consumeDingtalkOAuthState(expected: string): boolean {
  const saved = sessionStorage.getItem(STORAGE_KEY);
  sessionStorage.removeItem(STORAGE_KEY);
  return !!saved && saved === expected;
}

export function decodeDingtalkOAuthState(
  state: string,
): { tenant_id: number; redirect: string; redirect_uri: string } | null {
  if (!state) {
    return null;
  }
  try {
    const padded = state + '='.repeat((4 - (state.length % 4)) % 4);
    const raw = atob(padded.replace(/-/g, '+').replace(/_/g, '/'));
    const payload = JSON.parse(raw) as { t?: unknown; r?: unknown; u?: unknown };
    const tenantId = Number(payload.t);
    if (!Number.isFinite(tenantId) || tenantId <= 0) {
      return null;
    }
    const redirectUri = typeof payload.u === 'string' ? payload.u.trim() : '';
    if (!redirectUri) {
      return null;
    }
    return {
      tenant_id: tenantId,
      redirect: typeof payload.r === 'string' ? payload.r.trim() : '',
      redirect_uri: redirectUri,
    };
  } catch {
    return null;
  }
}
