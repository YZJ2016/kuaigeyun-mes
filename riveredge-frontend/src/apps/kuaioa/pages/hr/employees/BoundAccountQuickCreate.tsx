/**
 * 员工档案表单内「没有账号？一键创建」：生成登录账号 + 随机初始密码（无角色），
 * 创建成功后把 user_id 回填到外层员工表单的绑定字段，并仅本次展示凭据。
 */
import React, { useState } from 'react';
import { App, Form, Input, Modal, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { quickCreateEmployeeAccount } from '../../../services/employees';

type QuickCreateValues = {
  full_name: string;
  username?: string;
  phone?: string;
};

const BoundAccountQuickCreate: React.FC = () => {
  const { t } = useTranslation();
  const { message, modal } = App.useApp();
  const outerForm = Form.useFormInstance();
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [modalForm] = Form.useForm<QuickCreateValues>();

  const openModal = () => {
    modalForm.setFieldsValue({
      full_name: String(outerForm.getFieldValue('full_name') ?? ''),
      phone: String(outerForm.getFieldValue('phone') ?? ''),
      username: undefined,
    });
    setOpen(true);
  };

  const showCredentials = (username: string, password: string) => {
    modal.success({
      title: t('app.kuaioa.employee.accountCreated'),
      content: (
        <div>
          <div>
            {t('app.kuaioa.employee.accountUsername')}：
            <Typography.Text copyable strong>
              {username}
            </Typography.Text>
          </div>
          <div>
            {t('app.kuaioa.employee.accountPassword')}：
            <Typography.Text copyable strong>
              {password}
            </Typography.Text>
          </div>
          <div
            style={{
              marginTop: 8,
              color: 'var(--ant-color-text-secondary)',
              fontSize: 12,
            }}
          >
            {t('app.kuaioa.employee.accountCredentialHint')}
          </div>
        </div>
      ),
    });
  };

  const submit = async () => {
    const values = await modalForm.validateFields();
    setSubmitting(true);
    try {
      const res = await quickCreateEmployeeAccount({
        full_name: values.full_name.trim(),
        username: values.username?.trim() || undefined,
        phone: values.phone?.trim() || undefined,
      });
      outerForm.setFieldsValue({ user_id: res.user_id });
      setOpen(false);
      showCredentials(res.username, res.initial_password);
    } catch (error: unknown) {
      const err = error as { message?: string };
      message.error(err?.message || t('common.operationFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <Typography.Link onClick={openModal} style={{ fontSize: 12 }}>
        {t('app.kuaioa.employee.accountQuickCreate')}
      </Typography.Link>
      <Modal
        open={open}
        title={t('app.kuaioa.employee.accountQuickCreateTitle')}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        confirmLoading={submitting}
        onOk={() => void submit()}
        onCancel={() => setOpen(false)}
        destroyOnHidden
        width={420}
      >
        <Form form={modalForm} layout="vertical" preserve={false}>
          <Form.Item
            name="full_name"
            label={t('app.kuaioa.employee.fullName')}
            rules={[
              {
                required: true,
                message: t('app.kuaioa.employee.accountNameRequired'),
              },
            ]}
          >
            <Input maxLength={100} />
          </Form.Item>
          <Form.Item
            name="username"
            label={t('app.kuaioa.employee.accountUsername')}
            tooltip={t('app.kuaioa.employee.accountUsernameTip')}
          >
            <Input
              maxLength={50}
              placeholder={t('app.kuaioa.employee.accountUsernamePlaceholder')}
            />
          </Form.Item>
          <Form.Item name="phone" label={t('app.kuaioa.employee.phone')}>
            <Input maxLength={30} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default BoundAccountQuickCreate;
