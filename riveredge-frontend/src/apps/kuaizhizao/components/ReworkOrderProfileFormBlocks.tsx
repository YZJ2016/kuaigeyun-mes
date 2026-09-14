/**
 * 返工单行业 profile 表单块：路径类型、十段扩展字段、动态排位表
 */

import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ProFormDatePicker,
  ProFormDigit,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
  ProFormDependency,
} from '@ant-design/pro-components';
import { Col, Form as AntForm, Input, InputNumber, Row, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { UniTableDetail } from '../../../components/uni-table-detail';
import type { ReworkOrderFormProfile } from '../services/work-order';
import {
  buildEmptyPositionPlanRow,
  inferProfileFieldType,
  REWORK_HEADER_STATIC_KEYS,
  resolveReworkFieldLabel,
  sectionsForPath,
  sortedPositionPlanColumns,
  type ReworkProfileColumn,
} from '../utils/reworkOrderFormProfile';

function renderProfileField(
  fieldKey: string,
  profile: ReworkOrderFormProfile | null,
  t: (key: string, opts?: Record<string, unknown>) => string,
) {
  const label = resolveReworkFieldLabel(profile, fieldKey, fieldKey);
  const type = inferProfileFieldType(fieldKey);
  const span = type === 'textarea' ? 24 : 12;
  const col = (
    <Col span={span} key={fieldKey}>
      {type === 'textarea' ? (
        <ProFormTextArea name={fieldKey} label={label} fieldProps={{ rows: 2 }} />
      ) : type === 'date' ? (
        <ProFormDatePicker name={fieldKey} label={label} width="100%" />
      ) : type === 'decimal' ? (
        <ProFormDigit name={fieldKey} label={label} style={{ width: '100%' }} />
      ) : (
        <ProFormText name={fieldKey} label={label} />
      )}
    </Col>
  );
  return col;
}

export interface ReworkOrderProfileExtensionFieldsProps {
  profile: ReworkOrderFormProfile | null;
}

export const ReworkOrderProfileExtensionFields: React.FC<ReworkOrderProfileExtensionFieldsProps> = ({
  profile,
}) => {
  const { t } = useTranslation();
  const pathOptions = useMemo(
    () =>
      [...(profile?.rework_path_types || [])]
        .sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0))
        .map((item) => ({
          value: String(item.code),
          label: String(item.label || item.code),
        })),
    [profile],
  );

  if (!profile?.form_sections?.length && !pathOptions.length) {
    return null;
  }

  return (
    <>
      {pathOptions.length ? (
        <Row gutter={16}>
          <Col span={12}>
            <ProFormSelect
              name="rework_path_type"
              label={t('app.kuaizhizao.reworkOrder.profilePathType')}
              options={pathOptions}
              rules={[{ required: true, message: t('common.required') }]}
            />
          </Col>
        </Row>
      ) : null}
      <ProFormDependency name={['rework_path_type']}>
        {({ rework_path_type }) =>
          sectionsForPath(profile, rework_path_type).map((section) => {
            const fields = section.fields.filter((key) => !REWORK_HEADER_STATIC_KEYS.has(key));
            if (!fields.length) return null;
            return (
              <div key={section.key} style={{ marginBottom: 8 }}>
                <Typography.Title level={5} style={{ marginTop: 8, marginBottom: 8 }}>
                  {section.label}
                </Typography.Title>
                <Row gutter={16}>
                  {fields.map((fieldKey) => renderProfileField(fieldKey, profile, t))}
                </Row>
              </div>
            );
          })
        }
      </ProFormDependency>
    </>
  );
};

function renderPositionCell(
  col: ReworkProfileColumn,
  index: number,
  t: (key: string) => string,
) {
  const rules = col.required ? [{ required: true, message: t('common.required') }] : undefined;
  if (col.type === 'decimal') {
    return (
      <AntForm.Item name={[index, col.key]} rules={rules} style={{ marginBottom: 0 }}>
        <InputNumber size="small" style={{ width: '100%' }} min={0} />
      </AntForm.Item>
    );
  }
  return (
    <AntForm.Item name={[index, col.key]} rules={rules} style={{ marginBottom: 0 }}>
      <Input size="small" />
    </AntForm.Item>
  );
}

export interface ReworkOrderProfilePositionPlanListProps {
  profile: ReworkOrderFormProfile | null;
}

export const ReworkOrderProfilePositionPlanList: React.FC<ReworkOrderProfilePositionPlanListProps> = ({
  profile,
}) => {
  const { t } = useTranslation();
  const columns = useMemo(() => sortedPositionPlanColumns(profile), [profile]);

  const tableColumns = useMemo<ColumnsType<Record<string, unknown>>>(
    () =>
      columns.map((col) => ({
        title: col.label,
        dataIndex: col.key,
        width: col.width || 110,
        render: (_: unknown, __: unknown, index: number) => renderPositionCell(col, index, t),
      })),
    [columns, t],
  );

  const emptyRow = useMemo(() => buildEmptyPositionPlanRow(columns), [columns]);

  if (!profile?.position_plan_columns?.length) {
    return null;
  }

  return (
    <UniTableDetail
      name="position_plans"
      title={t('app.kuaizhizao.reworkOrder.sectionPositionPlans')}
      columns={tableColumns}
      initialValue={() => ({ ...emptyRow, sequence: 1 })}
      required={false}
      tableProps={{
        scroll: { x: columns.reduce((sum, c) => sum + (c.width || 110), 0) },
      }}
    />
  );
};
