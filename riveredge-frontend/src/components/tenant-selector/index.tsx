/**
 * 组织选择器组件
 *
 * 平台超级管理员可切换任意租户
 * 普通用户在账号属于多个租户时也可切换
 *
 * 平台超管的组织名不来自 /auth/me，真源是组织列表 / 当前组织详情；
 * 软切换 queryClient.clear 不得把这份非租户数据冲掉（见 applyTenantSwitch）。
 */

import React from 'react';
import { Select, Spin, message, theme } from 'antd';
import { SwapOutlined } from '@ant-design/icons';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { getTenantList, TenantStatus } from '../../services/tenant';
import {
  getMyTenants,
  setDefaultTenant,
  switchTenant,
  tenantNameFromLoginResponse,
  type TenantSwitchOption,
} from '../../services/auth';
import { setTenantId, getTenantId, isInfraSuperAdminUser, setToken, setUserInfo } from '../../utils/auth';
import {
  applyTenantSwitchSideEffects,
  prepareTenantSwitchNetwork,
} from '../../utils/applyTenantSwitch';
import { isRequestCancellation } from '../../utils/requestCancellation';
import { useGlobalStore } from '../../stores';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { MarkerTag } from '../../constants/statusBadges';
import TenantSelectionModal from '../tenant-selection-modal';
import './index.less';

interface TenantOption {
  id: number;
  name: string;
  /** 多账户登录默认进入组织 */
  isDefault?: boolean;
  domain?: string;
  status?: string;
}

interface TenantSelectorProps {
  /** 顶栏为深色背景时传 true，用于强制浅色文字 */
  headerLightText?: boolean;
}

/** 已从 API 确认过的组织名（跨 clear 的进程内缓存，禁止用 id 冒充名称） */
const knownTenantLabels = new Map<string, string>();

function rememberTenantLabel(id: string | number | null | undefined, name: string | undefined | null) {
  const idStr = id != null ? String(id) : '';
  const label = typeof name === 'string' ? name.trim() : '';
  if (!idStr || !label) return;
  knownTenantLabels.set(idStr, label);
}

function mapMyTenantsToOptions(tenants: TenantSwitchOption[]): TenantOption[] {
  return tenants
    .map((tenant) => ({
      id: Number(tenant.id),
      name: tenant.name,
      isDefault: tenant.is_default === true,
      domain: tenant.domain,
      status: tenant.status,
    }))
    .sort((a, b) => a.id - b.id);
}

/** 下拉可视高度：约 11 行选项（主+子演示组织一屏内看完） */
const TENANT_SELECTOR_LIST_HEIGHT = 11 * 32;

const SET_DEFAULT_OPTION_VALUE = '__set_login_default__';
/** 独立分隔行：勿把 border 画在「设置默认组织」选项内，否则 hover 背景会连分割线一起盖住 */
const SET_DEFAULT_DIVIDER_VALUE = '__set_login_default_divider__';

/**
 * 组织选择器组件
 */
const TenantSelector: React.FC<TenantSelectorProps> = ({ headerLightText }) => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const currentUser = useCurrentUser();
  const setCurrentUser = useGlobalStore((s) => s.setCurrentUser);
  const isInfraSuperAdmin = isInfraSuperAdminUser(currentUser);
  const currentTenantId = currentUser?.tenant_id ?? getTenantId();
  const [switching, setSwitching] = React.useState(false);
  const [setDefaultModalOpen, setSetDefaultModalOpen] = React.useState(false);
  const [settingDefaultId, setSettingDefaultId] = React.useState<number | null>(null);
  const switchingRef = React.useRef(false);
  const optionsErrorNotifiedRef = React.useRef(false);
  /** 多组织切换能力：queryClient.clear 后 options 短暂为空时仍保持 Select，避免退回只读胶囊 */
  const [canSwitch, setCanSwitch] = React.useState(isInfraSuperAdmin);

  const {
    data: tenantOptions = [],
    isLoading,
    isFetching,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['tenant-selector-options', isInfraSuperAdmin],
    queryFn: async (): Promise<TenantOption[]> => {
      if (isInfraSuperAdmin) {
        const resp = await getTenantList(
          {
            page: 1,
            page_size: 100,
            status: TenantStatus.ACTIVE,
            sort: 'id',
            order: 'asc',
          },
          true,
        );
        return resp.items
          .map((tenant) => ({ id: Number(tenant.id), name: tenant.name }))
          .sort((a, b) => a.id - b.id);
      }
      return mapMyTenantsToOptions(await getMyTenants());
    },
    enabled: !!currentUser,
  });

  React.useEffect(() => {
    if (isInfraSuperAdmin || tenantOptions.length > 1) {
      setCanSwitch(true);
      return;
    }
    if (!isFetching && !isLoading && !isError && tenantOptions.length <= 1) {
      setCanSwitch(false);
    }
  }, [isInfraSuperAdmin, tenantOptions.length, isFetching, isLoading, isError]);

  React.useEffect(() => {
    if (!isError) {
      optionsErrorNotifiedRef.current = false;
      return;
    }
    if (isRequestCancellation(error) || optionsErrorNotifiedRef.current) return;
    optionsErrorNotifiedRef.current = true;
    message.error(t('ui.message.tenantOptionsLoadFailed'));
  }, [isError, error, t]);

  const currentTenantIdStr = currentTenantId != null ? String(currentTenantId) : undefined;
  const currentTenantName = currentUser?.tenant_name?.trim() || '';

  React.useEffect(() => {
    for (const tenant of tenantOptions) {
      rememberTenantLabel(tenant.id, tenant.name);
    }
    rememberTenantLabel(currentTenantIdStr, currentTenantName);
  }, [tenantOptions, currentTenantIdStr, currentTenantName]);

  /** Select 选项：string label，避免 antd6 对 Option 子节点取标失败而回显 value（如 "1"） */
  const selectOptions = (() => {
    const mapped = tenantOptions.map((tenant) => ({
      value: String(tenant.id),
      label: tenant.name,
      isDefault: tenant.isDefault === true,
    }));
    if (
      currentTenantIdStr &&
      !mapped.some((option) => option.value === currentTenantIdStr)
    ) {
      const cached =
        currentTenantName || knownTenantLabels.get(currentTenantIdStr) || '';
      if (cached) {
        mapped.push({ value: currentTenantIdStr, label: cached, isDefault: false });
      }
    }
    return mapped.sort((a, b) => Number(a.value) - Number(b.value));
  })();

  const canManageLoginDefault = !isInfraSuperAdmin && selectOptions.length > 1;

  const selectOptionsWithFooter = canManageLoginDefault
    ? [
        ...selectOptions,
        {
          value: SET_DEFAULT_DIVIDER_VALUE,
          label: '',
          disabled: true,
          className: 'tenant-selector-default-divider',
        },
        {
          value: SET_DEFAULT_OPTION_VALUE,
          label: t('ui.action.setDefaultTenantEntry'),
          isDefault: false,
          className: 'tenant-selector-set-default-option',
        },
      ]
    : selectOptions;

  const defaultModalTenants = tenantOptions
    .filter((tenant) => Number.isFinite(tenant.id) && tenant.id > 0)
    .map((tenant) => ({
      id: tenant.id,
      name: tenant.name,
      domain: tenant.domain || '-',
      status: tenant.status || 'active',
      is_default: tenant.isDefault === true,
    }));

  const currentDefaultTenantId = tenantOptions.find((tenant) => tenant.isDefault)?.id;

  const resolveTenantLabel = (
    value: string | number | null | undefined,
    label?: React.ReactNode,
  ): string | undefined => {
    if (typeof label === 'string' && label.trim()) {
      return label.trim();
    }
    if (value == null) return undefined;
    const valueStr = String(value);
    const fromOptions = selectOptions.find((option) => option.value === valueStr)?.label?.trim();
    if (fromOptions) return fromOptions;
    if (valueStr === currentTenantIdStr && currentTenantName) {
      return currentTenantName;
    }
    return knownTenantLabels.get(valueStr);
  };

  const handleSetLoginDefault = async (tenantId: number | null) => {
    if (!canManageLoginDefault || settingDefaultId != null) return;
    try {
      setSettingDefaultId(tenantId ?? -1);
      const updated = await setDefaultTenant(tenantId);
      queryClient.setQueryData(
        ['tenant-selector-options', isInfraSuperAdmin],
        mapMyTenantsToOptions(updated),
      );
      message.success(
        tenantId == null
          ? t('ui.message.clearDefaultTenantSuccess')
          : t('ui.message.setDefaultTenantSuccess'),
      );
      setSetDefaultModalOpen(false);
    } catch (err: unknown) {
      if (!isRequestCancellation(err)) {
        const msg = err instanceof Error ? err.message : t('ui.message.setDefaultTenantFailed');
        message.error(msg);
      }
    } finally {
      setSettingDefaultId(null);
    }
  };

  const handleTenantChange = async (tenantId: string) => {
    if (tenantId === SET_DEFAULT_DIVIDER_VALUE) {
      return;
    }
    if (tenantId === SET_DEFAULT_OPTION_VALUE) {
      setSetDefaultModalOpen(true);
      return;
    }

    const nextId = Number(tenantId);
    if (!Number.isFinite(nextId) || nextId === currentTenantId || switchingRef.current) return;

    try {
      switchingRef.current = true;
      setSwitching(true);
      // 先掐断旧组织在途请求，再换票/清缓存，避免与壳层重拉叠满连接池导致 502
      prepareTenantSwitchNetwork();

      if (isInfraSuperAdmin) {
        const selected = tenantOptions.find((tenant) => Number(tenant.id) === nextId);
        const nextName = selected?.name || resolveTenantLabel(nextId) || '';
        if (!nextName) {
          throw new Error(t('ui.message.tenantNameUnavailable'));
        }
        rememberTenantLabel(nextId, nextName);
        setTenantId(nextId);
        const nextUser = {
          ...(currentUser || {}),
          tenant_id: nextId,
          tenant_name: nextName,
        };
        setCurrentUser(nextUser as any);
        setUserInfo(nextUser);
        message.success(t('ui.message.switchedTenant'));
        await applyTenantSwitchSideEffects(queryClient, navigate);
        return;
      }

      const response = await switchTenant(nextId);
      setToken(response.access_token);
      const selectedTenantId = response.user?.tenant_id || response.default_tenant_id || nextId;
      setTenantId(selectedTenantId);
      const tenantName = tenantNameFromLoginResponse(response);
      if (!tenantName) {
        throw new Error(t('ui.message.tenantNameUnavailable'));
      }
      rememberTenantLabel(selectedTenantId, tenantName);
      const nextUser = {
        ...(currentUser || {}),
        ...(response.user || {}),
        tenant_id: selectedTenantId,
        tenant_name: tenantName,
      };
      setCurrentUser(nextUser as any);
      setUserInfo(nextUser);
      message.success(t('ui.message.switchedTenant'));
      await applyTenantSwitchSideEffects(queryClient, navigate);
    } catch (err: any) {
      if (!isRequestCancellation(err)) {
        const status = err?.response?.status;
        const msg =
          status === 502 || status === 503 || status === 504
            ? t('errors.serviceUnreachable.content')
            : err?.message || t('pages.login.tenantSelectFailed');
        message.error(msg);
      }
    } finally {
      switchingRef.current = false;
      setSwitching(false);
    }
  };

  // 平台超管：有列表后补齐当前组织名；无当前组织时自动选第一个
  React.useEffect(() => {
    if (!isInfraSuperAdmin || tenantOptions.length === 0) return;

    if (!currentTenantId) {
      const firstTenant = tenantOptions[0];
      const firstId = Number(firstTenant.id);
      rememberTenantLabel(firstId, firstTenant.name);
      setTenantId(firstId);
      const user = useGlobalStore.getState().currentUser;
      if (user) {
        const nextUser = {
          ...user,
          tenant_id: firstId,
          tenant_name: firstTenant.name,
        };
        setCurrentUser(nextUser as any);
        setUserInfo(nextUser);
      }
      message.info(t('ui.message.autoSelectedTenant', { name: firstTenant.name }));
      return;
    }

    const matched = tenantOptions.find((tenant) => Number(tenant.id) === Number(currentTenantId));
    if (!matched?.name) return;
    rememberTenantLabel(currentTenantId, matched.name);
    if (currentUser?.tenant_name?.trim() === matched.name) return;
    const user = useGlobalStore.getState().currentUser;
    if (!user) return;
    const nextUser = {
      ...user,
      tenant_id: Number(currentTenantId),
      tenant_name: matched.name,
    };
    setCurrentUser(nextUser as any);
    setUserInfo(nextUser);
  }, [isInfraSuperAdmin, currentTenantId, tenantOptions, currentUser?.tenant_name, t, setCurrentUser]);

  const textFontSize = token.fontSize;
  const tenantTextStyle: React.CSSProperties = {
    fontSize: textFontSize,
    fontWeight: 500,
    lineHeight: `${Math.max(32, textFontSize + 8)}px`,
  };
  const optionsPending = isLoading || isFetching;

  if (canSwitch) {
    return (
      <div
        style={{ display: 'flex', alignItems: 'center' }}
        className={headerLightText ? 'tenant-selector-select-light-text' : undefined}
      >
        {switching ? (
          <Spin size="small" />
        ) : (
          <Select
            value={currentTenantIdStr}
            placeholder={
              optionsPending
                ? t('ui.placeholder.loading')
                : selectOptions.length
                  ? t('ui.placeholder.selectTenant')
                  : t('ui.message.tenantOptionsLoadFailed')
            }
            style={{
              minWidth: 120,
              maxWidth: 240,
              height: 32,
              padding: '0 12px',
              fontSize: textFontSize,
            }}
            size="small"
            className="tenant-selector-select"
            classNames={{ popup: { root: 'tenant-selector-dropdown' } }}
            suffixIcon={<SwapOutlined />}
            listHeight={TENANT_SELECTOR_LIST_HEIGHT}
            options={selectOptionsWithFooter}
            optionRender={(option) => {
              if (option.value === SET_DEFAULT_DIVIDER_VALUE) {
                return (
                  <div
                    aria-hidden
                    style={{
                      height: 1,
                      margin: '4px 0',
                      background: token.colorSplit,
                    }}
                  />
                );
              }
              if (option.value === SET_DEFAULT_OPTION_VALUE) {
                return (
                  <div style={{ color: token.colorPrimary, fontWeight: 500 }}>
                    {option.label}
                  </div>
                );
              }
              const isDefault = option.data?.isDefault === true;
              return (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 8,
                    minWidth: 0,
                  }}
                >
                  <span
                    style={{
                      flex: '1 1 auto',
                      minWidth: 0,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {option.label}
                  </span>
                  {isDefault ? (
                    <MarkerTag color="blue" style={{ marginInlineEnd: 0, flex: '0 0 auto' }}>
                      {t('components.tenantSelection.default')}
                    </MarkerTag>
                  ) : null}
                </div>
              );
            }}
            labelRender={(props) => {
              const resolved = resolveTenantLabel(props.value, props.label);
              if (resolved) {
                return <span style={tenantTextStyle}>{resolved}</span>;
              }
              if (optionsPending) {
                return <span style={tenantTextStyle}>{t('ui.placeholder.loading')}</span>;
              }
              return <span style={tenantTextStyle}>{t('ui.message.tenantNameUnavailable')}</span>;
            }}
            onChange={handleTenantChange}
            onOpenChange={(open) => {
              if (open && (isError || selectOptions.length === 0)) {
                void refetch();
              }
            }}
            disabled={switching || (optionsPending && selectOptions.length === 0)}
            notFoundContent={
              isError ? t('ui.message.tenantOptionsLoadFailed') : t('ui.placeholder.loading')
            }
          />
        )}
        {canManageLoginDefault ? (
          <TenantSelectionModal
            mode="setDefault"
            open={setDefaultModalOpen}
            tenants={defaultModalTenants}
            defaultTenantId={currentDefaultTenantId}
            title={t('components.tenantSelection.setDefaultTitle')}
            hint={t('components.tenantSelection.setDefaultHint')}
            closable
            confirmingTenantId={settingDefaultId}
            onSelect={(tenantId) => {
              void handleSetLoginDefault(tenantId);
            }}
            onCancel={() => {
              if (settingDefaultId != null) return;
              setSetDefaultModalOpen(false);
            }}
          />
        ) : null}
      </div>
    );
  }

  if (!currentTenantName) {
    return null;
  }

  const spanColor = headerLightText ? 'rgba(255, 255, 255, 0.85)' : token.colorText;
  return (
    <span
      style={{
        display: 'inline-block',
        maxWidth: 240,
        whiteSpace: 'nowrap',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        padding: '4px 16px',
        borderRadius: '16px',
        backgroundColor: token.colorFillTertiary,
        color: spanColor,
        fontSize: textFontSize,
        fontWeight: 500,
        height: 32,
        lineHeight: '32px',
        verticalAlign: 'middle',
      }}
    >
      {currentTenantName}
    </span>
  );
};

export default TenantSelector;
