import React from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Card, Col, Result, Row, Space, Table, Typography, message } from 'antd';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import { useRequest } from 'ahooks';
import { indElectronicsEsdApi } from '../../services/esd';

const { Paragraph, Title, Text } = Typography;

/** ESD 独立功能入口：项目清单预览 + 点检/看板。 */
export default function IndElectronicsEsdHubPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const perms = useResourcePermissions('ind-electronics:esd');

  const { data, loading, refresh } = useRequest(
    () => indElectronicsEsdApi.getCatalog(),
    { ready: !perms.enabled || perms.canRead },
  );

  if (perms.enabled && !perms.canRead) {
    return (
      <ListPageTemplate>
        <Result status="403" title={t('common.noPermission')} />
      </ListPageTemplate>
    );
  }

  const projects = data?.project_types || [];
  const scheme = data?.scheme;

  return (
    <ListPageTemplate>
      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <Title level={4} style={{ margin: 0 }}>
            {t('app.ind-electronics.menu.esd')}
          </Title>
          <Space wrap>
            {perms.canUpdate ? (
              <Button
                onClick={async () => {
                  await indElectronicsEsdApi.ensureCatalog();
                  message.success(t('app.ind-electronics.esd.ensureOk'));
                  refresh();
                }}
              >
                {t('app.ind-electronics.esd.ensureCatalog')}
              </Button>
            ) : null}
            <Button type="primary" onClick={() => navigate('/apps/ind-electronics/esd/inspection')}>
              {t('app.ind-electronics.menu.esdInspection')}
            </Button>
            <Button onClick={() => navigate('/apps/ind-electronics/esd/dashboard')}>
              {t('app.ind-electronics.menu.esdDashboard')}
            </Button>
          </Space>
        </div>

        <Alert
          type="info"
          showIcon
          title={t('app.ind-electronics.esd.introTitle')}
          description={t('app.ind-electronics.esd.introDesc')}
        />

        <Row gutter={[16, 16]}>
          <Col xs={24} md={10}>
            <Card title={t('app.ind-electronics.esd.schemeCard')} loading={loading}>
              {scheme ? (
                <Space orientation="vertical" size={4}>
                  <Text>
                    {t('app.ind-electronics.esd.schemeCode')}: {scheme.code}
                  </Text>
                  <Text>
                    {t('app.ind-electronics.esd.schemeName')}: {scheme.name}
                  </Text>
                  <Text type="secondary">
                    {t('app.ind-electronics.esd.captureMode')}: {scheme.capture_mode} /{' '}
                    {scheme.cycle_type}
                  </Text>
                  <Text type="secondary">
                    {t('app.ind-electronics.esd.activeCount', { count: data?.active_count ?? 0 })}
                  </Text>
                </Space>
              ) : (
                <Paragraph type="secondary">{t('app.ind-electronics.esd.schemeMissing')}</Paragraph>
              )}
            </Card>
          </Col>
          <Col xs={24} md={14}>
            <Card title={t('app.ind-electronics.esd.projectListTitle')} loading={loading}>
              <Table
                size="small"
                tableLayout="fixed"
                pagination={false}
                rowKey={(r) => r.code}
                dataSource={projects}
                columns={[
                  { title: t('app.ind-electronics.esd.colCode'), dataIndex: 'code', width: 100 },
                  { title: t('app.ind-electronics.esd.colLabel'), dataIndex: 'label', ellipsis: true },
                  {
                    title: t('common.status'),
                    dataIndex: 'active',
                    width: 80,
                    render: (v: boolean) =>
                      v === false
                        ? t('app.ind-electronics.esd.inactive')
                        : t('app.ind-electronics.esd.active'),
                  },
                ]}
              />
            </Card>
          </Col>
        </Row>
      </Space>
    </ListPageTemplate>
  );
}
