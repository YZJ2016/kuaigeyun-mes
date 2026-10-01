/**
 * 平台超管「管理员信息」：排版对齐个人资料（左摘要卡 + 右编辑/安全 Tabs）。
 */

import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ProForm,
  ProFormSwitch,
  ProFormText,
  type ProFormInstance,
} from '@ant-design/pro-components';
import {
  App,
  Avatar,
  Button,
  Card,
  Col,
  Descriptions,
  Divider,
  Grid,
  Row,
  Space,
  Tabs,
  Typography,
} from 'antd';
import { LogoutOutlined, UserOutlined } from '@ant-design/icons';
import { MarkerTag } from '../../../constants/statusBadges';
import { formatDateTimeBySiteSetting } from '../../../utils/format';
import {
  updateInfraSuperAdmin,
  type InfraSuperAdmin,
  type InfraSuperAdminUpdateRequest,
} from '../../../services/infraAdmin';
import InfraAdminPasswordPanel from './InfraAdminPasswordPanel';

const { Title, Text } = Typography;

export type InfraAdminInfoPaneProps = {
  admin?: InfraSuperAdmin;
  loading?: boolean;
  onLogout: () => void;
  onUpdated?: () => void;
};

const InfraAdminInfoPane: React.FC<InfraAdminInfoPaneProps> = ({
  admin,
  loading,
  onLogout,
  onUpdated,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const screens = Grid.useBreakpoint();
  const isDesktopTwoPane = !!screens.md;
  const formRef = useRef<ProFormInstance>();
  const [activeTab, setActiveTab] = useState('basic');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!admin) return;
    formRef.current?.setFieldsValue({
      username: admin.username,
      email: admin.email ?? '',
      full_name: admin.full_name ?? '',
      is_active: admin.is_active,
    });
  }, [admin]);

  const handleBasicSubmit = async (values: {
    email?: string;
    full_name?: string;
    is_active?: boolean;
  }) => {
    setSaving(true);
    try {
      const payload: InfraSuperAdminUpdateRequest = {
        email: values.email?.trim() ? values.email.trim() : undefined,
        full_name: values.full_name?.trim() ? values.full_name.trim() : undefined,
        is_active: values.is_active,
      };
      await updateInfraSuperAdmin(payload);
      messageApi.success(t('common.updateSuccess'));
      onUpdated?.();
    } catch (error: unknown) {
      const errMsg = error instanceof Error ? error.message : t('common.updateFailed');
      messageApi.error(errMsg);
      throw error;
    } finally {
      setSaving(false);
    }
  };

  const displayName = admin?.full_name?.trim() || admin?.username || t('pages.personal.profile.noName');

  return (
    <div
      style={{
        padding: '0 0 16px 0',
        margin: 0,
        boxSizing: 'border-box',
        height: isDesktopTwoPane
          ? 'calc(100vh - var(--header-height, 56px) - 96px)'
          : undefined,
        overflow: isDesktopTwoPane ? 'hidden' : undefined,
      }}
    >
      <Row gutter={16} style={{ height: isDesktopTwoPane ? '100%' : undefined }}>
        <Col xs={24} md={8} style={{ height: isDesktopTwoPane ? '100%' : undefined }}>
          <Card
            title={t('pages.personal.profile.userInfo')}
            loading={loading}
            extra={
              <Button type="link" icon={<LogoutOutlined />} onClick={onLogout} style={{ paddingInline: 0 }}>
                {t('pages.infra.admin.logout')}
              </Button>
            }
            style={{
              marginBottom: 16,
              position: isDesktopTwoPane ? 'sticky' : undefined,
              top: isDesktopTwoPane ? 0 : undefined,
            }}
          >
            <Space orientation="vertical" align="center" style={{ width: '100%' }}>
              <Avatar size={120} icon={<UserOutlined />} />
              <div style={{ textAlign: 'center', width: '100%' }}>
                <Title level={4} style={{ margin: '16px 0 8px 0' }}>
                  {displayName}
                </Title>
                <Text type="secondary">{admin?.username || '-'}</Text>
              </div>
            </Space>

            <Divider />

            <Descriptions column={1} size="small">
              <Descriptions.Item label={t('pages.infra.admin.id')}>
                {admin?.id ?? '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('pages.infra.admin.username')}>
                {admin?.username || '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('pages.infra.admin.email')}>
                {admin?.email?.trim() ? (
                  admin.email
                ) : (
                  <Text type="secondary">{t('pages.personal.profile.notSet')}</Text>
                )}
              </Descriptions.Item>
              <Descriptions.Item label={t('pages.infra.admin.fullName')}>
                {admin?.full_name?.trim() ? (
                  admin.full_name
                ) : (
                  <Text type="secondary">{t('pages.personal.profile.notSet')}</Text>
                )}
              </Descriptions.Item>
              <Descriptions.Item label={t('common.status')}>
                <MarkerTag color={admin?.is_active ? 'success' : 'default'}>
                  {admin?.is_active
                    ? t('pages.infra.admin.statusActive')
                    : t('pages.infra.admin.statusInactive')}
                </MarkerTag>
              </Descriptions.Item>
              <Descriptions.Item label={t('pages.infra.admin.lastLogin')}>
                {admin?.last_login
                  ? formatDateTimeBySiteSetting(admin.last_login)
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('common.createdAt')}>
                {admin?.created_at
                  ? formatDateTimeBySiteSetting(admin.created_at)
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('common.updatedAt')}>
                {admin?.updated_at
                  ? formatDateTimeBySiteSetting(admin.updated_at)
                  : '-'}
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>

        <Col
          xs={24}
          md={16}
          style={{
            height: isDesktopTwoPane ? '100%' : undefined,
            minHeight: isDesktopTwoPane ? 0 : undefined,
          }}
        >
          <Card
            title={t('pages.personal.profile.editProfile')}
            loading={loading}
            style={{
              height: isDesktopTwoPane ? '100%' : undefined,
              display: isDesktopTwoPane ? 'flex' : undefined,
              flexDirection: isDesktopTwoPane ? 'column' : undefined,
            }}
            styles={
              isDesktopTwoPane
                ? {
                    body: {
                      flex: 1,
                      minHeight: 0,
                      overflow: 'auto',
                    },
                  }
                : undefined
            }
          >
            <Tabs
              activeKey={activeTab}
              onChange={setActiveTab}
              style={{ minHeight: isDesktopTwoPane ? '100%' : undefined }}
              items={[
                {
                  key: 'basic',
                  label: t('pages.personal.profile.basicInfo'),
                  children: (
                    <ProForm
                      formRef={formRef}
                      layout="vertical"
                      onFinish={async (values) => {
                        await handleBasicSubmit(
                          values as {
                            email?: string;
                            full_name?: string;
                            is_active?: boolean;
                          },
                        );
                        return true;
                      }}
                      submitter={{
                        searchConfig: { submitText: t('common.save') },
                        resetButtonProps: { style: { display: 'none' } },
                        submitButtonProps: { loading: saving },
                      }}
                    >
                      <Row gutter={16}>
                        <Col xs={24} sm={12}>
                          <ProFormText
                            name="username"
                            label={t('pages.infra.admin.username')}
                            disabled
                            fieldProps={{ maxLength: 50 }}
                          />
                        </Col>
                        <Col xs={24} sm={12}>
                          <ProFormText
                            name="full_name"
                            label={t('pages.infra.admin.fullName')}
                            fieldProps={{
                              placeholder: t('pages.infra.admin.fullName'),
                              maxLength: 100,
                            }}
                          />
                        </Col>
                      </Row>
                      <Row gutter={16}>
                        <Col xs={24} sm={12}>
                          <ProFormText
                            name="email"
                            label={t('pages.infra.admin.email')}
                            fieldProps={{
                              placeholder: t('pages.login.emailPlaceholder'),
                              type: 'email',
                              maxLength: 255,
                            }}
                            rules={[
                              {
                                validator: (_, value) => {
                                  if (!value || String(value).trim() === '') {
                                    return Promise.resolve();
                                  }
                                  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
                                  if (emailRegex.test(String(value).trim())) {
                                    return Promise.resolve();
                                  }
                                  return Promise.reject(new Error(t('pages.login.emailInvalid')));
                                },
                              },
                            ]}
                          />
                        </Col>
                        <Col xs={24} sm={12}>
                          <ProFormSwitch
                            name="is_active"
                            label={t('common.status')}
                            fieldProps={{
                              checkedChildren: t('pages.infra.admin.statusActive'),
                              unCheckedChildren: t('pages.infra.admin.statusInactive'),
                            }}
                          />
                        </Col>
                      </Row>
                    </ProForm>
                  ),
                },
                {
                  key: 'security',
                  label: t('pages.personal.profile.securitySettings'),
                  children: <InfraAdminPasswordPanel embedded />,
                },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default InfraAdminInfoPane;
