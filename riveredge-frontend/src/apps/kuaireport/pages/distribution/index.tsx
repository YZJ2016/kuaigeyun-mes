import React, { useState } from 'react';
import { App, Button, Card, Form, Input, InputNumber, Select, Space, Table } from 'antd';
import {
  backfillDashboards,
  canView,
  createSubscription,
  grantShare,
  listDashboardVersions,
  listReportVersions,
  restoreDashboardVersion,
  restoreReportVersion,
  type ResourceType,
} from './api';

/**
 * 分发余项：角色授权、站内信订阅、版本回看。
 * 不打开免登录分享，也不在这里发 Excel。
 */
export default function DistributionPage() {
  const { message } = App.useApp();
  const [reportId, setReportId] = useState<number>();
  const [dashboardId, setDashboardId] = useState<number>();
  const [reportVersions, setReportVersions] = useState<any[]>([]);
  const [dashboardVersions, setDashboardVersions] = useState<any[]>([]);

  const run = async (work: () => Promise<void>) => {
    try {
      await work();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '操作失败');
    }
  };

  const onGrant = (values: {
    resource_type: ResourceType;
    resource_id: number;
    role_id: number;
  }) =>
    run(async () => {
      await grantShare({ ...values, permission: 'view' });
      message.success('已写入角色授权');
    });

  const onCheck = (values: { resource_type: ResourceType; resource_id: number }) =>
    run(async () => {
      const result = await canView(values.resource_type, values.resource_id);
      message.info(result?.allowed ? '当前用户的角色可以查看' : '当前用户的角色不能查看');
    });

  const onSubscribe = (values: {
    report_id: number;
    name: string;
    recipient_user_id: number;
    cron?: string;
  }) =>
    run(async () => {
      await createSubscription({
        report_id: values.report_id,
        name: values.name,
        recipient_user_ids: [values.recipient_user_id],
        cron: values.cron || '0 8 * * 1-5',
        channel: 'inbox',
        is_active: true,
      });
      message.success('已登记站内信订阅');
    });

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card title="按角色授权">
        <Form layout="inline" onFinish={onGrant}>
          <Form.Item name="resource_type" label="资源" rules={[{ required: true }]}>
            <Select
              style={{ width: 120 }}
              options={[
                { value: 'report', label: '报表' },
                { value: 'dashboard', label: '大屏' },
              ]}
            />
          </Form.Item>
          <Form.Item name="resource_id" label="资源 ID" rules={[{ required: true }]}>
            <InputNumber min={1} />
          </Form.Item>
          <Form.Item name="role_id" label="角色 ID" rules={[{ required: true }]}>
            <InputNumber min={1} />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            授权查看
          </Button>
        </Form>
        <Form layout="inline" onFinish={onCheck} style={{ marginTop: 12 }}>
          <Form.Item name="resource_type" label="资源" rules={[{ required: true }]}>
            <Select
              style={{ width: 120 }}
              options={[
                { value: 'report', label: '报表' },
                { value: 'dashboard', label: '大屏' },
              ]}
            />
          </Form.Item>
          <Form.Item name="resource_id" label="资源 ID" rules={[{ required: true }]}>
            <InputNumber min={1} />
          </Form.Item>
          <Button htmlType="submit">检查当前用户</Button>
        </Form>
      </Card>

      <Card title="定时订阅（站内信）">
        <Form layout="inline" onFinish={onSubscribe}>
          <Form.Item name="name" label="名称" rules={[{ required: true, max: 100 }]}>
            <Input maxLength={100} />
          </Form.Item>
          <Form.Item name="report_id" label="报表 ID" rules={[{ required: true }]}>
            <InputNumber min={1} />
          </Form.Item>
          <Form.Item name="recipient_user_id" label="用户 ID" rules={[{ required: true }]}>
            <InputNumber min={1} />
          </Form.Item>
          <Form.Item name="cron" label="Cron" initialValue="0 8 * * 1-5">
            <Input />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            保存订阅
          </Button>
        </Form>
      </Card>

      <Card title="账表版本">
        <Form
          layout="inline"
          onFinish={(values: { report_id: number }) =>
            run(async () => {
              setReportId(values.report_id);
              setReportVersions((await listReportVersions(values.report_id)) || []);
            })
          }
        >
          <Form.Item name="report_id" label="报表 ID" rules={[{ required: true }]}>
            <InputNumber min={1} />
          </Form.Item>
          <Button htmlType="submit">列出版本</Button>
        </Form>
        <Table
          style={{ marginTop: 12 }}
          rowKey="version_no"
          dataSource={reportVersions}
          pagination={false}
          columns={[
            { title: '版本', dataIndex: 'version_no' },
            { title: '备注', dataIndex: 'note' },
            {
              title: '操作',
              render: (_value, row) => (
                <Button
                  type="link"
                  onClick={() =>
                    run(async () => {
                      if (!reportId) return;
                      await restoreReportVersion(reportId, row.version_no);
                      message.success(`已恢复版本 ${row.version_no}`);
                    })
                  }
                >
                  恢复
                </Button>
              ),
            },
          ]}
        />
      </Card>

      <Card
        title="大屏版本"
        extra={
          <Button
            onClick={() =>
              run(async () => {
                const result = await backfillDashboards();
                message.success(`已补写 ${result?.dashboard_ids?.length || 0} 块大屏`);
              })
            }
          >
            补写尚无快照的大屏
          </Button>
        }
      >
        <Form
          layout="inline"
          onFinish={(values: { dashboard_id: number }) =>
            run(async () => {
              setDashboardId(values.dashboard_id);
              setDashboardVersions((await listDashboardVersions(values.dashboard_id)) || []);
            })
          }
        >
          <Form.Item name="dashboard_id" label="大屏 ID" rules={[{ required: true }]}>
            <InputNumber min={1} />
          </Form.Item>
          <Button htmlType="submit">列出版本</Button>
        </Form>
        <Table
          style={{ marginTop: 12 }}
          rowKey="version_no"
          dataSource={dashboardVersions}
          pagination={false}
          columns={[
            { title: '版本', dataIndex: 'version_no' },
            { title: '备注', dataIndex: 'note' },
            {
              title: '操作',
              render: (_value, row) => (
                <Button
                  type="link"
                  onClick={() =>
                    run(async () => {
                      if (!dashboardId) return;
                      await restoreDashboardVersion(dashboardId, row.version_no);
                      message.success(`已恢复版本 ${row.version_no}`);
                    })
                  }
                >
                  恢复
                </Button>
              ),
            },
          ]}
        />
      </Card>
    </Space>
  );
}
