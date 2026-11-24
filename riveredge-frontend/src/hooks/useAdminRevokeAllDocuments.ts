import { useQuery } from '@tanstack/react-query';
import {
  getBusinessConfig,
  isAdminRevokeAllDocumentsEnabled,
} from '../services/businessConfig';

export const BUSINESS_CONFIG_ADMIN_REVOKE_QUERY_KEY = ['businessConfigAdminRevoke'] as const;

export function useBusinessConfigForAdminRevokeQuery() {
  return useQuery({
    queryKey: BUSINESS_CONFIG_ADMIN_REVOKE_QUERY_KEY,
    queryFn: getBusinessConfig,
    staleTime: 5 * 60 * 1000,
  });
}

/** 业务参数：系统管理员可反审全单据；未加载完成时默认 false */
export function useAdminRevokeAllDocuments(defaultValue = false): boolean {
  const { data } = useBusinessConfigForAdminRevokeQuery();
  if (data === undefined) return defaultValue;
  return isAdminRevokeAllDocumentsEnabled(data);
}