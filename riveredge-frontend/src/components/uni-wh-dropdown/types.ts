import type { CSSProperties } from 'react';
import type { NamePath } from 'antd/es/form/interface';
import type { SizeType } from 'antd/es/config-provider/SizeContext';

export type UniWhWarehouseOption = {
  value: number;
  label: string;
  name: string;
  code?: string;
  /** 可出库库存（有 materialId 且库存已加载时） */
  stockQty?: number;
};

export type UniWhLocationOption = {
  value: number;
  label: string;
  code: string;
  stockQty?: number;
};

export type UniWhWarehouseChangePayload = {
  id: number;
  name: string;
  code?: string;
  stockQty?: number;
};

export type UniWhLocationChangePayload = {
  id: number;
  code: string;
  label: string;
};

export type UniWhDropdownBaseProps = {
  hostResource?: string;
  activeOnly?: boolean;
  disabled?: boolean;
  size?: SizeType;
  placeholder?: string;
  className?: string;
  style?: CSSProperties;
  getPopupContainer?: (node: HTMLElement) => HTMLElement;
};

export type UniWhDropdownProps = UniWhDropdownBaseProps & {
  /** Form.Item / ProForm 字段名；与 value 二选一 */
  name?: NamePath;
  value?: number;
  onChange?: (
    value: number | undefined,
    warehouse: UniWhWarehouseChangePayload | undefined,
  ) => void;
  /**
   * 传入后按物料加载各仓可出库库存，下拉展示「仓名（库存 n）」，并按库存降序。
   * 不传则仅展示仓编码+名称。
   */
  materialId?: number | null;
  /** 默认：有 materialId 时开启 */
  showStock?: boolean;
  /** 默认与 showStock 一致 */
  sortByStock?: boolean;
  required?: boolean;
  label?: string;
  allowClear?: boolean;
};

export type UniWhLocationDropdownProps = UniWhDropdownBaseProps & {
  name?: NamePath;
  value?: number;
  onChange?: (
    value: number | undefined,
    location: UniWhLocationChangePayload | undefined,
  ) => void;
  /** 未选仓库时禁用并提示先选仓 */
  warehouseId?: number | null;
  /** 传入后按物料+仓库加载各库位可出库库存（文案「库位（库存 n）」/「无库存」） */
  materialId?: number | null;
  /**
   * 默认：有 materialId 时开启（与仓库 UniWhDropdown 一致）。
   * 出库选位有物料时勿传 false，否则下拉只显示库位名不带库存。
   */
  showStock?: boolean;
  /** 默认与 showStock 一致：有货库位优先、按库存降序 */
  sortByStock?: boolean;
  allowClear?: boolean;
};
