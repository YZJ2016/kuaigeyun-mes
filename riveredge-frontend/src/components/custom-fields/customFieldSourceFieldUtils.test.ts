import { describe, expect, it } from 'vitest';
import {
  buildLinkFieldSelectOptions,
  buildSourceFieldSelectOptions,
} from './CustomFieldSourceFieldOption';
import type { CustomField } from '../../services/customField';
import type { CustomFieldSystemSourceField } from '../../services/customField';
import {
  encodeSourceFieldKey,
  normalizeManualSourceFieldOption,
  resolveSourceFormFieldName,
  resolveSourceMatchFieldDefault,
} from './customFieldSourceFieldUtils';

const scalar = (name: string, label = name): CustomFieldSystemSourceField => ({
  name,
  modelField: name,
  label,
  scope: 'system',
});

const link = (name: string, label = name): CustomFieldSystemSourceField => ({
  name,
  modelField: `${name.replace(/Id$/, '')}_id`,
  label,
  scope: 'system',
});

const customField = (partial: Partial<CustomField> & Pick<CustomField, 'code' | 'field_type'>): CustomField =>
  ({
    id: 1,
    uuid: 'u1',
    tenant_id: 1,
    name: partial.code,
    label: partial.code,
    table_name: 'master_data_boms',
    sort_order: 0,
    is_active: true,
    is_required: false,
    is_searchable: true,
    is_sortable: true,
    created_at: '',
    updated_at: '',
    ...partial,
  }) as CustomField;

describe('customFieldSourceFieldUtils', () => {
  it('encodes and resolves system source to form field name', () => {
    expect(encodeSourceFieldKey('system', 'materialId')).toBe('system:materialId');
    expect(resolveSourceFormFieldName('materialId', 'system')).toBe('materialId');
    expect(resolveSourceFormFieldName('unit_tip', 'custom')).toBe('custom_unit_tip');
  });

  it('defaults match field to id for known link and Id-suffixed system keys', () => {
    const linkKeys = new Set([encodeSourceFieldKey('system', 'materialId')]);
    const scalarKeys = new Set([encodeSourceFieldKey('system', 'version')]);
    expect(
      resolveSourceMatchFieldDefault('system:materialId', {
        linkFieldKeys: linkKeys,
        scalarFieldKeys: scalarKeys,
      }),
    ).toBe('id');
    expect(
      resolveSourceMatchFieldDefault('system:version', {
        linkFieldKeys: linkKeys,
        scalarFieldKeys: scalarKeys,
      }),
    ).toBe('code');
    expect(
      resolveSourceMatchFieldDefault('system:plantId', {
        linkFieldKeys: linkKeys,
        scalarFieldKeys: scalarKeys,
      }),
    ).toBe('id');
    expect(
      resolveSourceMatchFieldDefault('custom:qty', {
        linkFieldKeys: linkKeys,
        scalarFieldKeys: scalarKeys,
      }),
    ).toBe('code');
    expect(
      resolveSourceMatchFieldDefault(undefined, {
        linkFieldKeys: linkKeys,
        scalarFieldKeys: scalarKeys,
      }),
    ).toBe('code');
  });

  it('normalizes manual source search into selectable option', () => {
    expect(normalizeManualSourceFieldOption('  materialId  ', '自定义源字段')).toEqual({
      value: 'system:materialId',
      label: '自定义源字段 (materialId)',
      scope: 'system',
    });
    expect(normalizeManualSourceFieldOption('system:fooId', '自定义源字段')?.value).toBe(
      'system:fooId',
    );
    expect(normalizeManualSourceFieldOption('', '自定义源字段')).toBeNull();
  });
});

describe('buildLinkFieldSelectOptions', () => {
  it('merges scalar, link FK, and associated_object custom fields', () => {
    const options = buildLinkFieldSelectOptions(
      [scalar('version', '版本')],
      [link('materialId', '主物料')],
      [
        customField({ code: 'tip', field_type: 'text', sort_order: 1 }),
        customField({ code: 'mat_ref', field_type: 'associated_object', sort_order: 2 }),
        customField({ code: 'note', field_type: 'textarea', sort_order: 3 }),
      ],
    );
    const values = options.map((item) => item.value);
    expect(values).toContain('system:version');
    expect(values).toContain('system:materialId');
    expect(values).toContain('custom:tip');
    expect(values).toContain('custom:mat_ref');
    expect(values).not.toContain('custom:note');
  });

  it('buildSourceFieldSelectOptions excludes link-only FKs', () => {
    const options = buildSourceFieldSelectOptions(
      [scalar('version')],
      [customField({ code: 'tip', field_type: 'text', sort_order: 0 })],
    );
    expect(options.map((item) => item.value)).toEqual(['system:version', 'custom:tip']);
  });
});
