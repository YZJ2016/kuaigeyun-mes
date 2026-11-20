/** 接口库：接口类型（与后端 api_interface_type 一致） */
export type ApiInterfaceType = 'standard' | 'custom';

export const API_INTERFACE_TYPE_OPTIONS: { labelKey: string; value: ApiInterfaceType }[] = [
  { labelKey: 'pages.system.apis.apiInterfaceType.standard', value: 'standard' },
  { labelKey: 'pages.system.apis.apiInterfaceType.custom', value: 'custom' },
];
