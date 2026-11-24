import React from 'react';
import type { TFunction } from 'i18next';
import { MarkerTag } from '../../../../../constants/statusBadges';

export const OTHER_OUTBOUND_TYPE_MATERIAL = '物料出库';
export const OTHER_OUTBOUND_TYPE_ASSET = '资产出库';

export function translateOtherOutboundTypeLabel(t: TFunction, value?: string | null): string {
  const text = String(value ?? '').trim();
  if (text === OTHER_OUTBOUND_TYPE_ASSET) {
    return t('app.kuaizhizao.otherOutbound.outboundType.asset');
  }
  if (!text) {
    return '—';
  }
  if (text === OTHER_OUTBOUND_TYPE_MATERIAL) {
    return t('app.kuaizhizao.otherOutbound.outboundType.material');
  }
  return text;
}

export function renderOtherOutboundTypeMarkerTag(
  t: TFunction,
  value?: string | null,
): React.ReactNode {
  const text = String(value ?? '').trim();
  if (!text) {
    return '—';
  }
  const label = translateOtherOutboundTypeLabel(t, value);
  const color = text === OTHER_OUTBOUND_TYPE_ASSET ? 'gold' : 'blue';
  return React.createElement(MarkerTag, { color, variant: 'filled' }, label);
}