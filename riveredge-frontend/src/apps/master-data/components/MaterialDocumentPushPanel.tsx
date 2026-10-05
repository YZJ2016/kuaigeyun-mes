/**
 * 物料主数据外推：DocumentPushBatchPanel（source=material → kingdee_bd_material）。
 */
import React, { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { ApplicationConnection } from '../../../services/applicationConnection';
import type { API } from '../../../services/apiManagement';
import { DocumentPushBatchPanel } from '../../kuaizhizao/components/DocumentPushBatchPanel';
import { materialApi } from '../services/material';
import type { Material } from '../types/material';

export interface MaterialPushCandidate {
  id: number;
  main_code?: string;
  name?: string;
  specification?: string;
  is_active?: boolean;
}

export interface MaterialDocumentPushPanelProps {
  open: boolean;
  onClose: () => void;
  materialIds?: number[];
  onComplete?: () => void;
  embedded?: boolean;
}

const DEFAULT_PROFILES: string[] = [];
const KINGDEE_PROFILES = ['kingdee_bd_material'];
const SAVE_API_HINTS = ['bd_material', '物料', 'push_bd'];

function isKingdeeBdMaterialSaveApi(
  api: API,
  connection: ApplicationConnection | undefined,
): boolean {
  if (!connection) return false;
  if (api.connection_uuid && api.connection_uuid !== connection.uuid) return false;
  const code = String(api.code || '').toLowerCase();
  const path = String(api.path || '').toLowerCase();
  const name = String(api.name || '').toLowerCase();
  const hay = `${code} ${path} ${name}`;
  if (code.includes('save_bd_material') || code.includes('push_bd_material') || code.includes('push_bd')) {
    return true;
  }
  const isSave = path.includes('save') || hay.includes('save');
  const isMaterial = hay.includes('bd_material') || name.includes('物料');
  return isSave && isMaterial;
}

function preferMaterialApiUuid(items: API[]): string | undefined {
  const preferred =
    items.find((api) => String(api.code || '').toLowerCase().includes('push_bd_material')) ||
    items.find((api) => String(api.code || '').toLowerCase().includes('save_bd_material')) ||
    items.find((api) => String(api.name || '').includes('物料')) ||
    items[0];
  return preferred?.uuid;
}

function toCandidate(row: Material): MaterialPushCandidate | null {
  const id = Number(row.id);
  if (!Number.isFinite(id) || id <= 0) return null;
  return {
    id,
    main_code: row.mainCode || (row as { main_code?: string }).main_code || row.code,
    name: row.name,
    specification: row.specification,
    is_active: row.isActive ?? (row as { is_active?: boolean }).is_active,
  };
}

export const MaterialDocumentPushPanel: React.FC<MaterialDocumentPushPanelProps> = ({
  open,
  onClose,
  materialIds,
  onComplete,
  embedded = false,
}) => {
  const { t } = useTranslation();

  const columns = useMemo(
    () => [
      {
        title: t('app.master-data.materials.mainCode', { defaultValue: '物料编码' }),
        dataIndex: 'main_code',
        width: 160,
        ellipsis: true,
      },
      {
        title: t('app.master-data.materials.name', { defaultValue: '物料名称' }),
        dataIndex: 'name',
        width: 180,
        ellipsis: true,
      },
      {
        title: t('app.master-data.materials.specification', { defaultValue: '规格' }),
        dataIndex: 'specification',
        width: 140,
        ellipsis: true,
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
      const res = await materialApi.list({
        keyword: keyword || undefined,
        skip: (page - 1) * pageSize,
        limit: pageSize,
        is_active: true,
      } as any);
      let data = (res.items || [])
        .map(toCandidate)
        .filter((row): row is MaterialPushCandidate => !!row);

      if (preferIds.length && page === 1) {
        const missing = preferIds.filter((id) => !data.some((row) => row.id === id));
        if (missing.length) {
          const extras = await materialApi.list({ ids: missing.slice(0, 20) } as any);
          for (const row of extras.items || []) {
            const c = toCandidate(row);
            if (c) data.unshift(c);
          }
        }
        const preferSet = new Set(preferIds);
        data = [...data].sort((a, b) => (preferSet.has(a.id) ? 0 : 1) - (preferSet.has(b.id) ? 0 : 1));
      }

      return { data, total: res.total || data.length };
    },
    [],
  );

  if (!open) return null;

  return (
    <DocumentPushBatchPanel<MaterialPushCandidate>
      open={open}
      onClose={onClose}
      onComplete={onComplete}
      embedded={embedded}
      preferIds={materialIds}
      sourceType="material"
      defaultProfiles={DEFAULT_PROFILES}
      kingdeeProfiles={KINGDEE_PROFILES}
      title={t('app.master-data.materials.documentPush.title', { defaultValue: '推送物料' })}
      hint={t('app.master-data.materials.documentPush.hint', {
        defaultValue: '选择物料推送到外部系统（金蝶物料主数据）',
      })}
      pipelineDesc={t('app.master-data.materials.documentPush.pipelineDesc', {
        defaultValue: '物料 → 金蝶 BD_MATERIAL',
      })}
      searchPlaceholder={t('app.master-data.materials.documentPush.searchPlaceholder', {
        defaultValue: '搜索物料编码/名称',
      })}
      needSelectMessage={t('app.master-data.materials.documentPush.needSelect', {
        defaultValue: '请先勾选物料',
      })}
      confirmText={t('app.kuaizhizao.documentPush.batch.confirm')}
      columns={columns}
      getRowLabel={(row) => row.main_code || String(row.id)}
      loadCandidates={loadCandidates}
      matchSaveApi={isKingdeeBdMaterialSaveApi}
      preferSaveApi={preferMaterialApiUuid}
      saveApiSearchHints={SAVE_API_HINTS}
      showScheduleControls={false}
      successCountKey="app.kuaizhizao.documentPush.batch.success"
      partialCountKey="app.kuaizhizao.documentPush.batch.partial"
      failedTitleKey="app.kuaizhizao.documentPush.pushFailed"
      skippedHintKey="app.kuaizhizao.documentPush.batch.skippedHint"
    />
  );
};

export default MaterialDocumentPushPanel;
