/**
 * 报表中心列表。按 status / category / classify 筛选，并按 classify 分组。
 * 不提供设计器，不在此创建 category=custom 的报表。
 * 分享与关闭分享是显式动作：10 张系统报表默认 is_shared=false，须人开启。
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { App, Button, Input, Popconfirm, Select, Space, Table, Tag, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { ShareModal } from '../dashboards/ShareModal';
import {
  closeReportShare,
  listReports,
  publishReport,
  shareReport,
  type ReportCenterRow,
} from './api';

const { Title, Text } = Typography;

const STATUS_OPTIONS = [
  { value: 'DRAFT', label: '草稿' },
  { value: 'PUBLISHED', label: '已发布' },
];

export default function ReportCenterPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [rows, setRows] = useState<ReportCenterRow[]>([]);
  const [status, setStatus] = useState<string | undefined>();
  const [category, setCategory] = useState<string | undefined>();
  const [classify, setClassify] = useState<string | undefined>();
  const [classifyInput, setClassifyInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [shareTarget, setShareTarget] = useState<ReportCenterRow | null>(null);
  const classifyTimer = useRef<number | undefined>(undefined);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listReports({
        status: status || undefined,
        category: category || undefined,
        classify: classify || undefined,
      });
      setRows(Array.isArray(data) ? data : []);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '报表列表加载失败');
    } finally {
      setLoading(false);
    }
  }, [category, classify, status, message]);

  useEffect(() => {
    void load();
  }, [load]);

  // 分类输入防抖，避免每击键请求
  useEffect(() => {
    window.clearTimeout(classifyTimer.current);
    classifyTimer.current = window.setTimeout(() => {
      setClassify(classifyInput.trim() || undefined);
    }, 400);
    return () => window.clearTimeout(classifyTimer.current);
  }, [classifyInput]);

  const groups = useMemo(() => {
    const map = new Map<string, ReportCenterRow[]>();
    for (const row of rows) {
      const key = row.classify || '未分类';
      const bucket = map.get(key);
      if (bucket) bucket.push(row);
      else map.set(key, [row]);
    }
    return [...map.entries()];
  }, [rows]);

  const onPublish = async (row: ReportCenterRow) => {
    try {
      await publishReport(row.id);
      message.success(`「${row.name}」已发布`);
      void load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '发布失败');
    }
  };

  const onCloseShare = async (row: ReportCenterRow) => {
    try {
      await closeReportShare(row.id);
      message.success(`「${row.name}」已关闭分享`);
      void load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '关闭分享失败');
    }
  };

  return (
    <ListPageTemplate>
      <Title level={4}>报表中心</Title>
      <Space wrap style={{ marginBottom: 16 }}>
        <Select
          allowClear
          placeholder="状态"
          style={{ width: 140 }}
          value={status}
          onChange={(value) => setStatus(value)}
          options={STATUS_OPTIONS}
        />
        <Select
          allowClear
          placeholder="系统 / 自定义"
          style={{ width: 160 }}
          value={category}
          onChange={(value) => setCategory(value)}
          options={[
            { value: 'system', label: '系统报表' },
            { value: 'custom', label: '自定义报表' },
          ]}
        />
        <Input
          allowClear
          placeholder="业务分类"
          style={{ width: 160 }}
          value={classifyInput}
          onChange={(event) => setClassifyInput(event.target.value)}
        />
        <Button onClick={() => setStatus('DRAFT')}>只看草稿</Button>
      </Space>
      {groups.map(([group, items]) => (
        <section key={group} style={{ marginBottom: 24 }}>
          <Title level={5}>{group}</Title>
          <Table<ReportCenterRow>
            rowKey="id"
            loading={loading}
            pagination={false}
            dataSource={items}
            columns={[
              { title: '名称', dataIndex: 'name' },
              { title: '编码', dataIndex: 'code' },
              {
                title: '类别',
                dataIndex: 'category',
                render: (value: string) => (value === 'system' ? '系统报表' : '自定义报表'),
              },
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
                title: '操作',
                render: (_, row) => (
                  <Space size={0} wrap>
                    <Button
                      type="link"
                      onClick={() => navigate(`/apps/kuaireport/reports/view/${row.id}`)}
                    >
                      打开
                    </Button>
                    {row.category === 'custom' ? (
                      <Button
                        type="link"
                        onClick={() =>
                          navigate(`/apps/kuaireport/designer?reportId=${row.id}`)
                        }
                      >
                        编辑
                      </Button>
                    ) : null}
                    {row.status === 'PUBLISHED' ? null : (
                      <Button type="link" onClick={() => void onPublish(row)}>
                        发布
                      </Button>
                    )}
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
        </section>
      ))}
      {!loading && rows.length === 0 ? <Text type="secondary">没有报表</Text> : null}
      <ShareModal
        open={shareTarget != null}
        resourceName={shareTarget?.name}
        onSubmit={(body) => shareReport(shareTarget!.id, body)}
        onClose={(changed) => {
          setShareTarget(null);
          if (changed) void load();
        }}
      />
    </ListPageTemplate>
  );
}
