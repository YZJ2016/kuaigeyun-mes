// Exercises the actual UTS page scripts as TypeScript with platform boundaries stubbed.
// This checks state/request behavior, not HBuilderX compilation or native rendering.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('../../../riveredge-frontend/node_modules/typescript');
const root = path.resolve(__dirname, '..');
function page(file, extra = {}) {
  const source = fs.readFileSync(path.join(root, file), 'utf8');
  const script = source.match(/<script setup lang="uts">([\s\S]*?)<\/script>/)[1];
  const context = vm.createContext({
    ref: value => ({ value }), computed: fn => ({ get value() { return fn(); } }),
    UTSJSONObject: class { set(key, value) { this[key] = value; } },
    onLoad() {}, onShow() {}, getToken: () => 'token', readSessionName: () => '测试用户', readRecentRoutes: () => [], readRecentRoutes: () => [],
    getTenantName: () => '测试组织', takePendingEntry: () => '',
    fieldText: (row, key) => row?.[key] == null ? '' : String(row[key]),
    fieldNumber: (row, key) => Number(row?.[key] || 0), readRows: rows => rows,
    errorText: err => err.message, scopeTitle: scope => scope, toast() {}, ...extra,
  });
  // Only strip imports; compile the unchanged page functions and state declarations.
  const output = ts.transpileModule(script.replace(/import[\s\S]*?from ['"][^'"]+['"]/g, ''), { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS } }).outputText;
  vm.runInContext(output.replace(/^import .*$/gm, '').replace(/^.*require\(.*\);$/gm, ''), context);
  return expression => vm.runInContext(expression, context);
}
function block(errorText = '', badgeNote = '', showBadge = true) {
  return { scope: 'equipment', errorText, badgeNote, showBadge, pendingCount: 0, overdueCount: 0,
    sections: [{ cells: [{ key: 'faults', route: '/equipment/faults', uid: 'faults' }] }] };
}
test('home distinguishes failed, zero and unavailable counts while retaining entries', () => {
  const run = page('shell/workbench/index.uvue', { blocks: [block('internal/path/secret'), block('', '角标未能读取')] });
  run('applyHome(blocks)');
  assert.equal(run('homeWarnings.value.length'), 2);
  assert.equal(run('todoEmptyText.value'), '');
  assert.equal(run('loadedBlocks.value[1].sections.length'), 1);
  assert.equal(run('homeWarnings.value.join(" ").includes("secret")'), false);
  run('applyHome([ { ...blocks[1], badgeNote: "" } ])');
  assert.equal(run('todoEmptyText.value'), '当前故障与保养提醒均无待处理项');
  run('applyHome([])');
  assert.equal(run('todoEmptyText.value'), '当前没有可显示的待办统计');
  run('applyHome([{ ...blocks[1], badgeNote: "", showBadge: false }])');
  assert.equal(run('homeWarnings.value.length'), 1);
  assert.equal(run('todoEmptyText.value'), '');
  run('applyHome([blocks[0]])');
  assert.equal(run('homeWarnings.value.length'), 1);
  assert.equal(run('todoEmptyText.value'), '');
});
test('approval locks confirmation and request, cancellation makes no request', async () => {
  const modals = []; const requests = [];
  const run = page('features/workshop/reporting-approve/index.uvue', {
    uni: { showModal: options => modals.push(options) },
    request: options => { requests.push(options); return Promise.resolve([]); },
  });
  run('rows.value = [{id: 7, work_order_code: "WO7", operation_name: "装配", qualified_quantity: 9, unqualified_quantity: 1, work_hours: 2}]');
  run('approve(0); approve(0)');
  assert.equal(modals.length, 1);
  assert.equal(requests.length, 0);
  assert.match(modals[0].content, /合格.*9/);
  modals[0].success({ confirm: false });
  assert.equal(run('approving.value'), false);
  run('approve(0)');
  await modals[1].success({ confirm: true });
  assert.equal(requests.filter(r => r.method === 'POST').length, 1);
  assert.equal(run('rows.value.length'), 0);
  assert.equal(run('approving.value'), false);
});
test('failed approval unlocks and preserves record for a deliberate retry', async () => {
  let modal;
  const run = page('features/workshop/reporting-approve/index.uvue', {
    uni: { showModal: options => { modal = options; } },
    request: () => Promise.reject(new Error('提交失败')),
  });
  run('rows.value = [{id: 7}]; approve(0)');
  await modal.success({ confirm: true });
  assert.equal(run('approving.value'), false);
  assert.equal(run('rows.value.length'), 1);
  assert.equal(run('errorTextValue.value'), '提交失败');
});
test('request in flight prevents another modal or POST and removes only approved record', async () => {
  const modals = []; const requests = []; let finish;
  const run = page('features/workshop/reporting-approve/index.uvue', {
    uni: { showModal: options => modals.push(options) },
    request: options => { requests.push(options); return new Promise(resolve => { finish = resolve; }); },
  });
  run('rows.value = [{id: 7}, {id: 8}]; approve(0)');
  const submitted = modals[0].success({ confirm: true });
  run('approve(0); approve(1)');
  assert.equal(modals.length, 1);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].path, '/api/v1/apps/kuaizhizao/reporting/7/approve');
  assert.equal(requests[0].body, null);
  finish({}); await submitted;
  assert.equal(run('rows.value.length'), 1);
  assert.equal(run('rows.value[0].id'), 8);
  run('approve(0)');
  assert.equal(modals.length, 2);
});
test('modal failure unlocks without submitting', () => {
  let modal;
  const run = page('features/workshop/reporting-approve/index.uvue', {
    uni: { showModal: options => { modal = options; } },
    request: () => { assert.fail('must not submit'); },
  });
  run('rows.value = [{id: 7}]; approve(0)');
  modal.fail();
  assert.equal(run('approving.value'), false);
  assert.equal(run('rows.value.length'), 1);
});
test('home retry updates warnings and known counts; overlapping refreshes are ignored', async () => {
  let finish; let count = 0;
  const run = page('shell/workbench/index.uvue', {
    blocks: [block('failed')],
    loadWorkbench: () => { count++; return new Promise(resolve => { finish = resolve; }); },
  });
  run('applyHome(blocks)');
  const retry = run('refresh()');
  await run('refresh()');
  assert.equal(count, 1);
  assert.equal(run('todoEmptyText.value'), '');
  finish([block()]); await retry;
  assert.equal(run('homeWarnings.value.length'), 0);
  assert.equal(run('todoEmptyText.value'), '当前故障与保养提醒均无待处理项');
});
