import React, { useEffect, useRef, useState } from 'react';
import { App } from 'antd';
import { ProFormDigit, ProFormSelect, ProFormSwitch, ProFormText, type ProFormInstance } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { FormModalTemplate, MODAL_CONFIG } from '../../../../../components/layout-templates';
import { CustomFieldsFormSection } from '../../../../../components/custom-fields';
import { useCustomFields } from '../../../../../hooks/useCustomFields';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { createVehicle, updateVehicle, type Vehicle } from '../../../services/logistics';

const VEHICLE_CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_vehicles';
const VEHICLE_HOST_RESOURCE = 'kuaizhizao:vehicle';

export type VehicleFormModalProps = {
  open: boolean;
  editing?: Vehicle | null;
  onClose: () => void;
  onSuccess: (record: Vehicle) => void;
  zIndex?: number;
};

export const VehicleFormModal: React.FC<VehicleFormModalProps> = ({
  open,
  editing,
  onClose,
  onSuccess,
  zIndex,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const formRef = useRef<ProFormInstance>();
  const [submitting, setSubmitting] = useState(false);
  const isEdit = Boolean(editing?.id);
  const {
    customFields,
    customFieldValues,
    loadFieldValues,
    extractFormValues,
    saveCustomFieldValues,
    resetFieldValues,
  } = useCustomFields({
    tableName: VEHICLE_CUSTOM_FIELD_TABLE,
    hostResource: VEHICLE_HOST_RESOURCE,
    loadWhenOpen: true,
    open,
  });

  useEffect(() => {
    if (!open) return;
    if (editing) {
      formRef.current?.setFieldsValue(editing);
      if (editing.id != null) {
        void loadFieldValues(editing.id).then((cfValues) => {
          formRef.current?.setFieldsValue(cfValues);
        });
      }
      return;
    }
    formRef.current?.resetFields();
    resetFieldValues();
    formRef.current?.setFieldsValue({ ownership: 'internal', status: 'idle', is_enabled: true });
  }, [open, editing, loadFieldValues, resetFieldValues]);

  const handleFinish = async (values: Partial<Vehicle>) => {
    setSubmitting(true);
    try {
      const { customData, standardValues } = extractFormValues(values, formRef.current);
      const record = editing
        ? await updateVehicle(editing.id, standardValues)
        : await createVehicle(standardValues);
      if (record.id != null) {
        await saveCustomFieldValues(record.id, customData);
      }
      messageApi.success(editing ? t('common.updateSuccess') : t('common.createSuccess'));
      onSuccess(record);
      onClose();
    } catch (error) {
      messageApi.error(
        getApiErrorMessage(error, editing ? t('common.updateFailed') : t('common.createFailed')),
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <FormModalTemplate
      title={
        isEdit
          ? t('app.kuaizhizao.logistics.action.editVehicle')
          : t('app.kuaizhizao.logistics.action.createVehicle')
      }
      open={open}
      onClose={onClose}
      onFinish={handleFinish}
      isEdit={isEdit}
      loading={submitting}
      width={MODAL_CONFIG.SMALL_WIDTH}
      layout="vertical"
      formRef={formRef as React.RefObject<ProFormInstance>}
      initialValues={editing ?? { ownership: 'internal', status: 'idle', is_enabled: true }}
      zIndex={zIndex}
    >
      <ProFormText
        name="plate_number"
        label={t('app.kuaizhizao.logistics.field.plateNumber')}
        rules={[{ required: true }]}
      />
      <ProFormSelect
        name="vehicle_type"
        label={t('app.kuaizhizao.logistics.field.vehicleType')}
        allowClear
        options={[
          { value: 'van', label: t('app.kuaizhizao.logistics.option.vehicleType.van') },
          { value: 'flatbed', label: t('app.kuaizhizao.logistics.option.vehicleType.flatbed') },
          { value: 'refrigerated', label: t('app.kuaizhizao.logistics.option.vehicleType.refrigerated') },
          { value: 'trailer', label: t('app.kuaizhizao.logistics.option.vehicleType.trailer') },
          { value: 'other', label: t('app.kuaizhizao.logistics.option.vehicleType.other') },
        ]}
      />
      <ProFormSelect
        name="ownership"
        label={t('app.kuaizhizao.logistics.field.ownership')}
        options={[
          { label: t('app.kuaizhizao.logistics.option.ownership.internal'), value: 'internal' },
          { label: t('app.kuaizhizao.logistics.option.ownership.external'), value: 'external' },
        ]}
      />
      <ProFormDigit
        name="load_capacity"
        label={t('app.kuaizhizao.logistics.field.loadCapacity')}
        fieldProps={{ style: { width: '100%' } }}
      />
      <ProFormSelect
        name="status"
        label={t('common.status')}
        options={[
          { label: t('app.kuaizhizao.logistics.option.vehicleStatus.idle'), value: 'idle' },
          { label: t('app.kuaizhizao.logistics.option.vehicleStatus.inTransit'), value: 'in_transit' },
          { label: t('app.kuaizhizao.logistics.option.vehicleStatus.maintenance'), value: 'maintenance' },
          { label: t('app.kuaizhizao.logistics.option.vehicleStatus.disabled'), value: 'disabled' },
        ]}
      />
      <CustomFieldsFormSection
        customFields={customFields}
        customFieldValues={customFieldValues}
        gridColumns={1}
      />
      <ProFormSwitch name="is_enabled" label={t('common.enabled')} />
    </FormModalTemplate>
  );
};
