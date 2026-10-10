import React from 'react';
import { Button, Tooltip } from 'antd';
import type { TFunction } from 'i18next';
import {
  isLoginQuickProviderEnabled,
  type LoginQuickProviderId,
  type LoginQuickProvidersMap,
} from '../../../constants/loginQuickProviders';

type SocialIconKey = 'gitee' | 'qwei' | 'dingtalk' | 'feishu';

type ProviderConfig = {
  id: LoginQuickProviderId;
  iconKey: SocialIconKey;
  className: string;
  labelKey: string;
  enabledBg: string;
  enabledBorder: string;
  hoverBg: string;
  hoverBorder: string;
};

const PROVIDERS: ProviderConfig[] = [
  {
    id: 'gitee',
    iconKey: 'gitee',
    className: 'social-login-btn-gitee',
    labelKey: 'pages.login.giteeLogin',
    enabledBg: 'rgba(199, 29, 35, 0.75)',
    enabledBorder: 'rgba(199, 29, 35, 0.75)',
    hoverBg: '#C71D23',
    hoverBorder: '#C71D23',
  },
  {
    id: 'wechat_work',
    iconKey: 'qwei',
    className: 'social-login-btn-wechat-work',
    labelKey: 'pages.login.wechatWorkLogin',
    enabledBg: 'rgba(120, 195, 64, 0.5)',
    enabledBorder: 'rgba(120, 195, 64, 0.5)',
    hoverBg: '#78C340',
    hoverBorder: '#78C340',
  },
  {
    id: 'dingtalk',
    iconKey: 'dingtalk',
    className: 'social-login-btn-dingtalk',
    labelKey: 'pages.login.dingtalkLogin',
    enabledBg: 'rgba(0, 117, 255, 0.5)',
    enabledBorder: 'rgba(0, 117, 255, 0.5)',
    hoverBg: '#0075FF',
    hoverBorder: '#0075FF',
  },
  {
    id: 'feishu',
    iconKey: 'feishu',
    className: 'social-login-btn-feishu',
    labelKey: 'pages.login.feishuLogin',
    enabledBg: 'rgba(51, 112, 255, 0.5)',
    enabledBorder: 'rgba(51, 112, 255, 0.5)',
    hoverBg: '#3370FF',
    hoverBorder: '#3370FF',
  },
];

const DISABLED_BG = 'rgba(0, 0, 0, 0.06)';
const DISABLED_BORDER = 'rgba(0, 0, 0, 0.06)';

export type LoginQuickSocialButtonsProps = {
  socialIcons: Partial<Record<SocialIconKey, string>>;
  providers: Partial<LoginQuickProvidersMap> | null | undefined;
  onSocialLogin: (provider: LoginQuickProviderId) => void;
  t: TFunction;
};

const LoginQuickSocialButtons: React.FC<LoginQuickSocialButtonsProps> = ({
  socialIcons,
  providers,
  onSocialLogin,
  t,
}) => (
  <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
    {PROVIDERS.map((provider) => {
      const enabled = isLoginQuickProviderEnabled(providers, provider.id);
      const iconSrc = socialIcons[provider.iconKey];
      const tooltipTitle = enabled ? t(provider.labelKey) : t('pages.login.quickLoginNotEnabled');

      return (
        <Tooltip key={provider.id} title={tooltipTitle}>
          <Button
            type="default"
            shape="circle"
            size="large"
            disabled={!enabled}
            onClick={() => {
              if (enabled) {
                onSocialLogin(provider.id);
              }
            }}
            className={`social-login-btn ${provider.className}${enabled ? '' : ' social-login-btn--disabled'}`}
            style={{
              width: '40px',
              height: '40px',
              flexShrink: 0,
              backgroundColor: enabled ? provider.enabledBg : DISABLED_BG,
              borderColor: enabled ? provider.enabledBorder : DISABLED_BORDER,
              borderWidth: '0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: 0,
              transition: 'all 0.3s ease',
            }}
            onMouseEnter={(e) => {
              if (!enabled) {
                return;
              }
              e.currentTarget.style.backgroundColor = provider.hoverBg;
              e.currentTarget.style.borderColor = provider.hoverBorder;
            }}
            onMouseLeave={(e) => {
              if (!enabled) {
                return;
              }
              e.currentTarget.style.backgroundColor = provider.enabledBg;
              e.currentTarget.style.borderColor = provider.enabledBorder;
            }}
          >
            {iconSrc && (
              <img
                src={iconSrc}
                alt={t(provider.labelKey)}
                style={{
                  width: '24px',
                  height: '24px',
                  filter: enabled ? 'brightness(0) invert(1)' : 'grayscale(1) opacity(0.45)',
                }}
              />
            )}
          </Button>
        </Tooltip>
      );
    })}
  </div>
);

export default LoginQuickSocialButtons;
