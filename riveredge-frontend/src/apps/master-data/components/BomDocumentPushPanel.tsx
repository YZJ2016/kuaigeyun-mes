/**
 * 工程 BOM 外推：DocumentPushBatchPanel（source=engineering_bom → kingdee_eng_bom）。
 * 候选 id = 版本组 MIN(bom.id)。
 */
import React, { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { ApplicationConnection } from '../../../services/applicationConnection';
import type { API } from '../../../services/apiManagement';
import { DocumentPushBatchPanel } from '../../kuaizhizao/components/DocumentPushBatchPanel';
import { bomApi } from '../services/material';
import type { BOMGroupSummary } from '../types/material';

export interface BomPushCandidate {
  id: number;
  bom_code?: string;
  material_id?: number;
  version?: string;
  approval_status?: string;
  item_count?: number;
}

export interface BomDocumentPushPanelProps {
  open: boolean;
  onClose: () => void;
  bomIds?: number[];
  onComplete?: () => void;
  embedded?: boolean;
}

const DEFAULT_PROFILES: string[] = [];
const KINGDEE_PROFILES = ['kingdee_eng_bom'];
const SAVE_API_HINTS = ['eng_bom', '工程BOM', 'BOM', 'push_eng'];

function isKingdeeEngBomSaveApi(
  api: API,
  connection: ApplicationConnection | undefined,
): boolean {
  if (!connection) return false;
  if (api.connection_uuid && api.connection_uuid !== connection.uuid) return false;
  const code = String(api.code || '').toLowerCase();
  const path = String(api.path || '').toLowerCase();
  const name = String(api.name || '').toLowerCase();
  const hay = `${code} ${path} ${name}`;
  if (code.includes('save_eng_bom') || code.includes('push_eng_bom') || code.includes('push_eng')) {
    return true;
  }
  const isSave = path.includes('save') || hay.includes('save');
  const isBom = hay.includes('eng_bom') || name.includes('工程bom') || name.includes('bom');
  return isSave && isBom;
}

function preferBomApiUuid(items: API[]): string | undefined {
  const preferred =
    items.find((api) => String(api.code || '').toLowerCase().includes('push_eng_bom')) ||
    items.find((api) => String(api.code || '').toLowerCase().includes('save_eng_bom')) ||
    items.find((api) => String(api.name || '').includes('工程BOM')) ||
    items[0];
  return preferred?.uuid;
}

function toCandidate(row: BOMGroupSummary): BomPushCandidate | null {
  const id = Number(row.id);
  if (!Number.isFinite(id) || id <= 0) return null;
  return {
    id,
    bom_code: row.bom_code,
    material_id: row.material_id,
    version: row.version,
    approval_status: row.approval_status,
    item_count: row.item_count,
  };
}

export const BomDocumentPushPanel: React.FC<BomDocumentPushPanelProps> = ({
  open,
  onClose,
  bomIds,
  onComplete,
  embedded = false,
}) => {
  const { t } = useTranslation();

  const columns = useMemo(
    () => [
      {
        title: t('app.master-data.bom.bomCode', { defaultValue: 'BOM编码' }),
        dataIndex: 'bom_code',
        width: 160,
        ellipsis: true,
      },
      {
        title: t('app.master-data.bom.version', { defaultValue: '版本' }),
        dataIndex: 'version',
        width: 100,
      },
      {
        title: t('app.master-data.bom.approvalStatus', { defaultValue: '审核状态' }),
        dataIndex: 'approval_status',
        width: 100,
      },
      {
        title: t('app.master-data.bom.itemCount', { defaultValue: '子件数' }),
        dataIndex: 'item_count',
        width: 80,
      },
    ],
    [t],
  );

  const loadCandidates = useCallback(
    async ({
      keyword,
      page,
      pageSize,
      preferIds,
    }: {
      keyword: string;
      page: number;
      pageSize: number;
      preferIds: number[];
    }) => {
      const res = await bomApi.getGroups({
        keyword: keyword || undefined,
        skip: (page - 1) * pageSize,
        limit: pageSize,
        approvalStatus: 'approved',
        view: 'allBom',
      });
      let data = (res.data || [])
        .map(toCandidate)
        .filter((row): row is BomPushCandidate => !!row);

      if (preferIds.length && page === 1) {
        const preferSet = new Set(preferIds);
        data = [...data].sort((a, b) => (preferSet.has(a.id) ? 0 : 1) - (preferSet.has(b.id) ? 0 : 1));
      }

      return { data, total: res.total || data.length };
    },
    [],
  );

  if (!open) return null;

  return (
    <DocumentPushBatchPanel<BomPushCandidate>
      open={open}
      onClose={onClose}
      onComplete={onComplete}
      embedded={embedded}
      preferIds={bomIds}
      sourceType="engineering_bom"
      defaultProfiles={DEFAULT_PROFILES}
      kingdeeProfiles={KINGDEE_PROFILES}
      title={t('app.master-data.bom.documentPush.title', { defaultValue: '推送工程BOM' })}
      hint={t('app.master-data.bom.documentPush.hint', {
        defaultValue: '选择已审核 BOM 推送到外部系统',
      })}
      pipelineDesc={t('app.master-data.bom.documentPush.pipelineDesc', {
        defaultValue: '工程BOM → 金蝶 ENG_BOM',
      })}
      searchPlaceholder={t('app.master-data.bom.documentPush.searchPlaceholder', {
        defaultValue: '搜索BOM编码/物料',
      })}
      needSelectMessage={t('app.master-data.bom.documentPush.needSelect', {
        defaultValue: '请先勾选BOM',
      })}
      confirmText={t('app.kuaizhizao.documentPush.batch.confirm')}
      columns={columns}
      getRowLabel={(row) => row.bom_code || `${row.material_id}|${row.version}` || String(row.id)}
      loadCandidates={loadCandidates}
      matchSaveApi={isKingdeeEngBomSaveApi}
      preferSaveApi={preferBomApiUuid}
      saveApiSearchHints={SAVE_API_HINTS}
      showScheduleControls={false}
      successCountKey="app.kuaizhizao.documentPush.batch.success"
      partialCountKey="app.kuaizhizao.documentPush.batch.partial"
      failedTitleKey="app.kuaizhizao.documentPush.pushFailed"
      skippedHintKey="app.kuaizhizao.documentPush.batch.skippedHint"
    />
  );
};

export default BomDocumentPushPanel;
