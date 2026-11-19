import React, { useEffect } from 'react';
import { Form, InputNumber, Select, Space, Switch } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  normalizeSamplingSpec,
  type Gb2828InspectionLevel,
  type Gb2828Strictness,
  type SamplingSpec,
} from '../types/inspectionStepSpec';

type Props = {
  value?: SamplingSpec;
  onChange?: (spec: SamplingSpec) => void;
};

const GB2828_LEVELS: Gb2828InspectionLevel[] = ['S-1', 'S-2', 'S-3', 'S-4', 'I', 'II', 'III'];
const GB2828_STRICTNESS: Gb2828Strictness[] = ['normal', 'tightened', 'reduced'];
const GB2828_AQL_OPTIONS = [0.65, 1.0, 1.5, 2.5, 4.0, 6.5, 10.0];

export const InspectionSamplingSpecFields: React.FC<Props> = ({ value, onChange }) => {
  const { t } = useTranslation();
  const spec = normalizeSamplingSpec(value);

  useEffect(() => {
    onChange?.(normalizeSamplingSpec(value));
    // 挂载时将默认 n/Ac/Re 写入 Form，避免仅展示默认值却未注册字段
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 仅首次挂载同步
  }, []);

  const patch = (partial: Partial<SamplingSpec>) => {
    onChange?.({ ...spec, ...partial });
  };

  const isLotRatio = spec.mode === 'lot_ratio';
  const isGb2828 = spec.mode === 'gb2828_single';

  return (
    <Space wrap align="start">
      <Form.Item
        label={t('app.kuaizhizao.quality.plans.stepSpec.samplingMode')}
        style={{ marginBottom: 0 }}
      >
        <Select
          style={{ width: 200 }}
          value={spec.mode ?? 'fixed'}
          options={[
            {
              value: 'fixed',
              label: t('app.kuaizhizao.quality.plans.stepSpec.samplingModeFixed'),
            },
            {
              value: 'lot_ratio',
              label: t('app.kuaizhizao.quality.plans.stepSpec.samplingModeLotRatio'),
            },
            {
              value: 'gb2828_single',
              label: t('app.kuaizhizao.quality.plans.stepSpec.samplingModeGb2828'),
            },
          ]}
          onChange={(mode: SamplingSpec['mode']) => {
            if (mode === 'gb2828_single') {
              patch({
                mode: 'gb2828_single',
                level: 'II',
                aql: 2.5,
                strictness: 'normal',
                transfer_enabled: false,
              });
              return;
            }
            patch({ mode: mode ?? 'fixed' });
          }}
        />
      </Form.Item>
      {isGb2828 ? (
        <>
          <Form.Item
            label={t('app.kuaizhizao.quality.plans.stepSpec.gb2828Level')}
            style={{ marginBottom: 0 }}
          >
            <Select
              style={{ width: 100 }}
              value={spec.level ?? 'II'}
              options={GB2828_LEVELS.map((v) => ({ value: v, label: v }))}
              onChange={(level) => patch({ level })}
            />
          </Form.Item>
          <Form.Item
            label={t('app.kuaizhizao.quality.plans.stepSpec.gb2828Aql')}
            style={{ marginBottom: 0 }}
          >
            <Select
              style={{ width: 100 }}
              value={spec.aql ?? 2.5}
              options={GB2828_AQL_OPTIONS.map((v) => ({ value: v, label: String(v) }))}
              onChange={(aql) => patch({ aql })}
            />
          </Form.Item>
          <Form.Item
            label={t('app.kuaizhizao.quality.plans.stepSpec.gb2828Strictness')}
            style={{ marginBottom: 0 }}
          >
            <Select
              style={{ width: 120 }}
              value={spec.strictness ?? 'normal'}
              options={GB2828_STRICTNESS.map((v) => ({
                value: v,
                label: t(`app.kuaizhizao.quality.plans.stepSpec.gb2828Strictness.${v}`),
              }))}
              onChange={(strictness) => patch({ strictness })}
            />
          </Form.Item>
          <Form.Item
            label={t('app.kuaizhizao.quality.plans.stepSpec.gb2828Transfer')}
            style={{ marginBottom: 0 }}
          >
            <Switch
              checked={Boolean(spec.transfer_enabled)}
              onChange={(transfer_enabled) => patch({ transfer_enabled })}
            />
          </Form.Item>
        </>
      ) : null}
      {!isGb2828 && isLotRatio ? (
        <Form.Item
          label={t('app.kuaizhizao.quality.plans.stepSpec.lotSampleRatio')}
          style={{ marginBottom: 0 }}
        >
          <InputNumber
            min={0.01}
            max={100}
            step={1}
            value={spec.lot_sample_ratio ?? 10}
            onChange={(v) => patch({ lot_sample_ratio: v ?? 10 })}
            addonAfter="%"
            style={{ width: 120 }}
          />
        </Form.Item>
      ) : null}
      {!isGb2828 && !isLotRatio ? (
        <Form.Item
          label={t('app.kuaizhizao.quality.plans.stepSpec.sampleSize')}
          style={{ marginBottom: 0 }}
        >
          <InputNumber
            min={1}
            value={spec.sample_size}
            onChange={(v) => patch({ sample_size: v ?? 1 })}
            style={{ width: 100 }}
          />
        </Form.Item>
      ) : null}
      {!isGb2828 ? (
        <>
          <Form.Item
            label={t('app.kuaizhizao.quality.plans.stepSpec.acceptNum')}
            style={{ marginBottom: 0 }}
          >
            <InputNumber
              min={0}
              value={spec.accept_num}
              onChange={(v) => patch({ accept_num: v ?? 0 })}
              style={{ width: 100 }}
            />
          </Form.Item>
          <Form.Item
            label={t('app.kuaizhizao.quality.plans.stepSpec.rejectNum')}
            style={{ marginBottom: 0 }}
          >
            <InputNumber
              min={0}
              value={spec.reject_num}
              onChange={(v) => patch({ reject_num: v ?? 1 })}
              style={{ width: 100 }}
            />
          </Form.Item>
        </>
      ) : null}
    </Space>
  );
};
