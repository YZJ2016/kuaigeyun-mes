/**
 * 流程模板节点：按产品型号配置型号工期（表单，非 JSON）
 */

import React, { useMemo, useState } from 'react';
import { Button, Flex, Input, InputNumber, Popover, Typography } from 'antd';
import { EditOutlined, PlusOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { MarkerTag } from '../../../../../constants/statusBadges';
import { DELIVERY_CONFIG_ATTR_PRODUCT_MODEL } from '../../../constants/deliveryProject';

export type DurationRulesValue = {
  attr_key: string;
  days_by_value: Record<string, number>;
} | null;

interface DurationRulesByProductModelEditorProps {
  value?: DurationRulesValue;
  onChange: (value: DurationRulesValue) => void;
  disabled?: boolean;
}

function normalizeDaysMap(raw: Record<string, number> | undefined): Record<string, number> {
  if (!raw) {
    return {};
  }
  const out: Record<string, number> = {};
  for (const [key, days] of Object.entries(raw)) {
    const model = key.trim();
    if (!model) {
      continue;
    }
    const n = Number(days);
    if (!Number.isFinite(n) || n < 0) {
      continue;
    }
    out[model] = Math.floor(n);
  }
  return out;
}

function buildDurationRules(daysByValue: Record<string, number>): DurationRulesValue {
  const normalized = normalizeDaysMap(daysByValue);
  if (Object.keys(normalized).length === 0) {
    return null;
  }
  return {
    attr_key: DELIVERY_CONFIG_ATTR_PRODUCT_MODEL,
    days_by_value: normalized,
  };
}

function modelSortKey(model: string): number {
  const normalized = model.trim();
  const leadingNumber = normalized.match(/^(\d+)/);
  if (leadingNumber) {
    return Number(leadingNumber[1]);
  }
  if (/^[A-Z]$/i.test(normalized)) {
    return normalized.toUpperCase().charCodeAt(0);
  }
  return 9999 + normalized.charCodeAt(0);
}

function sortModelEntries(daysByValue: Record<string, number>): Array<[string, number]> {
  return Object.entries(daysByValue).sort(([a], [b]) => {
    const diff = modelSortKey(a) - modelSortKey(b);
    return diff !== 0 ? diff : a.localeCompare(b);
  });
}

const DurationRulesByProductModelEditor: React.FC<DurationRulesByProductModelEditorProps> = ({
  value,
  onChange,
  disabled = false,
}) => {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [customModel, setCustomModel] = useState('');

  const daysMap = useMemo(() => normalizeDaysMap(value?.days_by_value), [value?.days_by_value]);
  const sortedEntries = useMemo(() => sortModelEntries(daysMap), [daysMap]);
  const configuredModels = useMemo(
    () => sortedEntries.map(([model]) => model),
    [sortedEntries],
  );

  const patchDays = (model: string, days: number | null) => {
    const next = { ...daysMap };
    if (days == null || !Number.isFinite(days) || days < 0) {
      delete next[model];
    } else {
      next[model] = Math.floor(days);
    }
    onChange(buildDurationRules(next));
  };

  const addCustomModel = () => {
    const model = customModel.trim();
    if (!model) {
      return;
    }
    if (daysMap[model] != null) {
      setCustomModel('');
      return;
    }
    onChange(buildDurationRules({ ...daysMap, [model]: 0 }));
    setCustomModel('');
  };

  const clearAll = () => {
    onChange(null);
  };

  const dayUnit = t('app.kuaizhizao.deliveryProject.durationRulesDayUnit');
  const previewEntries = sortedEntries.slice(0, 3);
  const hiddenCount = Math.max(sortedEntries.length - previewEntries.length, 0);

  const popoverContent = (
    <div style={{ width: 320 }}>
      <Typography.Paragraph type="secondary" style={{ marginBottom: 12, fontSize: 12 }}>
        {t('app.kuaizhizao.deliveryProject.durationRulesFormHint')}
      </Typography.Paragraph>
      {configuredModels.length === 0 ? (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {t('app.kuaizhizao.deliveryProject.durationRulesEmptyHint')}
        </Typography.Text>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(72px, 1fr) 72px 20px',
            columnGap: 8,
            rowGap: 8,
            alignItems: 'center',
          }}
        >
          {configuredModels.map((model) => (
            <React.Fragment key={model}>
              <Typography.Text style={{ fontSize: 12 }} ellipsis={{ tooltip: model }}>
                {model}
              </Typography.Text>
              <InputNumber
                min={0}
                precision={0}
                size="small"
                style={{ width: '100%' }}
                placeholder={t('app.kuaizhizao.deliveryProject.durationRulesDaysPlaceholder')}
                value={daysMap[model]}
                disabled={disabled}
                onChange={(val) => patchDays(model, val == null ? null : Number(val))}
              />
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {dayUnit}
              </Typography.Text>
            </React.Fragment>
          ))}
        </div>
      )}
      <Flex gap={8} wrap="wrap" align="center" style={{ marginTop: 12 }}>
        <Input
          size="small"
          style={{ width: 120 }}
          placeholder={t('app.kuaizhizao.deliveryProject.durationRulesCustomModel')}
          value={customModel}
          disabled={disabled}
          onChange={(e) => setCustomModel(e.target.value)}
          onPressEnter={addCustomModel}
        />
        <Button size="small" icon={<PlusOutlined />} disabled={disabled} onClick={addCustomModel}>
          {t('app.kuaizhizao.deliveryProject.durationRulesAddModel')}
        </Button>
        <Button
          size="small"
          type="link"
          danger
          disabled={disabled || sortedEntries.length === 0}
          onClick={clearAll}
        >
          {t('app.kuaizhizao.deliveryProject.durationRulesClear')}
        </Button>
      </Flex>
    </div>
  );

  const trigger = (
    <Flex
      align="center"
      gap={6}
      wrap="wrap"
      style={{ minHeight: 24, cursor: disabled ? 'not-allowed' : 'pointer' }}
    >
      <Button
        type="text"
        size="small"
        disabled={disabled}
        icon={<EditOutlined />}
        style={{ flexShrink: 0, paddingInline: 4 }}
      />
      {sortedEntries.length === 0 ? (
        <Typography.Text type={disabled ? 'secondary' : 'link'} style={{ fontSize: 12 }}>
          {t('app.kuaizhizao.deliveryProject.durationRulesUnset')}
        </Typography.Text>
      ) : (
        <Flex gap={4} wrap="wrap" align="center">
          {previewEntries.map(([model, days]) => (
            <MarkerTag key={model} variant="filled" color="default">
              {t('app.kuaizhizao.deliveryProject.durationRulesModelDays', { model, days })}
            </MarkerTag>
          ))}
          {hiddenCount > 0 ? (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('app.kuaizhizao.deliveryProject.durationRulesMore', { count: hiddenCount })}
            </Typography.Text>
          ) : null}
        </Flex>
      )}
    </Flex>
  );

  return (
    <Popover
      open={open}
      trigger="click"
      placement="leftTop"
      content={popoverContent}
      onOpenChange={(next) => {
        if (!disabled) {
          setOpen(next);
        }
      }}
    >
      <div role="button" tabIndex={disabled ? -1 : 0} style={{ maxWidth: '100%' }}>
        {trigger}
      </div>
    </Popover>
  );
};

export default DurationRulesByProductModelEditor;
