/**
 * 班次新建/编辑弹窗
 */

import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ProFormDigit,
  ProFormInstance,
  ProFormSwitch,
  ProFormText,
  ProFormTimePicker,
} from '@ant-design/pro-components';
import { App } from 'antd';
import dayjs from 'dayjs';
import { FormModalTemplate } from '../../../components/layout-templates';
import { MODAL_CONFIG } from '../../../components/layout-templates/constants';
import { shiftApi } from '../services/performance';
import type { ShiftCreate, ShiftUpdate } from '../types/performance';
import {
  modalDateFieldProps,
  modalFieldLayoutFromColSpan,
  PERFORMANCE_FORM_MODAL_CLASS,
} from '../utils/performanceFormLayout';

export interface ShiftFormModalProps {
  open: boolean;
  onClose: () => void;
  editUuid: string | null;
  onSuccess: () => void;
}

function toClockDayjs(value?: string | null) {
  if (!value) return undefined;
  const parsed = dayjs(value, ['HH:mm:ss', 'HH:mm'], true);
  return parsed.isValid() ? parsed : undefined;
}

export const ShiftFormModal: React.FC<ShiftFormModalProps> = ({
  open,
  onClose,
  editUuid,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const formRef = useRef<ProFormInstance>();
  const [loading, setLoading] = useState(false);
  const isEdit = Boolean(editUuid);

  useEffect(() => {
    if (!open) return;
    formRef.current?.resetFields();
    formRef.current?.setFieldsValue({
      isActive: true,
      standardHours: 8,
      crossesMidnight: false,
      breakStart: undefined,
      breakEnd: undefined,
    });
    if (!editUuid) return;
    shiftApi
      .get(editUuid)
      .then((detail) => {
        formRef.current?.setFieldsValue({
          code: detail.code,
          name: detail.name,
          startTime: toClockDayjs(detail.startTime),
          endTime: toClockDayjs(detail.endTime),
          breakStart: toClockDayjs(detail.breakStart),
          breakEnd: toClockDayjs(detail.breakEnd),
          crossesMidnight: detail.crossesMidnight,
          standardHours: Number(detail.standardHours ?? 8),
          isActive: detail.isActive ?? true,
        });
      })
      .catch((err: any) =>
        messageApi.error(err?.message || t('app.kuaizhizao.performance.shifts.messages.loadFailed')),
      );
  }, [open, editUuid, messageApi, t]);

  const handleSubmit = async (values: Record<string, unknown>) => {
    try {
      setLoading(true);
      const breakStart = dayjs.isDayjs(values.breakStart)
        ? values.breakStart.format('HH:mm:ss')
        : values.breakStart || null;
      const breakEnd = dayjs.isDayjs(values.breakEnd)
        ? values.breakEnd.format('HH:mm:ss')
        : values.breakEnd || null;
      if (Boolean(breakStart) !== Boolean(breakEnd)) {
        messageApi.error(t('app.kuaizhizao.performance.shifts.messages.breakPairRequired'));
        return;
      }
      const payload = {
        code: values.code,
        name: values.name,
        startTime: dayjs.isDayjs(values.startTime)
          ? values.startTime.format('HH:mm:ss')
          : values.startTime,
        endTime: dayjs.isDayjs(values.endTime) ? values.endTime.format('HH:mm:ss') : values.endTime,
        breakStart,
        breakEnd,
        crossesMidnight: Boolean(values.crossesMidnight),
        standardHours: values.standardHours,
        isActive: Boolean(values.isActive),
      };
      if (isEdit && editUuid) {
        await shiftApi.update(editUuid, payload as ShiftUpdate);
        messageApi.success(t('common.updateSuccess'));
      } else {
        await shiftApi.create(payload as ShiftCreate);
        messageApi.success(t('common.createSuccess'));
      }
      onSuccess();
      onClose();
    } catch (err: any) {
      messageApi.error(
        err?.message || (isEdit ? t('common.updateFailed') : t('common.createFailed')),
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <FormModalTemplate
      title={
        isEdit
          ? t('app.kuaizhizao.performance.shifts.modal.editTitle')
          : t('app.kuaizhizao.performance.shifts.modal.createTitle')
      }
      open={open}
      onClose={onClose}
      onFinish={handleSubmit}
      isEdit={isEdit}
      loading={loading}
      width={MODAL_CONFIG.STANDARD_WIDTH}
      className={PERFORMANCE_FORM_MODAL_CLASS}
      formRef={formRef}
      layout="vertical"
      grid={false}
    >
      <ProFormText
        name="code"
        label={t('app.kuaizhizao.performance.shifts.form.code')}
        rules={[{ required: true }]}
        formItemProps={modalFieldLayoutFromColSpan(12)}
      />
      <ProFormText
        name="name"
        label={t('app.kuaizhizao.performance.shifts.form.name')}
        rules={[{ required: true }]}
        formItemProps={modalFieldLayoutFromColSpan(12)}
      />
      <ProFormTimePicker
        name="startTime"
        label={t('app.kuaizhizao.performance.shifts.form.startTime')}
        rules={[{ required: true }]}
        {...modalDateFieldProps()}
      />
      <ProFormTimePicker
        name="endTime"
        label={t('app.kuaizhizao.performance.shifts.form.endTime')}
        rules={[{ required: true }]}
        {...modalDateFieldProps()}
      />
      <ProFormTimePicker
        name="breakStart"
        label={t('app.kuaizhizao.performance.shifts.form.breakStart')}
        {...modalDateFieldProps()}
        formItemProps={{
          ...modalFieldLayoutFromColSpan(12),
          extra: t('app.kuaizhizao.performance.shifts.form.breakHint'),
        }}
      />
      <ProFormTimePicker
        name="breakEnd"
        label={t('app.kuaizhizao.performance.shifts.form.breakEnd')}
        {...modalDateFieldProps()}
        formItemProps={modalFieldLayoutFromColSpan(12)}
      />
      <ProFormDigit
        name="standardHours"
        label={t('app.kuaizhizao.performance.shifts.form.standardHours')}
        min={0}
        max={24}
        fieldProps={{ precision: 2 }}
        formItemProps={modalFieldLayoutFromColSpan(12)}
      />
      <ProFormSwitch
        name="crossesMidnight"
        label={t('app.kuaizhizao.performance.shifts.form.crossesMidnight')}
        formItemProps={modalFieldLayoutFromColSpan(12)}
      />
      <ProFormSwitch
        name="isActive"
        label={t('common.enabled')}
        formItemProps={modalFieldLayoutFromColSpan(12)}
      />
    </FormModalTemplate>
  );
};
