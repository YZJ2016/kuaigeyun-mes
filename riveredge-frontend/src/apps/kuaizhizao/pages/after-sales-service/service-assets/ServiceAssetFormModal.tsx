import React, { useEffect, useRef, useState } from 'react';
import { App, Form, Input } from 'antd';
import {
  ProFormDigit,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
  type ProFormInstance,
} from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { FormModalTemplate, MODAL_CONFIG } from '../../../../../components/layout-templates';
import { CustomFieldsFormSection } from '../../../../../components/custom-fields';
import { useCustomFields } from '../../../../../hooks/useCustomFields';
import { CustomerSelectDropdown } from '../../../../master-data/components/CustomerSelectDropdown';
import type { Customer } from '../../../../master-data/types/supply-chain';
import { UniMaterialSelect } from '../../../../../components/uni-material-select';
import {
  serviceAssetApi,
  type ServiceAsset,
  type ServiceAssetPayload,
} from '../../../services/after-sales-service';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';

const STATUS_OPTIONS = ['在用', '停用', '报废'];
const CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_service_assets';
const HOST_RESOURCE = 'kuaizhizao:service-asset';

function customerDisplayName(c: Customer | null | undefined): string {
  if (!c) return '';
  const row = c as Record<string, unknown>;
  return String(row.name ?? row.customer_name ?? '').trim();
}

export type ServiceAssetFormModalProps = {
  open: boolean;
  editing: ServiceAsset | null;
  onClose: () => void;
  onSuccess: () => void;
};

const ServiceAssetFormModal: React.FC<ServiceAssetFormModalProps> = ({
  open,
  editing,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const formRef = useRef<ProFormInstance>();
  const [submitting, setSubmitting] = useState(false);
  const {
    customFields,
    customFieldValues,
    loadFieldValues,
    extractFormValues,
    saveCustomFieldValues,
    resetFieldValues,
  } = useCustomFields({
    tableName: CUSTOM_FIELD_TABLE,
    hostResource: HOST_RESOURCE,
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
    formRef.current?.setFieldsValue({ status: '在用' });
  }, [editing, loadFieldValues, open, resetFieldValues]);

  const materialFallback =
    editing?.material_id != null
      ? {
          value: editing.material_id,
          label: [editing.material_code, editing.material_name, editing.material_spec]
            .filter(Boolean)
            .join(' '),
        }
      : undefined;

  const handleFinish = async (values: ServiceAssetPayload) => {
    setSubmitting(true);
    try {
      const { customData, standardValues } = extractFormValues(values, formRef.current);
      const payload = standardValues as ServiceAssetPayload;
      let savedId = editing?.id;
      if (editing) {
        await serviceAssetApi.update(editing.id, payload);
      } else {
        const created = await serviceAssetApi.create(payload);
        savedId = created.id;
      }
      if (savedId != null) {
        await saveCustomFieldValues(savedId, customData);
      }
      messageApi.success(editing ? t('common.saveSuccess') : t('common.createSuccess'));
      onSuccess();
      onClose();
    } catch (error) {
      messageApi.error(getApiErrorMessage(error, t('common.saveFailed')));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <FormModalTemplate
      open={open}
      title={
        editing
          ? t('app.kuaizhizao.afterSalesService.serviceAsset.editTitle')
          : t('app.kuaizhizao.afterSalesService.serviceAsset.createTitle')
      }
      formRef={formRef}
      width={MODAL_CONFIG.STANDARD_WIDTH}
      confirmLoading={submitting}
      onClose={() => {
        resetFieldValues();
        onClose();
      }}
      onFinish={handleFinish}
      initialValues={editing ?? { status: '在用' }}
    >
      <Form.Item name="customer_name" hidden>
        <Input />
      </Form.Item>
      <Form.Item
        name="customer_id"
        label={t('app.kuaizhizao.afterSalesService.serviceAsset.field.customerName')}
        rules={[{ required: true, message: t('app.kuaizhizao.afterSalesTicket.selectCustomerFirst') }]}
      >
        <CustomerSelectDropdown
          hostResource={HOST_RESOURCE}
          placeholder={t('app.kuaizhizao.afterSalesTicket.selectCustomerFirst')}
          style={{ width: '100%' }}
          onCustomerPick={(c) => {
            formRef.current?.setFieldsValue({
              customer_id: c?.id,
              customer_name: customerDisplayName(c),
            });
          }}
        />
      </Form.Item>
      <ProFormText name="material_code" hidden />
      <ProFormText name="material_name" hidden />
      <ProFormText name="material_spec" hidden />
      <UniMaterialSelect
        name="material_id"
        label={t('app.kuaizhizao.afterSalesService.serviceAsset.field.materialName')}
        placeholder={t('app.kuaizhizao.afterSalesService.common.selectMaterial')}
        showAdvancedSearch
        fallbackOption={materialFallback}
        fillMapping={{
          material_code: 'mainCode',
          material_name: 'name',
          material_spec: 'specification',
        }}
      />
      <ProFormText
        name="serial_number"
        label={t('app.kuaizhizao.afterSalesService.serviceAsset.field.serialNumber')}
      />
      <ProFormTextArea
        name="install_address"
        label={t('app.kuaizhizao.afterSalesService.serviceAsset.field.installAddress')}
        fieldProps={{ rows: 2 }}
      />
      <ProFormDigit
        name="warranty_months"
        label={t('app.kuaizhizao.afterSalesService.serviceAsset.field.warrantyMonths')}
        min={0}
        fieldProps={{ style: { width: '100%' } }}
      />
      <ProFormText
        name="warranty_policy"
        label={t('app.kuaizhizao.afterSalesService.serviceAsset.field.warrantyPolicy')}
      />
      <ProFormSelect
        name="status"
        label={t('common.status')}
        options={STATUS_OPTIONS.map((value) => ({ value, label: value }))}
      />
      <CustomFieldsFormSection
        customFields={customFields}
        customFieldValues={customFieldValues}
        gridColumns={1}
      />
      <ProFormTextArea name="notes" label={t('common.remark')} fieldProps={{ rows: 3 }} />
    </FormModalTemplate>
  );
};

export default ServiceAssetFormModal;
