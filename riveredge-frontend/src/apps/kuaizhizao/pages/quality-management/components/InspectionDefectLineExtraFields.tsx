import React from 'react';
import { Alert, Input, Row, Col } from 'antd';
import { useTranslation } from 'react-i18next';
import { UniWarehouseSelect } from '../../../../../components/uni-warehouse-select';
import { UniMaterialSelect } from '../../../../../components/uni-material-select';
import { UniWhLocationOrWholeAuto } from '../../../../../components/uni-wh-dropdown';
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

function DispositionWarehouseLocationRow({
  warehouseId,
  locationId,
  warehouseLabel,
  warehousePlaceholder,
  onWarehouseChange,
  onLocationChange,
}: {
  warehouseId?: number;
  locationId?: number;
  warehouseLabel: string;
  warehousePlaceholder: string;
  onWarehouseChange: (warehouseId: number | undefined) => void;
  onLocationChange: (locationId: number | undefined, locationCode?: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <Row gutter={16}>
      <Col span={12}>
        <div style={{ marginBottom: 4 }}>
          {warehouseLabel}
          <span style={{ color: '#ff4d4f' }}> *</span>
        </div>
        <UniWarehouseSelect
          value={warehouseId}
          placeholder={warehousePlaceholder}
          style={{ width: '100%' }}
          onChange={(value) => onWarehouseChange(value ?? undefined)}
        />
      </Col>
      <Col span={12}>
        <div style={{ marginBottom: 4 }}>
          {t('app.kuaizhizao.quality.common.form.dispositionLocation')}
        </div>
        <UniWhLocationOrWholeAuto
          warehouseId={warehouseId}
          value={locationId}
          style={{ width: '100%' }}
          selectWarehouseFirstPlaceholder={t(
            'app.kuaizhizao.quality.common.placeholder.selectWarehouseFirst',
          )}
          selectLocationPlaceholder={t(
            'app.kuaizhizao.quality.common.placeholder.dispositionLocation',
          )}
          onChange={(value, loc) => onLocationChange(value ?? undefined, loc?.code)}
        />
      </Col>
    </Row>
  );
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

  const clearLocationOnWarehouse = (warehouseId: number | undefined, warehouseKey: keyof InspectionDefectLineDraft) => {
    onChange({
      [warehouseKey]: warehouseId,
      location_id: undefined,
      location_code: undefined,
    } as Partial<InspectionDefectLineDraft>);
  };

  const patchLocation = (locationId: number | undefined, locationCode?: string) => {
    onChange({
      location_id: locationId,
      location_code: locationCode,
    });
  };

  return (
    <div style={{ padding: '8px 0 4px' }}>
      {hintText ? (
        <Alert type="info" showIcon style={{ marginBottom: 12 }} title={hintText} />
      ) : null}
      {disposition === 'downgrade' ? (
        <>
          <Row gutter={16} style={{ marginBottom: 12 }}>
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
          </Row>
          <DispositionWarehouseLocationRow
            warehouseId={line.downgrade_warehouse_id}
            locationId={line.location_id}
            warehouseLabel={t('app.kuaizhizao.quality.common.form.downgradeWarehouse')}
            warehousePlaceholder={t('app.kuaizhizao.quality.common.placeholder.downgradeWarehouse')}
            onWarehouseChange={(id) => clearLocationOnWarehouse(id, 'downgrade_warehouse_id')}
            onLocationChange={patchLocation}
          />
        </>
      ) : null}
      {disposition === 'quarantine' ? (
        <DispositionWarehouseLocationRow
          warehouseId={line.quarantine_warehouse_id}
          locationId={line.location_id}
          warehouseLabel={t('app.kuaizhizao.quality.common.form.quarantineWarehouse')}
          warehousePlaceholder={t('app.kuaizhizao.quality.common.placeholder.quarantineWarehouse')}
          onWarehouseChange={(id) => clearLocationOnWarehouse(id, 'quarantine_warehouse_id')}
          onLocationChange={patchLocation}
        />
      ) : null}
      {disposition === 'scrap' ? (
        <DispositionWarehouseLocationRow
          warehouseId={line.stock_warehouse_id}
          locationId={line.location_id}
          warehouseLabel={t('app.kuaizhizao.quality.common.form.scrapWarehouse')}
          warehousePlaceholder={t('app.kuaizhizao.quality.common.placeholder.scrapWarehouse')}
          onWarehouseChange={(id) => clearLocationOnWarehouse(id, 'stock_warehouse_id')}
          onLocationChange={patchLocation}
        />
      ) : null}
      {disposition === 'accept' ? (
        <DispositionWarehouseLocationRow
          warehouseId={line.stock_warehouse_id}
          locationId={line.location_id}
          warehouseLabel={t(
            source === 'finished'
              ? 'app.kuaizhizao.quality.common.form.acceptWarehouseFinished'
              : source === 'incoming'
                ? 'app.kuaizhizao.quality.common.form.acceptWarehouseIncoming'
                : 'app.kuaizhizao.quality.common.form.acceptWarehouse',
          )}
          warehousePlaceholder={t('app.kuaizhizao.quality.common.placeholder.acceptWarehouse')}
          onWarehouseChange={(id) => clearLocationOnWarehouse(id, 'stock_warehouse_id')}
          onLocationChange={patchLocation}
        />
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
