/**
 * 跨项目待办 — 聚合看板
 * 按单据类型分列；点击卡片进入对应业务列表。
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { App, Typography } from 'antd';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { renderDocumentStatusTag } from '../../../../utils/documentLifecycleStatusTag';
import { formatDateTimeBySiteSetting } from '../../../../utils/format';
import { getApiErrorMessage } from '../../../../utils/errorHandler';
import { AggregationKanban } from '../../components/AggregationKanban';
import {
  pendingInboxApi,
  type PendingInboxDocType,
  type PendingInboxItem,
} from '../../services/pending-inbox';

const { Text } = Typography;

const DOC_TYPE_KEYS: PendingInboxDocType[] = [
  'project_proposal',
  'bom_collab',
  'product_firmware',
  'sample_process',
  'material_review',
  'mold_sample',
  'trial_flow',
  'engineering_change',
];

const DOC_TYPE_COLORS: Record<string, string> = {
  project_proposal: '#1677ff',
  bom_collab: '#13c2c2',
  product_firmware: '#722ed1',
  sample_process: '#fa8c16',
  material_review: '#eb2f96',
  mold_sample: '#2f54eb',
  trial_flow: '#52c41a',
  engineering_change: '#fa541c',
};

const PendingInboxPage: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { message: messageApi } = App.useApp();
  const [searchParams] = useSearchParams();
  const filterProjectId = searchParams.get('project_id')
    ? Number(searchParams.get('project_id'))
    : undefined;

  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<PendingInboxItem[]>([]);

  const docTypeLabel = useCallback(
    (s: string) => t(`app.kuaiplm.pendingInbox.docType.${s}`, { defaultValue: s }),
    [t],
  );
  const statusLabel = useCallback(
    (s: string) => t(`app.kuaiplm.pendingInbox.status.${s}`, { defaultValue: s }),
    [t],
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await pendingInboxApi.list({
        skip: 0,
        limit: 200,
        project_id: filterProjectId,
      });
      setItems(res.items);
    } catch (e) {
      messageApi.error(getApiErrorMessage(e));
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [filterProjectId, messageApi]);

  useEffect(() => {
    void load();
  }, [load]);

  const openDoc = useCallback(
    (row: PendingInboxItem) => {
      const path = row.list_path || '/apps/kuaiplm/dashboard';
      if (row.project_id && !path.includes('project_id=')) {
        const sep = path.includes('?') ? '&' : '?';
        navigate(`${path}${sep}project_id=${row.project_id}`);
        return;
      }
      navigate(path);
    },
    [navigate],
  );

  const columns = useMemo(
    () =>
      DOC_TYPE_KEYS.map((docType) => ({
        id: docType,
        title: docTypeLabel(docType),
        color: DOC_TYPE_COLORS[docType],
        items: items.filter((row) => row.doc_type === docType),
      })),
    [docTypeLabel, items],
  );

  return (
    <ListPageTemplate prioritizeMainContentPaint={false}>
      <AggregationKanban<PendingInboxItem>
        title={t('app.kuaiplm.pendingInbox.title')}
        columns={columns}
        loading={loading}
        onRefresh={() => void load()}
        getItemKey={(row) => `${row.doc_type}-${row.doc_id}`}
        onCardClick={openDoc}
        emptyDescription={t('app.kuaiplm.pendingInbox.boardEmptyColumn')}
        renderCard={(row) => (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Text strong ellipsis style={{ fontSize: 13 }}>
              {row.doc_code || '—'}
            </Text>
            <Text ellipsis style={{ fontSize: 13 }}>
              {row.title || '—'}
            </Text>
            <Text type="secondary" ellipsis style={{ fontSize: 12 }}>
              {row.project_name
                ? `${row.project_name}${row.project_code ? ` (${row.project_code})` : ''}`
                : t('app.kuaiplm.pendingInbox.noProject')}
            </Text>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: 8,
                marginTop: 2,
              }}
            >
              {renderDocumentStatusTag(statusLabel(row.status), row.status)}
              <Text type="secondary" style={{ fontSize: 11, flexShrink: 0 }}>
                {formatDateTimeBySiteSetting(row.updated_at) || '—'}
              </Text>
            </div>
          </div>
        )}
      />
    </ListPageTemplate>
  );
};

export default PendingInboxPage;
