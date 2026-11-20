import React, { useEffect, useRef, useState } from 'react';
import { App, Col, DatePicker, Form, Input, Row } from 'antd';
import type { ProFormInstance } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { FormModalTemplate, MODAL_CONFIG } from '../../../../../components/layout-templates';
import { CustomFieldsFormSection } from '../../../../../components/custom-fields';
import { useCustomFields } from '../../../../../hooks/useCustomFields';
import { CustomerSelectDropdown } from '../../../../master-data/components/CustomerSelectDropdown';
import type { Customer } from '../../../../master-data/types/supply-chain';
import { UniUserSelect } from '../../../../../components/uni-user-select';
import { resolveUserUuidById } from '../../../components/EquipmentPersonSelect';
import {
  serviceDispatchApi,
  type ServiceDispatchOrder,
  type ServiceDispatchPayload,
} from '../../../services/after-sales-service';
import { formDateFormItemProps } from '../../../../../utils/formDate';
import { formatApiErrorDetail } from '../../../../../services/api';
import { AfterSalesSourceDocumentSelect } from '../shared/AfterSalesSourceDocumentSelect';

const CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_service_dispatch_orders';
const HOST_RESOURCE = 'kuaizhizao:service-dispatch';

function customerDisplayName(c: Customer | null | undefined): string {
  if (!c) return '';
  const row = c as Record<string, unknown>;
  return String(row.name ?? row.customer_name ?? '').trim();
}

const DispatchBlockedSourcesSync: React.FC<{
  open: boolean;
  editingId?: number;
  onBlockedChange: (next: Record<number, { disabled: boolean; reason: string }>) => void;
}> = ({ open, editingId, onBlockedChange }) => {
  const { t } = useTranslation();
  const sourceType = Form.useWatch('source_type') as string | undefined;
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void serviceDispatchApi
      .list({ skip: 0, limit: 200 })
      .then((res) => {
        if (cancelled) return;
        const blocked: Record<number, { disabled: boolean; reason: string }> = {};
        for (const row of res.items ?? []) {
          if (String(row.status ?? '').trim() === '已取消') continue;
          if (sourceType && row.source_type !== sourceType) continue;
          if (editingId && row.id === editingId) continue;
          blocked[row.source_id] = {
            disabled: true,
            reason: t('app.kuaizhizao.afterSalesService.dispatchOrder.sourceAlreadyDispatched', {
              code: row.dispatch_code,
            }),
          };
        }
        onBlockedChange(blocked);
      })
      .catch(() => {
        if (!cancelled) onBlockedChange({});
      });
    return () => {
      cancelled = true;
    };
  }, [editingId, onBlockedChange, open, sourceType, t]);
  return null;
};

export type DispatchOrderFormModalProps = {
  open: boolean;
  editing: ServiceDispatchOrder | null;
  onClose: () => void;
  onSuccess: () => void;
};

const DispatchOrderFormModal: React.FC<DispatchOrderFormModalProps> = ({
  open,
  editing,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const formRef = useRef<ProFormInstance>();
  const [submitting, setSubmitting] = useState(false);
  const [customerId, setCustomerId] = useState<number | undefined>();
  const [blockedSources, setBlockedSources] = useState<Record<number, { disabled: boolean; reason: string }>>({});
  const {
    customFields: formCustomFields,
    customFieldValues: formCustomFieldValues,
    loadFieldValues: loadFormCustomFieldValues,
    extractFormValues: extractCustomFormValues,
    saveCustomFieldValues,
    resetFieldValues: resetFormCustomFieldValues,
  } = useCustomFields({
    tableName: CUSTOM_FIELD_TABLE,
    hostResource: HOST_RESOURCE,
    loadWhenOpen: true,
    open,
  });

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const apply = async () => {
      if (editing) {
        setCustomerId(editing.customer_id != null ? Number(editing.customer_id) : undefined);
        const engineerUuid = await resolveUserUuidById(editing.engineer_id);
        if (cancelled) return;
        formRef.current?.setFieldsValue({
          ...editing,
          engineer_uuid: engineerUuid,
          planned_start_at_picker: editing.planned_start_at ? dayjs(editing.planned_start_at) : undefined,
          planned_end_at_picker: editing.planned_end_at ? dayjs(editing.planned_end_at) : undefined,
        });
        if (editing.id != null) {
          void loadFormCustomFieldValues(editing.id).then((cfValues) => {
            formRef.current?.setFieldsValue(cfValues);
          });
        }
      } else {
        setCustomerId(undefined);
        formRef.current?.resetFields();
        resetFormCustomFieldValues();
      }
    };
    void apply();
    return () => {
      cancelled = true;
    };
  }, [editing, loadFormCustomFieldValues, open, resetFormCustomFieldValues]);

  const handleFinish = async (values: Record<string, unknown>) => {
    const { customData, standardValues } = extractCustomFormValues(values, formRef.current);
    const {
      planned_start_at_picker,
      planned_end_at_picker,
      engineer_uuid: _uuid,
      ...rest
    } = standardValues as ServiceDispatchPayload & {
      planned_start_at_picker?: dayjs.Dayjs;
      planned_end_at_picker?: dayjs.Dayjs;
      engineer_uuid?: string;
    };
    const payload: ServiceDispatchPayload = {
      ...rest,
      planned_start_at: planned_start_at_picker?.format('YYYY-MM-DD HH:mm:ss'),
      planned_end_at: planned_end_at_picker?.format('YYYY-MM-DD HH:mm:ss'),
    };
    setSubmitting(true);
    try {
      let savedId = editing?.id;
      if (editing) {
        await serviceDispatchApi.update(editing.id, payload);
        messageApi.success(t('common.saveSuccess'));
      } else {
        const created = await serviceDispatchApi.create(payload);
        savedId = created.id;
        messageApi.success(t('common.createSuccess'));
      }
      if (savedId != null) {
        await saveCustomFieldValues(savedId, customData);
      }
      resetFormCustomFieldValues();
      onSuccess();
      onClose();
    } catch (error) {
      messageApi.error(formatApiErrorDetail(error) || t('common.saveFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <FormModalTemplate
      key={editing?.id ?? 'create'}
      formRef={formRef}
      open={open}
      onClose={() => {
        resetFormCustomFieldValues();
        onClose();
      }}
      title={
        editing
          ? t('app.kuaizhizao.afterSalesService.dispatchOrder.editTitle')
          : t('app.kuaizhizao.afterSalesService.dispatchOrder.createTitle')
      }
      width={MODAL_CONFIG.STANDARD_WIDTH}
      grid={false}
      isEdit={Boolean(editing)}
      loading={submitting}
      onFinish={handleFinish}
    >
      <DispatchBlockedSourcesSync
        open={open}
        editingId={editing?.id}
        onBlockedChange={setBlockedSources}
      />
      <Row gutter={16}>
        <Col span={12}>
          <Form.Item name="customer_name" hidden>
            <Input />
          </Form.Item>
          <Form.Item
            name="customer_id"
            label={t('app.kuaizhizao.afterSalesService.dispatchOrder.field.customerName')}
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
                  source_id: undefined,
                  source_code: undefined,
                });
              }}
            />
          </Form.Item>
        </Col>
        <Col span={12}>
          <AfterSalesSourceDocumentSelect
            customerId={customerId}
            allowedTypes={['install_execution', 'repair_order']}
            typeLabelKeyPrefix="app.kuaizhizao.afterSalesService.dispatchOrder.field"
            optionStateById={blockedSources}
          />
        </Col>
        <Col span={12}>
          <Form.Item name="engineer_id" hidden>
            <Input />
          </Form.Item>
          <Form.Item name="engineer_name" hidden>
            <Input />
          </Form.Item>
          <UniUserSelect
            name="engineer_uuid"
            label={t('app.kuaizhizao.afterSalesService.dispatchOrder.field.engineerName')}
            onChange={(_value, user) => {
              const picked = Array.isArray(user) ? user[0] : user;
              formRef.current?.setFieldsValue({
                engineer_id: picked?.id,
                engineer_name: picked?.full_name || picked?.username,
              });
            }}
          />
        </Col>
        <Col span={12}>
          <Form.Item name="site_address" label={t('app.kuaizhizao.afterSalesService.dispatchOrder.field.siteAddress')}>
            <Input.TextArea rows={2} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item
            name="planned_start_at_picker"
            label={t('app.kuaizhizao.afterSalesService.dispatchOrder.field.plannedStartAt')}
            {...formDateFormItemProps}
          >
            <DatePicker showTime style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item
            name="planned_end_at_picker"
            label={t('app.kuaizhizao.afterSalesService.dispatchOrder.field.plannedEndAt')}
            {...formDateFormItemProps}
          >
            <DatePicker showTime style={{ width: '100%' }} />
          </Form.Item>
        </Col>
      </Row>

      <CustomFieldsFormSection
        customFields={formCustomFields}
        customFieldValues={formCustomFieldValues}
        gridColumns={2}
      />

      <Row gutter={16}>
        <Col span={24}>
          <Form.Item name="notes" label={t('common.remark')}>
            <Input.TextArea rows={2} />
          </Form.Item>
        </Col>
      </Row>
    </FormModalTemplate>
  );
};

export default DispatchOrderFormModal;
