export function eligibleIotConnections<T extends { type: string; is_active: boolean }>(rows: T[], type: string): T[] {
  const types = type === 'http' ? ['API', 'api', 'Webhook'] : [type];
  return rows.filter(row => row.is_active && types.includes(row.type));
}

export function buildIotConnectionConfig(type: string, values: Record<string, unknown>): Record<string, unknown> {
  const keys: Record<string, string[]> = {
    mqtt: ['host', 'port', 'username', 'password', 'use_tls'],
    thingsboard: ['base_url', 'username', 'password'],
    jetlinks: ['base_url', 'token'],
  };
  if (!keys[type]) throw new Error('请选择 MQTT、ThingsBoard 或 JetLinks');
  return Object.fromEntries(keys[type].filter(key => values[key] !== undefined).map(key => [key, values[key]]));
}
