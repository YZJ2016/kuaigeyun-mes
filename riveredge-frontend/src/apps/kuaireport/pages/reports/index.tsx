/**
 * 报表中心。两个页签：我的报表、系统报表。
 * 列表用 UniTable。管理数据源跳到系统设置的数据源管理。
 */

import React, { useCallback, useRef, useState } from 'react';
import { App, Button, Modal, Popconfirm, Space, Tag, Typography } from 'antd';
import {
  AppstoreOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  PlusOutlined,
  UserOutlined,
} from '@ant-design/icons';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { MultiTabListPageTemplate } from '../../../../components/layout-templates';
import { renderUniTableOperationCell, rowActionKind, rowActionLabelKeep } from '../../../../components/uni-action';
import { UniTable } from '../../../../components/uni-table';
import { parseColumnFiltersParam } from '../../../../components/uni-query/columnFilterContract';
import { MountReportModal } from './MountReportModal';
import {
  createPublicLink,
  deleteReport,
  listReports,
  withdrawReport,
  type ReportCenterRow,
} from './api';

const CLASSIFY_ENUM = {
  销售: '销售',
  采购: '采购',
  生产: '生产',
  质量: '质量',
  仓库: '仓库',
  设备: '设备',
  财务: '财务',
  综合: '综合',
  库存: '库存',
  物料: '物料',
  未分类: '未分类',
};

const STATUS_ENUM = {
  DRAFT: '草稿',
  PUBLISHED: '已发布',
};

function statusLabel(status: string): string {
  if (status === 'PUBLISHED') return '已发布';
  if (status === 'DRAFT') return '草稿';
  return status;
}

function rawField(row: ReportCenterRow, field: string): string {
  const value = (row as unknown as Record<string, unknown>)[field];
  return value == null ? '' : String(value);
}

function fieldText(row: ReportCenterRow, field: string): string {
  const value = rawField(row, field);
  if (field === 'status') return statusLabel(value);
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

function applySearch(rows: ReportCenterRow[], search: Record<string, unknown> | undefined): ReportCenterRow[] {
  if (!search) return rows;
  let next = rows;
  const keyword = typeof search.keyword === 'string' ? search.keyword.trim().toLowerCase() : '';
  if (keyword) {
    next = next.filter((row) =>
      [row.code, row.name, row.description, row.classify, statusLabel(row.status)]
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

function ReportTable({
  category,
  mine,
}: {
  category: 'system' | 'custom';
  mine: boolean;
}) {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const actionRef = useRef<ActionType>();
  const [selectedKeys, setSelectedKeys] = useState<React.Key[]>([]);
  const [sharePath, setSharePath] = useState<string | null>(null);
  const [mountTarget, setMountTarget] = useState<ReportCenterRow | null>(null);

  const reload = useCallback(() => {
    actionRef.current?.reload?.();
  }, []);

  const goSources = () => navigate('/system/data-sources');

  const onShare = async (row: ReportCenterRow) => {
    try {
      const result = await createPublicLink(row.id);
      const path = result.share_path || '';
      setSharePath(path.startsWith('http') ? path : `${window.location.origin}${path}`);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '生成分享链接失败');
    }
  };

  const onWithdraw = async (row: ReportCenterRow) => {
    try {
      await withdrawReport(row.id);
      message.success(`「${row.name}」已撤回为草稿`);
      reload();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '撤回失败');
    }
  };

  const onDelete = async (row: ReportCenterRow) => {
    try {
      await deleteReport(row.id);
      message.success(`「${row.name}」已删除`);
      reload();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '删除失败');
    }
  };

  const onBatchDelete = async (keys: React.Key[]) => {
    const ids = keys.map((key) => Number(key)).filter((id) => Number.isFinite(id));
    if (!ids.length) return;
    try {
      await Promise.all(ids.map((id) => deleteReport(id)));
      message.success('已删除');
      setSelectedKeys([]);
      reload();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '批量删除失败');
      reload();
    }
  };

  const columns: ProColumns<ReportCenterRow>[] = [
      {
        title: '编号',
        dataIndex: 'code',
        copyable: true,
        width: 140,
        minWidth: 140,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
      },
      {
        title: '名称',
        dataIndex: 'name',
        width: 180,
        minWidth: 180,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
      },
      {
        title: '描述',
        dataIndex: 'description',
        key: 'description',
        width: 220,
        minWidth: 220,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
        render: (_, row) => row.description || '-',
      },
      {
        title: '分类',
        dataIndex: 'classify',
        width: 100,
        minWidth: 100,
        uniTableKeepWidth: true,
        resizable: false,
        valueEnum: CLASSIFY_ENUM,
        render: (_, row) => (row.classify ? <Tag color="blue">{row.classify}</Tag> : '-'),
      },
      {
        title: '更新时间',
        dataIndex: 'updated_at',
        key: 'updated_at',
        width: 168,
        minWidth: 168,
        uniTableKeepWidth: true,
        uniTableAuditStackedColumn: false,
        resizable: false,
        ellipsis: true,
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
        width: 288,
        minWidth: 288,
        uniTableKeepWidth: true,
        hideInSearch: true,
        render: (_, row) =>
          renderUniTableOperationCell(
            [
              <Button
                key="detail"
                {...rowActionKind('read')}
                onClick={() => navigate(`/apps/kuaireport/reports/view/${row.id}`)}
              />,
              <Button
                key="edit"
                {...rowActionKind('update')}
                onClick={() =>
                  navigate(
                    mine
                      ? `/apps/kuaireport/reports/${row.id}/edit`
                      : `/apps/kuaireport/designer?reportId=${row.id}`,
                  )
                }
              />,
              <Popconfirm key="delete" title="确定删除该报表？" onConfirm={() => void onDelete(row)}>
                <Button {...rowActionKind('delete')} />
              </Popconfirm>,
              <Button
                key="share"
                {...rowActionKind('skip')}
                {...rowActionLabelKeep()}
                onClick={() => void onShare(row)}
              >
                分享
              </Button>,
              <Button key="pro" {...rowActionKind('skip')} {...rowActionLabelKeep()}>
                专业
              </Button>,
              <Button
                key="mount"
                {...rowActionKind('skip')}
                {...rowActionLabelKeep()}
                onClick={() => setMountTarget(row)}
              >
                挂载
              </Button>,
              <Popconfirm
                key="withdraw"
                title={`确认将「${row.name}」撤回为草稿？撤回后已有分享链接将立即失效。`}
                onConfirm={() => void onWithdraw(row)}
              >
                <Button {...rowActionKind('skip')} {...rowActionLabelKeep()}>
                  撤回
                </Button>
              </Popconfirm>,
            ],
            `report-op-${row.id}`,
          ),
      },
    ];

  return (
    <>
      <UniTable<ReportCenterRow>
        actionRef={actionRef}
        rowKey="id"
        columns={columns}
        columnPersistenceId={mine ? 'kuaireport-reports-mine-v4' : 'kuaireport-reports-system-v4'}
        viewTypes={['card', 'table', 'help']}
        showImportButton={false}
        showExportButton={false}
        enableRowSelection={mine}
        selectedRowKeys={mine ? selectedKeys : undefined}
        onRowSelectionChange={mine ? setSelectedKeys : undefined}
        headerActions={
          <Space>
            {mine ? (
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => navigate('/apps/kuaireport/reports/new')}
              >
                新建自制报表 (Alt+N)
              </Button>
            ) : null}
            {mine ? (
              <Button
                danger
                icon={<DeleteOutlined />}
                disabled={selectedKeys.length === 0}
                onClick={() => {
                  Modal.confirm({
                    title: `确定删除选中的 ${selectedKeys.length} 张报表？`,
                    okText: '删除',
                    okButtonProps: { danger: true },
                    onOk: () => onBatchDelete(selectedKeys),
                  });
                }}
              >
                批量删除
              </Button>
            ) : null}
            <Button icon={<DatabaseOutlined />} onClick={goSources}>
              管理数据源
            </Button>
          </Space>
        }
        cardViewConfig={{
          renderCard: (row) => (
            <div style={{ padding: 16, border: '1px solid var(--river-border-color, #f0f0f0)', borderRadius: 8 }}>
              <Typography.Text strong>{row.name}</Typography.Text>
              <div style={{ marginTop: 8 }}>
                <Tag>{row.code}</Tag>
                {row.classify ? <Tag color="blue">{row.classify}</Tag> : null}
                {row.status === 'PUBLISHED' ? <Tag color="success">已发布</Tag> : <Tag>草稿</Tag>}
              </div>
            </div>
          ),
        }}
        request={async (params, _sort, _filter, searchFormValues) => {
          const data = await listReports({ category });
          let rows = Array.isArray(data) ? data : [];
          rows = applySearch(rows, searchFormValues as Record<string, unknown> | undefined);
          const current = Number(params?.current || 1);
          const pageSize = Number(params?.pageSize || 20);
          const start = (current - 1) * pageSize;
          return {
            data: rows.slice(start, start + pageSize),
            success: true,
            total: rows.length,
          };
        }}
      />
      <Modal
        title="分享报表"
        open={sharePath != null}
        onCancel={() => setSharePath(null)}
        footer={null}
        destroyOnHidden
      >
        <p style={{ marginBottom: 8 }}>分享链接（复制后发送给他人，无需登录即可查看）：</p>
        <Typography.Paragraph copyable style={{ marginBottom: 0 }}>
          {sharePath}
        </Typography.Paragraph>
      </Modal>
      <MountReportModal report={mountTarget} onClose={() => setMountTarget(null)} />
    </>
  );
}

export default function ReportCenterPage() {
  const [params] = useSearchParams();
  const [activeTab, setActiveTab] = useState(params.get('tab') === 'system' ? 'system' : 'mine');

  return (
    <MultiTabListPageTemplate
      activeTabKey={activeTab}
      onTabChange={setActiveTab}
      preserveMounted
      tabs={[
        {
          key: 'mine',
          label: (
            <Space>
              <UserOutlined />
              我的报表
            </Space>
          ),
          children: <ReportTable category="custom" mine />,
        },
        {
          key: 'system',
          label: (
            <Space>
              <AppstoreOutlined />
              系统报表
            </Space>
          ),
          children: <ReportTable category="system" mine={false} />,
        },
      ]}
    />
  );
}
