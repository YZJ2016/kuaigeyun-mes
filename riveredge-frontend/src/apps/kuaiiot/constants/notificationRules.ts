/** 快数采（kuaiiot）业务消息提醒单据类型 */

export const KUAIIOT_NOTIFICATION_DOCUMENT_OPTIONS = [
  {
    value: 'iot_alert',
    labelKey: 'pages.system.configCenter.notification.document.iot_alert',
    fallback: '设备告警',
  },
] as const;

export const KUAIIOT_NOTIFICATION_ACTION_OPTIONS: Record<
  string,
  Array<{ value: string; labelKey: string; fallback: string }>
> = {
  iot_alert: [
    {
      value: 'threshold_breached',
      labelKey: 'pages.system.configCenter.notification.action.iot_alert.threshold_breached',
      fallback: '阈值触发',
    },
    {
      value: 'device_offline',
      labelKey: 'pages.system.configCenter.notification.action.iot_alert.device_offline',
      fallback: '设备离线',
    },
  ],
};
