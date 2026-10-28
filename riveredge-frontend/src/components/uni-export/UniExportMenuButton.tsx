/**
 * 列表工具栏「导出」下拉（选中 / 本页 / 全部），与 UniTable 3.2 行为一致。
 * 可选 datasets：嵌套「导出列表 / 导出明细」等数据集，各自再选范围。
 * 图标与导入成对：ImportOutlined / ExportOutlined。
 */

import React from 'react';
import { Button, Dropdown, Tooltip } from 'antd';
import type { MenuProps } from 'antd';
import type { ButtonProps } from 'antd';
import { DownOutlined, ExportOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useUniTableDataActionIconOnly } from '../uni-table/dataActionIconOnlyContext';

export type UniExportScope = 'selected' | 'currentPage' | 'all';

export type UniExportDataset = {
  key: string;
  label: React.ReactNode;
};

export interface UniExportMenuButtonProps<T extends Record<string, any> = Record<string, any>> {
  onExport: (
    type: UniExportScope,
    selectedRowKeys?: React.Key[],
    currentPageData?: T[],
    dataset?: string,
  ) => void;
  selectedRowKeys: React.Key[];
  /** 当前表格数据（本页导出用） */
  tableData: T[];
  size?: ButtonProps['size'];
  /** 是否展示「导出选中」，默认 true */
  showSelected?: boolean;
  showCurrentPage?: boolean;
  showAll?: boolean;
  /**
   * 导出数据集（如列表 / 明细）。有值时菜单为二级：数据集 → 选中/本页/全部。
   * 未传则保持一级范围菜单（兼容既有页）。
   */
  datasets?: UniExportDataset[];
  /** 仅图标（窄屏/工具栏宽度不足） */
  iconOnly?: boolean;
  /** 按钮主文案（不传则使用 i18n components.uniTable.export） */
  buttonText?: string;
}

function buildScopeItems<T extends Record<string, any>>(options: {
  datasetKey?: string;
  showSelected: boolean;
  showCurrentPage: boolean;
  showAll: boolean;
  selectedRowKeys: React.Key[];
  tableData: T[];
  onExport: UniExportMenuButtonProps<T>['onExport'];
  t: (key: string) => string;
}): NonNullable<MenuProps['items']> {
  const {
    datasetKey,
    showSelected,
    showCurrentPage,
    showAll,
    selectedRowKeys,
    tableData,
    onExport,
    t,
  } = options;
  const keyPrefix = datasetKey ? `${datasetKey}-` : '';
  const items: NonNullable<MenuProps['items']> = [];
  if (showSelected) {
    items.push({
      key: `${keyPrefix}selected`,
      label: t('components.uniTable.exportSelected'),
      disabled: selectedRowKeys.length === 0,
      onClick: () => onExport('selected', selectedRowKeys, tableData, datasetKey),
    });
  }
  if (showCurrentPage) {
    items.push({
      key: `${keyPrefix}currentPage`,
      label: t('components.uniTable.exportCurrentPage'),
      onClick: () => onExport('currentPage', undefined, tableData, datasetKey),
    });
  }
  if (showAll) {
    items.push({
      key: `${keyPrefix}all`,
      label: t('components.uniTable.exportAll'),
      onClick: () => onExport('all', undefined, undefined, datasetKey),
    });
  }
  return items;
}

export function UniExportMenuButton<T extends Record<string, any> = Record<string, any>>({
  onExport,
  selectedRowKeys,
  tableData,
  size,
  showSelected = true,
  showCurrentPage = true,
  showAll = true,
  datasets,
  iconOnly: iconOnlyProp = false,
  buttonText,
}: UniExportMenuButtonProps<T>) {
  const { t } = useTranslation();
  const toolbarIconOnly = useUniTableDataActionIconOnly();
  const iconOnly = iconOnlyProp || toolbarIconOnly;
  const exportLabel = buttonText ?? t('common.export');

  const items: MenuProps['items'] =
    datasets && datasets.length > 0
      ? datasets.map((ds) => ({
          key: ds.key,
          label: ds.label,
          children: buildScopeItems({
            datasetKey: ds.key,
            showSelected,
            showCurrentPage,
            showAll,
            selectedRowKeys,
            tableData,
            onExport,
            t,
          }),
        }))
      : buildScopeItems({
          showSelected,
          showCurrentPage,
          showAll,
          selectedRowKeys,
          tableData,
          onExport,
          t,
        });

  if (!items || items.length === 0) return null;

  const trigger = (
    <Button icon={<ExportOutlined />} size={size} aria-label={exportLabel}>
      {iconOnly ? null : (
        <>
          {exportLabel}
          <DownOutlined style={{ fontSize: 10, marginInlineStart: 2, opacity: 0.65 }} />
        </>
      )}
    </Button>
  );

  return (
    <Dropdown
      menu={{ items }}
      placement="bottomRight"
      trigger={['hover', 'click']}
      mouseEnterDelay={0.05}
      mouseLeaveDelay={0.2}
    >
      {iconOnly ? <Tooltip title={exportLabel}>{trigger}</Tooltip> : trigger}
    </Dropdown>
  );
}
