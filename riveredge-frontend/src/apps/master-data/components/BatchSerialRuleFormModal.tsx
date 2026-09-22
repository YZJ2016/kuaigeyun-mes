/**
 * 批号 / 序列号规则新建编辑弹窗（可复用）
 *
 * 供规则管理页、物料表单内「快速新增规则」等场景使用。
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ProForm,
  ProFormDigit,
  ProFormInstance,
  ProFormSelect,
  ProFormSwitch,
  ProFormText,
  ProFormTextArea,
} from '@ant-design/pro-components';
import { App } from 'antd';
import { FormModalTemplate } from '../../../components/layout-templates';
import { MODAL_CONFIG } from '../../../components/layout-templates/constants';
import CodeRuleComponentBuilder from '../../../components/code-rule-component-builder';
import {
  batchRuleApi,
  serialRuleApi,
  type BatchRule,
  type SerialRule,
} from '../services/batchSerialRules';
import {
  BATCH_RULE_AVAILABLE_FIELDS,
  DEFAULT_BATCH_RULE_COMPONENTS,
} from '../constants/batchRuleConstants';
import {
  DEFAULT_SERIAL_RULE_COMPONENTS,
  SERIAL_RULE_AVAILABLE_FIELDS,
} from '../constants/serialRuleConstants';
import type { CodeRuleComponent } from '../../../types/codeRuleComponent';

export type BatchSerialRuleKind = 'batch' | 'serial';

export type BatchSerialRuleRecord = BatchRule | SerialRule;

export interface BatchSerialRuleFormModalProps {
  open: boolean;
  onClose: () => void;
  kind: BatchSerialRuleKind;
  /** 编辑时传入 uuid；快速新建传 null */
  editUuid?: string | null;
  onSuccess: (rule: BatchSerialRuleRecord) => void;
  zIndex?: number;
}

export const BatchSerialRuleFormModal: React.FC<BatchSerialRuleFormModalProps> = ({
  open,
  onClose,
  kind,
  editUuid = null,
  onSuccess,
  zIndex,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const formRef = useRef<ProFormInstance>();
  const [formLoading, setFormLoading] = useState(false);
  const [ruleComponents, setRuleComponents] = useState<CodeRuleComponent[]>([]);
  const isEdit = Boolean(editUuid);
  const isSerial = kind === 'serial';

  const seqResetOptions = useMemo(
    () => [
      { label: t('app.master-data.seqRules.seqResetNever'), value: 'never' },
      { label: t('app.master-data.seqRules.seqResetDaily'), value: 'daily' },
      { label: t('app.master-data.seqRules.seqResetMonthly'), value: 'monthly' },
      { label: t('app.master-data.seqRules.seqResetYearly'), value: 'yearly' },
    ],
    [t],
  );

  const defaultComponents = isSerial ? DEFAULT_SERIAL_RULE_COMPONENTS : DEFAULT_BATCH_RULE_COMPONENTS;
  const availableFields = isSerial ? SERIAL_RULE_AVAILABLE_FIELDS : BATCH_RULE_AVAILABLE_FIELDS;
  const reservedCode = isSerial ? 'SERIAL_DEFAULT' : 'BATCH_DEFAULT';
  const reservedCodeMessage = isSerial
    ? t('app.master-data.seqRules.serialDefaultCodeReserved')
    : t('app.master-data.seqRules.batchDefaultCodeReserved');
  const title = isEdit
    ? t(isSerial ? 'app.master-data.serialRules.editTitle' : 'app.master-data.batchRules.editTitle')
    : t(isSerial ? 'app.master-data.serialRules.createTitle' : 'app.master-data.batchRules.createTitle');
  const builderTitle = t(
    isSerial ? 'app.master-data.serialRules.builderTitle' : 'app.master-data.batchRules.builderTitle',
  );

  useEffect(() => {
    if (!open) return;
    formRef.current?.resetFields();
    if (!editUuid) {
      formRef.current?.setFieldsValue({ seqStart: 1, seqStep: 1, isActive: true });
      setRuleComponents([...defaultComponents]);
      return;
    }
    void (async () => {
      try {
        setFormLoading(true);
        const detail = isSerial
          ? await serialRuleApi.get(editUuid)
          : await batchRuleApi.get(editUuid);
        formRef.current?.setFieldsValue({
          name: detail.name,
          code: detail.code,
          description: detail.description,
          seqStart: detail.seqStart,
          seqStep: detail.seqStep,
          seqResetRule: detail.seqResetRule,
          isActive: detail.isActive,
        });
        setRuleComponents(
          detail.ruleComponents && Array.isArray(detail.ruleComponents) && detail.ruleComponents.length > 0
            ? (detail.ruleComponents as unknown as CodeRuleComponent[])
            : [...defaultComponents],
        );
      } catch (e: any) {
        messageApi.error(e?.message || t('app.master-data.seqRules.getDetailFailed'));
      } finally {
        setFormLoading(false);
      }
    })();
  }, [open, editUuid, defaultComponents, isSerial, messageApi, t]);

  const handleClose = () => {
    onClose();
    formRef.current?.resetFields();
    setRuleComponents([]);
  };

  const handleFinish = async (values: Record<string, unknown>) => {
    try {
      setFormLoading(true);
      const basePayload = {
        name: values.name as string,
        code: values.code as string,
        description: values.description as string,
        seqStart: (values.seqStart as number) ?? 1,
        seqStep: (values.seqStep as number) ?? 1,
        seqResetRule: values.seqResetRule as string,
        isActive: (values.isActive as boolean) ?? true,
      };
      const payload =
        ruleComponents.length > 0
          ? { ...basePayload, ruleComponents: ruleComponents as unknown as Record<string, unknown>[] }
          : basePayload;

      let saved: BatchSerialRuleRecord;
      if (isEdit && editUuid) {
        saved = isSerial
          ? await serialRuleApi.update(editUuid, payload)
          : await batchRuleApi.update(editUuid, payload);
        messageApi.success(t('common.updateSuccess'));
      } else {
        saved = isSerial
          ? await serialRuleApi.create(payload)
          : await batchRuleApi.create(payload);
        messageApi.success(t('common.createSuccess'));
      }
      onSuccess(saved);
      handleClose();
    } catch (e: any) {
      messageApi.error(e?.message || t('common.operationFailed'));
      throw e;
    } finally {
      setFormLoading(false);
    }
  };

  return (
    <FormModalTemplate
      title={title}
      open={open}
      onClose={handleClose}
      onFinish={handleFinish}
      isEdit={isEdit}
      width={MODAL_CONFIG.STANDARD_WIDTH}
      formRef={formRef}
      grid
      loading={formLoading}
      zIndex={zIndex}
    >
      <ProFormText
        name="name"
        label={t('app.master-data.seqRules.ruleName')}
        rules={[{ required: true }]}
        colProps={{ span: 12 }}
      />
      <ProFormText
        name="code"
        label={t('app.master-data.seqRules.ruleCode')}
        colProps={{ span: 12 }}
        placeholder={t('app.master-data.seqRules.ruleCodePlaceholder')}
        rules={[
          { required: true },
          {
            validator: async (_, value) => {
              const code = String(value ?? '').trim();
              if (code === reservedCode) {
                return Promise.reject(new Error(reservedCodeMessage));
              }
              return Promise.resolve();
            },
          },
        ]}
      />
      <ProFormDigit
        name="seqStart"
        label={t('app.master-data.seqRules.seqStart')}
        initialValue={1}
        colProps={{ span: 8 }}
      />
      <ProFormDigit
        name="seqStep"
        label={t('app.master-data.seqRules.seqStep')}
        initialValue={1}
        colProps={{ span: 8 }}
      />
      <ProFormSelect
        name="seqResetRule"
        label={t('app.master-data.seqRules.seqResetRule')}
        options={seqResetOptions}
        colProps={{ span: 8 }}
      />
      <ProForm.Item
        label={null}
        colon={false}
        colProps={{ span: 24 }}
        style={{ width: '100%', marginBottom: 24 }}
      >
        <div style={{ width: '100%', paddingLeft: 8, paddingRight: 8 }}>
          <CodeRuleComponentBuilder
            title={builderTitle}
            value={ruleComponents}
            onChange={setRuleComponents}
            availableFields={[...availableFields]}
            defaultComponents={defaultComponents}
          />
        </div>
      </ProForm.Item>
      <ProFormTextArea
        name="description"
        label={t('common.remark')}
        colProps={{ span: 24 }}
        fieldProps={{ rows: 2 }}
      />
      <ProFormSwitch
        name="isActive"
        label={t('common.status')}
        colProps={{ span: 12 }}
        initialValue={true}
      />
    </FormModalTemplate>
  );
};

export default BatchSerialRuleFormModal;
