import React, { useMemo, useRef, useState } from 'react';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { ProFormDigit, ProFormTextArea } from '@ant-design/pro-components';
import { App } from 'antd';
import { useTranslation } from 'react-i18next';
import { ActionConfirmPopconfirm } from '../../../../../components/action-confirm';
import { FormModalTemplate, ListPageTemplate, MODAL_CONFIG } from '../../../../../components/layout-templates';
import { MarkerTag } from '../../../../../constants/statusBadges';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { UniTable } from '../../../../../components/uni-table';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { downloadRecordsAsXlsx } from '../../../../../utils/exportRecordsXlsx';
import { fixedAssetService } from '../../../services/fixed-assets';

const RESOURCE = 'kuaicaiwu:fixed-asset';
const NS = 'app.kuaicaiwu.fixedAssets.periodClose';

type PeriodCloseRow = Record<string, unknown> & {
  id: number;
  period_year?: number;
  period_month?: number;
  fa_event_count?: number;
  voucher_pending_count?: number;
  voucher_draft_count?: number;
  voucher_reviewed_count?: number;
  voucher_posted_count?: number;
};

function resolveVoucherStatusLabel(row: PeriodCloseRow, t: (key: string) => string): string {
  const eventCount = Number(row.fa_event_count) || 0;
  const pending = Number(row.voucher_pending_count) || 0;
  const draft = Number(row.voucher_draft_count) || 0;
  const reviewed = Number(row.voucher_reviewed_count) || 0;
  const posted = Number(row.voucher_posted_count) || 0;

  if (eventCount <= 0) {
    return t(`${NS}.voucherStatus.noEvents`);
  }
  if (posted >= eventCount) {
    return t(`${NS}.voucherStatus.posted`);
  }
  if (pending > 0) {
    return t(`${NS}.voucherStatus.pendingGenerate`);
  }
  if (draft + reviewed > 0) {
    return t(`${NS}.voucherStatus.pendingPost`);
  }
  return t(`${NS}.voucherStatus.pendingGenerate`);
}

const FaPeriodClosePage: React.FC = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const { canUpdate } = useResourcePermissions(RESOURCE);
  const actionRef = useRef<ActionType>();
  const tableRowsRef = useRef<Record<string, unknown>[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [actionLoadingId, setActionLoadingId] = useState<number | null>(null);

  const handleGenerateVouchers = async (row: PeriodCloseRow) => {
    setActionLoadingId(row.id);
    try {
      const res = await fixedAssetService.generatePeriodCloseVouchers(row.id);
      message.success(
        t(`${NS}.generateSuccess`, {
          count: res.created_count ?? 0,
        }),
      );
      if (res.errors?.length) {
        message.warning(res.errors.slice(0, 3).join('；'));
      }
      actionRef.current?.reload();
    } catch (error) {
      message.error(getApiErrorMessage(error, t(`${NS}.generateFailed`)));
    } finally {
      setActionLoadingId(null);
    }
  };

  const handlePostVouchers = async (row: PeriodCloseRow) => {
    setActionLoadingId(row.id);
    try {
      const res = await fixedAssetService.postPeriodCloseVouchers(row.id);
      message.success(
        t(`${NS}.postSuccess`, {
          count: res.posted_count ?? 0,
        }),
      );
      if (res.errors?.length) {
        message.warning(res.errors.slice(0, 3).join('；'));
      }
      actionRef.current?.reload();
    } catch (error) {
      message.error(getApiErrorMessage(error, t(`${NS}.postFailed`)));
    } finally {
      setActionLoadingId(null);
    }
  };

  const columns: ProColumns<PeriodCloseRow>[] = useMemo(
    () => [
      {
        title: t(`${NS}.col.period`),
        dataIndex: 'period_year',
        width: 120,
        uniTableKeepWidth: true,
        render: (_, r) => `${r.period_year}-${String(r.period_month).padStart(2, '0')}`,
      },
      { title: t(`${NS}.col.closedAt`), dataIndex: 'closed_at', width: 180 },
      { title: t(`${NS}.col.closedBy`), dataIndex: 'closed_by_name', width: 120 },
      {
        title: t(`${NS}.col.voucherStatus`),
        width: 120,
        render: (_, r) => (
          <MarkerTag variant="filled">{resolveVoucherStatusLabel(r, t)}</MarkerTag>
        ),
      },
      {
        title: t(`${NS}.col.voucherProgress`),
        width: 140,
        render: (_, r) => {
          const total = Number(r.fa_event_count) || 0;
          const posted = Number(r.voucher_posted_count) || 0;
          if (total <= 0) return '—';
          return t(`${NS}.voucherProgress`, { posted, total });
        },
      },
      { title: t('common.notes'), dataIndex: 'notes', ellipsis: true },
      {
        title: t('common.actions'),
        valueType: 'option',
        width: 200,
        render: (_, record) => {
          if (!canUpdate) return [];
          const eventCount = Number(record.fa_event_count) || 0;
          const pending = Number(record.voucher_pending_count) || 0;
          const draft = Number(record.voucher_draft_count) || 0;
          const reviewed = Number(record.voucher_reviewed_count) || 0;
          const posted = Number(record.voucher_posted_count) || 0;
          const loading = actionLoadingId === record.id;
          const actions: React.ReactNode[] = [];

          if (eventCount > 0 && pending > 0) {
            actions.push(
              <a
                key="generate"
                style={loading ? { pointerEvents: 'none', opacity: 0.5 } : undefined}
                onClick={() => void handleGenerateVouchers(record)}
              >
                {t(`${NS}.action.generateVouchers`)}
              </a>,
            );
          }
          if (eventCount > 0 && posted < eventCount && (draft > 0 || reviewed > 0)) {
            actions.push(
              <ActionConfirmPopconfirm
                key="post"
                title={t(`${NS}.postConfirmTitle`)}
                description={t(`${NS}.postConfirmDesc`)}
                onConfirm={() => handlePostVouchers(record)}
              >
                <a style={loading ? { pointerEvents: 'none', opacity: 0.5 } : undefined}>
                  {t(`${NS}.action.postVouchers`)}
                </a>
              </ActionConfirmPopconfirm>,
            );
          }
          return actions;
        },
      },
    ],
    [t, canUpdate, actionLoadingId],
  );

  return (
    <ListPageTemplate>
      <UniTable
        actionRef={actionRef}
        rowKey="id"
        columnPersistenceId="apps.kuaicaiwu.fixed-assets.period-close.list-v2"
        columns={columns}
        permissionResource={RESOURCE}
        enableRowSelection
        selectedRowKeys={selectedRowKeys}
        onRowSelectionChange={setSelectedRowKeys}
        onTableDataChange={(rows) => {
          tableRowsRef.current = rows as Record<string, unknown>[];
        }}
        search={false}
        showCreateButton
        createButtonText={t(`${NS}.createButton`)}
        onCreate={() => setModalOpen(true)}
        showDeleteButton={false}
        showImportButton={false}
        showExportButton
        onExport={async (type, keys, pageData) => {
          let items = tableRowsRef.current;
          if (type === 'currentPage' && pageData?.length) {
            items = pageData as Record<string, unknown>[];
          } else if (type === 'selected' && keys?.length) {
            items = items.filter((row) => keys.includes(Number(row.id)));
          }
          if (items.length === 0) {
            message.warning(t('common.exportNoData'));
            return;
          }
          await downloadRecordsAsXlsx(items, [
            { key: 'period_year', title: t(`${NS}.field.year`) },
            { key: 'period_month', title: t(`${NS}.field.month`) },
            { key: 'closed_at', title: t(`${NS}.col.closedAt`) },
            { key: 'closed_by_name', title: t(`${NS}.col.closedBy`) },
            { key: 'notes', title: t('common.notes') },
          ], t(`${NS}.exportFileName`));
        }}
        request={async () => {
          const items = await fixedAssetService.listPeriodCloses();
          return { data: items, success: true, total: items.length };
        }}
      />
      <FormModalTemplate
        title={t(`${NS}.createTitle`)}
        open={modalOpen}
        onOpenChange={setModalOpen}
        modalProps={{ ...MODAL_CONFIG, destroyOnHidden: true }}
        onFinish={async (values) => {
          await fixedAssetService.closePeriod(values.period_year, values.period_month, values.notes);
          message.success(t(`${NS}.success`));
          setModalOpen(false);
          actionRef.current?.reload();
          return true;
        }}
      >
        <ProFormDigit name="period_year" label={t(`${NS}.field.year`)} rules={[{ required: true }]} />
        <ProFormDigit name="period_month" label={t(`${NS}.field.month`)} min={1} max={12} rules={[{ required: true }]} />
        <ProFormTextArea name="notes" label={t('common.notes')} />
      </FormModalTemplate>
    </ListPageTemplate>
  );
};

export default FaPeriodClosePage;
