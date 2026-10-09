import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
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
import { TouchScreenTemplate } from '../../../../components/layout-templates/hmi';
import { touchButtonProps } from '../../../../components/touch-terminal';
import { HMI_TOUCH } from '../../../../theme/hmi';
import { UniMaterialSelect } from '../../../../components/uni-material-select';
import { reportingClientChannelSourceI18nKey, STATION_ENTRY_PATH } from '../../../../utils/clientChannel';
import { convertProductionInputToBaseQty } from '../../../../utils/materialScenarioUnit';
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
import { useStationWriteEnabled } from '../entry/session';

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
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const workstationId = resolveWorkstationId(boundWorkstationId, searchParams.get('workstationId'));
  const selectedWorkOrderCode = searchParams.get('workOrderCode')?.trim() ?? '';
  const stationEntryPath =
    workstationId == null
      ? STATION_ENTRY_PATH
      : `${STATION_ENTRY_PATH}?workstationId=${workstationId}`;
  // 未确认操作员时可查看页面，报工/上下料/报废提交禁用
  const writeEnabled = useStationWriteEnabled();

  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<StationReportMode>('self');
  const [workOrder, setWorkOrder] = useState<WorkOrderRow | null>(null);
  const [operations, setOperations] = useState<OperationRow[]>([]);
  const [operation, setOperation] = useState<OperationRow | null>(null);
  const [team, setTeam] = useState<{ id: number; name: string } | null>(null);
  const [recordId, setRecordId] = useState<number | null>(null);
  const [recordUnqualified, setRecordUnqualified] = useState<number>(0);
  const [sourceLabel, setSourceLabel] = useState<string>('');
  const [material, setMaterial] = useState<Material | null>(null);
  const loadWorkOrderSeq = useRef(0);

  const unqualified = Form.useWatch('unqualified_quantity', form);

  // 换工单时清除上一张报工的提交态，避免后续上料/下料/报废误绑到旧报工记录
  const clearSubmissionState = () => {
    setRecordId(null);
    setRecordUnqualified(0);
    setSourceLabel('');
    setMaterial(null);
    form.setFieldsValue({
      qualified_quantity: 0,
      unqualified_quantity: 0,
      work_hours: 0,
      defect_reason: undefined,
      remarks: undefined,
      material_id: undefined,
      binding_quantity: 1,
      scrap_quantity: undefined,
      scrap_type: 'other',
      scrap_reason: undefined,
    });
  };

  const loadWorkOrder = async (selectedCode?: string) => {
    if (loading && !selectedCode) return;
    const code = String(selectedCode ?? form.getFieldValue('work_order_code') ?? '').trim();
    const requestSeq = ++loadWorkOrderSeq.current;
    setWorkOrder(null);
    setOperations([]);
    setOperation(null);
    clearSubmissionState();
    if (!code) {
      messageApi.warning('请输入工单编号');
      return;
    }
    setLoading(true);
    try {
      const raw = await workOrderApi.list({ code });
      const rows = rowsFromListResponse<WorkOrderRow>(raw);
      const matched = rows.find((row) => String(row.code ?? '').trim() === code);
      if (requestSeq !== loadWorkOrderSeq.current) return;
      if (!matched?.id) {
        messageApi.error('未找到该工单');
        return;
      }
      const opRaw = await workOrderApi.getOperations(String(matched.id));
      if (requestSeq !== loadWorkOrderSeq.current) return;
      const list = rowsFromListResponse<OperationRow>(opRaw);
      setWorkOrder(matched);
      setOperations(list);
      const pending = list.find((op) => op.status !== 'completed') ?? list[0] ?? null;
      setOperation(pending);
    } catch (error: unknown) {
      if (requestSeq === loadWorkOrderSeq.current) {
        messageApi.error(errorText(error) || '加载工单失败');
      }
    } finally {
      if (requestSeq === loadWorkOrderSeq.current) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    if (!selectedWorkOrderCode) return;
    form.setFieldValue('work_order_code', selectedWorkOrderCode);
    void loadWorkOrder(selectedWorkOrderCode);
  }, [selectedWorkOrderCode]);

  const submitReport = async () => {
    if (loading || !writeEnabled) return;
    const values = form.getFieldsValue();
    const qualifiedDisplay = Number(values.qualified_quantity) || 0;
    const unqualifiedDisplay = Number(values.unqualified_quantity) || 0;
    const workTime = resolveReportingWorkTimeForSubmit({
      work_hours: values.work_hours,
    });
    const decision = buildQuickReportingBody({
      mode,
      workstationId,
      operator,
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
        { stationOperatorSession: true },
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
    if (recordId == null || loading || !writeEnabled) return;
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
        await materialBindingApi.createFeeding(String(recordId), decision.body, {
          stationOperatorSession: true,
        });
      } else {
        await materialBindingApi.createDischarging(String(recordId), decision.body, {
          stationOperatorSession: true,
        });
      }
      messageApi.success(t('app.kuaizhizao.workOrder.kioskBindSuccess'));
    } catch (error: unknown) {
      messageApi.error(errorText(error) || t('app.kuaizhizao.workOrder.kioskBindFailed'));
    } finally {
      setLoading(false);
    }
  };

  const submitScrap = async () => {
    if (recordId == null || loading || !writeEnabled) return;
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
      await reportingApi.recordScrap(String(recordId), decision.body, {
        stationOperatorSession: true,
      });
      messageApi.success(t('app.kuaizhizao.workReporting.scrapCreateSuccess'));
    } catch (error: unknown) {
      messageApi.error(errorText(error) || t('app.kuaizhizao.workReporting.scrapCreateFailed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <TouchScreenTemplate title="快捷报工">
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Button
          {...touchButtonProps({ size: 'header', style: { height: HMI_TOUCH.HEADER_BTN_HEIGHT } })}
          onClick={() => navigate(stationEntryPath)}
        >
          返回工位入口
        </Button>
      </div>
      <Spin spinning={loading} style={{ display: 'block', flex: 1, minHeight: 0 }}>
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
          <div className="hmi-station-pane" style={{ flex: 1 }}>
            {workstationId == null ? <Alert type="warning" showIcon message="未绑定工位" /> : null}
            {mode === 'self' && !operator ? (
              <Alert type="warning" showIcon message="当前操作员未传入，本人报工不会提交" />
            ) : null}
            {operator && mode === 'self' ? (
              <Alert type="info" showIcon message={`当前操作员：${operator.name}`} />
            ) : null}
            {sourceLabel ? <Alert type="success" showIcon message={`报工来源：${sourceLabel}`} /> : null}
            {!writeEnabled ? (
              <Alert
                type="info"
                showIcon
                message="未确认操作员：可查看页面，报工、上下料与报废提交不可用"
              />
            ) : null}

            <div className="hmi-station-split hmi-station-split--balanced">
              <div className="hmi-station-pane">
                <Card title="报工对象">
                  <Radio.Group
                    value={mode}
                    onChange={(event) => setMode(event.target.value as StationReportMode)}
                    buttonStyle="solid"
                    size="large"
                  >
                    <Radio.Button value="self">本人</Radio.Button>
                    <Radio.Button value="team">小组</Radio.Button>
                  </Radio.Group>
                  {mode === 'team' ? (
                    <Form.Item
                      label={t('app.kuaizhizao.workReporting.producerModeTeam')}
                      style={{ marginTop: 16, marginBottom: 0 }}
                    >
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
                </Card>

                <Card title="工单">
                  <Form.Item name="work_order_code" label="工单编号">
                    <Input
                      size="large"
                      disabled={loading}
                      style={{ minHeight: HMI_TOUCH.INPUT_HEIGHT, fontSize: 24 }}
                      onChange={(event) => {
                        if (workOrder && event.target.value.trim() !== String(workOrder.code ?? '').trim()) {
                          setWorkOrder(null);
                          setOperations([]);
                          setOperation(null);
                          clearSubmissionState();
                        }
                      }}
                      onPressEnter={() => {
                        void loadWorkOrder();
                      }}
                    />
                  </Form.Item>
                  <Button
                    {...touchButtonProps({ variant: 'primary', size: 'action' })}
                    disabled={loading}
                    onClick={() => { void loadWorkOrder(); }}
                  >
                    加载工单
                  </Button>
                  {workOrder ? (
                    <div style={{ marginTop: 12, fontSize: 18 }}>
                      {workOrder.code} {workOrderDisplayName(workOrder)}
                    </div>
                  ) : null}
                  <Space wrap style={{ marginTop: 12 }}>
                    {operations.map((op) => (
                      <Button
                        key={String(op.operation_id)}
                        {...touchButtonProps({
                          variant: op.operation_id === operation?.operation_id ? 'primary' : 'default',
                          size: 'chip',
                        })}
                        onClick={() => setOperation(op)}
                      >
                        {op.operation_name || op.operation_code}
                      </Button>
                    ))}
                  </Space>
                </Card>
              </div>

              <div className="hmi-station-pane">
                <Card title="数量与提交">
                  <Form.Item
                    name="qualified_quantity"
                    label={t('app.kuaizhizao.workReporting.colQualifiedQty')}
                  >
                    <InputNumber min={0} size="large" style={{ width: '100%', minHeight: HMI_TOUCH.INPUT_HEIGHT }} />
                  </Form.Item>
                  <Form.Item
                    name="unqualified_quantity"
                    label={t('app.kuaizhizao.workReporting.colUnqualifiedQty')}
                  >
                    <InputNumber min={0} size="large" style={{ width: '100%', minHeight: HMI_TOUCH.INPUT_HEIGHT }} />
                  </Form.Item>
                  <Form.Item
                    name="work_hours"
                    label={t('app.kuaizhizao.workReporting.colWorkHours')}
                  >
                    <InputNumber min={0} size="large" style={{ width: '100%', minHeight: HMI_TOUCH.INPUT_HEIGHT }} />
                  </Form.Item>
                  {Number(unqualified) > 0 ? (
                    <Form.Item name="defect_reason" label="不良原因">
                      <Input size="large" style={{ minHeight: HMI_TOUCH.INPUT_HEIGHT }} />
                    </Form.Item>
                  ) : null}
                  <Form.Item name="remarks" label="备注">
                    <Input.TextArea rows={2} />
                  </Form.Item>
                  <Button
                    {...touchButtonProps({ variant: 'primary', size: 'primary' })}
                    block
                    disabled={!writeEnabled}
                    onClick={() => { void submitReport(); }}
                  >
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
                      <InputNumber min={0} size="large" style={{ width: '100%', minHeight: HMI_TOUCH.INPUT_HEIGHT }} />
                    </Form.Item>
                    <Space wrap>
                      <Button {...touchButtonProps({ size: 'action' })} disabled={!writeEnabled} onClick={() => { void submitBinding('feeding'); }}>上料</Button>
                      <Button {...touchButtonProps({ size: 'action' })} disabled={!writeEnabled} onClick={() => { void submitBinding('discharging'); }}>下料</Button>
                    </Space>
                    <Form.Item name="scrap_quantity" label="报废数量" style={{ marginTop: 16 }}>
                      <InputNumber min={0} size="large" style={{ width: '100%', minHeight: HMI_TOUCH.INPUT_HEIGHT }} />
                    </Form.Item>
                    <Form.Item name="scrap_type" label="报废类型">
                      <Radio.Group size="large">
                        <Radio.Button value="process">过程</Radio.Button>
                        <Radio.Button value="material">物料</Radio.Button>
                        <Radio.Button value="quality">质量</Radio.Button>
                        <Radio.Button value="equipment">设备</Radio.Button>
                        <Radio.Button value="other">其他</Radio.Button>
                      </Radio.Group>
                    </Form.Item>
                    <Form.Item name="scrap_reason" label="报废原因">
                      <Input size="large" style={{ minHeight: HMI_TOUCH.INPUT_HEIGHT }} />
                    </Form.Item>
                    <Button {...touchButtonProps({ variant: 'danger', size: 'action' })} disabled={!writeEnabled} onClick={() => { void submitScrap(); }}>报废</Button>
                  </Card>
                ) : null}
              </div>
            </div>
          </div>
        </Form>
      </Spin>
    </TouchScreenTemplate>
  );
}
