/** WorkBuddy Sidecar 对外 MCP 地址：固定 https + `/mcp`（与租户保留路径一致） */

export const WORKBUDDY_MCP_PUBLIC_PATH = '/mcp';

const HOST_PATTERN =
  /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$|^(?:\d{1,3}\.){3}\d{1,3}$|^[a-z0-9.-]+:\d+$/i;

function stripInput(raw: string): string {
  let s = (raw || '').trim();
  if (!s) return '';
  if (/^https?:\/\//i.test(s)) {
    try {
      const u = new URL(s);
      if (u.pathname && u.pathname !== '/' && u.pathname.replace(/\/+$/, '') !== WORKBUDDY_MCP_PUBLIC_PATH) {
        throw new Error('invalid_path');
      }
      return u.host;
    } catch (e) {
      if ((e as Error).message === 'invalid_path') throw e;
      return s.replace(/^https?:\/\//i, '').split('/')[0];
    }
  }
  return s.split('/')[0].split('?')[0];
}

export function parseWorkbuddyMcpPublicHost(storedUrl: string | null | undefined): string {
  const raw = (storedUrl || '').trim();
  if (!raw) return '';
  return stripInput(raw);
}

export function buildWorkbuddyMcpPublicUrl(hostInput: string): string {
  const host = stripInput(hostInput).toLowerCase();
  if (!host) {
    throw new Error('empty');
  }
  if (host.includes('/') || host.includes('\\')) {
    throw new Error('invalid_host');
  }
  if (!HOST_PATTERN.test(host)) {
    throw new Error('invalid_host');
  }
  return `https://${host}${WORKBUDDY_MCP_PUBLIC_PATH}`;
}

export function validateWorkbuddyMcpPublicHostInput(
  hostInput: string | null | undefined,
): string | true {
  const host = (hostInput || '').trim();
  if (!host) return '请输入 MCP 域名';
  try {
    buildWorkbuddyMcpPublicUrl(host);
    return true;
  } catch {
    return '请输入有效域名（勿含路径；系统将自动使用 https 与 /mcp）';
  }
}
