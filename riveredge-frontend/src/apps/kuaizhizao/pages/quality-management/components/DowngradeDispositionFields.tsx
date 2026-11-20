import React from 'react';
import { ProFormItem } from '@ant-design/pro-components';
import { Form } from 'antd';
import { useTranslation } from 'react-i18next';
import { UniMaterialSelect } from '../../../../../components/uni-material-select';
import { UniWarehouseSelect } from '../../../../../components/uni-warehouse-select';
import { UniWhLocationOrWholeAuto } from '../../../../../components/uni-wh-dropdown';

interface DowngradeDispositionFieldsProps {
  dispositionFieldName?: string;
  materialFieldName?: string;
  warehouseFieldName?: string;
}

export function DowngradeDispositionFields({
  dispositionFieldName = 'disposition',
  materialFieldName = 'downgrade_material_id',
  warehouseFieldName = 'downgrade_warehouse_id',
}: DowngradeDispositionFieldsProps) {
  const { t } = useTranslation();
  const form = Form.useFormInstance();
  const disposition = Form.useWatch(dispositionFieldName);
  const warehouseId = Form.useWatch(warehouseFieldName);

  if (disposition !== 'downgrade') {
    return null;
  }

  return (
    <>
      <ProFormItem
        name={materialFieldName}
        label={t('app.kuaizhizao.quality.common.form.downgradeMaterial')}
        rules={[{ required: true, message: t('app.kuaizhizao.quality.common.validation.requiredDowngradeMaterial') }]}
      >
        <UniMaterialSelect
          placeholder={t('app.kuaizhizao.quality.common.placeholder.downgradeMaterial')}
          style={{ width: '100%' }}
        />
      </ProFormItem>
      <ProFormItem
        name={warehouseFieldName}
        label={t('app.kuaizhizao.quality.common.form.downgradeWarehouse')}
        rules={[{ required: true, message: t('app.kuaizhizao.quality.common.validation.requiredDowngradeWarehouse') }]}
      >
        <UniWarehouseSelect
          placeholder={t('app.kuaizhizao.quality.common.placeholder.downgradeWarehouse')}
          style={{ width: '100%' }}
          onChange={() =>
            form.setFieldsValue({ location_id: undefined, location_code: undefined })
          }
        />
      </ProFormItem>
      <ProFormItem
        name="location_id"
        label={t('app.kuaizhizao.quality.common.form.dispositionLocation')}
      >
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
    </>
  );
}
