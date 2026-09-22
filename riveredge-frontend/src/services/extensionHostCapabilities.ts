import { apiRequest } from './api';

export type ExtensionHostCapability = {
  capability: string;
  module_app_code: string;
  extension_id: string;
  fetch_path?: string;
  navigation_path?: string;
  post_paths?: Record<string, string>;
};

type HostCapabilitiesResponse = {
  items: ExtensionHostCapability[];
  total: number;
};

let cachedCapabilities: ExtensionHostCapability[] | null = null;

export async function listExtensionHostCapabilities(
  options?: { refresh?: boolean },
): Promise<ExtensionHostCapability[]> {
  if (!options?.refresh && cachedCapabilities) {
    return cachedCapabilities;
  }
  const res = (await apiRequest('/core/applications/industry-extensions/host-capabilities', {
    method: 'GET',
  })) as HostCapabilitiesResponse;
  cachedCapabilities = Array.isArray(res.items) ? res.items : [];
  return cachedCapabilities;
}

export async function findHostCapability(
  capability: string,
): Promise<ExtensionHostCapability | undefined> {
  const items = await listExtensionHostCapabilities();
  return items.find((item) => item.capability === capability);
}

export async function fetchHostCapabilityData<T>(
  capability: string,
): Promise<T | null> {
  const cap = await findHostCapability(capability);
  if (!cap?.fetch_path) {
    return null;
  }
  return (await apiRequest(cap.fetch_path, { method: 'GET' })) as T;
}

export async function postHostCapabilityAction<T>(
  capability: string,
  action: string,
  body?: unknown,
): Promise<T | null> {
  const cap = await findHostCapability(capability);
  const path = cap?.post_paths?.[action];
  if (!path) {
    return null;
  }
  return (await apiRequest(path, {
    method: 'POST',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })) as T;
}
