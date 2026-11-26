/**
 * 图纸管理集成：反查弹窗、按图发放/借阅、详情抽屉记录 Tab
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  App,
  Button,
  Col,
  Empty,
  Form,
  Input,
  Modal,
  Row,
  Space,
  Spin,
  Table,
  Tabs,
} from 'antd';
import {
  ProFormDateTimePicker,
  ProFormInstance,
  ProFormItem,
  ProFormText,
  ProFormTextArea,
} from '@ant-design/pro-components';
import dayjs from 'dayjs';
import { FormModalTemplate, MODAL_CONFIG } from '../../../../../components/layout-templates';
import { UniDropdown } from '../../../../../components/uni-dropdown';
import { UniUserSelect } from '../../../../../components/uni-user-select';
import { MarkerTag, StatusTag } from '../../../../../constants/statusBadges';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { formatDateTimeBySiteSetting } from '../../../../../utils/format';
import { getDepartmentTree } from '../../../../../services/department';
import {
  flattenDepartmentTreeOptions,
  type DepartmentPickerOption,
} from '../../../utils/flattenDepartmentTreeOptions';
import {
  drawingDistributionApi,
  type DrawingDistribution,
  type DrawingDistributionStatus,
} from '../../../services/drawingDistribution';
import {
  drawingLoanApi,
  type DrawingLoan,
  type DrawingLoanStatus,
} from '../../../services/drawingLoan';
import {
  drawingWhereUsedApi,
  type DrawingWhereUsedUsage,
} from '../../../services/drawingWhereUsed';
import type { EngineeringDrawing, EngineeringDrawingRevisionBrief } from '../../../services/drawing';

const DIST_STATUS_COLOR: Record<DrawingDistributionStatus, string> = {
  Draft: 'default',
  Pending: 'processing',
  Issued: 'success',
  Recalled: 'default',
};

const LOAN_STATUS_COLOR: Record<DrawingLoanStatus, string> = {
  Draft: 'default',
  Pending: 'processing',
  Borrowed: 'success',
  Returned: 'default',
};

function dueAtPayload(value: unknown): string | undefined {
  if (value == null || value === '') return undefined;
  if (dayjs.isDayjs(value)) return value.toISOString();
  if (typeof value === 'string') return value;
  return undefined;
}

export type DrawingWhereUsedModalProps = {
  open: boolean;
  drawing: EngineeringDrawing | null;
  onClose: () => void;
};

export const DrawingWhereUsedModal: React.FC<DrawingWhereUsedModalProps> = ({
  open,
  drawing,
  onClose,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [usages, setUsages] = useState<DrawingWhereUsedUsage[]>([]);

  useEffect(() => {
    if (!open || !drawing?.uuid) {
      setUsages([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void drawingWhereUsedApi
      .query({ drawingUuid: drawing.uuid })
      .then((res) => {
        if (!cancelled) setUsages(res.usages ?? []);
      })
      .catch((e) => {
        if (!cancelled) {
          setUsages([]);
          messageApi.error(getApiErrorMessage(e) || t('app.master-data.drawingWhereUsed.queryFailed'));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, drawing?.uuid, messageApi, t]);

  return (
    <Modal
      title={`${t('app.master-data.menu.process.drawing-where-used')}${
        drawing ? `：${drawing.code}` : ''
      }`}
      open={open}
      onCancel={onClose}
      footer={
        <Button type="primary" onClick={onClose}>
          {t('common.close')}
        </Button>
      }
      width={720}
      destroyOnHidden
    >
      {loading ? (
        <Spin />
      ) : usages.length ? (
        <Table
          size="small"
          rowKey={(row) => `${row.kind}-${row.uuid}`}
          pagination={false}
          dataSource={usages}
          columns={[
            {
              title: t('app.master-data.drawingWhereUsed.usageKind'),
              dataIndex: 'kind',
              width: 120,
              render: (v: DrawingWhereUsedUsage['kind']) =>
                t(`app.master-data.drawingWhereUsed.kind.${v}`),
            },
            { title: t('app.master-data.drawingWhereUsed.usageCode'), dataIndex: 'code', width: 160 },
            { title: t('app.master-data.drawingWhereUsed.usageName'), dataIndex: 'name', ellipsis: true },
            {
              title: t('app.master-data.drawingWhereUsed.usageExtra'),
              dataIndex: 'extra',
              ellipsis: true,
            },
          ]}
        />
      ) : (
        <Empty description={t('app.master-data.drawings.whereUsedEmpty')} />
      )}
    </Modal>
  );
};

export type DrawingDistributeModalProps = {
  open: boolean;
  drawing: EngineeringDrawing | null;
  onClose: () => void;
  onSuccess?: () => void;
};

export const DrawingDistributeFromDrawingModal: React.FC<DrawingDistributeModalProps> = ({
  open,
  drawing,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const formRef = useRef<ProFormInstance>(undefined);
  const [departmentOptions, setDepartmentOptions] = useState<DepartmentPickerOption[]>([]);
  const [issueDepartmentUuid, setIssueDepartmentUuid] = useState<string | undefined>();

  useEffect(() => {
    if (!open) return;
    void getDepartmentTree({ is_active: true })
      .then((res) => setDepartmentOptions(flattenDepartmentTreeOptions(res?.items ?? [])))
      .catch(() => setDepartmentOptions([]));
  }, [open]);

  useEffect(() => {
    if (!open || !drawing) return;
    formRef.current?.setFieldsValue({
      name: `${t('app.master-data.drawingDistributions.create')}-${drawing.code}`,
      linesNote: `${drawing.code} ${drawing.name} Rev.${drawing.revision}`,
    });
  }, [open, drawing, t]);

  return (
    <FormModalTemplate
      title={t('app.master-data.drawingDistributions.createTitle')}
      open={open}
      onClose={() => {
        setIssueDepartmentUuid(undefined);
        formRef.current?.resetFields();
        onClose();
      }}
      formRef={formRef}
      width={MODAL_CONFIG.STANDARD_WIDTH}
      grid={false}
      onFinish={async (values) => {
        if (!drawing?.uuid) return;
        if (!values.issueDepartmentId || !values.recipientUserId) {
          messageApi.error(t('app.master-data.drawingDistributions.partyRequired'));
          return;
        }
        await drawingDistributionApi.create({
          name: values.name,
          issueDepartmentId: values.issueDepartmentId,
          recipientUserId: values.recipientUserId,
          remark: values.remark,
          lines: [{ drawingUuid: drawing.uuid }],
        });
        messageApi.success(t('common.saveSuccess'));
        setIssueDepartmentUuid(undefined);
        onClose();
        onSuccess?.();
      }}
    >
      <Row gutter={16}>
        <Col span={24}>
          <ProFormText
            name="name"
            label={t('app.master-data.drawingDistributions.name')}
            rules={[{ required: true, message: t('app.master-data.drawingDistributions.nameRequired') }]}
          />
        </Col>
        <Col span={12}>
          <ProFormItem
            name="issueDepartmentId"
            label={t('app.master-data.drawingDistributions.issueDepartment')}
            rules={[
              {
                required: true,
                message: t('app.master-data.drawingDistributions.issueDepartmentRequired'),
              },
            ]}
          >
            <UniDropdown
              placeholder={t('app.master-data.drawingDistributions.issueDepartmentPlaceholder')}
              options={departmentOptions.map((item) => ({ label: item.label, value: item.value }))}
              showSearch
              optionFilterProp="label"
              onChange={(value) => {
                const match = departmentOptions.find((item) => item.value === value);
                setIssueDepartmentUuid(match?.uuid);
                formRef.current?.setFieldsValue({
                  recipientUserUuid: undefined,
                  recipientUserId: undefined,
                });
              }}
            />
          </ProFormItem>
        </Col>
        <Col span={12}>
          <UniUserSelect
            name="recipientUserUuid"
            label={t('app.master-data.drawingDistributions.recipientUser')}
            placeholder={t('app.master-data.drawingDistributions.recipientUserPlaceholder')}
            required
            departmentUuid={issueDepartmentUuid}
            onChange={(_value: unknown, user: unknown) => {
              const picked = Array.isArray(user) ? user[0] : user;
              const id =
                picked && typeof picked === 'object' && 'id' in picked
                  ? (picked as { id: number }).id
                  : undefined;
              formRef.current?.setFieldsValue({ recipientUserId: id });
            }}
          />
          <Form.Item name="recipientUserId" hidden>
            <Input />
          </Form.Item>
        </Col>
        <Col span={24}>
          <ProFormText
            name="linesNote"
            label={t('app.master-data.drawingDistributions.lines')}
            disabled
          />
        </Col>
        <Col span={24}>
          <ProFormTextArea name="remark" label={t('common.remark')} />
        </Col>
      </Row>
    </FormModalTemplate>
  );
};

export type DrawingLoanFromDrawingModalProps = {
  open: boolean;
  drawing: EngineeringDrawing | null;
  onClose: () => void;
  onSuccess?: () => void;
};

export const DrawingLoanFromDrawingModal: React.FC<DrawingLoanFromDrawingModalProps> = ({
  open,
  drawing,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const formRef = useRef<ProFormInstance>(undefined);
  const [departmentOptions, setDepartmentOptions] = useState<DepartmentPickerOption[]>([]);
  const [borrowerDepartmentUuid, setBorrowerDepartmentUuid] = useState<string | undefined>();

  useEffect(() => {
    if (!open) return;
    void getDepartmentTree({ is_active: true })
      .then((res) => setDepartmentOptions(flattenDepartmentTreeOptions(res?.items ?? [])))
      .catch(() => setDepartmentOptions([]));
  }, [open]);

  useEffect(() => {
    if (!open || !drawing) return;
    formRef.current?.setFieldsValue({
      name: `${t('app.master-data.drawingLoans.create')}-${drawing.code}`,
      dueAt: dayjs().add(7, 'day'),
      linesNote: `${drawing.code} ${drawing.name} Rev.${drawing.revision}`,
    });
  }, [open, drawing, t]);

  return (
    <FormModalTemplate
      title={t('app.master-data.drawingLoans.createTitle')}
      open={open}
      onClose={() => {
        setBorrowerDepartmentUuid(undefined);
        formRef.current?.resetFields();
        onClose();
      }}
      formRef={formRef}
      width={MODAL_CONFIG.STANDARD_WIDTH}
      grid={false}
      onFinish={async (values) => {
        if (!drawing?.uuid) return;
        const dueAt = dueAtPayload(values.dueAt);
        if (!dueAt) {
          messageApi.error(t('app.master-data.drawingLoans.dueAtRequired'));
          return;
        }
        if (!values.borrowerDepartmentId || !values.borrowerUserId) {
          messageApi.error(t('app.master-data.drawingLoans.partyRequired'));
          return;
        }
        await drawingLoanApi.create({
          name: values.name,
          purpose: values.purpose,
          dueAt,
          borrowerDepartmentId: values.borrowerDepartmentId,
          borrowerUserId: values.borrowerUserId,
          lines: [{ drawingUuid: drawing.uuid }],
        });
        messageApi.success(t('common.saveSuccess'));
        setBorrowerDepartmentUuid(undefined);
        onClose();
        onSuccess?.();
      }}
    >
      <Row gutter={16}>
        <Col span={12}>
          <ProFormText
            name="name"
            label={t('app.master-data.drawingLoans.name')}
            rules={[{ required: true, message: t('app.master-data.drawingLoans.nameRequired') }]}
          />
        </Col>
        <Col span={12}>
          <ProFormDateTimePicker
            name="dueAt"
            label={t('app.master-data.drawingLoans.dueAt')}
            rules={[{ required: true, message: t('app.master-data.drawingLoans.dueAtRequired') }]}
          />
        </Col>
        <Col span={12}>
          <ProFormText name="purpose" label={t('app.master-data.drawingLoans.purpose')} />
        </Col>
        <Col span={12}>
          <ProFormItem
            name="borrowerDepartmentId"
            label={t('app.master-data.drawingLoans.borrowerDepartment')}
            rules={[
              {
                required: true,
                message: t('app.master-data.drawingLoans.borrowerDepartmentRequired'),
              },
            ]}
          >
            <UniDropdown
              placeholder={t('app.master-data.drawingLoans.borrowerDepartmentPlaceholder')}
              options={departmentOptions.map((item) => ({ label: item.label, value: item.value }))}
              showSearch
              optionFilterProp="label"
              onChange={(value) => {
                const match = departmentOptions.find((item) => item.value === value);
                setBorrowerDepartmentUuid(match?.uuid);
                formRef.current?.setFieldsValue({
                  borrowerUserUuid: undefined,
                  borrowerUserId: undefined,
                });
              }}
            />
          </ProFormItem>
        </Col>
        <Col span={12}>
          <UniUserSelect
            name="borrowerUserUuid"
            label={t('app.master-data.drawingLoans.borrowerUser')}
            placeholder={t('app.master-data.drawingLoans.borrowerUserPlaceholder')}
            required
            departmentUuid={borrowerDepartmentUuid}
            onChange={(_value: unknown, user: unknown) => {
              const picked = Array.isArray(user) ? user[0] : user;
              const id =
                picked && typeof picked === 'object' && 'id' in picked
                  ? (picked as { id: number }).id
                  : undefined;
              formRef.current?.setFieldsValue({ borrowerUserId: id });
            }}
          />
          <Form.Item name="borrowerUserId" hidden>
            <Input />
          </Form.Item>
        </Col>
        <Col span={24}>
          <ProFormText name="linesNote" label={t('app.master-data.drawingLoans.lines')} disabled />
        </Col>
      </Row>
    </FormModalTemplate>
  );
};

export type DrawingDetailRecordTabsProps = {
  drawing: EngineeringDrawing | null;
  revisions: EngineeringDrawingRevisionBrief[];
  revisionsLoading: boolean;
  statusLabel: (status: EngineeringDrawing['status']) => string;
  statusColor: Record<EngineeringDrawing['status'], string>;
  onOpenRevision: (rev: EngineeringDrawingRevisionBrief) => void;
  reloadToken?: number;
};

export const DrawingDetailRecordTabs: React.FC<DrawingDetailRecordTabsProps> = ({
  drawing,
  revisions,
  revisionsLoading,
  statusLabel,
  statusColor,
  onOpenRevision,
  reloadToken = 0,
}) => {
  const { t } = useTranslation();
  const [distLoading, setDistLoading] = useState(false);
  const [loanLoading, setLoanLoading] = useState(false);
  const [distributions, setDistributions] = useState<DrawingDistribution[]>([]);
  const [loans, setLoans] = useState<DrawingLoan[]>([]);
  const [activeKey, setActiveKey] = useState('revisions');

  const loadRecords = useCallback(async () => {
    if (!drawing?.uuid) {
      setDistributions([]);
      setLoans([]);
      return;
    }
    setDistLoading(true);
    setLoanLoading(true);
    try {
      const [distRes, loanRes] = await Promise.all([
        drawingDistributionApi.list({ drawingUuid: drawing.uuid, limit: 100 }),
        drawingLoanApi.list({ drawingUuid: drawing.uuid, limit: 100 }),
      ]);
      setDistributions(distRes.data ?? []);
      setLoans(loanRes.data ?? []);
    } catch {
      setDistributions([]);
      setLoans([]);
    } finally {
      setDistLoading(false);
      setLoanLoading(false);
    }
  }, [drawing?.uuid]);

  useEffect(() => {
    void loadRecords();
  }, [loadRecords, reloadToken]);

  const revisionPane = useMemo(() => {
    if (revisionsLoading) return <Spin />;
    if (!revisions.length) {
      return (
        <span style={{ color: 'var(--ant-color-text-secondary)' }}>
          {t('app.master-data.drawings.noRevisionHistory')}
        </span>
      );
    }
    return (
      <Space orientation="vertical" size={8} style={{ width: '100%' }}>
        {revisions.map((rev) => (
          <Space key={rev.uuid} wrap>
            <Button
              type={rev.uuid === drawing?.uuid ? 'primary' : 'default'}
              size="small"
              onClick={() => onOpenRevision(rev)}
            >
              {t('app.master-data.drawings.revision')} {rev.revision}
            </Button>
            <MarkerTag color={statusColor[rev.status]}>{statusLabel(rev.status)}</MarkerTag>
            {rev.releasedAt ? (
              <span style={{ color: 'var(--ant-color-text-secondary)', fontSize: 12 }}>
                {t('app.master-data.drawings.releasedAt')}: {rev.releasedAt}
              </span>
            ) : null}
          </Space>
        ))}
      </Space>
    );
  }, [
    revisionsLoading,
    revisions,
    drawing?.uuid,
    onOpenRevision,
    statusColor,
    statusLabel,
    t,
  ]);

  return (
    <Tabs
      activeKey={activeKey}
      onChange={setActiveKey}
      items={[
        {
          key: 'revisions',
          label: t('app.master-data.drawings.revisionHistory'),
          children: revisionPane,
        },
        {
          key: 'distributions',
          label: t('app.master-data.drawings.detailTabDistributions'),
          children: distLoading ? (
            <Spin />
          ) : (
            <Table
              size="small"
              rowKey="uuid"
              pagination={false}
              locale={{ emptyText: <Empty description={t('common.noData')} /> }}
              dataSource={distributions}
              columns={[
                { title: t('common.code'), dataIndex: 'code', width: 140 },
                { title: t('common.name'), dataIndex: 'name', ellipsis: true },
                {
                  title: t('common.status'),
                  dataIndex: 'status',
                  width: 100,
                  render: (v: DrawingDistributionStatus) => (
                    <StatusTag color={DIST_STATUS_COLOR[v]}>
                      {t(`app.master-data.drawingDistributions.status.${v}`)}
                    </StatusTag>
                  ),
                },
                {
                  title: t('app.master-data.drawingDistributions.recipientUser'),
                  dataIndex: 'recipientUserName',
                  width: 100,
                },
                {
                  title: t('app.master-data.drawingDistributions.issuedAt'),
                  dataIndex: 'issuedAt',
                  width: 160,
                  render: (v?: string) => (v ? formatDateTimeBySiteSetting(v) : '-'),
                },
              ]}
            />
          ),
        },
        {
          key: 'loans',
          label: t('app.master-data.drawings.detailTabLoans'),
          children: loanLoading ? (
            <Spin />
          ) : (
            <Table
              size="small"
              rowKey="uuid"
              pagination={false}
              locale={{ emptyText: <Empty description={t('common.noData')} /> }}
              dataSource={loans}
              columns={[
                { title: t('common.code'), dataIndex: 'code', width: 140 },
                { title: t('common.name'), dataIndex: 'name', ellipsis: true },
                {
                  title: t('common.status'),
                  dataIndex: 'status',
                  width: 100,
                  render: (v: DrawingLoanStatus) => (
                    <StatusTag color={LOAN_STATUS_COLOR[v]}>
                      {t(`app.master-data.drawingLoans.status.${v}`)}
                    </StatusTag>
                  ),
                },
                {
                  title: t('app.master-data.drawingLoans.borrowerUser'),
                  dataIndex: 'borrowerUserName',
                  width: 100,
                },
                {
                  title: t('app.master-data.drawingLoans.dueAt'),
                  dataIndex: 'dueAt',
                  width: 160,
                  render: (v?: string) => (v ? formatDateTimeBySiteSetting(v) : '-'),
                },
              ]}
            />
          ),
        },
      ]}
    />
  );
};
