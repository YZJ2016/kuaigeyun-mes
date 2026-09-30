import React from 'react';
import { Col, Form, Row, Switch, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { LOGIN_QUICK_PROVIDER_IDS, type LoginQuickProviderId } from '../../constants/loginQuickProviders';

const PROVIDER_LABEL_KEYS: Record<LoginQuickProviderId, string> = {
  wechat: 'pages.infra.platform.loginQuickProviderWechat',
  qq: 'pages.infra.platform.loginQuickProviderQq',
  wechat_work: 'pages.infra.platform.loginQuickProviderWechatWork',
  dingtalk: 'pages.infra.platform.loginQuickProviderDingtalk',
  feishu: 'pages.infra.platform.loginQuickProviderFeishu',
};

const LoginQuickProvidersSwitchesRow: React.FC = () => {
  const { t } = useTranslation();

  return (
    <div className="login-page-quick-providers-switches">
      <Typography.Text type="secondary" className="login-page-quick-providers-switches-title">
        {t('pages.infra.platform.loginQuickProvidersTitle')}
      </Typography.Text>
      <Row gutter={[16, 8]} style={{ marginTop: 8 }}>
        {LOGIN_QUICK_PROVIDER_IDS.map((providerId) => (
          <Col xs={24} sm={12} md={{ flex: '1 1 0' }} style={{ minWidth: 0 }} key={providerId}>
            <Form.Item
              name={['login_quick_providers', providerId]}
              label={t(PROVIDER_LABEL_KEYS[providerId])}
              valuePropName="checked"
            >
              <Switch />
            </Form.Item>
          </Col>
        ))}
      </Row>
    </div>
  );
};

export default LoginQuickProvidersSwitchesRow;
