/**
 * 工序外推：DocumentPushBatchPanel（source=process_operation → kingdee_eng_process）。
 * 与销售订单一致：列表勾选优先，目标/连接器/Save 接口由用户选择。
 */
import React, { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { ApplicationConnection } from '../../../services/applicationConnection';
import type { API } from '../../../services/apiManagement';
import { DocumentPushBatchPanel } from '../../kuaizhizao/components/DocumentPushBatchPanel';
import { operationApi } from '../services/process';
import type { Operation } from '../types/process';

export interface OperationPushCandidate {
  id: number;
  uuid?: string;
  code?: string;
  name?: string;
  is_active?: boolean;
}

export interface OperationDocumentPushPanelProps {
  open: boolean;
  onClose: () => void;
  operationIds?: number[];
  /** 列表勾选 uuid，用于补拉不在当前列表页的候选（对齐销售订单 getById） */
  operationUuids?: string[];
  onComplete?: () => void;
  embedded?: boolean;
}

const DEFAULT_PROFILES: string[] = [];
const KINGDEE_PROFILES = ['kingdee_eng_process'];
const SAVE_API_HINTS = ['eng_process', '工序', 'push_eng'];

function isKingdeeEngProcessSaveApi(
  api: API,
  connection: ApplicationConnection | undefined,
): boolean {
  if (!connection) return false;
  if (api.connection_uuid && api.connection_uuid !== connection.uuid) return false;
  const code = String(api.code || '').toLowerCase();
  const path = String(api.path || '').toLowerCase();
  const name = String(api.name || '').toLowerCase();
  const hay = `${code} ${path} ${name}`;
  if (
    code.includes('save_eng_process') ||
    code.includes('push_eng_process') ||
    code.includes('push_eng')
  ) {
    return true;
  }
  const isSave = path.includes('save') || hay.includes('save');
  const isOp = hay.includes('eng_process') || name.includes('工序');
  return isSave && isOp;
}

function preferOperationApiUuid(items: API[]): string | undefined {
  const preferred =
    items.find((api) => String(api.code || '').toLowerCase().includes('push_eng_process')) ||
    items.find((api) => String(api.code || '').toLowerCase().includes('save_eng_process')) ||
    items.find((api) => String(api.name || '').includes('工序')) ||
    items[0];
  return preferred?.uuid;
}

function toCandidate(row: Operation): OperationPushCandidate | null {
  const id = Number(row.id);
  if (!Number.isFinite(id) || id <= 0) return null;
  return {
    id,
    uuid: row.uuid,
    code: row.code,
    name: row.name,
    is_active: row.isActive ?? (row as { is_active?: boolean }).is_active,
  };
}

export const OperationDocumentPushPanel: React.FC<OperationDocumentPushPanelProps> = ({
  open,
  onClose,
  operationIds,
  operationUuids,
  onComplete,
  embedded = false,
}) => {
  const { t } = useTranslation();

  const columns = useMemo(
    () => [
      {
        title: t('app.master-data.operations.code', { defaultValue: '工序编码' }),
        dataIndex: 'code',
        width: 140,
        ellipsis: true,
      },
      {
        title: t('app.master-data.operations.name', { defaultValue: '工序名称' }),
        dataIndex: 'name',
        width: 180,
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
      const res = await operationApi.list({
        keyword: keyword || undefined,
        skip: (page - 1) * pageSize,
        limit: pageSize,
        is_active: true,
      } as any);
      const items = (res as any)?.items || (res as any)?.data || [];
      let data = (items as Operation[])
        .map(toCandidate)
        .filter((row): row is OperationPushCandidate => !!row);

      if (page === 1 && (preferIds.length || (operationUuids && operationUuids.length))) {
        const extras: OperationPushCandidate[] = [];
        const haveIds = new Set(data.map((row) => row.id));
        const haveUuids = new Set(data.map((row) => row.uuid).filter(Boolean) as string[]);
        for (const uuid of (operationUuids || []).slice(0, 20)) {
          if (!uuid || haveUuids.has(uuid)) continue;
          try {
            const one = await operationApi.get(uuid);
            const c = toCandidate(one);
            if (c) {
              extras.push(c);
              haveIds.add(c.id);
              if (c.uuid) haveUuids.add(c.uuid);
            }
          } catch {
            // ignore
          }
        }
        data = [...extras, ...data];
        const preferSet = new Set(preferIds);
        data = [...data].sort((a, b) => (preferSet.has(a.id) ? 0 : 1) - (preferSet.has(b.id) ? 0 : 1));
      }

      return { data, total: (res as any)?.total || data.length };
    },
    [operationUuids],
  );

  if (!open) return null;

  return (
    <DocumentPushBatchPanel<OperationPushCandidate>
      open={open}
      onClose={onClose}
      onComplete={onComplete}
      embedded={embedded}
      preferIds={operationIds}
      sourceType="process_operation"
      defaultProfiles={DEFAULT_PROFILES}
      kingdeeProfiles={KINGDEE_PROFILES}
      title={t('app.master-data.operations.documentPush.title', { defaultValue: '推送工序' })}
      hint={t('app.master-data.operations.documentPush.hint', {
        defaultValue: '选择工序推送到外部系统',
      })}
      pipelineDesc={t('app.master-data.operations.documentPush.pipelineDesc', {
        defaultValue: '工序 → 金蝶 ENG_Process',
      })}
      searchPlaceholder={t('app.master-data.operations.documentPush.searchPlaceholder', {
        defaultValue: '搜索工序编码/名称',
      })}
      needSelectMessage={t('app.master-data.operations.documentPush.needSelect', {
        defaultValue: '请先勾选工序',
      })}
      confirmText={t('app.kuaizhizao.documentPush.batch.confirm')}
      columns={columns}
      getRowLabel={(row) => row.code || String(row.id)}
      loadCandidates={loadCandidates}
      matchSaveApi={isKingdeeEngProcessSaveApi}
      preferSaveApi={preferOperationApiUuid}
      saveApiSearchHints={SAVE_API_HINTS}
      showScheduleControls={false}
      successCountKey="app.kuaizhizao.documentPush.batch.success"
      partialCountKey="app.kuaizhizao.documentPush.batch.partial"
      failedTitleKey="app.kuaizhizao.documentPush.pushFailed"
      skippedHintKey="app.kuaizhizao.documentPush.batch.skippedHint"
    />
  );
};

export default OperationDocumentPushPanel;
