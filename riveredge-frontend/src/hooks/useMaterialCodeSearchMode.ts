import { useQuery } from '@tanstack/react-query';
import {
  getBusinessConfig,
  resolveMaterialCodeSearchMode,
  type MaterialCodeSearchMode,
} from '../services/businessConfig';
import { MATERIAL_QUICK_CREATE_ALLOWED_QUERY_KEY } from './useMaterialQuickCreateAllowed';

/** 与配置中心共用 businessConfig 缓存 */
export function useMaterialCodeSearchMode(): MaterialCodeSearchMode {
  const { data } = useQuery({
    queryKey: MATERIAL_QUICK_CREATE_ALLOWED_QUERY_KEY,
    queryFn: getBusinessConfig,
    staleTime: 5 * 60 * 1000,
  });
  return resolveMaterialCodeSearchMode(data);
}