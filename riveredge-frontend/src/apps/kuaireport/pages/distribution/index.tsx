import React, { useEffect, useState } from 'react';
import {
  App,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Switch,
  Table,
} from 'antd';
import { getUserList, type User } from '../../../../services/user';
import { listReports, type ReportCenterRow } from '../reports/api';
import { listDashboards, type DashboardRow } from '../dashboards/api';
import {
  backfillDashboards,
  canView,
  createSubscription,
  grantShare,
  listDashboardVersions,
  listGrants,
  listReportVersions,
  restoreDashboardVersion,
  restoreReportVersion,
  type GrantRow,
  type ResourceType,
} from './api';

const RESOURCE_TYPE_OPTIONS = [
  { value: 'report', label: '报表' },
  { value: 'dashboard', label: '大屏' },
];

/**
 * 分发余项：角色授权、站内信订阅、版本回看。
 * 不打开免登录分享，也不在这里发 Excel。
 * 后端无订阅列表/停用/删除端点，本页只做登记；授权用 role_id 数字 id
 *（/core/roles 列表只暴露 uuid，这里保留手填 id）。
 */
export default function DistributionPage() {
  const { message } = App.useApp();
  const [grantForm] = Form.useForm();
  const [checkForm] = Form.useForm();
  const [reportId, setReportId] = useState<number>();
  const [dashboardId, setDashboardId] = useState<number>();
  const [reportVersions, setReportVersions] = useState<any[]>([]);
  const [dashboardVersions, setDashboardVersions] = useState<any[]>([]);
  const [grants, setGrants] = useState<GrantRow[]>([]);
  const [reports, setReports] = useState<ReportCenterRow[]>([]);
  const [dashboards, setDashboards] = useState<DashboardRow[]>([]);
  const [users, setUsers] = useState<User[]>([]);

  const grantResourceType = (Form.useWatch('resource_type', grantForm) ||
    'report') as ResourceType;
  const checkResourceType = (Form.useWatch('resource_type', checkForm) ||
    'report') as ResourceType;

  useEffect(() => {
    listReports({})
      .then((list) => setReports(Array.isArray(list) ? list : []))
      .catch(() => undefined);
    listDashboards()
      .then((list) => setDashboards(Array.isArray(list) ? list : []))
      .catch(() => undefined);
    getUserList({ page: 1, page_size: 500 })
      .then((res) => setUsers(res?.items || []))
      .catch(() => undefined);
  }, []);

  const resourceOptions = (type: ResourceType) =>
    (type === 'report' ? reports : dashboards).map((row) => ({
      value: row.id,
      label: `${row.name}（${row.code}）`,
    }));

  const userOptions = users.map((user) => ({
    value: user.id,
    label: user.full_name ? `${user.full_name}（${user.username}）` : user.username,
  }));

  const run = async (work: () => Promise<void>) => {
    try {
      await work();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '操作失败');
    }
  };

  const loadGrants = (resourceType: ResourceType, resourceId: number) =>
    run(async () => {
      setGrants((await listGrants(resourceType, resourceId)) || []);
    });

  const onGrant = (values: {
    resource_type: ResourceType;
    resource_id: number;
    role_id: number;
  }) =>
    run(async () => {
      await grantShare({ ...values, permission: 'view' });
      message.success('已写入角色授权');
      await loadGrants(values.resource_type, values.resource_id);
    });

  const onCheck = (values: { resource_type: ResourceType; resource_id: number }) =>
    run(async () => {
      const result = await canView(values.resource_type, values.resource_id);
      message.info(result?.allowed ? '当前用户的角色可以查看' : '当前用户的角色不能查看');
      await loadGrants(values.resource_type, values.resource_id);
    });

  const onSubscribe = (values: {
    report_id: number;
    name: string;
    recipient_user_ids: number[];
    cron?: string;
    attach_excel?: boolean;
    filters?: string;
  }) => {
    let filters: Record<string, unknown> | undefined;
    const raw = (values.filters || '').trim();
    if (raw) {
      try {
        const parsed: unknown = JSON.parse(raw);
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
          throw new Error('not-object');
        }
        filters = parsed as Record<string, unknown>;
      } catch {
        message.error('筛选需是 JSON 对象，例如 {"status":"ok"}');
        return Promise.resolve();
      }
    }
    return run(async () => {
      await createSubscription({
        report_id: values.report_id,
        name: values.name,
        recipient_user_ids: values.recipient_user_ids,
        cron: values.cron || '0 8 * * 1-5',
        channel: 'inbox',
        attach_excel: values.attach_excel ?? true,
        filters,
        is_active: true,
      });
      message.success('已登记站内信订阅');
    });
  };

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card title="按角色授权">
        <Form form={grantForm} layout="inline" onFinish={onGrant}>
          <Form.Item
            name="resource_type"
            label="资源"
            rules={[{ required: true }]}
            initialValue="report"
          >
            <Select style={{ width: 120 }} options={RESOURCE_TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item name="resource_id" label="资源" rules={[{ required: true }]}>
            <Select
              showSearch
              optionFilterProp="label"
              style={{ width: 240 }}
              options={resourceOptions(grantResourceType)}
            />
          </Form.Item>
          <Form.Item
            name="role_id"
            label="角色 ID"
            rules={[{ required: true }]}
            tooltip="授权走角色数字 id；角色管理列表只暴露 uuid"
          >
            <InputNumber min={1} />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            授权查看
          </Button>
        </Form>
        <Form form={checkForm} layout="inline" onFinish={onCheck} style={{ marginTop: 12 }}>
          <Form.Item
            name="resource_type"
            label="资源"
            rules={[{ required: true }]}
            initialValue="report"
          >
            <Select style={{ width: 120 }} options={RESOURCE_TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item name="resource_id" label="资源" rules={[{ required: true }]}>
            <Select
              showSearch
              optionFilterProp="label"
              style={{ width: 240 }}
              options={resourceOptions(checkResourceType)}
            />
          </Form.Item>
          <Button htmlType="submit">检查当前用户并列出授权</Button>
        </Form>
        <Table<GrantRow>
          style={{ marginTop: 12 }}
          rowKey="id"
          size="small"
          dataSource={grants}
          pagination={false}
          columns={[
            { title: '角色 ID', dataIndex: 'role_id' },
            { title: '资源类型', dataIndex: 'resource_type' },
            { title: '资源 ID', dataIndex: 'resource_id' },
            { title: '权限', dataIndex: 'permission' },
          ]}
        />
      </Card>

      <Card title="定时订阅（站内信）">
        <Form layout="vertical" onFinish={onSubscribe}>
          <Space wrap align="start">
            <Form.Item name="name" label="名称" rules={[{ required: true, max: 100 }]}>
              <Input maxLength={100} style={{ width: 180 }} />
            </Form.Item>
            <Form.Item name="report_id" label="报表" rules={[{ required: true }]}>
              <Select
                showSearch
                optionFilterProp="label"
                style={{ width: 240 }}
                options={reports.map((row) => ({
                  value: row.id,
                  label: `${row.name}（${row.code}）`,
                }))}
              />
            </Form.Item>
            <Form.Item
              name="recipient_user_ids"
              label="收件人（可多选）"
              rules={[{ required: true, message: '请选择至少一个收件人' }]}
            >
              <Select
                mode="multiple"
                showSearch
                optionFilterProp="label"
                style={{ minWidth: 240 }}
                options={userOptions}
              />
            </Form.Item>
            <Form.Item name="cron" label="Cron" initialValue="0 8 * * 1-5">
              <Input style={{ width: 160 }} />
            </Form.Item>
            <Form.Item
              name="attach_excel"
              label="附全量 Excel"
              valuePropName="checked"
              initialValue={true}
            >
              <Switch />
            </Form.Item>
          </Space>
          <Form.Item
            name="filters"
            label="筛选（JSON 对象，可选）"
            style={{ maxWidth: 560 }}
          >
            <Input.TextArea rows={2} placeholder='{"status":"ok"}' />
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
