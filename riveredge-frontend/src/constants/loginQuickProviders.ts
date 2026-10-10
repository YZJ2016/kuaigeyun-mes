export type LoginQuickProviderId =

  | 'gitee'

  | 'wechat_work'

  | 'dingtalk'

  | 'feishu';



export type LoginQuickProvidersMap = Record<LoginQuickProviderId, boolean>;



/** 顺序即管理端开关与登录页图标顺序；Gitee 居首。 */

export const LOGIN_QUICK_PROVIDER_IDS: LoginQuickProviderId[] = [

  'gitee',

  'wechat_work',

  'dingtalk',

  'feishu',

];



export function defaultLoginQuickProviders(): LoginQuickProvidersMap {

  return {

    gitee: true,

    wechat_work: true,

    dingtalk: true,

    feishu: true,

  };

}



export function resolveLoginQuickProviders(

  raw?: Partial<LoginQuickProvidersMap> | null,

): LoginQuickProvidersMap {

  const merged = defaultLoginQuickProviders();

  if (!raw || typeof raw !== 'object') {

    return merged;

  }

  for (const id of LOGIN_QUICK_PROVIDER_IDS) {

    if (raw[id] !== undefined && raw[id] !== null) {

      merged[id] = Boolean(raw[id]);

    }

  }

  return merged;

}



export function isLoginQuickProviderEnabled(

  providers: Partial<LoginQuickProvidersMap> | null | undefined,

  providerId: LoginQuickProviderId,

): boolean {

  return resolveLoginQuickProviders(providers)[providerId];

}


