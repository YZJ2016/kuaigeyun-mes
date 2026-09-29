import { describe, expect, it } from 'vitest';
import {
  AUTOMATION_CATEGORIES,
  PARAMETER_CATEGORIES,
  FLOW_CATEGORIES,
} from './configTree';

const TOOLBAR_SOURCE_PATHS = [
  'parameters.work_order.toolbar_sync_enabled',
  'parameters.work_order.toolbar_push_enabled',
  'parameters.reporting.toolbar_sync_enabled',
  'parameters.reporting.toolbar_push_enabled',
  'parameters.sales.toolbar_sync_enabled',
  'parameters.sales.toolbar_push_enabled',
  'parameters.purchase.toolbar_sync_enabled',
  'parameters.purchase.toolbar_push_enabled',
  'parameters.warehouse.toolbar_sync_enabled',
  'parameters.warehouse.toolbar_push_enabled',
];

function allParams() {
  return [...PARAMETER_CATEGORIES, ...FLOW_CATEGORIES, ...AUTOMATION_CATEGORIES].flatMap(
    (c) => c.params,
  );
}

describe('configTree toolbar / empty modules', () => {
  it('exposes all toolbar sync/push switches', () => {
    const paths = new Set(allParams().map((p) => p.sourcePath));
    for (const path of TOOLBAR_SOURCE_PATHS) {
      expect(paths.has(path)).toBe(true);
    }
  });

  it('does not expose multi_unit fake switch', () => {
    const paths = allParams().map((p) => p.sourcePath);
    expect(paths).not.toContain('parameters.warehouse.multi_unit');
  });

  it('equipment module stays empty in parameter and automation trees', () => {
    const paramEquip = PARAMETER_CATEGORIES.find((c) => c.id === 'equipment');
    const autoEquip = AUTOMATION_CATEGORIES.find((c) => c.id === 'equipment');
    expect(paramEquip?.params ?? []).toEqual([]);
    expect(autoEquip?.params ?? []).toEqual([]);
  });
});
