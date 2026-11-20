import React, { useMemo } from 'react';
import { DatePicker, Select, theme } from 'antd';
import type { Dayjs } from 'dayjs';
import { useTranslation } from 'react-i18next';
import { getUniToolbarControlShellStyle } from '../../../../../components/uni-search/toolbarChrome';
import {
  detectPartnerStatementPeriodPreset,
  PARTNER_STATEMENT_PERIOD_PRESETS,
  resolvePartnerStatementPeriodPreset,
  type PartnerStatementPeriodPreset,
} from '../../../utils/partnerStatementPeriodQuick';

const PS = 'app.kuaicaiwu.partnerStatement';

export type PartnerStatementPeriodQuickSelectProps = {
  value: [Dayjs, Dayjs];
  onChange: (next: [Dayjs, Dayjs]) => void;
  onPeriodCleared?: () => void;
  startPlaceholder: string;
  endPlaceholder: string;
};

export const PartnerStatementPeriodQuickSelect: React.FC<PartnerStatementPeriodQuickSelectProps> = ({
  value,
  onChange,
  onPeriodCleared,
  startPlaceholder,
  endPlaceholder,
}) => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const shellStyle = getUniToolbarControlShellStyle(token);

  const preset = useMemo(() => detectPartnerStatementPeriodPreset(value), [value]);

  const presetOptions = useMemo(
    () => [
      ...PARTNER_STATEMENT_PERIOD_PRESETS.map((p) => ({
        value: p,
        label: t(`${PS}.periodPreset.${p}`),
      })),
      { value: 'custom' as const, label: t(`${PS}.periodPreset.custom`) },
    ],
    [t],
  );

  const applyRange = (next: [Dayjs, Dayjs]) => {
    onChange([next[0].startOf('day'), next[1].endOf('day')]);
    onPeriodCleared?.();
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <DatePicker.RangePicker
        allowClear={false}
        value={value}
        onChange={(v) => {
          if (v?.[0] && v?.[1]) {
            applyRange([v[0], v[1]]);
          }
        }}
        placeholder={[startPlaceholder, endPlaceholder]}
        style={{ minWidth: 260 }}
      />
      <Select<PartnerStatementPeriodPreset | 'custom'>
        size="middle"
        value={preset}
        options={presetOptions}
        popupMatchSelectWidth={false}
        style={{ ...shellStyle, width: 108, flex: '0 0 108px' }}
        onChange={(nextPreset) => {
          if (nextPreset === 'custom') return;
          applyRange(resolvePartnerStatementPeriodPreset(nextPreset));
        }}
      />
    </div>
  );
};