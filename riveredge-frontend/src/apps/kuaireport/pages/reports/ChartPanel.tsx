/**
 * 向导第三步和已保存报表的图表预览。
 * 表格不需要坐标轴；折线、柱状、面积、散点、饼图需要分类和数值；指标卡只要数值。
 */

import React, { useEffect, useRef } from 'react';
import { Area, Bar, Column, Line, Pie, Scatter } from '@ant-design/charts';
import { Button, DatePicker, Drawer, Empty, Form, Input, InputNumber, Select, Space, Statistic, Table } from 'antd';
import type { ReportFieldMapping, ReportParameterConfig } from '../../../../components/uni-report';

const { RangePicker } = DatePicker;

export interface ChartPoint {
  x: string;
  y: number;
}

export function chartPoints(
  rows: Record<string, unknown>[],
  xField?: string,
  yField?: string,
): ChartPoint[] {
  return rows.map((row, index) => {
    const rawX = xField ? row[xField] : index + 1;
    const rawY = yField ? row[yField] : 0;
    const y = typeof rawY === 'number' ? rawY : Number(rawY);
    return {
      x: rawX == null || rawX === '' ? String(index + 1) : String(rawX),
      y: Number.isFinite(y) ? y : 0,
    };
  });
}

function bindDrill(
  plot: { on: (event: string, handler: (evt: unknown) => void) => void; off: (event: string, handler: (evt: unknown) => void) => void },
  onDrill?: (value: string) => void,
) {
  if (!onDrill) return undefined;
  const handler = (evt: unknown) => {
    const data = (evt as { data?: { data?: { x?: string } } })?.data?.data;
    if (data?.x != null) onDrill(String(data.x));
  };
  plot.on('element:click', handler);
  return () => plot.off('element:click', handler);
}

export function ChartCanvas({
  chartType,
  rows,
  xField,
  yField,
  fields,
  drillEnabled,
  onDrill,
}: {
  chartType: string;
  rows: Record<string, unknown>[];
  xField?: string;
  yField?: string;
  fields: ReportFieldMapping[];
  drillEnabled?: boolean;
  onDrill?: (value: string) => void;
}) {
  const cleanup = useRef<(() => void) | undefined>(undefined);
  useEffect(() => () => cleanup.current?.(), []);

  const ready = (plot: Parameters<typeof bindDrill>[0]) => {
    cleanup.current?.();
    cleanup.current = bindDrill(plot, drillEnabled ? onDrill : undefined);
  };

  if (chartType === 'table') {
    const columns = (fields.length ? fields : Object.keys(rows[0] || {}).map((field) => ({ field, label: field })))
      .filter((field) => field.field)
      .map((field) => ({
        title: field.label || field.field,
        dataIndex: field.field,
        ellipsis: true,
      }));
    return (
      <Table
        size="small"
        rowKey={(_, index) => String(index)}
        columns={columns}
        dataSource={rows}
        pagination={{ pageSize: 10, showSizeChanger: false }}
      />
    );
  }

  if (chartType === 'card') {
    const points = chartPoints(rows, xField, yField);
    const total = points.reduce((sum, point) => sum + point.y, 0);
    const label = fields.find((field) => field.field === yField)?.label || yField || '数值';
    return <Statistic title={label} value={total} />;
  }

  const needsX = chartType !== 'card';
  if ((needsX && !xField) || !yField) {
    return null;
  }
  const points = chartPoints(rows, xField, yField);
  if (chartType === 'pie') {
    return <Pie data={points} angleField="y" colorField="x" height={320} onReady={ready} />;
  }
  if (chartType === 'bar') {
    return <Bar data={points} xField="y" yField="x" height={320} onReady={ready} />;
  }
  if (chartType === 'scatter') {
    return <Scatter data={points} xField="x" yField="y" height={320} onReady={ready} />;
  }
  if (chartType === 'area') {
    return <Area data={points} xField="x" yField="y" height={320} onReady={ready} />;
  }
  if (chartType === 'column') {
    return <Column data={points} xField="x" yField="y" height={320} onReady={ready} />;
  }
  return (
    <Line
      data={points}
      xField="x"
      yField="y"
      height={320}
      point={{ shape: 'diamond', size: 4 }}
      onReady={ready}
    />
  );
}

export function axisHint(chartType: string, xField?: string, yField?: string, categoryLabel = 'X轴 / 分组字段', valueLabel = 'Y轴 / 数值字段') {
  if (chartType === 'table') return '';
  if (chartType === 'card') return yField ? '' : `请选择${valueLabel}`;
  if (!xField) return `请选择${categoryLabel}`;
  if (!yField) return `请选择${valueLabel}`;
  return '';
}

export function QueryPanel({
  parameters,
  onSubmit,
}: {
  parameters: ReportParameterConfig[];
  onSubmit: (values: Record<string, unknown>) => void;
}) {
  const [form] = Form.useForm();
  if (!parameters.length) return null;
  return (
    <Form
      form={form}
      layout="inline"
      style={{ marginBottom: 12 }}
      onFinish={(values) => {
        const next: Record<string, unknown> = {};
        parameters.forEach((parameter) => {
          const value = values[parameter.key];
          if (parameter.control === 'dateRange' && Array.isArray(value)) {
            next[`${parameter.key}_start`] = value[0]?.format?.('YYYY-MM-DD');
            next[`${parameter.key}_end`] = value[1]?.format?.('YYYY-MM-DD');
            return;
          }
          if (parameter.control === 'date' && value?.format) {
            next[parameter.key] = value.format('YYYY-MM-DD');
            return;
          }
          if (value !== undefined && value !== null && value !== '') next[parameter.key] = value;
        });
        onSubmit(next);
      }}
    >
      {parameters.map((parameter) => (
        <Form.Item key={parameter.key} name={parameter.key} label={parameter.label || parameter.key}>
          {parameter.control === 'number' ? (
            <InputNumber />
          ) : parameter.control === 'date' ? (
            <DatePicker />
          ) : parameter.control === 'dateRange' ? (
            <RangePicker />
          ) : parameter.control === 'select' ? (
            <Select
              allowClear
              style={{ minWidth: 140 }}
              options={(parameter.options || []).map((option) => ({
                label: option.label,
                value: option.value,
              }))}
            />
          ) : (
            <Input allowClear />
          )}
        </Form.Item>
      ))}
      <Form.Item>
        <Space>
          <Button type="primary" htmlType="submit">
            查询
          </Button>
          <Button
            onClick={() => {
              form.resetFields();
              onSubmit({});
            }}
          >
            重置
          </Button>
        </Space>
      </Form.Item>
    </Form>
  );
}

export function DrillDrawer({
  open,
  title,
  rows,
  fields,
  onClose,
}: {
  open: boolean;
  title: string;
  rows: Record<string, unknown>[];
  fields: ReportFieldMapping[];
  onClose: () => void;
}) {
  const columns = (fields.length ? fields : Object.keys(rows[0] || {}).map((field) => ({ field, label: field }))).map(
    (field) => ({
      title: field.label || field.field,
      dataIndex: field.field,
      ellipsis: true,
    }),
  );
  return (
    <Drawer title={title || '明细下钻'} open={open} width={720} onClose={onClose}>
      <Table size="small" rowKey={(_, index) => String(index)} columns={columns} dataSource={rows} pagination={{ pageSize: 10 }} />
    </Drawer>
  );
}
