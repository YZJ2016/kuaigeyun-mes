import React from 'react';
import { Button, Dropdown, Space, Tooltip } from 'antd';
import type { ButtonProps } from 'antd';
import { DownOutlined, FileSearchOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

export interface UniPullMenuItem {
  key: string;
  label?: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  type?: 'divider';
}

export interface UniPullCreateToolbarProps {
  createLabel: React.ReactNode;
  onCreate: () => void;
  menuItems: UniPullMenuItem[];
  createIcon?: React.ReactNode;
  size?: ButtonProps['size'];
  /** 作为列表子项时的 React key（与 compactKey 默认同值） */
  compactKey?: string;
}

/**
 * 统一“新建 + 加载建单”入口。
 * 页面只需要传主按钮行为和加载菜单项，避免重复拼装 Dropdown 结构。
 */
export const UniPullCreateToolbar: React.FC<UniPullCreateToolbarProps> = ({
  createLabel,
  onCreate,
  menuItems,
  createIcon,
  size,
  compactKey = 'uni-pull-create-toolbar',
}) => {
  const { t } = useTranslation();
  const createButtonLabel =
    typeof createLabel === 'string'
      ? createLabel.replace(/\s*\(Alt\+N\)/gi, '').trimEnd()
      : createLabel;

  return (
    <Space.Compact key={compactKey} className="uni-pull-create-toolbar">
      <Tooltip title={t('common.shortcutNewHover')}>
        <Button type="primary" size={size} icon={createIcon} onClick={onCreate}>
          {createButtonLabel}
        </Button>
      </Tooltip>
      <Dropdown
        trigger={['click']}
        menu={{
          items: menuItems.map((it) =>
            it.type === 'divider'
              ? { type: 'divider' as const, key: it.key }
              : {
                  key: it.key,
                  label: it.label,
                  disabled: it.disabled,
                  onClick: it.onClick,
                },
          ),
        }}
      >
        <Button type="primary" size={size} icon={<DownOutlined />} />
      </Dropdown>
    </Space.Compact>
  );
};

export interface UniPullLoadButtonProps {
  /** 默认「从单据加载」 */
  label?: React.ReactNode;
  menuItems: UniPullMenuItem[];
  icon?: React.ReactNode;
  type?: ButtonProps['type'];
  color?: ButtonProps['color'];
  variant?: ButtonProps['variant'];
  compactKey?: string;
}

/**
 * 独立的「从单据加载」入口，与「新建」主按钮并列，便于发现取单能力。
 */
export const UniPullLoadButton: React.FC<UniPullLoadButtonProps> = ({
  label,
  menuItems,
  icon,
  type,
  color = 'primary',
  variant = 'outlined',
  compactKey = 'uni-pull-load-button',
}) => {
  const { t } = useTranslation();
  const resolvedLabel = label ?? t('components.uniPull.loadFromDocument');
  const actionableItems = menuItems.filter((item) => item.type !== 'divider' && !item.disabled);

  if (actionableItems.length === 1 && actionableItems[0].onClick) {
    const onlyItem = actionableItems[0];
    return (
      <Button
        key={compactKey}
        type={type}
        color={color}
        variant={variant}
        icon={icon ?? <FileSearchOutlined />}
        onClick={onlyItem.onClick}
      >
        {resolvedLabel}
      </Button>
    );
  }

  return (
  <Dropdown
    key={compactKey}
    trigger={['click']}
    menu={{
      items: menuItems.map((it) =>
        it.type === 'divider'
          ? { type: 'divider' as const, key: it.key }
          : {
              key: it.key,
              label: it.label,
              disabled: it.disabled,
              onClick: it.onClick,
            },
      ),
    }}
  >
    <Button type={type} color={color} variant={variant} icon={icon ?? <FileSearchOutlined />}>
      {resolvedLabel}
      <DownOutlined style={{ fontSize: 10, marginLeft: 4 }} />
    </Button>
  </Dropdown>
  );
};

