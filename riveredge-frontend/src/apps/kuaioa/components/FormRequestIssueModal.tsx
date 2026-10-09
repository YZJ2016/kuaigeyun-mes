import React, { useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { ProFormInstance } from '@ant-design/pro-components';
import { ProFormSelect } from '@ant-design/pro-components';
import { App } from 'antd';
import { FormModalTemplate } from '../../../components/layout-templates';
import { UniUserSelect } from '../../../components/uni-user-select';
import { getRoleList } from '../../../services/role';
import { getApiErrorMessage } from '../../../utils/errorHandler';
import { issueFormRequest, type FormRequest } from '../services/forms';

type Props = {
  open: boolean;
  target: FormRequest | null;
  onClose: () => void;
  onSuccess: () => void;
};

const FormRequestIssueModal: React.FC<Props> = ({ open, target, onClose, onSuccess }) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const formRef = useRef<ProFormInstance>();

  return (
    <FormModalTemplate
      title={t('app.kuaioa.formRequest.issueTitle')}
      open={open}
      onClose={onClose}
      formRef={formRef}
      grid={false}
      onFinish={async (values) => {
        if (!target?.id) return;
        const userIds = (values.issue_user_ids as number[] | undefined) ?? [];
        const roleUuids = (values.issue_role_uuids as string[] | undefined) ?? [];
        if (!userIds.length && !roleUuids.length) {
          messageApi.warning(t('app.kuaioa.formRequest.issueNeedTargets'));
          return;
        }
        try {
          await issueFormRequest(target.id, {
            user_ids: userIds,
            role_uuids: roleUuids,
          });
          messageApi.success(t('app.kuaioa.formRequest.issueSuccess'));
          onClose();
          onSuccess();
        } catch (error) {
          messageApi.error(getApiErrorMessage(error, t('common.operationFailed')));
        }
      }}
    >
      <UniUserSelect
        name="issue_user_ids"
        label={t('app.kuaioa.formRequest.issueUsers')}
        mode="multiple"
      />
      <ProFormSelect
        name="issue_role_uuids"
        label={t('app.kuaioa.formRequest.issueRoles')}
        mode="multiple"
        showSearch
        request={async () => {
          const res = await getRoleList({ page_size: 200, is_active: true });
          return (res.items ?? []).map((r) => ({
            value: r.uuid,
            label: r.name,
          }));
        }}
      />
    </FormModalTemplate>
  );
};

export default FormRequestIssueModal;
