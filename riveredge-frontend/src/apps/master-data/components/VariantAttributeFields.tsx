/**
 * 属性组合表单字段（主数据 / 价格本 / 单据行共用）
 */

import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App, Col, Form, Input, InputNumber, Modal, Row, Select, Spin, Typography, theme } from 'antd';
import { UniDropdown } from '../../../components/uni-dropdown';
import { MODAL_NESTED_ABOVE_PARENT_OFFSET } from '../../../components/layout-templates/constants';
import { MODAL_ISOLATE_POINTER_PROPS } from '../../../utils/modalEventIsolation';
import { variantAttributeApi } from '../services/variant-attribute';
import type { VariantAttributeDefinition } from '../types/variant-attribute';

export interface VariantAttributeFieldsProps {
  definitions: VariantAttributeDefinition[];
  /** Form.List 内嵌时使用，如 [field.name, 'variantAttributes'] */
  namePrefix?: (string | number)[];
  loading?: boolean;
  colSpan?: { xs?: number; sm?: number; md?: number };
  /** 组合明细表：每属性仅选一个值（禁用多选） */
  singleValueOnly?: boolean;
  /** 枚举下拉底部「快速新增属性值」；默认开启 */
  enableEnumQuickAdd?: boolean;
  /** 属性定义变更后回写父级（如刷新组合表可选值） */
  onDefinitionsChange?: (next: VariantAttributeDefinition[]) => void;
  /** 外层弹窗 zIndex，嵌套「新增属性值」时叠在其上 */
  parentModalZIndex?: number;
}

export const VariantAttributeFields: React.FC<VariantAttributeFieldsProps> = ({
  definitions,
  namePrefix = [],
  loading = false,
  colSpan = { xs: 24, sm: 12, md: 8 },
  singleValueOnly = false,
  enableEnumQuickAdd = true,
  onDefinitionsChange,
  parentModalZIndex,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const { token } = theme.useToken();
  const form = Form.useFormInstance();
  const [localDefs, setLocalDefs] = useState(definitions);
  const [quickAddDef, setQuickAddDef] = useState<VariantAttributeDefinition | null>(null);
  const [quickAddValue, setQuickAddValue] = useState('');
  const [quickAddSubmitting, setQuickAddSubmitting] = useState(false);

  useEffect(() => {
    setLocalDefs(definitions);
  }, [definitions]);

  const applyDefinitions = (next: VariantAttributeDefinition[]) => {
    setLocalDefs(next);
    onDefinitionsChange?.(next);
  };

  const fieldNamePath = (attributeName: string) =>
    namePrefix.length ? [...namePrefix, attributeName] : [attributeName];

  const handleQuickAddConfirm = async () => {
    if (!quickAddDef) return;
    const trimmed = quickAddValue.trim();
    if (!trimmed) {
      messageApi.warning(t('app.master-data.variantAttributes.enumValueRequired'));
      return;
    }
    const existing = (quickAddDef.enum_values || []).map((v) => String(v).trim());
    if (existing.some((v) => v === trimmed)) {
      messageApi.warning(t('app.master-data.variantAttributes.enumValueExists'));
      return;
    }
    try {
      setQuickAddSubmitting(true);
      const updated = await variantAttributeApi.update(quickAddDef.uuid, {
        enum_values: [...existing, trimmed],
      });
      applyDefinitions(localDefs.map((d) => (d.uuid === updated.uuid ? updated : d)));
      const namePath = fieldNamePath(quickAddDef.attribute_name);
      const multi = !singleValueOnly && !!quickAddDef.allow_multiple;
      if (multi) {
        const current = form.getFieldValue(namePath);
        const prev = Array.isArray(current) ? current.map(String) : current != null && current !== '' ? [String(current)] : [];
        form.setFieldValue(namePath, [...new Set([...prev, trimmed])]);
      } else {
        form.setFieldValue(namePath, trimmed);
      }
      messageApi.success(t('common.createSuccess'));
      setQuickAddDef(null);
      setQuickAddValue('');
    } catch (e: any) {
      messageApi.error(e?.message || t('common.operationFailed'));
    } finally {
      setQuickAddSubmitting(false);
    }
  };

  const quickAddModalZIndex =
    (parentModalZIndex ?? token.zIndexPopupBase) + MODAL_NESTED_ABOVE_PARENT_OFFSET;

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 16 }}>
        <Spin size="small" />
      </div>
    );
  }

  if (localDefs.length === 0) {
    return (
      <Typography.Text type="secondary">
        {t('app.master-data.materialForm.noVariantDef')}
      </Typography.Text>
    );
  }

  return (
    <>
      <Row gutter={[12, 8]}>
        {localDefs.map((def) => (
          <Col {...colSpan} key={def.attribute_name}>
            <Form.Item
              name={namePrefix.length ? [...namePrefix, def.attribute_name] : def.attribute_name}
              label={def.display_name}
              tooltip={def.description}
              style={namePrefix.length ? { marginBottom: 8 } : undefined}
            >
              {def.attribute_type === 'enum' ? (
                <UniDropdown
                  allowClear
                  showSearch
                  mode={!singleValueOnly && def.allow_multiple ? 'multiple' : undefined}
                  placeholder={t('app.master-data.materialForm.selectAttr', { name: def.display_name })}
                  options={(def.enum_values || []).map((v) => ({ label: v, value: v }))}
                  quickCreate={
                    enableEnumQuickAdd
                      ? {
                          label: t('app.master-data.variantAttributes.quickAddEnumValue'),
                          onClick: () => {
                            setQuickAddDef(def);
                            setQuickAddValue('');
                          },
                        }
                      : undefined
                  }
                />
              ) : def.attribute_type === 'number' ? (
                <InputNumber style={{ width: '100%' }} />
              ) : def.attribute_type === 'boolean' ? (
                <Select
                  allowClear
                  options={[
                    { label: t('common.yes'), value: true },
                    { label: t('common.no'), value: false },
                  ]}
                />
              ) : def.attribute_type === 'date' ? (
                <Input type="date" />
              ) : (
                <Input maxLength={def.validation_rules?.max_length} />
              )}
            </Form.Item>
          </Col>
        ))}
      </Row>

      <Modal
        title={t('app.master-data.variantAttributes.quickAddEnumValueTitle', {
          name: quickAddDef?.display_name || '',
        })}
        open={!!quickAddDef}
        onCancel={() => {
          if (quickAddSubmitting) return;
          setQuickAddDef(null);
          setQuickAddValue('');
        }}
        onOk={() => void handleQuickAddConfirm()}
        confirmLoading={quickAddSubmitting}
        destroyOnHidden
        zIndex={quickAddModalZIndex}
        maskProps={{ ...MODAL_ISOLATE_POINTER_PROPS }}
        wrapProps={{ ...MODAL_ISOLATE_POINTER_PROPS }}
      >
        <Input
          autoFocus
          value={quickAddValue}
          onChange={(e) => setQuickAddValue(e.target.value)}
          placeholder={t('app.master-data.variantAttributes.quickAddEnumValuePlaceholder')}
          onPressEnter={() => void handleQuickAddConfirm()}
          maxLength={100}
        />
      </Modal>
    </>
  );
};

export function parseVariantAttributesValue(
  raw: unknown,
): Record<string, unknown> | undefined {
  if (raw == null || raw === '') return undefined;
  if (typeof raw === 'object' && !Array.isArray(raw)) {
    return raw as Record<string, unknown>;
  }
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw);
      return typeof parsed === 'object' && parsed != null && !Array.isArray(parsed)
        ? (parsed as Record<string, unknown>)
        : undefined;
    } catch {
      return undefined;
    }
  }
  return undefined;
}

export function formatVariantAttributesSummary(attrs?: Record<string, unknown> | null): string {
  if (!attrs || Object.keys(attrs).length === 0) return '';
  return Object.entries(attrs)
    .map(([k, v]) => `${k}=${Array.isArray(v) ? v.join(',') : String(v)}`)
    .join('; ');
}
