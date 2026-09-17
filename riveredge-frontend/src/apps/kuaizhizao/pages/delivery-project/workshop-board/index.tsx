/**
 * 交付项目车间台账：一行一项目，任务列展示齐套/日期（对齐 Excel 宽表扫视）
 */
import React, { useCallback, useMemo, useRef, useState } from 'react';
import { App, DatePicker, Select, Space } from 'antd';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import dayjs from 'dayjs';
import { UniTable } from '../../../../../components/uni-table';
import { ListPageTemplate } from '../../../../../components/layout-templates';
import { rowActionOpenWorkbench } from '../../../../../components/uni-action';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { formatBusinessDateOnly } from '../../../../../utils/format';
import {
  DELIVERY_BOARD_SECTION,
  DELIVERY_KIT_STATUS,
  DELIVERY_NODE_TASK_STATUS,
  DELIVERY_PROJECT_STATUS,
  deliveryProjectApi,
  type DeliveryWorkshopBoardCell,
  type DeliveryWorkshopBoardColumn,
  type DeliveryWorkshopBoardRow,
} from '../../../services/delivery-project';
import { alignProColumns, GLOBAL_DOC_LIST_FIELD_RANK } from '../../sales-management/shared/documentFieldAlignment';
import { renderDeliveryStatusTag } from '../shared/deliveryListPresentation';
import {
  DELIVERY_CUSTOMER_COLUMN_DEFAULTS,
  DELIVERY_PROJECT_NAME_REMAINDER_COLUMN_DEFAULTS,
} from '../shared/deliveryTableColumns';

type BoardRow = DeliveryWorkshopBoardRow & { id: number };

function cellMap(row: DeliveryWorkshopBoardRow): Record<string, DeliveryWorkshopBoardCell> {
  const map: Record<string, DeliveryWorkshopBoardCell> = {};
  for (const cell of row.cells || []) {
    map[cell.task_key] = cell;
  }
  return map;
}

const WorkshopBoardPage: React.FC = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const actionRef = useRef<ActionType>(null);
  const perms = useResourcePermissions('kuaizhizao:delivery-project');
  const [boardColumns, setBoardColumns] = useState<DeliveryWorkshopBoardColumn[]>([]);
  const [savingKey, setSavingKey] = useState<string | null>(null);

  const openWorkbench = useCallback(
    (projectId: number) => {
      navigate(`/apps/kuaizhizao/delivery-project/projects/${projectId}`);
    },
    [navigate],
  );

  const patchCell = useCallback(
    async (
      row: BoardRow,
      col: DeliveryWorkshopBoardColumn,
      patch: { kit_status?: string; actual_end_date?: string | null },
    ) => {
      const cell = cellMap(row)[col.task_key];
      if (!cell?.task_id) {
        message.warning(t('app.kuaizhizao.deliveryProject.workshopBoard.noTask'));
        return;
      }
      const key = `${row.project_id}:${col.task_key}`;
      setSavingKey(key);
      try {
        await deliveryProjectApi.patchWorkshopBoardCell({
          project_id: row.project_id,
          task_id: cell.task_id,
          ...patch,
        });
        actionRef.current?.reload();
      } catch (e) {
        message.error(getApiErrorMessage(e) || t('common.saveFailed'));
      } finally {
        setSavingKey(null);
      }
    },
    [message, t],
  );

  const columns: ProColumns<BoardRow>[] = useMemo(() => {
    const base: ProColumns<BoardRow>[] = [
      {
        title: t('app.kuaizhizao.deliveryProject.fields.projectCode'),
        dataIndex: 'project_code',
        key: 'project_code',
        copyable: true,
        width: 140,
        fixed: 'left',
        render: (_, r) => (
          <a onClick={() => openWorkbench(r.project_id)}>{r.project_code}</a>
        ),
      },
      {
        title: t('app.kuaizhizao.deliveryProject.fields.projectName'),
        dataIndex: 'project_name',
        key: 'project_name',
        ...DELIVERY_PROJECT_NAME_REMAINDER_COLUMN_DEFAULTS,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.deliveryProject.fields.customerName'),
        dataIndex: 'customer_name',
        key: 'customer_name',
        ...DELIVERY_CUSTOMER_COLUMN_DEFAULTS,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.deliveryProject.fields.material'),
        dataIndex: 'material_name',
        key: 'material_name',
        width: 140,
        ellipsis: true,
        render: (_, r) => r.material_name || r.material_code || t('common.empty'),
      },
      {
        title: t('app.kuaizhizao.deliveryProject.configAttrs.productModel'),
        dataIndex: 'product_model',
        key: 'product_model',
        width: 120,
        search: false,
        uniTableKeepWidth: true,
        render: (_, r) => {
          const model = r.config_attrs?.product_model;
          return model ? String(model) : t('common.empty');
        },
      },
      {
        title: t('app.kuaizhizao.deliveryProject.fields.deliveryDate'),
        dataIndex: 'delivery_date',
        key: 'delivery_date',
        width: 120,
        render: (_, r) => formatBusinessDateOnly(r.delivery_date) || t('common.empty'),
      },
      {
        title: t('app.kuaizhizao.deliveryProject.fields.boardSection'),
        dataIndex: 'board_section',
        key: 'board_section',
        width: 100,
        valueType: 'select',
        valueEnum: Object.fromEntries(
          Object.entries(DELIVERY_BOARD_SECTION).map(([k, v]) => [k, { text: v }]),
        ),
        render: (_, r) =>
          DELIVERY_BOARD_SECTION[r.board_section] ||
          t(`app.kuaizhizao.deliveryProject.boardSection.${r.board_section}`, {
            defaultValue: r.board_section,
          }),
      },
      {
        title: t('app.kuaizhizao.deliveryProject.fields.status'),
        dataIndex: 'status',
        key: 'lifecycle',
        width: 100,
        valueType: 'select',
        valueEnum: Object.fromEntries(
          Object.entries(DELIVERY_PROJECT_STATUS).map(([k, v]) => [k, { text: v }]),
        ),
        render: (_, r) => renderDeliveryStatusTag(r.status, DELIVERY_PROJECT_STATUS),
      },
      {
        title: t('app.kuaizhizao.deliveryProject.fields.progress'),
        dataIndex: 'progress_percent',
        key: 'progress_percent',
        width: 90,
        search: false,
        render: (_, r) => `${Number(r.progress_percent || 0).toFixed(0)}%`,
      },
    ];

    const taskCols: ProColumns<BoardRow>[] = boardColumns.map((col) => ({
      title: `${col.node_name}/${col.task_name}`,
      dataIndex: `cell_${col.task_key}`,
      key: `cell_${col.task_key}`,
      search: false,
      width: 160,
      uniTableKeepWidth: true,
      render: (_, r) => {
        const cell = cellMap(r)[col.task_key];
        const busy = savingKey === `${r.project_id}:${col.task_key}`;
        const canEdit = Boolean(perms.canUpdate && cell?.task_id);
        if (col.track_mode === 'kit' || cell?.track_mode === 'kit') {
          return (
            <Space orientation="vertical" size={4} style={{ width: '100%' }}>
              <Select
                size="small"
                style={{ width: '100%' }}
                disabled={!canEdit || busy}
                value={cell?.kit_status || 'none'}
                options={Object.entries(DELIVERY_KIT_STATUS).map(([value, label]) => ({
                  value,
                  label,
                }))}
                onChange={(v) => void patchCell(r, col, { kit_status: v })}
              />
              <DatePicker
                size="small"
                style={{ width: '100%' }}
                disabled={!canEdit || busy}
                value={cell?.actual_end_date ? dayjs(cell.actual_end_date) : null}
                onChange={(d) =>
                  void patchCell(r, col, {
                    actual_end_date: d ? d.format('YYYY-MM-DD') : null,
                  })
                }
              />
            </Space>
          );
        }
        return (
          <Space orientation="vertical" size={4}>
            <span>
              {cell?.status
                ? DELIVERY_NODE_TASK_STATUS[cell.status] || cell.status
                : t('common.empty')}
            </span>
            <span>{formatBusinessDateOnly(cell?.actual_end_date) || t('common.empty')}</span>
          </Space>
        );
      },
    }));

    return alignProColumns([...base, ...taskCols], GLOBAL_DOC_LIST_FIELD_RANK);
  }, [boardColumns, openWorkbench, patchCell, perms.canUpdate, savingKey, t]);

  return (
    <ListPageTemplate>
      <UniTable<BoardRow>
        actionRef={actionRef}
        rowKey="id"
        columns={columns}
        permissionResource="kuaizhizao:delivery-project"
        columnPersistenceId="apps.kuaizhizao.pages.delivery-project.workshop-board.v1"
        showCreateButton={false}
        search={{ labelWidth: 'auto' }}
        toolBarRender={() => []}
        rowActions={(row) => [
          rowActionOpenWorkbench({
            key: 'open',
            onClick: () => openWorkbench(row.project_id),
          }),
        ]}
        request={async (params) => {
          const res = await deliveryProjectApi.workshopBoard({
            skip: ((params.current || 1) - 1) * (params.pageSize || 20),
            limit: params.pageSize || 20,
            keyword: params.keyword as string | undefined,
            board_section: params.board_section as string | undefined,
            status: params.status as string | undefined,
          });
          setBoardColumns(res.columns || []);
          return {
            data: (res.items || []).map((item) => ({ ...item, id: item.project_id })),
            success: true,
            total: res.total || 0,
          };
        }}
      />
    </ListPageTemplate>
  );
};

export default WorkshopBoardPage;
