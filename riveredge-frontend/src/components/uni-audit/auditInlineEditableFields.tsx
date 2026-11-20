import React from 'react';
import { Input, InputNumber, Switch, Typography } from 'antd';
import type { EditableFieldOption } from '../../services/approvalProcess';
import { useTranslation } from 'react-i18next';

export function resolveEditableFieldKeys(
  editableFields: string[] | '*' | undefined,
  catalog: EditableFieldOption[],
): string[] {
  if (!editableFields || (Array.isArray(editableFields) && editableFields.length === 0)) {
    return [];
  }
  if (editableFields === '*' || (Array.isArray(editableFields) && editableFields.includes('*'))) {
    return catalog.map((c) => c.field);
  }
  if (Array.isArray(editableFields)) {
    return editableFields.filter((f) => catalog.some((c) => c.field === f));
  }
  return [];
}

export function buildAuditDocumentUpdates(
  catalog: EditableFieldOption[],
  editableFields: string[] | '*' | undefined,
  values: Record<string, unknown>,
): Record<string, unknown> | undefined {
  const keys = resolveEditableFieldKeys(editableFields, catalog);
  if (!keys.length) return undefined;
  const out: Record<string, unknown> = {};
  for (const key of keys) {
    if (!(key in values)) continue;
    const val = values[key];
    if (val === undefined || val === null || val === '') continue;
    out[key] = val;
  }
  if (Object.keys(out).length === 0) return undefined;
  return out;
}

type AuditInlineEditableFieldsProps = {
  catalog: EditableFieldOption[];
  editableFields: string[] | '*' | undefined;
  values: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
};

export const AuditInlineEditableFields: React.FC<AuditInlineEditableFieldsProps> = ({
  catalog,
  editableFields,
  values,
  onChange,
}) => {
  const { t } = useTranslation();
  const keys = resolveEditableFieldKeys(editableFields, catalog);
  if (!keys.length) return null;

  return (
    <div
      style={{
        marginBottom: 12,
        padding: '10px 12px',
        border: '1px solid rgba(0, 0, 0, 0.06)',
        borderRadius: 6,
        background: '#f7f8fa',
      }}
    >
      <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>
        {t('components.uniAudit.inlineEditableTitle')}
      </Typography.Text>
      {keys.map((key) => {
        const meta = catalog.find((c) => c.field === key);
        const label = meta?.label || key;
        const type = meta?.type || 'string';
        if (type === 'boolean') {
          return (
            <div key={key} style={{ marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Typography.Text style={{ minWidth: 96 }}>{label}</Typography.Text>
              <Switch
                checked={Boolean(values[key])}
                onChange={(checked) => onChange({ ...values, [key]: checked })}
              />
            </div>
          );
        }
        if (type === 'number') {
          return (
            <div key={key} style={{ marginBottom: 8 }}>
              <Typography.Text style={{ display: 'block', marginBottom: 4 }}>{label}</Typography.Text>
              <InputNumber
                style={{ width: '100%' }}
                min={0}
                value={values[key] as number | undefined}
                onChange={(val) => onChange({ ...values, [key]: val ?? undefined })}
              />
            </div>
          );
        }
        if (type === 'text') {
          return (
            <div key={key} style={{ marginBottom: 8 }}>
              <Typography.Text style={{ display: 'block', marginBottom: 4 }}>{label}</Typography.Text>
              <Input.TextArea
                rows={2}
                value={values[key] != null ? String(values[key]) : ''}
                onChange={(e) => onChange({ ...values, [key]: e.target.value })}
              />
            </div>
          );
        }
        return (
          <div key={key} style={{ marginBottom: 8 }}>
            <Typography.Text style={{ display: 'block', marginBottom: 4 }}>{label}</Typography.Text>
            <Input
              value={values[key] != null ? String(values[key]) : ''}
              onChange={(e) => onChange({ ...values, [key]: e.target.value })}
            />
          </div>
        );
      })}
    </div>
  );
};
