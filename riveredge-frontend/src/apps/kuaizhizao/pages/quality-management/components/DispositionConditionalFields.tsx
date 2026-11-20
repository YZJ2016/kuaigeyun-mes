import React from 'react';
import { Alert, Form } from 'antd';
import { ProFormItem } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { UniWarehouseSelect } from '../../../../../components/uni-warehouse-select';
import { UniWhLocationOrWholeAuto } from '../../../../../components/uni-wh-dropdown';
import { DowngradeDispositionFields } from './DowngradeDispositionFields';

const EFFECT_HINT_KEYS: Record<string, string> = {
  return: 'app.kuaizhizao.quality.nc.dispositionHint.return',
  accept: 'app.kuaizhizao.quality.nc.dispositionHint.accept',
  quarantine: 'app.kuaizhizao.quality.nc.dispositionHint.quarantine',
  rework: 'app.kuaizhizao.quality.nc.dispositionHint.rework',
  scrap: 'app.kuaizhizao.quality.nc.dispositionHint.scrap',
  downgrade: 'app.kuaizhizao.quality.nc.dispositionHint.downgrade',
  other: 'app.kuaizhizao.quality.nc.dispositionHint.other',
};

function DispositionLocationField({ warehouseId }: { warehouseId?: number }) {
  const { t } = useTranslation();
  const form = Form.useFormInstance();
  return (
    <ProFormItem name="location_id" label={t('app.kuaizhizao.quality.common.form.dispositionLocation')}>
      <UniWhLocationOrWholeAuto
        warehouseId={warehouseId}
        style={{ width: '100%' }}
        selectWarehouseFirstPlaceholder={t(
          'app.kuaizhizao.quality.common.placeholder.selectWarehouseFirst',
        )}
        selectLocationPlaceholder={t(
          'app.kuaizhizao.quality.common.placeholder.dispositionLocation',
        )}
        onChange={(value, loc) => {
          form.setFieldsValue({
            location_id: value,
            location_code: loc?.code,
          });
        }}
      />
    </ProFormItem>
  );
}

/** 随处置变化的字段与保存后闭环说明（七种处置统一入口） */
export function DispositionConditionalFields({
  dispositionFieldName = 'disposition',
}: {
  dispositionFieldName?: string;
}) {
  const { t } = useTranslation();
  const form = Form.useFormInstance();
  const disposition = Form.useWatch(dispositionFieldName);
  const quarantineWarehouseId = Form.useWatch('quarantine_warehouse_id');
  const stockWarehouseId = Form.useWatch('stock_warehouse_id');
  const hintKey = disposition ? EFFECT_HINT_KEYS[String(disposition)] : undefined;

  const clearLocation = () => {
    form.setFieldsValue({ location_id: undefined, location_code: undefined });
  };

  return (
    <>
      {hintKey ? (
        <Alert type="info" showIcon style={{ marginBottom: 16 }} title={t(hintKey)} />
      ) : null}
      <DowngradeDispositionFields dispositionFieldName={dispositionFieldName} />
      {disposition === 'quarantine' ? (
        <>
          <ProFormItem
            name="quarantine_warehouse_id"
            label={t('app.kuaizhizao.quality.common.form.quarantineWarehouse')}
            rules={[
              {
                required: true,
                message: t('app.kuaizhizao.quality.common.validation.requiredQuarantineWarehouse'),
              },
            ]}
          >
            <UniWarehouseSelect
              placeholder={t('app.kuaizhizao.quality.common.placeholder.quarantineWarehouse')}
              style={{ width: '100%' }}
              onChange={() => clearLocation()}
            />
          </ProFormItem>
          <DispositionLocationField warehouseId={quarantineWarehouseId} />
        </>
      ) : null}
      {disposition === 'scrap' ? (
        <>
          <ProFormItem
            name="stock_warehouse_id"
            label={t('app.kuaizhizao.quality.common.form.scrapWarehouse')}
            rules={[
              {
                required: true,
                message: t('app.kuaizhizao.quality.common.validation.requiredScrapWarehouse'),
              },
            ]}
          >
            <UniWarehouseSelect
              placeholder={t('app.kuaizhizao.quality.common.placeholder.scrapWarehouse')}
              style={{ width: '100%' }}
              onChange={() => clearLocation()}
            />
          </ProFormItem>
          <DispositionLocationField warehouseId={stockWarehouseId} />
        </>
      ) : null}
      {disposition === 'accept' ? (
        <>
          <ProFormItem
            name="stock_warehouse_id"
            label={t('app.kuaizhizao.quality.common.form.acceptWarehouse')}
            rules={[
              {
                required: true,
                message: t('app.kuaizhizao.quality.common.validation.requiredAcceptWarehouse'),
              },
            ]}
          >
            <UniWarehouseSelect
              placeholder={t('app.kuaizhizao.quality.common.placeholder.acceptWarehouse')}
              style={{ width: '100%' }}
              onChange={() => clearLocation()}
            />
          </ProFormItem>
          <DispositionLocationField warehouseId={stockWarehouseId} />
        </>
      ) : null}
      <ProFormItem name="location_code" hidden>
        <input />
      </ProFormItem>
    </>
  );
}

/** 台账更新处置成功提示 key（按处置码） */
export function getDispositionSuccessMessageKey(disposition?: string): string {
  switch (disposition) {
    case 'return':
      return 'app.kuaizhizao.quality.nc.messages.updateDispositionSuccessReturn';
    case 'accept':
      return 'app.kuaizhizao.quality.nc.messages.updateDispositionSuccessAccept';
    case 'quarantine':
      return 'app.kuaizhizao.quality.nc.messages.updateDispositionSuccessQuarantine';
    case 'rework':
      return 'app.kuaizhizao.quality.nc.messages.updateDispositionSuccessRework';
    case 'scrap':
      return 'app.kuaizhizao.quality.nc.messages.updateDispositionSuccessScrap';
    case 'downgrade':
      return 'app.kuaizhizao.quality.nc.messages.updateDispositionSuccessDowngrade';
    case 'other':
      return 'app.kuaizhizao.quality.nc.messages.updateDispositionSuccessOther';
    default:
      return 'app.kuaizhizao.quality.nc.messages.updateDispositionSuccess';
  }
}
