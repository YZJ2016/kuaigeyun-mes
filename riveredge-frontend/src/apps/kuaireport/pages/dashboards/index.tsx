/**
 * 大屏列表。GET /apps/kuaireport/dashboards。
 * 操作：设计（?id= 回显编辑）、预览、分享、关闭分享；版本回看/恢复在分发页。
 */

import React, { useCallback, useEffect, useState } from 'react';
import { App, Button, Popconfirm, Space, Table, Tag, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { ShareModal } from './ShareModal';
import { closeDashboardShare, listDashboards, shareDashboard, type DashboardRow } from './api';

const { Title, Text } = Typography;

export default function DashboardListPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [rows, setRows] = useState<DashboardRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [shareTarget, setShareTarget] = useState<DashboardRow | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listDashboards();
      setRows(Array.isArray(data) ? data : []);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '大屏列表加载失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    void load();
  }, [load]);

  const onCloseShare = async (row: DashboardRow) => {
    try {
      await closeDashboardShare(row.id);
      message.success(`「${row.name}」已关闭分享`);
      void load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '关闭分享失败');
    }
  };

  return (
    <ListPageTemplate>
      <Title level={4}>大屏</Title>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" onClick={() => navigate('/apps/kuaireport/dashboards/design')}>
          新建大屏
        </Button>
        <Button onClick={() => navigate('/apps/kuaireport/distribution')}>版本回看</Button>
      </Space>
      <Table<DashboardRow>
        rowKey="id"
        loading={loading}
        pagination={false}
        dataSource={rows}
        columns={[
          { title: '名称', dataIndex: 'name' },
          { title: '编码', dataIndex: 'code' },
          {
            title: '状态',
            dataIndex: 'status',
            render: (value: string) =>
              value === 'PUBLISHED' ? (
                <Tag color="blue">已发布</Tag>
              ) : value === 'DRAFT' ? (
                <Tag>草稿</Tag>
              ) : (
                <Tag color="blue">{value}</Tag>
              ),
          },
          {
            title: '分享',
            dataIndex: 'is_shared',
            render: (value: boolean) =>
              value ? <Tag color="green">已开启</Tag> : <Tag>未开启</Tag>,
          },
          {
            title: '更新时间',
            dataIndex: 'updated_at',
            render: (value?: string) => (value ? new Date(value).toLocaleString() : '—'),
          },
          {
            title: '操作',
            render: (_, row) => (
              <Space size={0} wrap>
                <Button
                  type="link"
                  onClick={() => navigate(`/apps/kuaireport/dashboards/design?id=${row.id}`)}
                >
                  设计
                </Button>
                <Button
                  type="link"
                  onClick={() => navigate(`/apps/kuaireport/dashboards/${row.id}/preview`)}
                >
                  预览
                </Button>
                <Button type="link" onClick={() => setShareTarget(row)}>
                  分享
                </Button>
                {row.is_shared ? (
                  <Popconfirm
                    title="关闭后分享链接立即失效"
                    onConfirm={() => void onCloseShare(row)}
                  >
                    <Button type="link" danger>
                      关闭分享
                    </Button>
                  </Popconfirm>
                ) : null}
              </Space>
            ),
          },
        ]}
      />
      {!loading && rows.length === 0 ? <Text type="secondary">没有大屏</Text> : null}
      <ShareModal
        open={shareTarget != null}
        resourceName={shareTarget?.name}
        onSubmit={(body) => shareDashboard(shareTarget!.id, body)}
        onClose={(changed) => {
          setShareTarget(null);
          if (changed) void load();
        }}
      />
    </ListPageTemplate>
  );
}
