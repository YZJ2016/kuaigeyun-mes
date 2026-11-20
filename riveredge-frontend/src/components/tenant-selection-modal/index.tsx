/**
 * 组织选择弹窗
 *
 * - enter：登录多组织进入（图标行，点行即进）
 * - setDefault：顶栏设置默认进入组织（单选 + 确认，避免误当成登录页）
 */

import React from 'react';
import { Button, Modal, Radio, Space, Typography, Tag, theme } from 'antd';
import { Building2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { MarkerTag } from '../../constants/statusBadges';

const { Text } = Typography;

/**
 * 组织信息接口
 */
export interface TenantInfo {
  id: number;
  name: string;
  domain: string;
  status: string;
  /** 多账户登录默认进入组织（与登录响应 default_tenant_id 对齐） */
  is_default?: boolean;
}

/**
 * 组织选择弹窗组件属性
 */
interface TenantSelectionModalProps {
  /**
   * 是否显示弹窗
   */
  open: boolean;

  /**
   * 组织列表
   */
  tenants: TenantInfo[];

  /**
   * 默认选中的组织 ID
   */
  defaultTenantId?: number;

  /**
   * 选择回调。
   * enter：进入组织；setDefault：组织 ID，或 null 表示「登录时选择」
   */
  onSelect: (tenantId: number | null) => void;

  /**
   * 关闭弹窗的回调函数
   */
  onCancel: () => void;

  /** 覆盖标题（如顶栏「设置默认进入组织」） */
  title?: string;

  /** 覆盖说明文案 */
  hint?: string;

  /** 登录选组织默认不可关；顶栏设默认可关 */
  closable?: boolean;

  /** 正在写入默认的组织 ID（确认按钮 loading） */
  confirmingTenantId?: number | null;

  /**
   * enter：登录进入；setDefault：仅改默认进入组织
   */
  mode?: 'enter' | 'setDefault';
}

/**
 * 组织选择弹窗组件
 *
 * 显示用户可访问的组织列表，供用户选择要进入的组织
 */
export default function TenantSelectionModal({
  open,
  tenants,
  defaultTenantId,
  onSelect,
  onCancel,
  title,
  hint,
  closable = false,
  confirmingTenantId = null,
  mode = 'enter',
}: TenantSelectionModalProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const isSetDefault = mode === 'setDefault';
  const ASK_EACH_LOGIN = 'ask_each_login' as const;
  type SetDefaultPick = number | typeof ASK_EACH_LOGIN;

  const explicitDefaultId = (tenants || []).find((tenant) => tenant.is_default === true)?.id;
  const baselinePick: SetDefaultPick =
    explicitDefaultId != null ? explicitDefaultId : ASK_EACH_LOGIN;
  const [pickedId, setPickedId] = React.useState<SetDefaultPick>(baselinePick);

  React.useEffect(() => {
    if (!open) return;
    setPickedId(baselinePick);
  }, [open, baselinePick]);

  /**
   * 获取组织状态标签
   *
   * @param status - 组织状态
   * @returns 状态标签
   */
  const getStatusTag = (status: string) => {
    const statusMap: Record<string, { color: string; textKey: string }> = {
      active: { color: 'success', textKey: 'components.tenantSelection.statusActive' },
      inactive: { color: 'default', textKey: 'components.tenantSelection.statusInactive' },
      expired: { color: 'error', textKey: 'components.tenantSelection.statusExpired' },
      suspended: { color: 'warning', textKey: 'components.tenantSelection.statusSuspended' },
    };

    const statusInfo = statusMap[status] || { color: 'default', textKey: '' };
    return <Tag color={statusInfo.color}>{statusInfo.textKey ? t(statusInfo.textKey) : status}</Tag>;
  };

  const isDefaultTenant = (tenant: TenantInfo) =>
    tenant.is_default === true ||
    (!isSetDefault && tenant.is_default !== false && defaultTenantId === tenant.id);

  if (isSetDefault) {
    const confirming = confirmingTenantId != null;
    const unchanged = pickedId === baselinePick;
    const renderPickCard = (
      key: string,
      selected: boolean,
      onPick: () => void,
      body: React.ReactNode,
    ) => (
      <button
        key={key}
        type="button"
        disabled={confirming}
        onClick={onPick}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          width: '100%',
          margin: 0,
          padding: '12px 14px',
          textAlign: 'left',
          cursor: confirming ? 'wait' : 'pointer',
          borderRadius: 8,
          border: `1px solid ${selected ? token.colorPrimary : token.colorBorderSecondary}`,
          background: selected ? token.colorPrimaryBg : token.colorBgContainer,
          boxShadow: 'none',
          opacity: confirming && !selected ? 0.55 : 1,
        }}
      >
        <Radio checked={selected} disabled={confirming} tabIndex={-1} />
        <span style={{ flex: 1, minWidth: 0 }}>{body}</span>
      </button>
    );

    return (
      <Modal
        title={title ?? t('components.tenantSelection.setDefaultTitle')}
        open={open}
        onCancel={() => {
          if (confirming) return;
          onCancel();
        }}
        width={520}
        closable={closable && !confirming}
        destroyOnHidden
        mask={{ closable: closable && !confirming }}
        footer={
          <Space>
            <Button
              onClick={() => {
                if (confirming) return;
                onCancel();
              }}
              disabled={confirming}
            >
              {t('common.cancel')}
            </Button>
            <Button
              type="primary"
              loading={confirming}
              disabled={unchanged}
              onClick={() => {
                if (confirming || unchanged) return;
                onSelect(pickedId === ASK_EACH_LOGIN ? null : pickedId);
              }}
            >
              {t('common.save')}
            </Button>
          </Space>
        }
      >
        <Text type="secondary" style={{ display: 'block', marginBottom: 12, fontSize: 13 }}>
          {hint ?? t('components.tenantSelection.setDefaultHint')}
        </Text>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {(tenants || []).map((tenant) =>
            renderPickCard(
              String(tenant.id),
              pickedId === tenant.id,
              () => setPickedId(tenant.id),
              <>
                <span
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    flexWrap: 'wrap',
                    fontWeight: 500,
                    color: token.colorText,
                  }}
                >
                  <span
                    style={{
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      maxWidth: '100%',
                    }}
                  >
                    {tenant.name}
                  </span>
                  {isDefaultTenant(tenant) ? (
                    <MarkerTag color="blue" style={{ marginInlineEnd: 0 }}>
                      {t('components.tenantSelection.default')}
                    </MarkerTag>
                  ) : null}
                </span>
                {tenant.domain ? (
                  <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 2 }}>
                    {tenant.domain}
                  </Text>
                ) : null}
              </>,
            ),
          )}
          {renderPickCard(
            ASK_EACH_LOGIN,
            pickedId === ASK_EACH_LOGIN,
            () => setPickedId(ASK_EACH_LOGIN),
            <>
              <span style={{ fontWeight: 500, color: token.colorText }}>
                {t('components.tenantSelection.askEachLogin')}
              </span>
              <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 2 }}>
                {t('components.tenantSelection.askEachLoginHint')}
              </Text>
            </>,
          )}
        </div>
      </Modal>
    );
  }

  return (
    <Modal
      title={title ?? t('components.tenantSelection.title')}
      open={open}
      onCancel={onCancel}
      footer={null}
      width={500}
      closable={closable}
      destroyOnHidden
      mask={{ closable }}
    >
      <div style={{ marginBottom: 16 }}>
        <Text type="secondary">
          {hint ?? t('components.tenantSelection.hint')}
        </Text>
      </div>

      <div>
        {(tenants || []).map((tenant) => (
          <div
            key={tenant.id}
            style={{
              cursor: confirmingTenantId != null ? 'wait' : 'pointer',
              padding: '12px 16px',
              borderRadius: '6px',
              transition: 'all 0.3s',
              display: 'flex',
              alignItems: 'center',
              opacity: confirmingTenantId != null && confirmingTenantId !== tenant.id ? 0.55 : 1,
            }}
            onClick={() => {
              if (confirmingTenantId != null) return;
              onSelect(tenant.id);
            }}
            onMouseEnter={(e) => {
              if (confirmingTenantId != null) return;
              e.currentTarget.style.backgroundColor = '#f5f5f5';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'transparent';
            }}
          >
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 40,
                height: 40,
                marginRight: 12,
              }}
              aria-hidden
            >
              <Building2 size={26} strokeWidth={2} color="#1677ff" />
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span>{tenant.name}</span>
                {getStatusTag(tenant.status)}
                {isDefaultTenant(tenant) ? (
                  <MarkerTag color="blue" style={{ marginInlineEnd: 0 }}>
                    {t('components.tenantSelection.default')}
                  </MarkerTag>
                ) : null}
              </div>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {t('components.tenantSelection.domainLabel')}: {tenant.domain}
              </Text>
            </div>
          </div>
        ))}
      </div>
    </Modal>
  );
}
