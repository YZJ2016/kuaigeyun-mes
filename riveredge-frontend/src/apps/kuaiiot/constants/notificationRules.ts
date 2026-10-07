export const KUAIIOT_NOTIFICATION_DOCUMENT_OPTIONS = [
  { value: 'kuaiiot_alert', labelKey: 'kuaiiot.alert', fallback: '数采告警' },
];
export const KUAIIOT_NOTIFICATION_ACTION_OPTIONS = {
  kuaiiot_alert: [
    { value: 'raised', labelKey: 'kuaiiot.raised', fallback: '告警触发' },
    { value: 'recovered', labelKey: 'kuaiiot.recovered', fallback: '告警恢复' },
  ],
};
