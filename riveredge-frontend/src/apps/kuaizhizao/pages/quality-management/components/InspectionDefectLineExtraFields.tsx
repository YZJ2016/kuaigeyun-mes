import React from 'react';
import { Alert, Input, Row, Col } from 'antd';
import { useTranslation } from 'react-i18next';
import { UniWarehouseSelect } from '../../../../../components/uni-warehouse-select';
import { UniMaterialSelect } from '../../../../../components/uni-material-select';
import type {
  InspectionDefectDispositionSource,
  InspectionDefectLineDraft,
} from './defectRecordLineTypes';

const EFFECT_HINT_KEYS: Record<string, string> = {
  return: 'app.kuaizhizao.quality.nc.dispositionHint.return',
  accept: 'app.kuaizhizao.quality.nc.dispositionHint.accept',
  quarantine: 'app.kuaizhizao.quality.nc.dispositionHint.quarantine',
  rework: 'app.kuaizhizao.quality.nc.dispositionHint.rework',
  scrap: 'app.kuaizhizao.quality.nc.dispositionHint.scrap',
  downgrade: 'app.kuaizhizao.quality.nc.dispositionHint.downgrade',
  other: 'app.kuaizhizao.quality.nc.dispositionHint.other',
};

type InspectionDefectLineExtraFieldsProps = {
  line: InspectionDefectLineDraft;
  onChange: (patch: Partial<InspectionDefectLineDraft>) => void;
  source?: InspectionDefectDispositionSource;
};

function resolveDispositionHintKey(
  disposition: string,
  source?: InspectionDefectDispositionSource,
): string | undefined {
  const base = EFFECT_HINT_KEYS[disposition];
  if (!base || !source) return base;
  return `${base}.${source}`;
}

export function InspectionDefectLineExtraFields({
  line,
  onChange,
  source,
}: InspectionDefectLineExtraFieldsProps) {
  const { t } = useTranslation();
  const disposition = String(line.disposition || '');
  const baseHintKey = EFFECT_HINT_KEYS[disposition];
  const hintKey = resolveDispositionHintKey(disposition, source);
  const hintText = hintKey
    ? t(hintKey, { defaultValue: baseHintKey ? t(baseHintKey) : '' })
    : undefined;

  return (
    <div style={{ padding: '8px 0 4px' }}>
      {hintText ? (
        <Alert type="info" showIcon style={{ marginBottom: 12 }} title={hintText} />
      ) : null}
      {disposition === 'downgrade' ? (
        <Row gutter={16}>
          <Col span={12}>
            <div style={{ marginBottom: 4 }}>
              {t('app.kuaizhizao.quality.common.form.downgradeMaterial')}
              <span style={{ color: '#ff4d4f' }}> *</span>
            </div>
            <UniMaterialSelect
              value={line.downgrade_material_id}
              placeholder={t('app.kuaizhizao.quality.common.placeholder.downgradeMaterial')}
              style={{ width: '100%' }}
              onChange={(value) => onChange({ downgrade_material_id: value ?? undefined })}
            />
          </Col>
          <Col span={12}>
            <div style={{ marginBottom: 4 }}>
              {t('app.kuaizhizao.quality.common.form.downgradeWarehouse')}
              <span style={{ color: '#ff4d4f' }}> *</span>
            </div>
            <UniWarehouseSelect
              value={line.downgrade_warehouse_id}
              placeholder={t('app.kuaizhizao.quality.common.placeholder.downgradeWarehouse')}
              style={{ width: '100%' }}
              onChange={(value) => onChange({ downgrade_warehouse_id: value ?? undefined })}
            />
          </Col>
        </Row>
      ) : null}
      {disposition === 'quarantine' ? (
        <Row gutter={16}>
          <Col span={12}>
            <div style={{ marginBottom: 4 }}>
              {t('app.kuaizhizao.quality.common.form.quarantineWarehouse')}
              <span style={{ color: '#ff4d4f' }}> *</span>
            </div>
            <UniWarehouseSelect
              value={line.quarantine_warehouse_id}
              placeholder={t('app.kuaizhizao.quality.common.placeholder.quarantineWarehouse')}
              style={{ width: '100%' }}
              onChange={(value) => onChange({ quarantine_warehouse_id: value ?? undefined })}
            />
          </Col>
        </Row>
      ) : null}
      {disposition === 'scrap' ? (
        <Row gutter={16}>
          <Col span={12}>
            <div style={{ marginBottom: 4 }}>
              {t('app.kuaizhizao.quality.common.form.scrapWarehouse')}
              <span style={{ color: '#ff4d4f' }}> *</span>
            </div>
            <UniWarehouseSelect
              value={line.stock_warehouse_id}
              placeholder={t('app.kuaizhizao.quality.common.placeholder.scrapWarehouse')}
              style={{ width: '100%' }}
              onChange={(value) => onChange({ stock_warehouse_id: value ?? undefined })}
            />
          </Col>
        </Row>
      ) : null}
      {disposition === 'accept' ? (
        <Row gutter={16}>
          <Col span={12}>
            <div style={{ marginBottom: 4 }}>
              {t(
                source === 'finished'
                  ? 'app.kuaizhizao.quality.common.form.acceptWarehouseFinished'
                  : source === 'incoming'
                    ? 'app.kuaizhizao.quality.common.form.acceptWarehouseIncoming'
                    : 'app.kuaizhizao.quality.common.form.acceptWarehouse',
              )}
              <span style={{ color: '#ff4d4f' }}> *</span>
            </div>
            <UniWarehouseSelect
              value={line.stock_warehouse_id}
              placeholder={t('app.kuaizhizao.quality.common.placeholder.acceptWarehouse')}
              style={{ width: '100%' }}
              onChange={(value) => onChange({ stock_warehouse_id: value ?? undefined })}
            />
          </Col>
        </Row>
      ) : null}
      {disposition === 'other' ? (
        <Row gutter={16}>
          <Col span={24}>
            <div style={{ marginBottom: 4 }}>
              {t('common.remark')}
              <span style={{ color: '#ff4d4f' }}> *</span>
            </div>
            <Input.TextArea
              rows={2}
              value={line.remarks}
              placeholder={t('common.remark')}
              onChange={(e) => onChange({ remarks: e.target.value })}
            />
          </Col>
        </Row>
      ) : null}
    </div>
  );
}
