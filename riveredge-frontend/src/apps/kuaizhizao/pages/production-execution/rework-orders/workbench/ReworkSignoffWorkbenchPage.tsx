/**
 * 会签返工办理台：按客户节点链办理；已办部门可点开只读查看，方便协作。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Row,
  Space,
  Steps,
  Switch,
  Tabs,
} from 'antd';
import type { FormInstance } from 'antd/es/form';
import { useNavigate, useParams } from 'react-router-dom';
import { ListPageTemplate, ProjectWorkbenchToolbar } from '@/components/layout-templates';
import { MarkerTag } from '@/constants/statusBadges';
import { reworkOrderApi } from '../../../../services/production';
import { getApiErrorMessage } from '@/utils/errorHandler';

type SignoffStep = Record<string, unknown> & {
  dept_code?: string;
  dept_name?: string;
  status?: string;
  notes?: string;
  signer_name?: string;
  signed_at?: string;
};

type Detail = Record<string, unknown> & {
  id?: number;
  code?: string;
  status?: string;
  review_status?: string;
  rework_reason?: string;
  current_node_key?: string;
  current_node_name?: string;
  signoff_overdue?: boolean;
  extension_payload?: Record<string, unknown>;
  signoffs?: SignoffStep[];
  product_code?: string;
  product_name?: string;
  quantity?: number;
  need_warehouse_in?: boolean | null;
  no_scrap_confirmed?: boolean;
  material_reqs?: Array<Record<string, unknown>>;
  scrap_lines?: Array<Record<string, unknown>>;
  position_plans?: Array<Record<string, unknown>>;
};

const NODE_NOW: Record<string, string> = {
  quality: '现在轮到质量。填写返工要求提出，保存后点「交给下一部门」，进入 IE 排位策划。',
  rd: '现在轮到研发。填写目标型号和两型号差异，点「交给下一部门」，单据到质量。',
  ie_engineering:
    '现在轮到 IE 工程师。维护返工排位策划与材料报废（无报废须勾选确认），保存后点「交给下一部门」进入排位审核。',
  position_review:
    '现在轮到返工排位审核。生产经理、质量经理、PQC 主管分别在三个分区保存填报，全部完成后点「交给下一部门」。',
  manufacturing:
    '现在轮到生产。填写返工工序、排位和报废（没有报废就打开「无物料报废」），点「交给下一部门」，单据到采购。',
  purchasing: '现在轮到采购。填写物料和到位时间，点「交给下一部门」，单据进入审核批准。',
  leader: '现在轮到审核批准（运营副总）。点「交给下一部门」送审。审批通过后，再点一次，单据到计划。',
  planning: '现在轮到计划。填写排产计划说明，点「交给下一部门」，进入返工执行。',
  rework_exec:
    '现在轮到返工执行。仓库、生产、质量 PQC 三个分区分别保存后，点「交给下一部门」进入完工入库。',
  warehouse: '现在轮到仓库。填写确认说明，点「交给下一部门」，单据到生产入库。',
  manufacturing_exec: '现在轮到完工入库。确认是否入库后点「交给下一部门」，单据到财务。',
  finance: '现在轮到财务。点「交给下一部门」后单据关闭。',
  closed: '这张单已关闭，只可查看。左侧点已办部门可看各节点填写内容。',
};

const NODE_FIELDS: Record<string, Array<{ key: string; label: string; area?: boolean }>> = {
  rd: [
    { key: 'target_product_code', label: '目标型号' },
    { key: 'rd_material_diff', label: '型号差异说明', area: true },
  ],
  quality: [{ key: 'quality_requirements_text', label: '返工要求', area: true }],
  manufacturing: [{ key: 'manufacturing_process_notes', label: '返工工序', area: true }],
  planning: [{ key: 'plan_schedule_notes', label: '排产计划说明', area: true }],
  warehouse: [{ key: 'warehouse_confirm_notes', label: '仓库确认', area: true }],
  prod_mgr: [{ key: 'prod_mgr_signoff_notes', label: '生产经理会签意见', area: true }],
  quality_mgr: [{ key: 'quality_mgr_signoff_notes', label: '质量经理会签意见', area: true }],
  pqc: [{ key: 'pqc_signoff_notes', label: 'PQC 主管会签意见', area: true }],
  warehouse_exec: [{ key: 'warehouse_confirm_notes', label: '仓库确认说明', area: true }],
  production_exec: [{ key: 'production_exec_notes', label: '生产主管执行说明', area: true }],
  quality_pqc_exec: [{ key: 'quality_pqc_exec_notes', label: '质量 PQC 执行说明', area: true }],
};

const MULTI_SECTION: Record<string, Array<{ key: string; label: string; fieldGroup: string }>> = {
  position_review: [
    { key: 'prod_mgr', label: '生产部经理', fieldGroup: 'prod_mgr' },
    { key: 'quality_mgr', label: '质量部经理', fieldGroup: 'quality_mgr' },
    { key: 'pqc', label: 'PQC 主管', fieldGroup: 'pqc' },
  ],
  rework_exec: [
    { key: 'warehouse', label: '仓库主管', fieldGroup: 'warehouse_exec' },
    { key: 'production', label: '生产主管', fieldGroup: 'production_exec' },
    { key: 'quality_pqc', label: '质量 PQC 主管', fieldGroup: 'quality_pqc_exec' },
  ],
};

function applyDetailToForm(form: FormInstance, row: Detail) {
  const payload = row.extension_payload || {};
  const plan = (row.position_plans || [])[0] || {};
  const scrap = (row.scrap_lines || [])[0] || {};
  const mat = (row.material_reqs || [])[0] || {};
  form.setFieldsValue({
    ...payload,
    need_warehouse_in: row.need_warehouse_in,
    no_scrap_confirmed: Boolean(row.no_scrap_confirmed),
    position_sequence: plan.sequence ?? 1,
    station_name: plan.station_name || '',
    scrap_material_code: scrap.material_code || '',
    scrap_qty: scrap.qty ?? 0,
    scrap_reason: scrap.scrap_reason || '',
    buy_material_code: mat.material_code || '',
    buy_material_name: mat.material_name || '',
    buy_qty: mat.qty ?? row.quantity ?? 1,
    required_at: mat.required_at || '',
  });
}

const ReworkSignoffWorkbenchPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [form] = Form.useForm();
  const [assigneeId, setAssigneeId] = useState<number | null>(null);
  const [notes, setNotes] = useState('');
  const [viewingNode, setViewingNode] = useState('');
  const [activeSubSection, setActiveSubSection] = useState('');

  const load = useCallback(async () => {
    if (!id) return;
    const row = (await reworkOrderApi.get(id)) as Detail;
    setDetail(row);
    applyDetailToForm(form, row);
    const current = String(row.current_node_key || '');
    if (current && current !== 'closed') {
      setViewingNode(current);
    } else {
      const signed = (row.signoffs || []).filter((s) => String(s.status) === 'signed');
      const last = signed[signed.length - 1];
      setViewingNode(String(last?.dept_code || 'sales'));
    }
  }, [form, id]);

  useEffect(() => {
    void load().catch((e) => message.error(getApiErrorMessage(e)));
  }, [load, message]);

  const currentNode = String(detail?.current_node_key || '');
  const chainVersion = Number(
    (detail?.extension_payload?.signoff_flow as Record<string, unknown> | undefined)?.chain_version || 1,
  );
  const steps = useMemo(() => detail?.signoffs || [], [detail]);
  const viewing = viewingNode || currentNode;
  const multiSections = MULTI_SECTION[viewing] || [];
  const subSection =
    activeSubSection ||
    (multiSections[0]?.key ?? '');
  const fields =
  multiSections.length > 0
    ? NODE_FIELDS[MULTI_SECTION[viewing]?.find((s) => s.key === subSection)?.fieldGroup || ''] || []
    : NODE_FIELDS[viewing] || [];
  const canEdit = Boolean(viewing) && viewing === currentNode && currentNode !== 'closed';
  const viewingStep = steps.find((s) => String(s.dept_code) === viewing);
  const viewingName = String(
    viewingStep?.dept_name || detail?.current_node_name || viewing || '',
  );
  const currentName = String(detail?.current_node_name || currentNode || '草稿');

  const savePayload = async () => {
    if (!detail?.id || !canEdit) return;
    const values = form.getFieldsValue();
    const payload = {
      ...(detail.extension_payload || {}),
      target_product_code: values.target_product_code,
      rd_material_diff: values.rd_material_diff,
      quality_requirements_text: values.quality_requirements_text,
      manufacturing_process_notes: values.manufacturing_process_notes,
      plan_schedule_notes: values.plan_schedule_notes,
      warehouse_confirm_notes: values.warehouse_confirm_notes,
      prod_mgr_signoff_notes: values.prod_mgr_signoff_notes,
      quality_mgr_signoff_notes: values.quality_mgr_signoff_notes,
      pqc_signoff_notes: values.pqc_signoff_notes,
      production_exec_notes: values.production_exec_notes,
      quality_pqc_exec_notes: values.quality_pqc_exec_notes,
    };
    const body: Record<string, unknown> = { extension_payload: payload };
    if (currentNode === 'manufacturing_exec') {
      body.need_warehouse_in = Boolean(values.need_warehouse_in);
    }
    if (currentNode === 'ie_engineering' || (chainVersion < 2 && currentNode === 'manufacturing')) {
      body.position_plans = [
        {
          sequence: values.position_sequence || 1,
          station_name: values.station_name || '工位',
          planned_qty: detail.quantity || 1,
        },
      ];
      if (values.no_scrap_confirmed) {
        body.no_scrap_confirmed = true;
        body.scrap_lines = [];
      } else {
        body.no_scrap_confirmed = false;
        body.scrap_lines = [
          {
            material_code: values.scrap_material_code || detail.product_code,
            material_name: values.scrap_material_name || detail.product_name,
            qty: values.scrap_qty || 1,
            scrap_reason: values.scrap_reason || '返工报废',
          },
        ];
      }
    }
    if (currentNode === 'purchasing') {
      body.material_reqs = [
        {
          line_no: 1,
          material_code: values.buy_material_code || detail.product_code,
          material_name: values.buy_material_name || detail.product_name,
          qty: values.buy_qty || detail.quantity || 1,
          required_at: values.required_at,
        },
      ];
    }
    await reworkOrderApi.update(String(detail.id), body);
  };

  const alertDescription = (() => {
    if (!currentNode) {
      return '这张单还是草稿。请回列表，勾选后点工具栏「提交」，或在该行点「提交」。提交后才会按部门顺序往下走。';
    }
    if (!canEdit) {
      return `正在查看「${viewingName}」已填内容（只读），方便协作。当前办理在「${currentName}」，点左侧「当前」可回去填写。`;
    }
    return NODE_NOW[currentNode] || '填写本部门内容后，点「交给下一部门」。';
  })();

  const saveCurrentSection = async () => {
    if (!detail?.id || !canEdit) return;
    await savePayload();
    if (multiSections.length && subSection) {
      await reworkOrderApi.saveSignoffSection(Number(detail.id), currentNode, subSection);
    }
  };

  return (
    <ListPageTemplate>
      <Space orientation="vertical" size="middle" className="project-workbench-shell" style={{ width: '100%' }}>
      <ProjectWorkbenchToolbar
        backLabel="返回列表"
        onBack={() => navigate('/apps/kuaizhizao/production-execution/rework-orders')}
        title={`${detail?.code || ''} ${detail?.product_name || ''}`}
        status={
          <span>
            {currentName}
            {detail?.signoff_overdue ? '（超当日）' : ''}
          </span>
        }
        actions={
          <Space>
            <Button
              disabled={!canEdit}
              onClick={async () => {
                try {
                  await saveCurrentSection();
                  message.success(multiSections.length ? '本分区已保存' : '已保存');
                  await load();
                } catch (e) {
                  message.error(getApiErrorMessage(e));
                }
              }}
            >
              {multiSections.length ? '保存本分区' : '保存'}
            </Button>
            <Button
              type="primary"
              disabled={!canEdit}
              onClick={async () => {
                try {
                  await saveCurrentSection();
                  await reworkOrderApi.completeSignoff(Number(detail?.id), notes);
                  message.success('已办理当前节点');
                  setNotes('');
                  await load();
                } catch (e) {
                  message.error(getApiErrorMessage(e));
                }
              }}
            >
              交给下一部门
            </Button>
            <Button
              disabled={!canEdit || currentNode === 'sales'}
              onClick={async () => {
                if (!notes.trim()) {
                  message.error('退回须填写原因');
                  return;
                }
                try {
                  await reworkOrderApi.returnSignoff(Number(detail?.id), notes);
                  message.success('已退回上一节点');
                  setNotes('');
                  await load();
                } catch (e) {
                  message.error(getApiErrorMessage(e));
                }
              }}
            >
              退回
            </Button>
          </Space>
        }
      />
      <Card size="small" className="project-workbench-overview">
        <Row gutter={[24, 16]}>
          <Col xs={24} md={16}>
            <Descriptions column={{ xs: 1, sm: 2 }} size="small">
              <Descriptions.Item label="产品线">
                {String((detail?.extension_payload as Record<string, unknown>)?.product_line_code || '—')}
              </Descriptions.Item>
              <Descriptions.Item label="路径">
                {String((detail?.extension_payload as Record<string, unknown>)?.rework_path_type || 'aa').toUpperCase()}
                {' '}
                {chainVersion >= 2 ? '白板新链 v2' : '旧链 v1（在途）'}
              </Descriptions.Item>
              <Descriptions.Item label="当前节点">{currentName}</Descriptions.Item>
              <Descriptions.Item label="审核状态">{String(detail?.review_status || '—')}</Descriptions.Item>
            </Descriptions>
          </Col>
        </Row>
      </Card>
      {chainVersion < 2 ? (
        <Alert
          showIcon
          type="warning"
          style={{ marginTop: 12 }}
          title="此单走旧九步会签链"
          description="在升级前已提交的返工单会继续显示「生产 / 仓库」等旧节点；新提交的单据会走白板新链（IE工程师、返工排位审核、返工执行三分区）。若要验收 v2，请新建一张会签返工单并点「提交」后再进入办理台。请确认本地后端已重启以加载最新会签编排。"
        />
      ) : null}
      <Alert
        showIcon
        style={{ marginTop: 12 }}
        type={canEdit ? 'info' : currentNode ? 'warning' : 'warning'}
        title={
          canEdit
            ? `当前：${currentName}`
            : currentNode
              ? `查看：${viewingName}`
              : '尚未提交'
        }
        description={alertDescription}
      />
      <Steps
        style={{ marginTop: 12 }}
        size="small"
        current={Math.max(
          0,
          steps.findIndex((step) => String(step.dept_code) === currentNode),
        )}
        items={steps.map((step) => ({
          title: String(step.dept_name || step.dept_code),
          status:
            String(step.status) === 'signed'
              ? 'finish'
              : String(step.dept_code) === currentNode
                ? 'process'
                : 'wait',
        }))}
        onChange={(idx) => {
          const step = steps[idx];
          if (!step) return;
          const code = String(step.dept_code || '');
          const signed = String(step.status) === 'signed';
          const isCurrent = code === currentNode;
          if (signed || isCurrent || currentNode === 'closed') {
            setViewingNode(code);
            setActiveSubSection(MULTI_SECTION[code]?.[0]?.key || '');
          }
        }}
      />
      <div style={{ display: 'grid', gridTemplateColumns: '240px 1fr', gap: 16, marginTop: 12 }}>
        <Card size="small" title="审批顺序">
          {steps.map((step) => {
            const code = String(step.dept_code || '');
            const signed = String(step.status) === 'signed';
            const isCurrent = code === currentNode;
            const selected = code === viewing;
            const clickable = signed || isCurrent || currentNode === 'closed';
            const badge = signed
              ? { text: '已办', color: 'success' as const }
              : isCurrent
                ? { text: '当前', color: 'processing' as const }
                : { text: '待办', color: 'default' as const };
            return (
              <div
                key={code}
                role={clickable ? 'button' : undefined}
                tabIndex={clickable ? 0 : undefined}
                onClick={() => {
                  if (clickable) {
                    setViewingNode(code);
                    setActiveSubSection(MULTI_SECTION[code]?.[0]?.key || '');
                  }
                }}
                onKeyDown={(e) => {
                  if (clickable && (e.key === 'Enter' || e.key === ' ')) {
                    e.preventDefault();
                    setViewingNode(code);
                  }
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 8,
                  padding: '6px 8px',
                  margin: '0 -8px',
                  borderRadius: 6,
                  cursor: clickable ? 'pointer' : 'default',
                  border: selected ? '1px solid rgba(0, 0, 0, 0.15)' : '1px solid transparent',
                  background: selected ? '#f7f8fa' : 'transparent',
                }}
              >
                <span>{String(step.dept_name || step.dept_code)}</span>
                <MarkerTag color={badge.color}>{badge.text}</MarkerTag>
              </div>
            );
          })}
        </Card>
        <Card
          size="small"
          title={canEdit ? '本节点' : `已办查看：${viewingName}`}
          extra={
            !canEdit && currentNode && currentNode !== 'closed' ? (
              <Button type="link" size="small" onClick={() => setViewingNode(currentNode)}>
                回到当前办理
              </Button>
            ) : null
          }
        >
          <Descriptions column={2} size="small">
            <Descriptions.Item label="型号">{String(detail?.product_code || '')}</Descriptions.Item>
            <Descriptions.Item label="数量">{String(detail?.quantity ?? '')}</Descriptions.Item>
            {viewing === 'sales' ? (
              <Descriptions.Item label="返工原因" span={2}>
                {String(detail?.rework_reason || '')}
              </Descriptions.Item>
            ) : null}
            {viewingStep?.signer_name ? (
              <Descriptions.Item label="办理人">
                {String(viewingStep.signer_name)}
              </Descriptions.Item>
            ) : null}
            {viewingStep?.signed_at ? (
              <Descriptions.Item label="办理时间">
                {String(viewingStep.signed_at)}
              </Descriptions.Item>
            ) : null}
            {viewingStep?.notes ? (
              <Descriptions.Item label="办理说明" span={2}>
                {String(viewingStep.notes)}
              </Descriptions.Item>
            ) : null}
          </Descriptions>
          {multiSections.length > 0 ? (
            <Tabs
              style={{ marginTop: 8 }}
              activeKey={subSection}
              onChange={(key) => setActiveSubSection(key)}
              items={multiSections.map((s) => ({ key: s.key, label: s.label }))}
            />
          ) : null}
          <Form form={form} layout="vertical" style={{ marginTop: 12 }} disabled={!canEdit}>
            {fields.map((field) => (
              <Form.Item key={field.key} name={field.key} label={field.label}>
                {field.area ? <Input.TextArea rows={3} /> : <Input />}
              </Form.Item>
            ))}
            {viewing === 'ie_engineering' || (chainVersion < 2 && viewing === 'manufacturing') ? (
              <>
                <Form.Item name="position_sequence" label="排位工序序号">
                  <InputNumber min={1} />
                </Form.Item>
                <Form.Item name="station_name" label="工位">
                  <Input />
                </Form.Item>
                <Form.Item name="no_scrap_confirmed" label="无物料报废" valuePropName="checked">
                  <Switch />
                </Form.Item>
                <Form.Item name="scrap_material_code" label="报废料号">
                  <Input />
                </Form.Item>
                <Form.Item name="scrap_qty" label="报废数量">
                  <InputNumber min={0} />
                </Form.Item>
                <Form.Item name="scrap_reason" label="报废原因">
                  <Input />
                </Form.Item>
              </>
            ) : null}
            {viewing === 'purchasing' ? (
              <>
                <Form.Item name="buy_material_code" label="物料代码">
                  <Input />
                </Form.Item>
                <Form.Item name="buy_qty" label="需求数量">
                  <InputNumber min={0} />
                </Form.Item>
                <Form.Item
                  name="required_at"
                  label="物料到位时间"
                  rules={canEdit ? [{ required: true }] : undefined}
                >
                  <Input placeholder="YYYY-MM-DD HH:mm:ss" />
                </Form.Item>
              </>
            ) : null}
            {viewing === 'manufacturing_exec' ? (
              <Form.Item name="need_warehouse_in" label="返工是否入库" valuePropName="checked">
                <Switch />
              </Form.Item>
            ) : null}
            {viewing === 'leader' ? (
              <Descriptions size="small" column={1}>
                <Descriptions.Item label="审核状态">
                  {String(detail?.review_status || '')}
                </Descriptions.Item>
              </Descriptions>
            ) : null}
            {viewing === 'finance' && !fields.length ? (
              <div style={{ color: 'rgba(0,0,0,0.45)' }}>财务节点无额外表单字段，确认后关闭单据。</div>
            ) : null}
          </Form>
          {canEdit ? (
            <>
              <Space>
                <InputNumber
                  placeholder="办理人用户 ID"
                  value={assigneeId ?? undefined}
                  onChange={(v) => setAssigneeId(typeof v === 'number' ? v : null)}
                />
                <Button
                  disabled={!assigneeId || !currentNode}
                  onClick={async () => {
                    try {
                      await reworkOrderApi.assignSignoff(
                        Number(detail?.id),
                        currentNode,
                        Number(assigneeId),
                      );
                      message.success('已指定办理人并提醒');
                    } catch (e) {
                      message.error(getApiErrorMessage(e));
                    }
                  }}
                >
                  指定本节点办理人
                </Button>
              </Space>
              <Input.TextArea
                style={{ marginTop: 12 }}
                rows={2}
                placeholder="办理说明 / 退回原因"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </>
          ) : null}
        </Card>
      </div>
      </Space>
    </ListPageTemplate>
  );
};

export default ReworkSignoffWorkbenchPage;
