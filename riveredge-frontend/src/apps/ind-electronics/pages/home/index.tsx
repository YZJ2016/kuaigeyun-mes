import React from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Card, Typography } from 'antd';
import { ListPageTemplate } from '../../../../components/layout-templates';

const { Paragraph } = Typography;

/** 电子制造行业包首页：说明已启用的替代/独立扩展。 */
export default function IndElectronicsHomePage() {
  const { t } = useTranslation();
  return (
    <ListPageTemplate>
      <Card>
        <Paragraph>{t('app.ind-electronics.home.intro')}</Paragraph>
        <Alert
          type="info"
          showIcon
          title={t('app.ind-electronics.home.replaceTitle')}
          description={t('app.ind-electronics.home.replaceHint')}
          style={{ marginBottom: 16 }}
        />
        <Alert
          type="success"
          showIcon
          title={t('app.ind-electronics.home.standaloneTitle')}
          description={t('app.ind-electronics.home.standaloneHint')}
        />
      </Card>
    </ListPageTemplate>
  );
}
