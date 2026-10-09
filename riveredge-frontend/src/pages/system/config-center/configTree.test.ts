import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  AUTOMATION_CATEGORIES,
  PARAMETER_CATEGORIES,
  FLOW_CATEGORIES,
} from './configTree';

const REMOVED_TOOLBAR_SOURCE_PATHS = [
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
  it('does not expose toolbar sync/push in business config (moved to role permissions)', () => {
    const paths = new Set(allParams().map((p) => p.sourcePath));
    for (const path of REMOVED_TOOLBAR_SOURCE_PATHS) {
      assert.strictEqual(paths.has(path), false);
    }
  });

  it('does not expose multi_unit fake switch', () => {
    const paths = allParams().map((p) => p.sourcePath);
    assert.ok(!(paths).includes('parameters.warehouse.multi_unit'));
  });

  it('equipment module stays empty in parameter and automation trees', () => {
    const equipmentParam = PARAMETER_CATEGORIES.find((c) => c.id === 'equipment');
    const equipmentAuto = AUTOMATION_CATEGORIES.find((c) => c.id === 'equipment');
    assert.strictEqual((equipmentParam?.params ?? []).length, 0);
    assert.strictEqual((equipmentAuto?.params ?? []).length, 0);
  });
});
