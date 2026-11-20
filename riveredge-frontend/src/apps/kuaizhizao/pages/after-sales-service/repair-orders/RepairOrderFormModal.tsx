import React, { useEffect, useMemo, useRef, useState } from 'react';
import { App, Form, Input, Select } from 'antd';
import {
  ProFormDateTimePicker,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
  type ProFormInstance,
} from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { FormModalTemplate, MODAL_CONFIG } from '../../../../../components/layout-templates';
import { CustomFieldsFormSection } from '../../../../../components/custom-fields';
import { useCustomFields } from '../../../../../hooks/useCustomFields';
import { CustomerSelectDropdown } from '../../../../master-data/components/CustomerSelectDropdown';
import type { Customer } from '../../../../master-data/types/supply-chain';
import {
  repairOrderApi,
  serviceAssetApi,
  type RepairOrder,
  type RepairOrderPayload,
  type ServiceAsset,
} from '../../../services/after-sales-service';
import { formDateFormItemProps } from '../../../../../utils/formDate';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { AfterSalesSourceDocumentSelect } from '../shared/AfterSalesSourceDocumentSelect';

const REPAIR_MODES = ['现场', '返厂'];
const WARRANTY_STATUSES = ['保内', '保外', '待判定'];
const CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_repair_orders';
const HOST_RESOURCE = 'kuaizhizao:repair-order';

function customerDisplayName(c: Customer | null | undefined): string {
  if (!c) return '';
  const row = c as Record<string, unknown>;
  return String(row.name ?? row.customer_name ?? '').trim();
}

export type RepairOrderFormModalProps = {
  open: boolean;
  editing: RepairOrder | null;
  onClose: () => void;
  onSuccess: () => void;
};

const RepairOrderFormModal: React.FC<RepairOrderFormModalProps> = ({
  open,
  editing,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const formRef = useRef<ProFormInstance>();
  const [submitting, setSubmitting] = useState(false);
  const [assets, setAssets] = useState<ServiceAsset[]>([]);
  const [ticketBlocked, setTicketBlocked] = useState<
    Record<number, { disabled: boolean; reason: string }>
  >({});
  const [customerId, setCustomerId] = useState<number | undefined>();
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
    let cancelled = false;
    void Promise.all([
      serviceAssetApi.list({ skip: 0, limit: 100, customer_id: customerId || undefined }),
      repairOrderApi.list({ skip: 0, limit: 200 }),
    ])
      .then(([assetRes, repairRes]) => {
        if (cancelled) return;
        setAssets(assetRes.items ?? []);
        const blocked: Record<number, { disabled: boolean; reason: string }> = {};
        for (const row of repairRes.items ?? []) {
          const ticketId = Number(row.after_sales_ticket_id);
          if (!Number.isFinite(ticketId) || ticketId <= 0) continue;
          if (editing?.id && row.id === editing.id) continue;
          blocked[ticketId] = {
            disabled: true,
            reason: t('app.kuaizhizao.afterSalesService.repairOrder.ticketAlreadyHasRepair', {
              code: row.order_code,
            }),
          };
        }
        setTicketBlocked(blocked);
      })
      .catch(() => {
        if (!cancelled) {
          setAssets([]);
          setTicketBlocked({});
        }
      });
    return () => {
      cancelled = true;
    };
  }, [customerId, editing?.id, open, t]);

  useEffect(() => {
    if (!open) return;
    if (editing) {
      setCustomerId(editing.customer_id != null ? Number(editing.customer_id) : undefined);
      formRef.current?.setFieldsValue({
        ...editing,
        reported_at_picker: editing.reported_at ? dayjs(editing.reported_at) : undefined,
      });
      if (editing.id != null) {
        void loadFieldValues(editing.id).then((cfValues) => {
          formRef.current?.setFieldsValue(cfValues);
        });
      }
      return;
    }
    formRef.current?.resetFields();
    resetFieldValues();
    setCustomerId(undefined);
    formRef.current?.setFieldsValue({
      repair_mode: '现场',
      warranty_status: '待判定',
      reported_at_picker: dayjs(),
    });
  }, [editing, loadFieldValues, open, resetFieldValues]);

  const assetOptions = useMemo(
    () =>
      assets.map((row) => ({
        value: row.id,
        label: `${row.asset_code}${row.customer_name ? ` ${row.customer_name}` : ''}`,
      })),
    [assets],
  );

  const handleFinish = async (values: Record<string, unknown>) => {
    setSubmitting(true);
    try {
      const { customData, standardValues } = extractFormValues(values, formRef.current);
      const {
        reported_at_picker,
        _ticket_source_type: _ignored,
        ...rest
      } = standardValues as RepairOrderPayload & {
        reported_at_picker?: dayjs.Dayjs;
        _ticket_source_type?: string;
      };
      const payload: RepairOrderPayload = {
        ...rest,
        reported_at: reported_at_picker?.format('YYYY-MM-DD HH:mm:ss') ?? '',
      };
      let savedId = editing?.id;
      if (editing) {
        await repairOrderApi.update(editing.id, payload);
      } else {
        const created = await repairOrderApi.create(payload);
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
          ? t('app.kuaizhizao.afterSalesService.repairOrder.editTitle')
          : t('app.kuaizhizao.afterSalesService.repairOrder.createTitle')
      }
      formRef={formRef}
      width={MODAL_CONFIG.STANDARD_WIDTH}
      confirmLoading={submitting}
      grid={false}
      onClose={() => {
        resetFieldValues();
        onClose();
      }}
      onFinish={handleFinish}
      initialValues={
        editing
          ? {
              ...editing,
              reported_at_picker: editing.reported_at ? dayjs(editing.reported_at) : undefined,
            }
          : {
              repair_mode: '现场',
              warranty_status: '待判定',
              reported_at_picker: dayjs(),
            }
      }
    >
      <Form.Item name="customer_name" hidden>
        <Input />
      </Form.Item>
      <Form.Item name="after_sales_ticket_code" hidden>
        <Input />
      </Form.Item>
      <Form.Item name="service_asset_code" hidden>
        <Input />
      </Form.Item>
      <Form.Item
        name="customer_id"
        label={t('app.kuaizhizao.afterSalesService.repairOrder.field.customerName')}
        rules={[{ required: true, message: t('app.kuaizhizao.afterSalesTicket.selectCustomerFirst') }]}
      >
        <CustomerSelectDropdown
          hostResource={HOST_RESOURCE}
          placeholder={t('app.kuaizhizao.afterSalesTicket.selectCustomerFirst')}
          style={{ width: '100%' }}
          onCustomerPick={(c) => {
            setCustomerId(c?.id != null ? Number(c.id) : undefined);
            formRef.current?.setFieldsValue({
              customer_id: c?.id,
              customer_name: customerDisplayName(c),
              after_sales_ticket_id: undefined,
              after_sales_ticket_code: undefined,
              service_asset_id: undefined,
              service_asset_code: undefined,
            });
          }}
        />
      </Form.Item>
      <AfterSalesSourceDocumentSelect
        sourceTypeField="_ticket_source_type"
        sourceIdField="after_sales_ticket_id"
        sourceCodeField="after_sales_ticket_code"
        customerId={customerId}
        allowedTypes={['after_sales_ticket']}
        typeLabelKeyPrefix="app.kuaizhizao.afterSalesService.repairOrder.field"
        hideTypeSelect
        fixedSourceType="after_sales_ticket"
        optionStateById={ticketBlocked}
        onPicked={(picked) => {
          if (!picked) return;
          setCustomerId(picked.customerId != null ? Number(picked.customerId) : undefined);
          formRef.current?.setFieldsValue({
            customer_id: picked.customerId,
            customer_name: picked.customerName,
            after_sales_ticket_id: picked.value,
            after_sales_ticket_code: picked.code,
          });
        }}
      />
      <Form.Item
        name="service_asset_id"
        label={t('app.kuaizhizao.afterSalesService.repairOrder.field.assetCode')}
      >
        <Select
          allowClear
          showSearch
          optionFilterProp="label"
          options={assetOptions}
          onChange={(value: number | undefined) => {
            const picked = assets.find((row) => row.id === value);
            if (picked?.customer_id != null) {
              setCustomerId(Number(picked.customer_id));
            }
            formRef.current?.setFieldsValue({
              service_asset_id: value,
              service_asset_code: picked?.asset_code,
              customer_id: picked?.customer_id ?? formRef.current?.getFieldValue('customer_id'),
              customer_name: picked?.customer_name ?? formRef.current?.getFieldValue('customer_name'),
            });
          }}
        />
      </Form.Item>
      <ProFormSelect
        name="repair_mode"
        label={t('app.kuaizhizao.afterSalesService.repairOrder.field.repairMode')}
        options={REPAIR_MODES.map((value) => ({ value, label: value }))}
      />
      <ProFormSelect
        name="warranty_status"
        label={t('app.kuaizhizao.afterSalesService.repairOrder.field.warrantyStatus')}
        options={WARRANTY_STATUSES.map((value) => ({ value, label: value }))}
      />
      <ProFormTextArea
        name="fault_description"
        label={t('app.kuaizhizao.afterSalesService.repairOrder.field.faultDescription')}
        rules={[{ required: true, message: t('common.required') }]}
        fieldProps={{ rows: 3 }}
      />
      <ProFormTextArea
        name="site_address"
        label={t('app.kuaizhizao.afterSalesService.repairOrder.field.siteAddress')}
        fieldProps={{ rows: 2 }}
      />
      <ProFormDateTimePicker
        name="reported_at_picker"
        label={t('app.kuaizhizao.afterSalesService.repairOrder.field.reportedAt')}
        rules={[{ required: true, message: t('common.required') }]}
        {...formDateFormItemProps}
        fieldProps={{ style: { width: '100%' } }}
      />
      <CustomFieldsFormSection
        customFields={customFields}
        customFieldValues={customFieldValues}
        gridColumns={1}
      />
      <ProFormTextArea name="notes" label={t('common.remark')} fieldProps={{ rows: 2 }} />
      <ProFormText name="after_sales_ticket_id" hidden />
    </FormModalTemplate>
  );
};

export default RepairOrderFormModal;
