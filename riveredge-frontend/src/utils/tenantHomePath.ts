import {
  EFFECTIVE_HOME_QUERY_KEY,
  getEffectiveHome,
  getTenantBackendHome,
  TENANT_BACKEND_HOME_QUERY_KEY,
} from '../services/menu';
import { queryClient } from '../queryClient';
import { getTenantId, getToken } from './auth';
import { getDefaultTenantHomePath, getPersistedConfigs, resolveEffectiveHomePath, useConfigStore } from '../stores/configStore';

/** 登录后 / 切换租户落地路径（与 UniTabs 首位首页一致；须 await 后再 navigate，避免闪工作台/兜底页）。 */
export async function resolvePostLoginHomePath(configs?: Record<string, any> | null): Promise<string> {
  const effectiveConfigs = configs ?? getPersistedConfigs() ?? useConfigStore.getState().configs ?? {};
  const tenantIdStr = getTenantId()?.toString() ?? null;

  if (tenantIdStr && getToken()) {
    try {
      const [effectiveHome, tenantBackendHome] = await Promise.all([
        queryClient.fetchQuery({
          queryKey: [...EFFECTIVE_HOME_QUERY_KEY, tenantIdStr],
          queryFn: getEffectiveHome,
          staleTime: 60 * 1000,
        }),
        queryClient.fetchQuery({
          queryKey: [...TENANT_BACKEND_HOME_QUERY_KEY, tenantIdStr],
          queryFn: getTenantBackendHome,
          staleTime: 60 * 1000,
        }),
      ]);
      return resolveEffectiveHomePath(effectiveHome, tenantBackendHome?.path, effectiveConfigs);
    } catch {
      return resolveEffectiveHomePath(null, null, effectiveConfigs);
    }
  }

  try {
    const effectiveHome = await getEffectiveHome();
    return resolveEffectiveHomePath(effectiveHome, null, effectiveConfigs);
  } catch {
    return resolveEffectiveHomePath(null, null, effectiveConfigs);
  }
}

/** 显式 redirect 或 API 不可用时的本地回退（不含自定义首页） */
export function getImmediatePostLoginHomePath(redirect?: string | null): string {
  const r = redirect?.trim();
  if (r) return r;
  return getDefaultTenantHomePath();
}

/** 登录 / 切租户：无 redirect 时解析有效首页；有 redirect 时原样使用 */
export async function resolvePostLoginNavigatePath(redirect?: string | null): Promise<string> {
  const r = redirect?.trim();
  if (r) return r;
  return resolvePostLoginHomePath();
}
