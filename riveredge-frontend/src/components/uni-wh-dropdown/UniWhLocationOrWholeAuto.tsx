import React from 'react';
import { useTranslation } from 'react-i18next';
import { UniWhLocationDropdown } from './UniWhLocationDropdown';
import type { UniWhLocationDropdownProps } from './types';
import { useWarehouseHasLocations } from './useWarehouseHasLocations';

export type UniWhLocationOrWholeAutoProps = Omit<
  UniWhLocationDropdownProps,
  'disabled' | 'placeholder'
> & {
  warehouseId?: number;
  disabled?: boolean;
  selectWarehouseFirstPlaceholder: string;
  selectLocationPlaceholder: string;
};

export function UniWhLocationOrWholeAuto({
  warehouseId,
  disabled,
  selectWarehouseFirstPlaceholder,
  selectLocationPlaceholder,
  ...dropdownProps
}: UniWhLocationOrWholeAutoProps) {
  const { t } = useTranslation();
  const whId = warehouseId != null && warehouseId > 0 ? warehouseId : undefined;
  const hasLocations = useWarehouseHasLocations(whId);

  if (whId == null) {
    return (
      <UniWhLocationDropdown
        {...dropdownProps}
        warehouseId={undefined}
        disabled={disabled ?? true}
        placeholder={selectWarehouseFirstPlaceholder}
      />
    );
  }

  if (hasLocations === false) {
    return (
      <span className="uni-wh-whole-location-auto">
        {t('app.kuaizhizao.warehouseOutbound.pull.wholeLocationAuto')}
      </span>
    );
  }

  return (
    <UniWhLocationDropdown
      {...dropdownProps}
      warehouseId={whId}
      disabled={disabled || hasLocations === undefined}
      placeholder={selectLocationPlaceholder}
    />
  );
}
