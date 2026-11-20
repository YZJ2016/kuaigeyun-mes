/**
 * 系统配置列表展示：启用/类型/标识 → MarkerTag；流程/登录/备份等状态 → StatusTag。
 * 系统级多为配置主数据：业务列不堆叠（与主数据 plants 一致）；审计叠列另议。
 */
import { useEffect, useState } from 'react';
import type { TFunction } from 'i18next';
import { Avatar, Tooltip, theme } from 'antd';
import { MarkerTag, StatusTag } from '../../../constants/statusBadges';
import {
  getAvatarFontSize,
  getAvatarText,
  getAvatarUrl,
  getCachedAvatarUrl,
  getImageAvatarCircleStyle,
  getTextAvatarCircleStyle,
  isTextAvatarDisplay,
} from '../../../utils/avatar';
import type { UserOauthBindings } from '../../../services/user';
import wecomLogo from '../../../assets/social/qwei.svg';
import dingtalkLogo from '../../../assets/social/dingtalk.svg';
import feishuLogo from '../../../assets/social/feishu.svg';

const OAUTH_BIND_ICON_ITEMS: Array<{
  key: keyof UserOauthBindings;
  src: string;
  color: string;
  titleKey: string;
}> = [
  {
    key: 'wecom',
    src: wecomLogo,
    color: '#78C340',
    titleKey: 'field.user.oauthBoundWecom',
  },
  {
    key: 'dingtalk',
    src: dingtalkLogo,
    color: '#0075FF',
    titleKey: 'field.user.oauthBoundDingtalk',
  },
  {
    key: 'feishu',
    src: feishuLogo,
    color: '#3370FF',
    titleKey: 'field.user.oauthBoundFeishu',
  },
];

/** 用户名旁：已绑定企微/钉钉/飞书时显示小品牌图标 */
export function UserOauthBindingIcons({
  bindings,
  t,
}: {
  bindings?: UserOauthBindings | null;
  t: TFunction;
}) {
  if (!bindings) {
    return null;
  }
  const items = OAUTH_BIND_ICON_ITEMS.filter((item) => Boolean(bindings[item.key]));
  if (items.length === 0) {
    return null;
  }
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        flexShrink: 0,
        marginLeft: 6,
        verticalAlign: 'middle',
      }}
    >
      {items.map((item) => (
        <Tooltip key={item.key} title={t(item.titleKey)}>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 16,
              height: 16,
              borderRadius: '50%',
              background: item.color,
              flexShrink: 0,
            }}
          >
            <img
              src={item.src}
              alt=""
              width={10}
              height={10}
              style={{ display: 'block', objectFit: 'contain' }}
            />
          </span>
        </Tooltip>
      ))}
    </span>
  );
}

export function SystemUserAvatar({
  avatarUuid,
  fullName,
  username,
  size = 32,
}: {
  avatarUuid?: string | null;
  fullName?: string;
  username?: string;
  size?: number;
}) {
  const { token } = theme.useToken();
  const [src, setSrc] = useState<string | undefined>(() =>
    avatarUuid ? getCachedAvatarUrl(avatarUuid) : undefined,
  );
  const [imageFailed, setImageFailed] = useState(false);

  useEffect(() => {
    setImageFailed(false);
    if (!avatarUuid) {
      setSrc(undefined);
      return;
    }
    const cached = getCachedAvatarUrl(avatarUuid);
    if (cached) {
      setSrc(cached);
      return;
    }
    let cancelled = false;
    getAvatarUrl(avatarUuid)
      .then((url) => {
        if (!cancelled) setSrc(url);
      })
      .catch(() => {
        if (!cancelled) setSrc(undefined);
      });
    return () => {
      cancelled = true;
    };
  }, [avatarUuid]);

  const textAvatar = isTextAvatarDisplay(src, imageFailed);

  return (
    <Avatar
      size={size}
      src={textAvatar ? undefined : src}
      onError={() => {
        setImageFailed(true);
        return false;
      }}
      style={{
        ...(textAvatar ? getTextAvatarCircleStyle(token) : getImageAvatarCircleStyle()),
        flexShrink: 0,
        fontSize: getAvatarFontSize(size),
      }}
    >
      {textAvatar ? getAvatarText(fullName, username) : null}
    </Avatar>
  );
}

export function renderSystemActiveTag(
  t: TFunction,
  isActive?: boolean | null,
  enabledKey = 'common.enabled',
  disabledKey = 'common.disabled',
) {
  return (
    <MarkerTag color={isActive ? 'success' : 'default'}>
      {isActive ? t(enabledKey) : t(disabledKey)}
    </MarkerTag>
  );
}

export function renderSystemTypeMarker(label: string, color: string = 'processing') {
  const text = String(label ?? '').trim();
  if (!text) return '-';
  return <MarkerTag color={color}>{text}</MarkerTag>;
}

export function renderSystemYesNoTag(
  t: TFunction,
  value?: boolean | null,
  yesKey = 'common.yes',
  noKey = 'common.no',
) {
  return (
    <MarkerTag color={value ? 'processing' : 'default'}>
      {value ? t(yesKey) : t(noKey)}
    </MarkerTag>
  );
}

/** 审批实例 / 登录结果 / 备份任务等流程态 */
export function renderSystemStatusTag(label: string, color: string = 'default') {
  const text = String(label ?? '').trim();
  if (!text) return '-';
  return <StatusTag color={color}>{text}</StatusTag>;
}
