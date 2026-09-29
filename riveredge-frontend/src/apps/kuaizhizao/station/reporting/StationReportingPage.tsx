import React, { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  App,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Radio,
  Space,
  Spin,
} from 'antd';
import { TouchScreenTemplate } from '../../../../components/layout-templates/TouchScreenTemplate';
import { UniMaterialSelect } from '../../../../components/uni-material-select';
import { UniUserSelect } from '../../../../components/uni-user-select';
import { useCurrentUser } from '../../../../hooks/useCurrentUser';
import { reportingClientChannelSourceI18nKey } from '../../../../utils/clientChannel';
import { convertProductionInputToBaseQty } from '../../../../utils/materialScenarioUnit';
import { hasModulePermission } from '../../../../utils/permissionContract';
import { WorkGroupSelectDropdown } from '../../../master-data/components/WorkGroupSelectDropdown';
import type { WorkGroup } from '../../../master-data/types/factory';
import type { Material } from '../../../master-data/types/material';
import { reportingApi, workOrderApi, materialBindingApi } from '../../services/production';
import { coerceReportingCreateStrings } from '../../utils/reportingPayload';
import { resolveReportingWorkTimeForSubmit } from '../../utils/reportingWorkTime';
import {
  buildMaterialBindingBody,
  buildQuickReportingBody,
  buildScrapBody,
  resolveWorkstationId,
  rowsFromListResponse,
  workOrderDisplayName,
  type StationOperator,
  type StationReportMode,
} from './quickReporting';

const ASSIGN_RESOURCE = 'kuaizhizao:production-execution-reporting';

export type StationReportingPageProps = {
  /** 157 入口已绑定工位。缺省时读 URL query `workstationId`。 */
  workstationId?: number | null;
  /** 157 当前操作员。entry 未导出读取函数时由挂载方传入；缺省则本人报工不提交。 */
  operator?: StationOperator | null;
};

type WorkOrderRow = {
  id?: number;
  code?: string;
  name?: string | null;
  product_name?: string | null;
  product_unit?: string;
  base_unit?: string;
  unit_to_base_factor?: number;
};

type OperationRow = {
  operation_id?: number;
  operation_code?: string;
  operation_name?: string;
  status?: string;
};

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : '';
}

export const StationReportingPage: React.FC<StationReportingPageProps> = ({
  workstationId: boundWorkstationId,
  operator = null,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const [searchParams] = useSearchParams();
  const currentUser = useCurrentUser();
  const canAssign = useMemo(
    () => hasModulePermission(currentUser, ASSIGN_RESOURCE, 'assign'),
    [currentUser],
  );
  const workstationId = resolveWorkstationId(boundWorkstationId, searchParams.get('workstationId'));

  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<StationReportMode>('self');
  const [workOrder, setWorkOrder] = useState<WorkOrderRow | null>(null);
  const [operations, setOperations] = useState<OperationRow[]>([]);
  const [operation, setOperation] = useState<OperationRow | null>(null);
  const [proxyWorker, setProxyWorker] = useState<StationOperator | null>(null);
  const [team, setTeam] = useState<{ id: number; name: string } | null>(null);
  const [recordId, setRecordId] = useState<number | null>(null);
  const [recordUnqualified, setRecordUnqualified] = useState<number>(0);
  const [sourceLabel, setSourceLabel] = useState<string>('');
  const [material, setMaterial] = useState<Material | null>(null);

  const unqualified = Form.useWatch('unqualified_quantity', form);

  const loadWorkOrder = async () => {
    const code = String(form.getFieldValue('work_order_code') ?? '').trim();
    if (!code) {
      messageApi.warning('请输入工单编号');
      return;
    }
    setLoading(true);
    try {
      const raw = await workOrderApi.list({ code });
      const rows = rowsFromListResponse<WorkOrderRow>(raw);
      const matched = rows.find((row) => String(row.code ?? '').trim() === code) ?? rows[0];
      if (!matched?.id) {
        messageApi.error('未找到该工单');
        setWorkOrder(null);
        setOperations([]);
        setOperation(null);
        return;
      }
      setWorkOrder(matched);
      const opRaw = await workOrderApi.getOperations(String(matched.id));
      const list = rowsFromListResponse<OperationRow>(opRaw);
      setOperations(list);
      const pending = list.find((op) => op.status !== 'completed') ?? list[0] ?? null;
      setOperation(pending);
    } catch (error: unknown) {
      messageApi.error(errorText(error) || '加载工单失败');
    } finally {
      setLoading(false);
    }
  };

  const submitReport = async () => {
    const values = form.getFieldsValue();
    const qualifiedDisplay = Number(values.qualified_quantity) || 0;
    const unqualifiedDisplay = Number(values.unqualified_quantity) || 0;
    const workTime = resolveReportingWorkTimeForSubmit({
      work_hours: values.work_hours,
    });
    const decision = buildQuickReportingBody({
      mode,
      hasAssignPermission: canAssign,
      workstationId,
      operator,
      proxyWorker,
      team,
      workOrder,
      operation,
      qualifiedQuantity: workOrder
        ? convertProductionInputToBaseQty(qualifiedDisplay, workOrder)
        : qualifiedDisplay,
      unqualifiedQuantity: workOrder
        ? convertProductionInputToBaseQty(unqualifiedDisplay, workOrder)
        : unqualifiedDisplay,
      workHours: workTime.work_hours,
      reportedAt: workTime.reported_at,
      defectReason: values.defect_reason,
      remarks: values.remarks,
    });
    if (!decision.submit) {
      if (decision.reason === 'proxy-forbidden') {
        messageApi.warning('没有代报权限，请求未发出');
        return;
      }
      if (decision.reason === 'missing-operator') {
        messageApi.warning('当前操作员未传入，本人报工不会提交');
        return;
      }
      if (decision.reason === 'missing-workstation') {
        messageApi.warning('未绑定工位');
        return;
      }
      if (decision.reason === 'missing-team') {
        messageApi.warning(t('app.kuaizhizao.workReporting.formWorkGroupRequired'));
        return;
      }
      if (decision.reason === 'quantity-not-positive') {
        messageApi.warning(t('app.kuaizhizao.workReporting.quantityMustBePositive'));
        return;
      }
      if (decision.reason === 'missing-defect-reason') {
        messageApi.warning('有不合格数量时需填写不良原因');
        return;
      }
      messageApi.warning('报工信息不完整');
      return;
    }

    setLoading(true);
    try {
      const created = await reportingApi.quickCreate(
        coerceReportingCreateStrings(decision.body, workOrder ?? undefined),
      );
      const createdId = Number((created as { id?: number } | null)?.id);
      if (!Number.isFinite(createdId) || createdId <= 0) {
        messageApi.error(t('app.kuaizhizao.workReporting.createFailed'));
        return;
      }
      setRecordId(createdId);
      setRecordUnqualified(Number((created as { unqualified_quantity?: number }).unqualified_quantity) || Number(decision.body.unqualified_quantity) || 0);
      const channel = (created as { client_channel?: string | null }).client_channel;
      const labelKey = reportingClientChannelSourceI18nKey(channel);
      setSourceLabel(labelKey ? t(labelKey) : '');
      messageApi.success(t('app.kuaizhizao.workReporting.createSuccess'));
    } catch (error: unknown) {
      messageApi.error(errorText(error) || t('app.kuaizhizao.workReporting.createFailed'));
    } finally {
      setLoading(false);
    }
  };

  const submitBinding = async (bindingType: 'feeding' | 'discharging') => {
    if (recordId == null) return;
    const values = form.getFieldsValue();
    const decision = buildMaterialBindingBody({
      bindingType,
      materialId: material?.id ?? values.material_id,
      quantity: values.binding_quantity,
      materialCode: material?.mainCode || material?.code,
      materialName: material?.name,
    });
    if (!decision.submit) {
      messageApi.warning(decision.reason === 'missing-material' ? '请选择物料' : '绑定数量须大于 0');
      return;
    }
    setLoading(true);
    try {
      if (bindingType === 'feeding') {
        await materialBindingApi.createFeeding(String(recordId), decision.body);
      } else {
        await materialBindingApi.createDischarging(String(recordId), decision.body);
      }
      messageApi.success(t('app.kuaizhizao.workOrder.kioskBindSuccess'));
    } catch (error: unknown) {
      messageApi.error(errorText(error) || t('app.kuaizhizao.workOrder.kioskBindFailed'));
    } finally {
      setLoading(false);
    }
  };

  const submitScrap = async () => {
    if (recordId == null) return;
    const values = form.getFieldsValue();
    const decision = buildScrapBody({
      scrapQuantity: values.scrap_quantity,
      scrapReason: values.scrap_reason,
      scrapType: values.scrap_type,
      unqualifiedQuantity: recordUnqualified,
    });
    if (!decision.submit) {
      messageApi.warning(
        decision.reason === 'exceeds-unqualified'
          ? '报废数量不能超过不合格数量'
          : '请填写报废数量和原因',
      );
      return;
    }
    setLoading(true);
    try {
      await reportingApi.recordScrap(String(recordId), decision.body);
      messageApi.success(t('app.kuaizhizao.workReporting.scrapCreateSuccess'));
    } catch (error: unknown) {
      messageApi.error(errorText(error) || t('app.kuaizhizao.workReporting.scrapCreateFailed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <TouchScreenTemplate title="快捷报工">
      <Spin spinning={loading}>
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            qualified_quantity: 0,
            unqualified_quantity: 0,
            work_hours: 0,
            scrap_type: 'other',
            binding_quantity: 1,
          }}
        >
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            {workstationId == null ? <Alert type="warning" showIcon message="未绑定工位" /> : null}
            {mode === 'self' && !operator ? (
              <Alert type="warning" showIcon message="当前操作员未传入，本人报工不会提交" />
            ) : null}
            {operator && mode === 'self' ? (
              <Alert type="info" showIcon message={`当前操作员：${operator.name}`} />
            ) : null}
            {sourceLabel ? <Alert type="success" showIcon message={`报工来源：${sourceLabel}`} /> : null}

            <Card>
              <Radio.Group
                value={mode}
                onChange={(event) => setMode(event.target.value as StationReportMode)}
                buttonStyle="solid"
                size="large"
              >
                <Radio.Button value="self">本人</Radio.Button>
                <Radio.Button value="proxy" disabled={!canAssign}>代报</Radio.Button>
                <Radio.Button value="team">小组</Radio.Button>
              </Radio.Group>
            </Card>

            {mode === 'proxy' && canAssign ? (
              <UniUserSelect
                name="proxy_worker_uuid"
                label="生产人员"
                placeholder={t('app.kuaizhizao.workReporting.formProxyWorkerPlaceholder')}
                onChange={(_uuid, user) => {
                  const picked = user && !Array.isArray(user) ? user : null;
                  setProxyWorker(
                    picked?.id
                      ? { id: picked.id, name: String(picked.full_name || picked.username || '').trim() }
                      : null,
                  );
                }}
              />
            ) : null}

            {mode === 'team' ? (
              <Form.Item label={t('app.kuaizhizao.workReporting.producerModeTeam')}>
                <WorkGroupSelectDropdown
                  onWorkGroupPick={(group: WorkGroup | null) => {
                    if (!group?.id || !String(group.name || '').trim()) {
                      setTeam(null);
                      return;
                    }
                    setTeam({ id: Number(group.id), name: String(group.name).trim() });
                  }}
                />
              </Form.Item>
            ) : null}

            <Card title="工单">
              <Form.Item name="work_order_code" label="工单编号">
                <Input
                  size="large"
                  onPressEnter={() => {
                    void loadWorkOrder();
                  }}
                />
              </Form.Item>
              <Button size="large" onClick={() => { void loadWorkOrder(); }}>
                加载工单
              </Button>
              {workOrder ? (
                <div style={{ marginTop: 12 }}>
                  {workOrder.code} {workOrderDisplayName(workOrder)}
                </div>
              ) : null}
              <Space wrap style={{ marginTop: 12 }}>
                {operations.map((op) => (
                  <Button
                    key={String(op.operation_id)}
                    size="large"
                    type={op.operation_id === operation?.operation_id ? 'primary' : 'default'}
                    onClick={() => setOperation(op)}
                  >
                    {op.operation_name || op.operation_code}
                  </Button>
                ))}
              </Space>
            </Card>

            <Card>
              <Form.Item
                name="qualified_quantity"
                label={t('app.kuaizhizao.workReporting.colQualifiedQty')}
              >
                <InputNumber min={0} size="large" style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item
                name="unqualified_quantity"
                label={t('app.kuaizhizao.workReporting.colUnqualifiedQty')}
              >
                <InputNumber min={0} size="large" style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item
                name="work_hours"
                label={t('app.kuaizhizao.workReporting.colWorkHours')}
              >
                <InputNumber min={0} size="large" style={{ width: '100%' }} />
              </Form.Item>
              {Number(unqualified) > 0 ? (
                <Form.Item name="defect_reason" label="不良原因">
                  <Input size="large" />
                </Form.Item>
              ) : null}
              <Form.Item name="remarks" label="备注">
                <Input.TextArea rows={2} />
              </Form.Item>
              <Button type="primary" size="large" block onClick={() => { void submitReport(); }}>
                提交报工
              </Button>
            </Card>

            {recordId != null ? (
              <Card title={`报工记录 ${recordId}`}>
                <UniMaterialSelect
                  name="material_id"
                  label="物料"
                  onChange={(_id, picked) => {
                    setMaterial(picked && !Array.isArray(picked) ? picked : null);
                  }}
                />
                <Form.Item name="binding_quantity" label="数量">
                  <InputNumber min={0} size="large" style={{ width: '100%' }} />
                </Form.Item>
                <Space>
                  <Button size="large" onClick={() => { void submitBinding('feeding'); }}>上料</Button>
                  <Button size="large" onClick={() => { void submitBinding('discharging'); }}>下料</Button>
                </Space>
                <Form.Item name="scrap_quantity" label="报废数量" style={{ marginTop: 16 }}>
                  <InputNumber min={0} size="large" style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item name="scrap_type" label="报废类型">
                  <Radio.Group>
                    <Radio.Button value="process">过程</Radio.Button>
                    <Radio.Button value="material">物料</Radio.Button>
                    <Radio.Button value="quality">质量</Radio.Button>
                    <Radio.Button value="equipment">设备</Radio.Button>
                    <Radio.Button value="other">其他</Radio.Button>
                  </Radio.Group>
                </Form.Item>
                <Form.Item name="scrap_reason" label="报废原因">
                  <Input size="large" />
                </Form.Item>
                <Button size="large" onClick={() => { void submitScrap(); }}>报废</Button>
              </Card>
            ) : null}
          </Space>
        </Form>
      </Spin>
    </TouchScreenTemplate>
  );
}
