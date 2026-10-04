/**
 * 大屏中心。列表用 UniTable：搜索、草稿/已发布、卡片与表格。
 * 设计、预览走已有页面；分享与版本回看收在「更多」。
 */

import React, { useCallback, useRef, useState } from 'react';
import { App, Button, Dropdown, Modal, Popconfirm, Select, Space, Tag, Typography } from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { useNavigate } from 'react-router-dom';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { downloadRecordsAsXlsx } from '../../../../utils/exportRecordsXlsx';
import { renderUniTableOperationCell, rowActionKind, rowActionLabelKeep } from '../../../../components/uni-action';
import { UniTable } from '../../../../components/uni-table';
import { parseColumnFiltersParam } from '../../../../components/uni-query/columnFilterContract';
import { MountReportModal } from '../reports/MountReportModal';
import { ShareModal } from './ShareModal';
import {
  clearDashboardMount,
  createDashboard,
  deleteDashboard,
  getDashboardMount,
  listDashboards,
  mountDashboard,
  shareDashboard,
  type DashboardRow,
} from './api';
import { DASHBOARD_TEMPLATES, templateCreateBody } from './dashboardTemplates';

const BOARD_PARENT_NAMES = ['app.kuaireport.menu.board-design', '看板设计'];

const STATUS_ENUM = {
  DRAFT: '草稿',
  PUBLISHED: '已发布',
};

function statusLabel(status: string): string {
  if (status === 'PUBLISHED') return '已发布';
  if (status === 'DRAFT') return '草稿';
  return status;
}

function formatTime(value?: string): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function rawField(row: DashboardRow, field: string): string {
  const value = (row as unknown as Record<string, unknown>)[field];
  return value == null ? '' : String(value);
}

function fieldText(row: DashboardRow, field: string): string {
  const value = rawField(row, field);
  if (field === 'status') return statusLabel(value);
  if (field === 'updated_at') return formatTime(value);
  return value;
}

function sameText(actual: string, expected: string): boolean {
  return actual === expected || actual === statusLabel(expected).toLowerCase();
}

function matchFilter(raw: string, shown: string, op: string, value: unknown): boolean {
  const text = shown.toLowerCase();
  const rawText = raw.toLowerCase();
  const expected = value == null ? '' : String(value).toLowerCase();
  if (op === 'eq') return sameText(text, expected) || sameText(rawText, expected);
  if (op === 'ne') return !sameText(text, expected) && !sameText(rawText, expected);
  if (op === 'startswith') return text.startsWith(expected) || rawText.startsWith(expected);
  if (op === 'endswith') return text.endsWith(expected) || rawText.endsWith(expected);
  if (op === 'isnull') return expected === 'true' || expected === '1' ? raw === '' : raw !== '';
  if (!expected) return true;
  return text.includes(expected) || rawText.includes(expected);
}

function applySearch(rows: DashboardRow[], search: Record<string, unknown> | undefined): DashboardRow[] {
  if (!search) return rows;
  let next = rows;
  const keyword = typeof search.keyword === 'string' ? search.keyword.trim().toLowerCase() : '';
  if (keyword) {
    next = next.filter((row) =>
      [row.code, row.name, statusLabel(row.status), formatTime(row.updated_at)]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword)),
    );
  }
  for (const [key, value] of Object.entries(search)) {
    if (key === 'keyword' || key === 'column_filters' || value == null || value === '') continue;
    if (typeof value === 'object') continue;
    const expected = String(value).toLowerCase();
    next = next.filter((row) => {
      const shown = fieldText(row, key).toLowerCase();
      const raw = rawField(row, key).toLowerCase();
      return shown.includes(expected) || raw.includes(expected);
    });
  }
  const filters = parseColumnFiltersParam(search.column_filters);
  for (const filter of filters) {
    next = next.filter((row) =>
      matchFilter(rawField(row, filter.field), fieldText(row, filter.field), filter.op, filter.value),
    );
  }
  return next;
}

export default function DashboardListPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const actionRef = useRef<ActionType>();
  const [rows, setRows] = useState<DashboardRow[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<React.Key[]>([]);
  const [shareTarget, setShareTarget] = useState<DashboardRow | null>(null);
  const [mountTarget, setMountTarget] = useState<DashboardRow | null>(null);
  const [templateOpen, setTemplateOpen] = useState(false);
  const [templateKey, setTemplateKey] = useState(DASHBOARD_TEMPLATES[0].key);
  const [copying, setCopying] = useState(false);

  const reload = useCallback(() => {
    actionRef.current?.reload?.();
  }, []);

  const goDesign = (id?: number) => {
    navigate(id == null ? '/apps/kuaireport/dashboards/design' : `/apps/kuaireport/dashboards/design?id=${id}`);
  };

  const onDelete = async (row: DashboardRow) => {
    try {
      await deleteDashboard(row.id);
      message.success(`「${row.name}」已删除`);
      setSelectedKeys((keys) => keys.filter((key) => Number(key) !== row.id));
      reload();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '删除失败');
    }
  };

  const onBatchDelete = async (keys: React.Key[]) => {
    const ids = keys.map((key) => Number(key)).filter((id) => Number.isFinite(id));
    if (!ids.length) return;
    try {
      await Promise.all(ids.map((id) => deleteDashboard(id)));
      message.success('已删除');
      setSelectedKeys([]);
      reload();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '批量删除失败');
      reload();
    }
  };

  const onCreateFromTemplate = async () => {
    const body = templateCreateBody(templateKey);
    if (!body) {
      message.warning('请选择一个模板');
      return;
    }
    setCopying(true);
    try {
      const created = await createDashboard(body);
      message.success('已从模板创建');
      setTemplateOpen(false);
      goDesign(created.id);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '从模板新建失败');
    } finally {
      setCopying(false);
    }
  };

  const columns: ProColumns<DashboardRow>[] = [
    {
      title: '编号',
      dataIndex: 'code',
      copyable: true,
      width: 200,
      minWidth: 200,
      uniTableKeepWidth: true,
      resizable: false,
      ellipsis: true,
    },
    {
      title: '名称',
      dataIndex: 'name',
      width: 240,
      minWidth: 240,
      uniTableKeepWidth: true,
      resizable: false,
      ellipsis: true,
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 180,
      minWidth: 180,
      uniTableKeepWidth: true,
      uniTableAuditStackedColumn: false,
      resizable: false,
      ellipsis: true,
      render: (_, row) => formatTime(row.updated_at),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      minWidth: 100,
      uniTableKeepWidth: true,
      resizable: false,
      valueEnum: STATUS_ENUM,
      render: (_, row) =>
        row.status === 'PUBLISHED' ? <Tag color="success">已发布</Tag> : <Tag>草稿</Tag>,
    },
    {
      title: '操作',
      dataIndex: 'actions',
      key: 'actions',
      width: 260,
      minWidth: 260,
      uniTableKeepWidth: true,
      hideInSearch: true,
      render: (_, row) =>
        renderUniTableOperationCell(
          [
            <Popconfirm
              key="delete"
              title={`确定删除「${row.name}」？`}
              data-action-priority={10}
              onConfirm={() => void onDelete(row)}
            >
              <Button {...rowActionKind('delete')} />
            </Popconfirm>,
            <Button
              key="design"
              {...rowActionKind('update')}
              {...rowActionLabelKeep()}
              data-action-priority={20}
              onClick={() => goDesign(row.id)}
            >
              设计
            </Button>,
            <Button
              key="preview"
              {...rowActionKind('read')}
              {...rowActionLabelKeep()}
              data-action-priority={30}
              onClick={() => navigate(`/apps/kuaireport/dashboards/${row.id}/preview`)}
            >
              预览
            </Button>,
            <Dropdown
              key="more"
              menu={{
                items: [
                  { key: 'share', label: '分享', onClick: () => setShareTarget(row) },
                  { key: 'mount', label: '挂载', onClick: () => setMountTarget(row) },
                ],
              }}
            >
              <Button {...rowActionKind('skip')} {...rowActionLabelKeep()}>
                更多
              </Button>
            </Dropdown>,
          ],
          `dashboard-op-${row.id}`,
        ),
    },
  ];

  return (
    <ListPageTemplate>
      <UniTable<DashboardRow>
        actionRef={actionRef}
        rowKey="id"
        columns={columns}
        columnPersistenceId="kuaireport-dashboards-v1"
        viewTypes={['card', 'table', 'help']}
        showImportButton={false}
        onExport={async (type, keys, pageData) => {
          const source =
            type === 'currentPage'
              ? ((pageData as DashboardRow[] | undefined) ?? [])
              : type === 'selected'
                ? rows.filter((row) => keys?.some((key) => Number(key) === row.id))
                : rows;
          if (!source.length) {
            message.warning('没有可导出的数据');
            return;
          }
          await downloadRecordsAsXlsx(
            source.map((row) => ({
              code: row.code,
              name: row.name,
              updated_at: formatTime(row.updated_at),
              status: statusLabel(row.status),
            })),
            'dashboards.xlsx',
            {
              sheetName: '大屏中心',
              columns: [
                { key: 'code', title: '编号' },
                { key: 'name', title: '名称' },
                { key: 'updated_at', title: '更新时间' },
                { key: 'status', title: '状态' },
              ],
            },
          );
        }}
        enableRowSelection
        selectedRowKeys={selectedKeys}
        onRowSelectionChange={setSelectedKeys}
        onCreate={() => goDesign()}
        headerActions={
          <Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => goDesign()}>
              新建大屏 (Alt+N)
            </Button>
            <Button
              onClick={() => {
                setTemplateKey(DASHBOARD_TEMPLATES[0].key);
                setTemplateOpen(true);
              }}
            >
              从模板新建
            </Button>
            <Button
              danger
              icon={<DeleteOutlined />}
              disabled={selectedKeys.length === 0}
              onClick={() => {
                Modal.confirm({
                  title: `确定删除选中的 ${selectedKeys.length} 个大屏？`,
                  okText: '删除',
                  okButtonProps: { danger: true },
                  onOk: () => onBatchDelete(selectedKeys),
                });
              }}
            >
              批量删除
            </Button>
          </Space>
        }
        cardViewConfig={{
          renderCard: (row) => (
            <div style={{ padding: 16, border: '1px solid var(--river-border-color, #f0f0f0)', borderRadius: 8 }}>
              <Typography.Text strong>{row.name}</Typography.Text>
              <div style={{ marginTop: 8 }}>
                <Tag>{row.code}</Tag>
                {row.status === 'PUBLISHED' ? <Tag color="success">已发布</Tag> : <Tag>草稿</Tag>}
              </div>
            </div>
          ),
        }}
        request={async (params, _sort, _filter, searchFormValues) => {
          const data = await listDashboards();
          const loaded = Array.isArray(data) ? data : [];
          setRows(loaded);
          const filtered = applySearch(loaded, searchFormValues as Record<string, unknown> | undefined);
          const current = Number(params?.current || 1);
          const pageSize = Number(params?.pageSize || 20);
          const start = (current - 1) * pageSize;
          return {
            data: filtered.slice(start, start + pageSize),
            success: true,
            total: filtered.length,
          };
        }}
      />
      <Modal
        title="从官方模板新建"
        open={templateOpen}
        okText="新建"
        confirmLoading={copying}
        onOk={() => void onCreateFromTemplate()}
        onCancel={() => {
          if (copying) return;
          setTemplateOpen(false);
        }}
        destroyOnHidden
      >
        <Typography.Paragraph style={{ marginBottom: 12 }}>
          选择模板后将创建草稿大屏并进入设计器。
        </Typography.Paragraph>
        <Select
          style={{ width: '100%' }}
          value={templateKey}
          options={DASHBOARD_TEMPLATES.map((item) => ({
            value: item.key,
            label: `${item.name} — ${item.description}`,
          }))}
          onChange={(value) => setTemplateKey(value)}
        />
      </Modal>
      <MountReportModal
        report={mountTarget}
        onClose={() => setMountTarget(null)}
        defaultParentNames={BOARD_PARENT_NAMES}
        loadMount={getDashboardMount}
        saveMount={mountDashboard}
        removeMount={clearDashboardMount}
        description={
          <span>
            将大屏加入左侧菜单，可选快报表或其他应用下的分组。
            <br />
            将出现在「看板设计」下。入口仍打开本大屏预览，需具备对应查看权限。
          </span>
        }
      />
      <ShareModal
        open={shareTarget != null}
        resourceName={shareTarget?.name}
        onSubmit={(body) => shareDashboard(shareTarget!.id, body)}
        onClose={(changed) => {
          setShareTarget(null);
          if (changed) reload();
        }}
      />
    </ListPageTemplate>
  );
}
