/**
 * 试流新建/编辑弹窗 — 头字段与工序预览由 form-profile 驱动
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ProFormDatePicker,
  ProFormDigit,
  ProFormInstance,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
} from '@ant-design/pro-components';
import { Alert, App, Col, Form as AntForm, Input, InputNumber, Row } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { FormModalGridBlock, FormModalTemplate } from '../../../components/layout-templates';
import { UniTableDetail } from '../../../components/uni-table-detail';
import { getApiErrorMessage } from '../../../utils/errorHandler';
import Phase2ProjectSelect from './Phase2ProjectSelect';
import {
  trialFlowApi,
  type TrialFlow,
  type TrialFlowBusinessType,
  type TrialFlowFormProfile,
  type TrialFlowMaterialLine,
} from '../services/trial-flow';
import { isIndustryFormProfileActive } from '../../../utils/industryFormProfile';
import {
  buildHeaderExtensionPayload,
  mergeHeaderExtensionIntoForm,
  sortedHeaderFields,
  stepsForBusinessType,
  type TrialFlowProfileHeaderField,
} from '../utils/trialFlowFormProfile';

const TYPE_KEYS: TrialFlowBusinessType[] = ['component', 'structure', 'complete'];

export interface TrialFlowFormModalProps {
  open: boolean;
  editing?: TrialFlow | null;
  filterProjectId?: number;
  onClose: () => void;
  onSuccess: () => void;
}

function renderHeaderField(field: TrialFlowProfileHeaderField) {
  const span = field.type === 'textarea' ? 24 : 12;
  const col = (
    <Col span={span} key={field.key}>
      {field.type === 'textarea' ? (
        <ProFormTextArea name={field.key} label={field.label} />
      ) : field.type === 'select' ? (
        <ProFormSelect
          name={field.key}
          label={field.label}
          options={field.options || []}
        />
      ) : field.type === 'date' ? (
        <ProFormDatePicker name={field.key} label={field.label} width="100%" />
      ) : field.type === 'decimal' ? (
        <ProFormDigit name={field.key} label={field.label} style={{ width: '100%' }} />
      ) : (
        <ProFormText name={field.key} label={field.label} />
      )}
    </Col>
  );
  return col;
}

const TrialFlowFormModal: React.FC<TrialFlowFormModalProps> = ({
  open,
  editing,
  filterProjectId,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const formRef = useRef<ProFormInstance | undefined>(undefined);
  const [formProfile, setFormProfile] = useState<TrialFlowFormProfile | null>(null);
  const [previewType, setPreviewType] = useState<TrialFlowBusinessType>('component');

  const typeLabel = (s: string) =>
    t(`app.kuaiplm.trialFlow.businessType.${s}`, { defaultValue: s });

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void trialFlowApi
      .formProfile()
      .then((p) => {
        if (!cancelled) setFormProfile(p);
      })
      .catch((e) => {
        if (!cancelled) messageApi.error(getApiErrorMessage(e));
      });
    return () => {
      cancelled = true;
    };
  }, [open, messageApi]);

  const industryActive = isIndustryFormProfileActive(formProfile);
  const headerFields = useMemo(
    () => sortedHeaderFields(formProfile, industryActive),
    [formProfile, industryActive],
  );
  const stepPreview = useMemo(
    () => stepsForBusinessType(formProfile, previewType, industryActive),
    [formProfile, previewType, industryActive],
  );

  const lineColumns = useMemo<ColumnsType>(
    () => [
      {
        title: t('app.kuaiplm.trialFlow.fields.materialCode'),
        dataIndex: 'material_code',
        width: 140,
        render: (_: unknown, __: unknown, index: number) => (
          <AntForm.Item
            name={[index, 'material_code']}
            rules={[{ required: true, message: t('common.required') }]}
            style={{ marginBottom: 0 }}
          >
            <Input size="small" />
          </AntForm.Item>
        ),
      },
      {
        title: t('app.kuaiplm.trialFlow.fields.materialName'),
        dataIndex: 'material_name',
        render: (_: unknown, __: unknown, index: number) => (
          <AntForm.Item
            name={[index, 'material_name']}
            rules={[{ required: true, message: t('common.required') }]}
            style={{ marginBottom: 0 }}
          >
            <Input size="small" />
          </AntForm.Item>
        ),
      },
      {
        title: t('app.kuaiplm.trialFlow.fields.qty'),
        dataIndex: 'qty',
        width: 100,
        render: (_: unknown, __: unknown, index: number) => (
          <AntForm.Item name={[index, 'qty']} style={{ marginBottom: 0 }}>
            <InputNumber size="small" style={{ width: '100%' }} />
          </AntForm.Item>
        ),
      },
      {
        title: t('app.kuaiplm.trialFlow.fields.unit'),
        dataIndex: 'unit',
        width: 80,
        render: (_: unknown, __: unknown, index: number) => (
          <AntForm.Item name={[index, 'unit']} style={{ marginBottom: 0 }}>
            <Input size="small" />
          </AntForm.Item>
        ),
      },
    ],
    [t],
  );

  const initialValues = useMemo(() => {
    if (editing) {
      return {
        project_id: editing.project_id,
        business_type: editing.business_type,
        title: editing.title,
        remarks: editing.remarks,
        ...mergeHeaderExtensionIntoForm(editing),
        materials: editing.materials?.length
          ? editing.materials
          : [{ material_code: '', material_name: '' }],
      };
    }
    return {
      project_id: filterProjectId,
      business_type: 'component' as TrialFlowBusinessType,
      materials: [{ material_code: '', material_name: '' }],
    };
  }, [editing, filterProjectId]);

  useEffect(() => {
    if (!open) return;
    const bt = (editing?.business_type || 'component') as TrialFlowBusinessType;
    setPreviewType(bt);
    formRef.current?.setFieldsValue(initialValues);
  }, [open, editing?.uuid, formProfile, initialValues, editing?.business_type]);

  return (
    <FormModalTemplate
      key={editing?.uuid ?? 'create-trial-flow'}
      title={
        editing
          ? t('app.kuaiplm.trialFlow.editButton', { defaultValue: t('common.edit') })
          : t('app.kuaiplm.trialFlow.createButton')
      }
      open={open}
      onClose={onClose}
      formRef={formRef}
      grid={false}
      width={headerFields.length ? 920 : 860}
      initialValues={initialValues}
      onFinish={async (values) => {
        try {
          const materials = ((values.materials || []) as TrialFlowMaterialLine[])
            .filter((m) => m?.material_code && m?.material_name)
            .map((m) => ({
              material_id: m.material_id ?? null,
              material_code: String(m.material_code).trim(),
              material_name: String(m.material_name).trim(),
              qty: m.qty ?? null,
              unit: m.unit || null,
              remarks: m.remarks || null,
            }));
          const payload = {
            project_id: Number(values.project_id),
            business_type: values.business_type as TrialFlowBusinessType,
            title: String(values.title || '').trim(),
            remarks: values.remarks || null,
            extension_payload: buildHeaderExtensionPayload(values, formProfile, industryActive),
            materials,
          };
          if (editing?.id) {
            await trialFlowApi.update(editing.id, payload);
          } else {
            await trialFlowApi.create(payload);
          }
          messageApi.success(t('common.saveSuccess'));
          onSuccess();
          onClose();
        } catch (e) {
          messageApi.error(getApiErrorMessage(e));
          throw e;
        }
      }}
    >
      <Row gutter={16}>
        <Col span={12}>
          <Phase2ProjectSelect
            name="project_id"
            label={t('app.kuaiplm.trialFlow.fields.project')}
            rules={[{ required: true }]}
            disabled={!!editing}
          />
        </Col>
        <Col span={12}>
          <ProFormSelect
            name="business_type"
            label={t('app.kuaiplm.trialFlow.fields.businessType')}
            rules={[{ required: true }]}
            disabled={!!editing}
            fieldProps={{
              onChange: (v) => setPreviewType(v as TrialFlowBusinessType),
            }}
            options={TYPE_KEYS.map((k) => ({ label: typeLabel(k), value: k }))}
          />
        </Col>
        <Col span={24}>
          <ProFormText
            name="title"
            label={t('app.kuaiplm.trialFlow.fields.title')}
            rules={[{ required: true }]}
          />
        </Col>
        {headerFields.map((field) => renderHeaderField(field))}
      </Row>
      {!editing && stepPreview.length > 0 ? (
        <FormModalGridBlock>
          <Alert
            type="info"
            showIcon
            title={t('app.kuaiplm.trialFlow.fields.stepPreview')}
            description={stepPreview.map((s) => s.step_name).join(' → ')}
          />
        </FormModalGridBlock>
      ) : null}
      <UniTableDetail
        name="materials"
        title={t('app.kuaiplm.trialFlow.fields.materials')}
        required
        requiredMessage={t('app.kuaiplm.trialFlow.messages.materialRequired')}
        columns={lineColumns}
        initialValue={{ material_code: '', material_name: '' }}
        minRows={1}
      />
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={24}>
          <ProFormTextArea name="remarks" label={t('common.remark')} />
        </Col>
      </Row>
    </FormModalTemplate>
  );
};

export default TrialFlowFormModal;
