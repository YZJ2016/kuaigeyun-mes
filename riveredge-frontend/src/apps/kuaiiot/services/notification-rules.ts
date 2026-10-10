import { apiRequest } from '../../../services/api';

export function loadKuaiiotNotificationRulePresets(): Promise<{
  created: number;
  updated: number;
  repaired_templates?: number;
  templates_created?: number;
  skipped_duplicate: number;
  skipped_missing_template: number;
  total_rules: number;
}> {
  return apiRequest('/apps/kuaiiot/config/notification-rules/load-presets', {
    method: 'POST',
  });
}
