import React, { useCallback, useState } from 'react';
import { App, Button, Input } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import { foreignTradeApi } from '../../services/foreignTradeApi';
import { INQUIRY_IMPORT_HEADERS, parseInquiryTsv } from '../../utils/inquiryImport';

export default function InquiryImportPage() {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const perms = useResourcePermissions('ind-foreign-trade:export-customer');
  const [importText, setImportText] = useState('');
  const [importing, setImporting] = useState(false);

  const runImport = useCallback(async () => {
    const items = parseInquiryTsv(importText);
    if (items.length === 0) {
      message.warning(t('app.ind-foreign-trade.import.empty'));
      return;
    }
    setImporting(true);
    try {
      const res = await foreignTradeApi.importInquiry(items);
      message.success(
        t('app.ind-foreign-trade.import.done', {
          success: res.success_count,
          failed: res.failed_count,
        }),
      );
      if (res.failed_count > 0) {
        const firstErr = res.items.find((i) => !i.success)?.error;
        if (firstErr) message.warning(firstErr);
      }
      if (res.success_count > 0) {
        navigate('/apps/ind-foreign-trade/export-customers');
      }
    } catch (e: any) {
      message.error(e?.message || t('app.ind-foreign-trade.import.failed'));
    } finally {
      setImporting(false);
    }
  }, [importText, message, navigate, t]);

  return (
    <ListPageTemplate>
      <div
        style={{
          maxWidth: 920,
          margin: '0 auto',
          padding: 16,
          border: '1px solid rgba(0, 0, 0, 0.06)',
          borderRadius: 6,
          background: '#f7f8fa',
        }}
      >
        <h2 style={{ marginTop: 0 }}>{t('app.ind-foreign-trade.import.title')}</h2>
        <p style={{ color: 'rgba(0,0,0,0.45)', marginBottom: 12 }}>
          {t('app.ind-foreign-trade.import.hint')}
        </p>
        <Input.TextArea
          rows={16}
          value={importText}
          onChange={(e) => setImportText(e.target.value)}
          placeholder={INQUIRY_IMPORT_HEADERS.join('\t')}
          disabled={!perms.canImport}
        />
        <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
          <Button type="primary" loading={importing} disabled={!perms.canImport} onClick={() => void runImport()}>
            {t('app.ind-foreign-trade.import.button')}
          </Button>
          <Button onClick={() => navigate('/apps/ind-foreign-trade/export-customers')}>
            {t('app.ind-foreign-trade.menu.exportCustomers')}
          </Button>
        </div>
      </div>
    </ListPageTemplate>
  );
}
