import React from 'react';
import { UniWhDropdown, UniWhLocationOrWholeAuto } from '../../../../../components/uni-wh-dropdown';
import { DOCUMENT_DETAIL_CONTROL_SIZE } from '../../../components/document-detail-table/documentDetailTable';
import { getPopupContainerInModal } from '../../../../../utils/modalEventIsolation';

export const PURCHASE_INBOUND_WH_HOST = 'kuaizhizao:inbound';

export type PurchaseInboundLineWarehouseCellProps = {
  materialId?: number;
  warehouseId?: number;
  disabled?: boolean;
  placeholder: string;
  getPopupContainer?: (node: HTMLElement) => HTMLElement;
  onChange: (
    warehouseId: number | undefined,
    warehouse: { id: number; name: string; code?: string } | undefined,
  ) => void;
};

export function PurchaseInboundLineWarehouseCell({
  materialId,
  warehouseId,
  disabled,
  placeholder,
  getPopupContainer,
  onChange,
}: PurchaseInboundLineWarehouseCellProps) {
  const mid = materialId != null && materialId > 0 ? materialId : undefined;
  return (
    <UniWhDropdown
      style={{ width: '100%', minWidth: 118 }}
      size={DOCUMENT_DETAIL_CONTROL_SIZE}
      hostResource={PURCHASE_INBOUND_WH_HOST}
      materialId={mid}
      showStock={mid != null}
      sortByStock={mid != null}
      value={warehouseId}
      disabled={disabled}
      placeholder={placeholder}
      getPopupContainer={getPopupContainer ?? getPopupContainerInModal}
      onChange={onChange}
    />
  );
}

export type PurchaseInboundLineLocationCellProps = {
  materialId?: number;
  warehouseId?: number;
  locationId?: number;
  disabled?: boolean;
  selectWarehouseFirstPlaceholder: string;
  selectLocationPlaceholder: string;
  getPopupContainer?: (node: HTMLElement) => HTMLElement;
  onChange: (
    locationId: number | undefined,
    location: { id: number; code: string } | undefined,
  ) => void;
};

export function PurchaseInboundLineLocationCell({
  materialId,
  warehouseId,
  locationId,
  disabled,
  selectWarehouseFirstPlaceholder,
  selectLocationPlaceholder,
  getPopupContainer,
  onChange,
}: PurchaseInboundLineLocationCellProps) {
  const whId = warehouseId != null && warehouseId > 0 ? warehouseId : undefined;
  const mid = materialId != null && materialId > 0 ? materialId : undefined;
  return (
    <UniWhLocationOrWholeAuto
      style={{ width: '100%', minWidth: 118 }}
      size={DOCUMENT_DETAIL_CONTROL_SIZE}
      hostResource={PURCHASE_INBOUND_WH_HOST}
      warehouseId={whId}
      materialId={mid}
      showStock={false}
      allowClear={false}
      value={locationId}
      disabled={disabled}
      selectWarehouseFirstPlaceholder={selectWarehouseFirstPlaceholder}
      selectLocationPlaceholder={selectLocationPlaceholder}
      getPopupContainer={getPopupContainer ?? getPopupContainerInModal}
      onChange={onChange}
    />
  );
}
