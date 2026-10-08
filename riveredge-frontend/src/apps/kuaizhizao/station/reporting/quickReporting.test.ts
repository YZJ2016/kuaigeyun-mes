import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  buildMaterialBindingBody,
  buildQuickReportingBody,
  buildScrapBody,
  resolveWorkstationId,
  type QuickReportInput,
} from './quickReporting.ts';

const base: QuickReportInput = {
  mode: 'self',
  workstationId: 9,
  operator: { id: 3, name: '张三' },
  team: null,
  workOrder: { id: 11, code: 'WO-1', name: '', product_name: '产品A' },
  operation: { operation_id: 22, operation_code: 'OP-1', operation_name: '组装' },
  qualifiedQuantity: 2,
  unqualifiedQuantity: 0,
  workHours: 1.5,
  reportedAt: '2026-09-29 10:00:00',
};

test('workstationId query is used when the page has no bound id', () => {
  assert.equal(resolveWorkstationId(null, '15'), 15);
  assert.equal(resolveWorkstationId(undefined, '0'), null);
  assert.equal(resolveWorkstationId(4, '15'), 4);
});

test('self report writes the given operator and workstation, not a channel field', () => {
  const decision = buildQuickReportingBody({
    ...base,
    unqualifiedQuantity: 1,
    defectReason: '划伤',
  });
  assert.equal(decision.submit, true);
  if (!decision.submit) return;
  assert.equal(decision.body.worker_id, 3);
  assert.equal(decision.body.worker_name, '张三');
  assert.equal(decision.body.work_order_name, '产品A');
  assert.deepEqual(decision.body.device_info, { workstation_id: 9 });
  assert.equal(decision.body.reported_quantity, 3);
  assert.deepEqual(decision.body.defect, { defect_quantity: 1, defect_reason: '划伤' });
  assert.equal('client_channel' in decision.body, false);
  assert.equal('team_id' in decision.body, false);
});

test('self report without an operator does not submit', () => {
  const decision = buildQuickReportingBody({ ...base, operator: null });
  assert.equal(decision.submit, false);
  if (!decision.submit) assert.equal(decision.reason, 'missing-operator');
});

test('team report builds a body without an operator', () => {
  const decision = buildQuickReportingBody({
    ...base,
    mode: 'team',
    operator: null,
    team: { id: 6, name: '甲班' },
  });
  assert.equal(decision.submit, true);
  if (!decision.submit) return;
  assert.equal(decision.body.team_id, 6);
  assert.equal(decision.body.team_name, '甲班');
  assert.equal(decision.body.worker_name, '甲班');
  assert.equal('worker_id' in decision.body, false);
});

test('feeding and scrap bodies use the existing subsidiary fields', () => {
  const feeding = buildMaterialBindingBody({
    bindingType: 'feeding',
    materialId: 41,
    quantity: 2,
    materialCode: 'M-1',
    materialName: '钢板',
  });
  assert.equal(feeding.submit, true);
  if (feeding.submit) {
    assert.equal(feeding.body.binding_type, 'feeding');
    assert.equal(feeding.body.material_id, 41);
    assert.equal(feeding.body.quantity, 2);
  }
  const scrap = buildScrapBody({
    scrapQuantity: 1,
    scrapReason: '报废',
    scrapType: 'process',
    unqualifiedQuantity: 1,
  });
  assert.equal(scrap.submit, true);
  if (scrap.submit) {
    assert.equal(scrap.body.scrap_type, 'process');
    assert.equal(scrap.body.scrap_quantity, 1);
  }
  const over = buildScrapBody({
    scrapQuantity: 3,
    scrapReason: '报废',
    unqualifiedQuantity: 1,
  });
  assert.equal(over.submit, false);
});
