import React, { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ProForm, ProFormText, type ProFormInstance } from '@ant-design/pro-components';
import { App, theme, Typography } from 'antd';
import { changeInfraSuperAdminPassword } from '../../../services/infraAdmin';

const InfraAdminPasswordPanel: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const { token } = theme.useToken();
  const formRef = useRef<ProFormInstance>();
  const [loading, setLoading] = useState(false);

  const handleFinish = async (values: {
    old_password: string;
    new_password: string;
    confirm_password: string;
  }) => {
    if (values.new_password !== values.confirm_password) {
      throw new Error(t('pages.personal.profile.passwordMismatch'));
    }
    setLoading(true);
    try {
      await changeInfraSuperAdminPassword({
        old_password: values.old_password,
        new_password: values.new_password,
      });
      formRef.current?.resetFields();
      messageApi.success(t('pages.personal.profile.passwordChangeSuccess'));
    } catch (error: unknown) {
      const errMsg = error instanceof Error ? error.message : t('pages.personal.profile.passwordChangeFailed');
      messageApi.error(errMsg);
      throw error;
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        marginTop: 24,
        padding: 16,
        border: `1px solid ${token.colorBorderSecondary}`,
        borderRadius: token.borderRadiusLG,
        background: token.colorFillAlter,
        maxWidth: 480,
      }}
    >
      <Typography.Title level={5} style={{ marginTop: 0, marginBottom: 16 }}>
        {t('pages.infra.admin.changePasswordSectionTitle')}
      </Typography.Title>
      <ProForm
        formRef={formRef}
        layout="vertical"
        onFinish={async (values) => {
          await handleFinish(values as { old_password: string; new_password: string; confirm_password: string });
          return true;
        }}
        submitter={{
          searchConfig: {
            submitText: t('pages.personal.profile.changePassword'),
          },
          resetButtonProps: { style: { display: 'none' } },
          submitButtonProps: { loading },
        }}
      >
        <ProFormText.Password
          name="old_password"
          label={t('pages.personal.profile.currentPassword')}
          fieldProps={{
            placeholder: t('pages.personal.profile.currentPasswordPlaceholder'),
            autoComplete: 'current-password',
          }}
          rules={[
            { required: true, message: t('pages.personal.profile.currentPasswordPlaceholder') },
            { min: 8, message: t('pages.login.passwordLen') },
            { max: 128, message: t('pages.login.passwordLenMax') },
          ]}
        />
        <ProFormText.Password
          name="new_password"
          label={t('pages.personal.profile.newPassword')}
          fieldProps={{
            placeholder: t('pages.personal.profile.newPasswordPlaceholder'),
            autoComplete: 'new-password',
          }}
          rules={[
            { required: true, message: t('pages.personal.profile.newPassword') },
            { min: 8, message: t('pages.login.passwordLen') },
            { max: 128, message: t('pages.login.passwordLenMax') },
          ]}
        />
        <ProFormText.Password
          name="confirm_password"
          label={t('pages.personal.profile.confirmNewPassword')}
          fieldProps={{
            placeholder: t('pages.personal.profile.confirmNewPasswordPlaceholder'),
            autoComplete: 'new-password',
          }}
          rules={[
            { required: true, message: t('pages.personal.profile.confirmNewPasswordPlaceholder') },
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (!value || getFieldValue('new_password') === value) {
                  return Promise.resolve();
                }
                return Promise.reject(new Error(t('pages.login.confirmPasswordMismatch')));
              },
            }),
          ]}
        />
      </ProForm>
    </div>
  );
};

export default InfraAdminPasswordPanel;
