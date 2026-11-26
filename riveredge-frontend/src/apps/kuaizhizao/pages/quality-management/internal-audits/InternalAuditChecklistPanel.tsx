import React, { useEffect, useState } from 'react';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { App, Button, Input, Popconfirm, Select, Table } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  qualityQmsApi,
  QmsInternalAuditChecklistItem,
} from '../../../services/quality-qms';
import QmsClauseSelect from '../qms/QmsClauseSelect';
import {
  QMS_CHECKLIST_CONCLUSION_OPTIONS,
  QMS_NC_SEVERITY_OPTIONS,
} from '../qms/qmsMeta';

type Props = {
  auditId: number;
  standardId?: number | null;
  canUpdate: boolean;
  readOnly: boolean;
  onChanged?: () => void;
};

const InternalAuditChecklistPanel: React.FC<Props> = ({
  auditId,
  standardId,
  canUpdate,
  readOnly,
  onChanged,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const [rows, setRows] = useState<QmsInternalAuditChecklistItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState<{
    clause_id?: number;
    checkpoint?: string;
    conclusion: string;
    evidence?: string;
    nc_severity?: string;
  }>({ conclusion: 'pending', nc_severity: 'general' });

  const reload = async () => {
    setLoading(true);
    try {
      const res = await qualityQmsApi.internalAudits.checklistItems(auditId);
      setRows(res.items || []);
    } catch (e: any) {
      messageApi.error(e?.message || t('common.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void reload();
  }, [auditId]);

  const addRow = async () => {
    if (!draft.clause_id) {
      messageApi.warning(t('app.kuaizhizao.quality.qms.checklist.clauseRequired'));
      return;
    }
    try {
      await qualityQmsApi.internalAudits.createChecklistItem(auditId, {
        clause_id: draft.clause_id,
        checkpoint: draft.checkpoint,
        conclusion: draft.conclusion,
        evidence: draft.evidence,
        sort_order: rows.length + 1,
        nc_severity: draft.conclusion === 'nonconform' ? draft.nc_severity : undefined,
      });
      setDraft({ conclusion: 'pending', nc_severity: 'general' });
      messageApi.success(t('common.saveSuccess'));
      await reload();
      onChanged?.();
    } catch (e: any) {
      messageApi.error(e?.message || t('common.saveFailed'));
    }
  };

  const patchRow = async (
    row: QmsInternalAuditChecklistItem,
    patch: Partial<QmsInternalAuditChecklistItem> & { nc_severity?: string },
  ) => {
    try {
      await qualityQmsApi.internalAudits.updateChecklistItem(auditId, row.id, patch);
      await reload();
      onChanged?.();
    } catch (e: any) {
      messageApi.error(e?.message || t('common.saveFailed'));
    }
  };

  const removeRow = async (row: QmsInternalAuditChecklistItem) => {
    try {
      await qualityQmsApi.internalAudits.deleteChecklistItem(auditId, row.id);
      messageApi.success(t('common.deleteSuccess'));
      await reload();
      onChanged?.();
    } catch (e: any) {
      messageApi.error(e?.message || t('common.operationFailed'));
    }
  };

  const conclusionOptions = QMS_CHECKLIST_CONCLUSION_OPTIONS.map((o) => ({
    value: o.value,
    label: t(o.labelKey),
  }));

  return (
    <div>
      <div style={{ fontWeight: 600, marginBottom: 8 }}>
        {t('app.kuaizhizao.quality.qms.checklist.rows')}
      </div>
      {canUpdate && !readOnly ? (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
          <div style={{ minWidth: 220, flex: 1 }}>
            <QmsClauseSelect
              value={draft.clause_id}
              onChange={(v) => setDraft((prev) => ({ ...prev, clause_id: Number(v) || undefined }))}
              standardId={standardId || undefined}
              disabled={!standardId}
            />
          </div>
          <Input
            style={{ flex: 1, minWidth: 160 }}
            placeholder={t('app.kuaizhizao.quality.qms.checklist.checkpoint')}
            value={draft.checkpoint}
            onChange={(e) => setDraft((prev) => ({ ...prev, checkpoint: e.target.value }))}
          />
          <Select
            style={{ width: 120 }}
            options={conclusionOptions}
            value={draft.conclusion}
            onChange={(v) => setDraft((prev) => ({ ...prev, conclusion: v }))}
          />
          {draft.conclusion === 'nonconform' ? (
            <Select
              style={{ width: 100 }}
              value={draft.nc_severity}
              options={QMS_NC_SEVERITY_OPTIONS.filter((o) => o.value !== 'observation').map((o) => ({
                value: o.value,
                label: t(o.labelKey),
              }))}
              onChange={(v) => setDraft((prev) => ({ ...prev, nc_severity: v }))}
            />
          ) : null}
          <Button type="primary" icon={<PlusOutlined />} onClick={() => void addRow()}>
            {t('app.kuaizhizao.quality.qms.checklist.addRow')}
          </Button>
        </div>
      ) : null}
      <Table
        size="small"
        rowKey="id"
        loading={loading}
        pagination={false}
        dataSource={rows}
        columns={[
          {
            title: t('app.kuaizhizao.quality.qms.clauseLabel'),
            dataIndex: 'clause_label',
            width: 160,
            ellipsis: true,
          },
          {
            title: t('app.kuaizhizao.quality.qms.checklist.checkpoint'),
            dataIndex: 'checkpoint',
            ellipsis: true,
          },
          {
            title: t('app.kuaizhizao.quality.qms.checklist.conclusion'),
            dataIndex: 'conclusion',
            width: 130,
            render: (value, row) =>
              canUpdate && !readOnly ? (
                <Select
                  size="small"
                  style={{ width: '100%' }}
                  value={value}
                  options={conclusionOptions}
                  onChange={(v) =>
                    void patchRow(row, {
                      conclusion: v,
                      nc_severity: v === 'nonconform' ? 'general' : undefined,
                    })
                  }
                />
              ) : (
                conclusionOptions.find((o) => o.value === value)?.label || value
              ),
          },
          {
            title: t('app.kuaizhizao.quality.qms.checklist.evidence'),
            dataIndex: 'evidence',
            ellipsis: true,
            render: (value, row) =>
              canUpdate && !readOnly ? (
                <Input
                  size="small"
                  defaultValue={value || ''}
                  onBlur={(e) => {
                    if ((e.target.value || '') !== (value || '')) {
                      void patchRow(row, { evidence: e.target.value });
                    }
                  }}
                />
              ) : (
                value || '-'
              ),
          },
          {
            title: t('app.kuaizhizao.quality.qms.ncReportCode'),
            dataIndex: 'nc_report_code',
            width: 140,
            render: (value, row) =>
              value
                ? `${value}${row.nc_report_status ? ` (${row.nc_report_status})` : ''}`
                : '-',
          },
          ...(canUpdate && !readOnly
            ? [
                {
                  title: t('common.actions'),
                  width: 48,
                  render: (_: unknown, row: QmsInternalAuditChecklistItem) => (
                    <Popconfirm
                      title={t('app.kuaizhizao.quality.qms.checklist.deleteConfirm')}
                      okText={t('common.confirm')}
                      cancelText={t('common.cancel')}
                      onConfirm={() => removeRow(row)}
                    >
                      <Button type="link" danger size="small" icon={<DeleteOutlined />} />
                    </Popconfirm>
                  ),
                },
              ]
            : []),
        ]}
      />
    </div>
  );
};

export default InternalAuditChecklistPanel;
