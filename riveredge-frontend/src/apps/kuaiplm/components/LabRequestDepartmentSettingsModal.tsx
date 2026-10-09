/**
 * 实验委托：委托部门 / 检测部门可选范围设置（写入 parameters.kuaiplm.*）
 * 空 = 不限制（全量启用部门）。
 */

import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, App } from 'antd';
import { ProFormSelect, type ProFormInstance } from '@ant-design/pro-components';
import {
  FormModalGridBlock,
  FormModalTemplate,
  MODAL_CONFIG,
} from '../../../components/layout-templates';
import {
  batchUpdateProcessParameters,
  getBusinessConfig,
} from '../../../services/businessConfig';
import { getDepartmentTree } from '../../../services/department';
import { getApiErrorMessage } from '../../../utils/errorHandler';
import {
  flattenLabDeptOptions,
  normalizeDeptUuidList,
  resolveLabRequestDeptScopeFromConfig,
  type LabDeptOption,
} from '../utils/labRequestDepartmentScope';

type Props = {
  open: boolean;
  onClose: () => void;
  /** 保存成功后回调（刷新列表页下拉白名单） */
  onSaved?: (scope: { delegateUuids: string[]; testUuids: string[] }) => void;
};

export const LabRequestDepartmentSettingsModal: React.FC<Props> = ({
  open,
  onClose,
  onSaved,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const formRef = useRef<ProFormInstance>();
  const [loading, setLoading] = useState(false);
  const [deptOptions, setDeptOptions] = useState<LabDeptOption[]>([]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    void Promise.all([getBusinessConfig(), getDepartmentTree({ is_active: true })])
      .then(([config, deptRes]) => {
        if (cancelled) return;
        const options = flattenLabDeptOptions(deptRes.items ?? []);
        setDeptOptions(options);
        const scope = resolveLabRequestDeptScopeFromConfig(config);
        formRef.current?.setFieldsValue({
          lab_request_delegate_dept_uuids: scope.delegateUuids,
          lab_request_test_dept_uuids: scope.testUuids,
        });
      })
      .catch((error) => {
        if (cancelled) return;
        messageApi.error(getApiErrorMessage(error, t('common.loadFailed')));
        setDeptOptions([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, messageApi, t]);

  const selectOptions = deptOptions.map((o) => ({
    label: o.label,
    value: o.uuid,
  }));

  return (
    <FormModalTemplate
      title={t('app.kuaiplm.labRequest.deptSettings.title')}
      open={open}
      onClose={onClose}
      width={MODAL_CONFIG.STANDARD_WIDTH}
      formRef={formRef}
      loading={loading}
      grid
      onFinish={async (values) => {
        const delegateUuids = normalizeDeptUuidList(values.lab_request_delegate_dept_uuids);
        const testUuids = normalizeDeptUuidList(values.lab_request_test_dept_uuids);
        try {
          await batchUpdateProcessParameters({
            parameters: {
              kuaiplm: {
                lab_request_delegate_dept_uuids: delegateUuids,
                lab_request_test_dept_uuids: testUuids,
              },
            },
          });
          messageApi.success(t('common.saveSuccess'));
          onSaved?.({ delegateUuids, testUuids });
          onClose();
        } catch (error) {
          messageApi.error(getApiErrorMessage(error, t('common.saveFailed')));
          throw error;
        }
      }}
    >
      <FormModalGridBlock>
        <Alert
          type="info"
          showIcon
          title={t('app.kuaiplm.labRequest.deptSettings.hint')}
          style={{ marginBottom: 16 }}
        />
      </FormModalGridBlock>
      <ProFormSelect
        name="lab_request_delegate_dept_uuids"
        label={t('app.kuaiplm.labRequest.fields.delegateDept')}
        mode="multiple"
        showSearch
        allowClear
        options={selectOptions}
        placeholder={t('app.kuaiplm.labRequest.deptSettings.unlimitedPlaceholder')}
        fieldProps={{ optionFilterProp: 'label' }}
        colProps={{ span: 24 }}
      />
      <ProFormSelect
        name="lab_request_test_dept_uuids"
        label={t('app.kuaiplm.labRequest.fields.testDept')}
        mode="multiple"
        showSearch
        allowClear
        options={selectOptions}
        placeholder={t('app.kuaiplm.labRequest.deptSettings.unlimitedPlaceholder')}
        fieldProps={{ optionFilterProp: 'label' }}
        colProps={{ span: 24 }}
      />
    </FormModalTemplate>
  );
};
