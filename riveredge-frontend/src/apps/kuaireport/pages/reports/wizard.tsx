/**
 * 新建 / 编辑自制报表。三步：基本信息、数据集与参数、图表预览。
 * 系统报表只读，不从这里保存。归属「系统报表」只有租户管理员能选。
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Card,
  Empty,
  Input,
  Radio,
  Select,
  Space,
  Steps,
  Switch,
  Tag,
  Typography,
  App,
} from 'antd';
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons';
import { useNavigate, useParams } from 'react-router-dom';
import { getDatasetList } from '../../../../services/dataset';
import { useCurrentUser } from '../../../../hooks/useCurrentUser';
import { isAdminBypass } from '../../../../utils/permission';
import type { ReportConfigSchema, ReportParameterConfig } from '../../../../components/uni-report';
import { ChartCanvas, DrillDrawer, axisHint } from './ChartPanel';
import {
  createWizardReport,
  detectDatasetFields,
  getReport,
  previewDataset,
  updateWizardReport,
  type WizardSaveBody,
} from './api';

const CLASSIFIES = ['销售', '采购', '生产', '质量', '仓库', '设备', '财务', '综合', '库存', '物料', '未分类'];

const CHARTS: Array<{
  value: string;
  label: string;
  slots: Array<'category' | 'value'>;
  categoryLabel?: string;
  valueLabel?: string;
  tip?: string;
}> = [
  { value: 'table', label: '基础表格', slots: [], tip: '表格将展示数据集中的全部可见字段，无需配置坐标轴。' },
  { value: 'line', label: '折线图', slots: ['category', 'value'] },
  { value: 'bar', label: '柱状图', slots: ['category', 'value'] },
  { value: 'column', label: '柱状图（垂直）', slots: ['category', 'value'] },
  { value: 'pie', label: '饼图', slots: ['category', 'value'], categoryLabel: '分类字段', valueLabel: '数值字段' },
  { value: 'area', label: '面积图', slots: ['category', 'value'] },
  { value: 'scatter', label: '散点图', slots: ['category', 'value'], categoryLabel: 'X轴字段', valueLabel: 'Y轴字段' },
  { value: 'card', label: '指标卡', slots: ['value'], valueLabel: '数值字段' },
];

const PARAM_TYPES = [
  { value: 'text', label: '文本' },
  { value: 'number', label: '数字' },
  { value: 'date', label: '日期' },
  { value: 'dateRange', label: '日期范围' },
  { value: 'select', label: '下拉' },
];

interface FieldTag {
  field: string;
  label: string;
}

interface DatasetOption {
  uuid: string;
  code: string;
  name: string;
}

function nextParamKey(parameters: ReportParameterConfig[]): string {
  const used = new Set(parameters.map((item) => item.key));
  let index = parameters.length + 1;
  while (used.has(`param_${index}`)) index += 1;
  return `param_${index}`;
}

export default function ReportWizardPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const params = useParams();
  const reportId = params.reportId ? Number(params.reportId) : undefined;
  const admin = isAdminBypass(useCurrentUser());
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [readOnly, setReadOnly] = useState(false);
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [classify, setClassify] = useState('未分类');
  const [category, setCategory] = useState<'custom' | 'system'>('custom');
  const [description, setDescription] = useState('');
  const [datasets, setDatasets] = useState<DatasetOption[]>([]);
  const [datasetUuid, setDatasetUuid] = useState<string>();
  const [fields, setFields] = useState<FieldTag[]>([]);
  const [detecting, setDetecting] = useState(false);
  const [parameters, setParameters] = useState<ReportParameterConfig[]>([]);
  const [drill, setDrill] = useState(false);
  const [chartType, setChartType] = useState('table');
  const [xField, setXField] = useState<string>();
  const [yField, setYField] = useState<string>();
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [previewing, setPreviewing] = useState(false);
  const [drillValue, setDrillValue] = useState<string | null>(null);

  const chart = CHARTS.find((item) => item.value === chartType) || CHARTS[0];
  const dataset = datasets.find((item) => item.uuid === datasetUuid);

  useEffect(() => {
    getDatasetList({ page: 1, page_size: 100, is_active: true })
      .then((res) => {
        setDatasets(
          (res.items || []).map((item) => ({ uuid: item.uuid, code: item.code, name: item.name })),
        );
      })
      .catch((err: Error) => message.error(err.message || '数据集加载失败'));
  }, [message]);

  useEffect(() => {
    if (!reportId) return;
    let cancelled = false;
    getReport(reportId)
      .then((row) => {
        if (cancelled) return;
        setCode(row.code);
        setName(row.name);
        setClassify(row.classify || '未分类');
        setCategory(row.category === 'system' ? 'system' : 'custom');
        setDescription(row.description || '');
        setReadOnly(Boolean(row.is_system) || row.category === 'system');
        const config = row.report_config || {};
        setDatasetUuid(config.dataset_uuid);
        setChartType(config.chart_type || 'table');
        setParameters(config.parameters || []);
        setDrill(Boolean(config.interaction?.drilldown?.enabled));
        const saved = config.fields || [];
        setFields(saved.map((field) => ({ field: field.field, label: field.label || field.field })));
        setXField(saved.find((field) => field.x_axis)?.field);
        setYField(saved.find((field) => field.y_axis)?.field);
      })
      .catch((err: Error) => message.error(err.message || '报表加载失败'));
    return () => {
      cancelled = true;
    };
  }, [message, reportId]);

  const detect = async (uuid = datasetUuid) => {
    if (!uuid) {
      message.warning('请选择数据集');
      return;
    }
    setDetecting(true);
    try {
      const res = await detectDatasetFields(uuid);
      const next = (res.fields || []).map((field) => ({
        field: field.field,
        label: field.label || field.field,
      }));
      setFields(next);
      setXField((current) => (current && next.some((field) => field.field === current) ? current : undefined));
      setYField((current) => (current && next.some((field) => field.field === current) ? current : undefined));
    } catch (err) {
      message.error(err instanceof Error ? err.message : '字段检测失败');
    } finally {
      setDetecting(false);
    }
  };

  const refreshPreview = async () => {
    if (!datasetUuid) {
      message.warning('请选择数据集');
      return;
    }
    setPreviewing(true);
    try {
      const res = await previewDataset({
        dataset_uuid: datasetUuid,
        dataset_code: dataset?.code,
        chart_type: chartType,
        page_size: 50,
      });
      setRows(res.data || []);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '预览失败');
    } finally {
      setPreviewing(false);
    }
  };

  useEffect(() => {
    if (step === 2 && datasetUuid) void refreshPreview();
    // 只在进入第三步或切换数据集时拉样本，刷新按钮单独触发。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, datasetUuid]);

  const fieldOptions = fields.map((field) => ({
    value: field.field,
    label: `${field.label} (${field.field})`,
  }));

  const config = useMemo<ReportConfigSchema>(() => {
    const mapped = fields.map((field) => ({
      field: field.field,
      label: field.label,
      visible: true,
      x_axis: field.field === xField,
      y_axis: field.field === yField,
    }));
    return {
      chart_type: chartType,
      dataset_uuid: datasetUuid,
      dataset_code: dataset?.code,
      fields: mapped,
      parameters,
      interaction: {
        drilldown: {
          enabled: drill,
          dimension_field: xField,
          detail_chart_type: 'table',
          title: '明细下钻',
        },
        global_filter_keys: parameters.map((item) => item.key),
      },
      page_size: 50,
    };
  }, [chartType, dataset?.code, datasetUuid, drill, fields, parameters, xField, yField]);

  const goNext = () => {
    if (step === 0) {
      if (!code.trim() || !name.trim()) {
        message.warning('请填写报表编号和报表名称');
        return;
      }
    }
    if (step === 1 && !datasetUuid) {
      message.warning('请选择数据集');
      return;
    }
    setStep((current) => Math.min(current + 1, 2));
  };

  const save = async (status: 'DRAFT' | 'PUBLISHED') => {
    if (readOnly) return;
    const hint = axisHint(chartType, xField, yField, chart.categoryLabel, chart.valueLabel);
    if (hint) {
      message.warning(hint);
      return;
    }
    const body: WizardSaveBody = {
      code: code.trim(),
      name: name.trim(),
      description: description.trim() || null,
      category: admin ? category : 'custom',
      classify,
      report_config: config,
      status,
    };
    setLoading(true);
    try {
      if (reportId) await updateWizardReport(reportId, body);
      else await createWizardReport(body);
      message.success(status === 'PUBLISHED' ? (reportId ? '已保存并发布' : '已创建并发布') : reportId ? '保存成功' : '创建成功');
      navigate(`/apps/kuaireport/reports?tab=${body.category === 'system' ? 'system' : 'mine'}`);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败');
    } finally {
      setLoading(false);
    }
  };

  const missing = axisHint(chartType, xField, yField, chart.categoryLabel, chart.valueLabel);
  const drillRows = drillValue
    ? rows.filter((row) => xField && String(row[xField] ?? '') === drillValue)
    : [];

  return (
    <div style={{ background: '#f5f7fa', minHeight: '100%', padding: 16 }}>
      <div style={{ background: '#fff', padding: '8px 16px', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
        <Button type="link" icon={<ArrowLeftOutlined />} onClick={() => navigate('/apps/kuaireport/reports')}>
          返回
        </Button>
        <span style={{ fontSize: 16, fontWeight: 600 }}>{reportId ? '编辑报表' : '新建报表'}</span>
      </div>
      <Card styles={{ body: { paddingBottom: 12 } }}>
        <Steps
          current={step}
          items={[{ title: '基本信息' }, { title: '数据配置' }, { title: '可视化设计' }]}
          style={{ maxWidth: 720, margin: '8px auto 24px' }}
        />
        {step === 0 ? (
          <div style={{ maxWidth: 640, margin: '0 auto' }}>
            <Field label="报表编号" required>
              <Input value={code} disabled={readOnly} onChange={(event) => setCode(event.target.value)} />
            </Field>
            <Field label="报表名称" required>
              <Input value={name} disabled={readOnly} onChange={(event) => setName(event.target.value)} />
            </Field>
            <Field label="分类">
              <Select
                value={classify}
                disabled={readOnly}
                options={CLASSIFIES.map((item) => ({ value: item, label: item }))}
                onChange={setClassify}
              />
            </Field>
            <Field label="报表归属">
              <Radio.Group
                value={category}
                disabled={readOnly}
                onChange={(event) => setCategory(event.target.value)}
              >
                <Radio value="custom">我的报表（个人使用）</Radio>
                <Radio value="system" disabled={!admin}>
                  系统报表（需管理员权限）
                </Radio>
              </Radio.Group>
            </Field>
            <Field label="备注">
              <Input.TextArea
                value={description}
                disabled={readOnly}
                rows={4}
                placeholder="可选"
                onChange={(event) => setDescription(event.target.value)}
              />
            </Field>
          </div>
        ) : null}
        {step === 1 ? (
          <div style={{ maxWidth: 760, margin: '0 auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
              <Typography.Text strong>数据集配置</Typography.Text>
              <Button type="link" onClick={() => navigate('/system/datasets')}>
                数据集管理
              </Button>
            </div>
            <Select
              showSearch
              optionFilterProp="label"
              placeholder="选择数据集"
              style={{ width: '100%' }}
              disabled={readOnly}
              value={datasetUuid}
              options={datasets.map((item) => ({
                value: item.uuid,
                label: `${item.name}（${item.code}）`,
              }))}
              onChange={(value) => {
                setDatasetUuid(value);
                setFields([]);
                setXField(undefined);
                setYField(undefined);
                void detect(value);
              }}
            />
            <div style={{ marginTop: 16, display: 'flex', justifyContent: 'space-between' }}>
              <Typography.Text type="secondary">检测到字段</Typography.Text>
              <Button size="small" loading={detecting} disabled={!datasetUuid} onClick={() => void detect()}>
                重新检测
              </Button>
            </div>
            <div style={{ marginTop: 8, minHeight: 32 }}>
              {fields.map((field) => (
                <Tag key={field.field} color="blue" style={{ marginBottom: 8 }}>
                  {field.label} ({field.field})
                </Tag>
              ))}
            </div>
            <Typography.Text strong>参数面板 / 过滤条件</Typography.Text>
            <div>
              <Typography.Text type="secondary">配置后在预览页显示查询面板，支持下钻与全局筛选。</Typography.Text>
            </div>
            {!readOnly ? (
              <Button
                style={{ marginTop: 8 }}
                onClick={() =>
                  setParameters((current) => [
                    ...current,
                    { key: nextParamKey(current), label: '', control: 'text' },
                  ])
                }
              >
                添加参数
              </Button>
            ) : null}
            {parameters.map((parameter, index) => (
              <Space key={`${parameter.key}-${index}`} style={{ display: 'flex', marginTop: 8 }} align="start">
                <Input
                  placeholder="参数名"
                  value={parameter.key}
                  disabled={readOnly}
                  onChange={(event) =>
                    setParameters((current) =>
                      current.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, key: event.target.value } : item,
                      ),
                    )
                  }
                />
                <Input
                  placeholder="显示名"
                  value={parameter.label}
                  disabled={readOnly}
                  onChange={(event) =>
                    setParameters((current) =>
                      current.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, label: event.target.value } : item,
                      ),
                    )
                  }
                />
                <Select
                  style={{ width: 120 }}
                  value={parameter.control || 'text'}
                  disabled={readOnly}
                  options={PARAM_TYPES}
                  onChange={(value) =>
                    setParameters((current) =>
                      current.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, control: value } : item,
                      ),
                    )
                  }
                />
                {parameter.control === 'select' ? (
                  <Input
                    placeholder="选项，逗号分隔"
                    disabled={readOnly}
                    value={(parameter.options || []).map((option) => option.label).join(',')}
                    onChange={(event) => {
                      const options = event.target.value
                        .split(',')
                        .map((item) => item.trim())
                        .filter(Boolean)
                        .map((item) => ({ label: item, value: item }));
                      setParameters((current) =>
                        current.map((item, itemIndex) => (itemIndex === index ? { ...item, options } : item)),
                      );
                    }}
                  />
                ) : null}
                {!readOnly ? (
                  <Button
                    danger
                    onClick={() => setParameters((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                  >
                    删除
                  </Button>
                ) : null}
              </Space>
            ))}
            <div style={{ marginTop: 16 }}>
              <Space>
                <Switch checked={drill} disabled={readOnly} onChange={setDrill} />
                <span>启用图表下钻</span>
              </Space>
              <div>
                <Typography.Text type="secondary">开启后，点击图表上的维度会打开该维度的明细表。</Typography.Text>
              </div>
            </div>
          </div>
        ) : null}
        {step === 2 ? (
          <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 16 }}>
            <div>
              <Typography.Text strong>配置选项</Typography.Text>
              <Field label="图表类型">
                <Select
                  value={chartType}
                  disabled={readOnly}
                  options={CHARTS.map((item) => ({ value: item.value, label: item.label }))}
                  onChange={(value) => {
                    setChartType(value);
                    const next = CHARTS.find((item) => item.value === value);
                    if (!next?.slots.includes('category')) setXField(undefined);
                    if (!next?.slots.includes('value')) setYField(undefined);
                  }}
                />
              </Field>
              {chart.tip ? <Typography.Text type="secondary">{chart.tip}</Typography.Text> : null}
              {chart.slots.includes('category') ? (
                <Field label={chart.categoryLabel || 'X轴 / 分组字段'} required>
                  <Select
                    allowClear
                    value={xField}
                    disabled={readOnly}
                    options={fieldOptions}
                    onChange={setXField}
                  />
                </Field>
              ) : null}
              {chart.slots.includes('value') ? (
                <Field label={chart.valueLabel || 'Y轴 / 数值字段'} required>
                  <Select
                    allowClear
                    value={yField}
                    disabled={readOnly}
                    options={fieldOptions}
                    onChange={setYField}
                  />
                </Field>
              ) : null}
            </div>
            <div style={{ border: '1px solid #f0f0f0', borderRadius: 8, padding: 16, minHeight: 360 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
                <Typography.Text strong>预览</Typography.Text>
                <Button icon={<ReloadOutlined />} loading={previewing} onClick={() => void refreshPreview()}>
                  刷新预览
                </Button>
              </div>
              {missing ? (
                <Empty description={missing} />
              ) : (
                <ChartCanvas
                  chartType={chartType}
                  rows={rows}
                  xField={xField}
                  yField={yField}
                  fields={config.fields || []}
                  drillEnabled={drill}
                  onDrill={setDrillValue}
                />
              )}
              <div style={{ marginTop: 12, color: '#8c8c8c' }}>
                已加载 {rows.length} 行样本数据（最多 50 行）
                {drill ? '，点击图表维度可下钻明细' : ''}
              </div>
            </div>
          </div>
        ) : null}
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 24 }}>
          <Button disabled={step === 0} onClick={() => setStep((current) => current - 1)}>
            上一步
          </Button>
          <Space>
            {step < 2 ? (
              <Button type="primary" onClick={goNext}>
                下一步
              </Button>
            ) : readOnly ? null : (
              <>
                <Button loading={loading} onClick={() => void save('DRAFT')}>
                  保存草稿
                </Button>
                <Button type="primary" loading={loading} onClick={() => void save('PUBLISHED')}>
                  保存并发布
                </Button>
              </>
            )}
          </Space>
        </div>
      </Card>
      <DrillDrawer
        open={drillValue != null}
        title="明细下钻"
        rows={drillRows}
        fields={config.fields || []}
        onClose={() => setDrillValue(null)}
      />
    </div>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ marginBottom: 6 }}>
        {required ? <span style={{ color: '#ff4d4f', marginRight: 4 }}>*</span> : null}
        {label}
      </div>
      {children}
    </div>
  );
}
