import React, { useState } from 'react';
import { Button, Col, Form, Input, Modal, Row, Space, Switch, Typography } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { LOGIN_QUICK_PROVIDER_IDS, type LoginQuickProviderId } from '../../constants/loginQuickProviders';

const PROVIDER_LABEL_KEYS: Record<LoginQuickProviderId, string> = {
  gitee: 'pages.infra.platform.loginQuickProviderGitee',
  wechat_work: 'pages.infra.platform.loginQuickProviderWechatWork',
  dingtalk: 'pages.infra.platform.loginQuickProviderDingtalk',
  feishu: 'pages.infra.platform.loginQuickProviderFeishu',
};

export type LoginQuickProvidersSwitchesRowProps = {
  /** 平台管理：GITEE 旁显示「配置」打开 OAuth 凭证弹窗 */
  showGiteeOauthCredentials?: boolean;
  giteeSecretConfigured?: boolean;
};

const LoginQuickProvidersSwitchesRow: React.FC<LoginQuickProvidersSwitchesRowProps> = ({
  showGiteeOauthCredentials = false,
  giteeSecretConfigured = false,
}) => {
  const { t } = useTranslation();
  const [giteeModalOpen, setGiteeModalOpen] = useState(false);

  return (
    <div className="login-page-quick-providers-switches">
      <Typography.Text type="secondary" className="login-page-quick-providers-switches-title">
        {t('pages.infra.platform.loginQuickProvidersTitle')}
      </Typography.Text>
      <Row gutter={[16, 8]} style={{ marginTop: 8 }}>
        {LOGIN_QUICK_PROVIDER_IDS.map((providerId) => {
          const isGitee = providerId === 'gitee';
          const label = t(PROVIDER_LABEL_KEYS[providerId]);
          return (
            <Col xs={24} sm={12} md={{ flex: '1 1 0' }} style={{ minWidth: 0 }} key={providerId}>
              <Form.Item
                name={['login_quick_providers', providerId]}
                label={
                  isGitee && showGiteeOauthCredentials ? (
                    <Space size={8} wrap>
                      <span>{label}</span>
                      <Button
                        type="link"
                        size="small"
                        icon={<SettingOutlined />}
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setGiteeModalOpen(true);
                        }}
                        style={{ paddingInline: 0, height: 'auto' }}
                      >
                        {t('pages.infra.platform.giteeOauthConfigButton')}
                      </Button>
                    </Space>
                  ) : (
                    label
                  )
                }
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>
            </Col>
          );
        })}
      </Row>

      {showGiteeOauthCredentials ? (
        <Modal
          title={t('pages.infra.platform.giteeOauthCredentialsTitle')}
          open={giteeModalOpen}
          onCancel={() => setGiteeModalOpen(false)}
          onOk={() => setGiteeModalOpen(false)}
          okText={t('pages.infra.platform.giteeOauthConfigDone')}
          cancelButtonProps={{ style: { display: 'none' } }}
          destroyOnHidden={false}
          forceRender
          width={560}
          mask={{ closable: true }}
        >
          <Typography.Paragraph type="secondary" style={{ marginBottom: 16, fontSize: 12 }}>
            {t('pages.infra.platform.giteeOauthCredentialsHint')}
          </Typography.Paragraph>
          <Form.Item name="gitee_oauth_client_id" label={t('pages.infra.platform.giteeOauthClientId')}>
            <Input
              allowClear
              placeholder={t('pages.infra.platform.giteeOauthClientIdPlaceholder')}
              autoComplete="off"
            />
          </Form.Item>
          <Form.Item
            name="gitee_oauth_client_secret"
            label={t('pages.infra.platform.giteeOauthClientSecret')}
            extra={
              giteeSecretConfigured
                ? t('pages.infra.platform.giteeOauthClientSecretConfiguredHint')
                : undefined
            }
          >
            <Input.Password
              allowClear
              placeholder={
                giteeSecretConfigured
                  ? t('pages.infra.platform.giteeOauthClientSecretKeepPlaceholder')
                  : t('pages.infra.platform.giteeOauthClientSecretPlaceholder')
              }
              autoComplete="new-password"
            />
          </Form.Item>
        </Modal>
      ) : null}
    </div>
  );
};

export default LoginQuickProvidersSwitchesRow;
