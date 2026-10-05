import React, { useCallback, useState } from 'react';
import { App, Button, Input } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import { foreignTradeApi } from '../../services/foreignTradeApi';
import {
  INQUIRY_FILE_HEADERS,
  parseInquirySpreadsheetMl,
  parseInquiryTsv,
  type InquiryParseResult,
} from '../../utils/inquiryImport';
import type { InquiryImportRow } from '../../services/foreignTradeApi';

export default function InquiryImportPage() {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const perms = useResourcePermissions('ind-foreign-trade:export-customer');
  const [importText, setImportText] = useState('');
  const [importing, setImporting] = useState(false);

  const explainParse = useCallback(
    (parsed: InquiryParseResult) => {
      if (parsed.ok) return null;
      if (parsed.reason === 'header') return t('app.ind-foreign-trade.import.headerMismatch');
      if (parsed.reason === 'notSpreadsheet') return t('app.ind-foreign-trade.import.notSpreadsheet');
      return t('app.ind-foreign-trade.import.empty');
    },
    [t],
  );

  const runImport = useCallback(
    async (items: InquiryImportRow[]) => {
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
    },
    [message, navigate, t],
  );

  const importPasted = useCallback(async () => {
    const parsed = parseInquiryTsv(importText);
    const errorText = explainParse(parsed);
    if (!parsed.ok) {
      message.warning(errorText || t('app.ind-foreign-trade.import.empty'));
      return;
    }
    await runImport(parsed.rows);
  }, [explainParse, importText, message, runImport, t]);

  const importFile = useCallback(
    async (file: File) => {
      const xml = await file.text();
      const parsed = parseInquirySpreadsheetMl(xml);
      const errorText = explainParse(parsed);
      if (!parsed.ok) {
        message.warning(errorText || t('app.ind-foreign-trade.import.failed'));
        return;
      }
      await runImport(parsed.rows);
    },
    [explainParse, message, runImport, t],
  );

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
        <div style={{ marginBottom: 12 }}>
          <input
            type="file"
            accept=".xls,.xml,text/xml,application/vnd.ms-excel"
            disabled={!perms.canImport || importing}
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = '';
              if (file) void importFile(file);
            }}
          />
        </div>
        <Input.TextArea
          rows={16}
          value={importText}
          onChange={(e) => setImportText(e.target.value)}
          placeholder={INQUIRY_FILE_HEADERS.join('\t')}
          disabled={!perms.canImport}
        />
        <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
          <Button type="primary" loading={importing} disabled={!perms.canImport} onClick={() => void importPasted()}>
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
