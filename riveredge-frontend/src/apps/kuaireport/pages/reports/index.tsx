/**
 * 报表中心列表。按 status / category / classify 筛选，并按 classify 分组。
 * 不提供设计器，不在此创建 category=custom 的报表。
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Input, Select, Space, Table, Tag, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { listReports, type ReportCenterRow } from './api';

const { Title, Text } = Typography;

export default function ReportCenterPage() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<ReportCenterRow[]>([]);
  const [status, setStatus] = useState<string | undefined>();
  const [category, setCategory] = useState<string | undefined>();
  const [classify, setClassify] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listReports({
        status: status || undefined,
        category: category || undefined,
        classify: classify || undefined,
      });
      setRows(Array.isArray(data) ? data : []);
    } finally {
      setLoading(false);
    }
  }, [category, classify, status]);

  useEffect(() => {
    void load();
  }, [load]);

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

  return (
    <ListPageTemplate>
      <Title level={4}>报表中心</Title>
      <Space wrap style={{ marginBottom: 16 }}>
        <Input
          allowClear
          placeholder="状态，草稿为 DRAFT"
          style={{ width: 200 }}
          value={status}
          onChange={(event) => setStatus(event.target.value || undefined)}
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
          value={classify}
          onChange={(event) => setClassify(event.target.value || undefined)}
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
                  value === 'DRAFT' ? <Tag>草稿</Tag> : <Tag color="blue">{value}</Tag>,
              },
              {
                title: '分享',
                dataIndex: 'is_shared',
                render: (value: boolean) => (value ? '已开启' : '未开启'),
              },
              {
                title: '操作',
                render: (_, row) => (
                  <Button
                    type="link"
                    onClick={() => navigate(`/apps/kuaireport/reports/view/${row.id}`)}
                  >
                    打开
                  </Button>
                ),
              },
            ]}
          />
        </section>
      ))}
      {!loading && rows.length === 0 ? <Text type="secondary">没有报表</Text> : null}
    </ListPageTemplate>
  );
}
