import { useQuery } from '@tanstack/react-query';
import {
  getBusinessConfig,
  isMaterialQuickCreateAllowed,
} from '../services/businessConfig';

/** 与配置中心共用 businessConfig 缓存，保存后即时生效 */
export const MATERIAL_QUICK_CREATE_ALLOWED_QUERY_KEY = ['businessConfig'] as const;

/** 读取业务配置：是否允许单据内「快速新增物料」 */
export function useMaterialQuickCreateAllowedQuery() {
  return useQuery({
    queryKey: MATERIAL_QUICK_CREATE_ALLOWED_QUERY_KEY,
    queryFn: getBusinessConfig,
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * 单据物料下拉是否显示快速新增。
 * 未加载完成时默认 true，避免配置接口慢时闪断入口。
 */
export function useMaterialQuickCreateAllowed(defaultValue = true): boolean {
  const { data } = useMaterialQuickCreateAllowedQuery();
  if (data === undefined) return defaultValue;
  return isMaterialQuickCreateAllowed(data);
}
