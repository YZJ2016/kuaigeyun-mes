import React, { useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { ProFormInstance } from '@ant-design/pro-components';
import { ProFormSelect } from '@ant-design/pro-components';
import { App } from 'antd';
import { FormModalTemplate } from '../../../components/layout-templates';
import { getApiErrorMessage } from '../../../utils/errorHandler';
import { replyConfirmationFormRequest, type FormRequest } from '../services/forms';

type Props = {
  open: boolean;
  target: FormRequest | null;
  onClose: () => void;
  onSuccess: () => void;
};

const FormRequestSalesReplyModal: React.FC<Props> = ({ open, target, onClose, onSuccess }) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const formRef = useRef<ProFormInstance>();

  return (
    <FormModalTemplate
      title={t('app.kuaioa.formRequest.salesReplyTitle')}
      open={open}
      onClose={onClose}
      formRef={formRef}
      grid={false}
      onFinish={async (values) => {
        if (!target?.id) return;
        const confirmation_result = String(values.confirmation_result || '').trim();
        if (!confirmation_result) {
          messageApi.warning(t('app.kuaioa.formRequest.salesReplyNeedResult'));
          return;
        }
        try {
          await replyConfirmationFormRequest(target.id, { confirmation_result });
          messageApi.success(t('app.kuaioa.formRequest.salesReplySuccess'));
          onClose();
          onSuccess();
        } catch (error) {
          messageApi.error(getApiErrorMessage(error, t('common.operationFailed')));
        }
      }}
    >
      <ProFormSelect
        name="confirmation_result"
        label={t('app.kuaioa.formRequest.salesReplyResult')}
        rules={[{ required: true }]}
        options={[
          { value: 'agree', label: t('app.kuaioa.formRequest.confirmationResult.agree') },
          { value: 'reject', label: t('app.kuaioa.formRequest.confirmationResult.reject') },
          {
            value: 'conditional',
            label: t('app.kuaioa.formRequest.confirmationResult.conditional'),
          },
        ]}
      />
    </FormModalTemplate>
  );
};

export default FormRequestSalesReplyModal;
