import React, { useEffect, useRef, useState } from 'react';
import { App } from 'antd';
import { ProFormSelect, ProFormSwitch, ProFormText, type ProFormInstance } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { FormModalTemplate, MODAL_CONFIG } from '../../../../../components/layout-templates';
import { CustomFieldsFormSection } from '../../../../../components/custom-fields';
import { useCustomFields } from '../../../../../hooks/useCustomFields';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { createDriver, updateDriver, type Driver } from '../../../services/logistics';

const DRIVER_CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_drivers';
const DRIVER_HOST_RESOURCE = 'kuaizhizao:driver';

export type DriverFormModalProps = {
  open: boolean;
  editing?: Driver | null;
  onClose: () => void;
  onSuccess: (record: Driver) => void;
  zIndex?: number;
};

export const DriverFormModal: React.FC<DriverFormModalProps> = ({
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
    tableName: DRIVER_CUSTOM_FIELD_TABLE,
    hostResource: DRIVER_HOST_RESOURCE,
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
    formRef.current?.setFieldsValue({ ownership: 'internal', is_enabled: true });
  }, [open, editing, loadFieldValues, resetFieldValues]);

  const handleFinish = async (values: Partial<Driver>) => {
    setSubmitting(true);
    try {
      const { customData, standardValues } = extractFormValues(values, formRef.current);
      const record = editing
        ? await updateDriver(editing.id, standardValues)
        : await createDriver(standardValues);
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
          ? t('app.kuaizhizao.logistics.action.editDriver')
          : t('app.kuaizhizao.logistics.action.createDriver')
      }
      open={open}
      onClose={onClose}
      onFinish={handleFinish}
      isEdit={isEdit}
      loading={submitting}
      width={MODAL_CONFIG.SMALL_WIDTH}
      layout="vertical"
      formRef={formRef as React.RefObject<ProFormInstance>}
      initialValues={editing ?? { ownership: 'internal', is_enabled: true }}
      zIndex={zIndex}
    >
      {!isEdit ? (
        <ProFormText
          name="code"
          label={t('common.code')}
          placeholder={t('app.kuaizhizao.logistics.placeholder.autoCode')}
        />
      ) : null}
      <ProFormText
        name="name"
        label={t('app.kuaizhizao.logistics.field.driverName')}
        rules={[{ required: true }]}
      />
      <ProFormText name="phone" label={t('app.kuaizhizao.logistics.field.phone')} />
      <ProFormText name="license_number" label={t('app.kuaizhizao.logistics.field.licenseNumber')} />
      <ProFormSelect
        name="ownership"
        label={t('app.kuaizhizao.logistics.field.ownership')}
        options={[
          { label: t('app.kuaizhizao.logistics.option.ownership.internal'), value: 'internal' },
          { label: t('app.kuaizhizao.logistics.option.ownership.external'), value: 'external' },
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
