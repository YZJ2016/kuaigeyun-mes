import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
const require = createRequire(import.meta.url);
const ts = require('typescript');
for (const extension of ['.ts', '.tsx']) {
  require.extensions[extension] = (module, filename) => {
    const { outputText } = ts.transpileModule(readFileSync(filename, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020 },
    });
    module._compile(outputText, filename);
  };
}
const { resolveLayoutPlan } = require('../../src/components/uni-table/uniTableLayoutEngine.ts');
const { alignIotTableColumns } = require('../../src/apps/kuaiiot/components/table-parity.ts');
const columns = [
  { dataIndex: 'code', width: 140, uniTableKeepWidth: true },
  ...['name', 'threshold'].map(dataIndex => ({ dataIndex, minWidth: 140, uniTablePrimaryFlex: true, uniTableRemainderFlex: true, uniTableEqualRemainder: true })),
];
const layout = (input, width) => resolveLayoutPlan({ columns: input, containerWidth: width, includeSelection: false, scrollYEnabled: false });
test('IoT paired flexible columns share the available width equally', () => {
  const result = layout(columns, 1000);
  assert.deepEqual(result.columns.map(c => c.width), [140, 430, 430]);
  assert.equal(result.scrollX, 1000);
});
test('paired columns retain their minimum width on a narrow table', () => {
  const result = layout(columns, 300);
  assert.deepEqual(result.columns.map(c => c.width), [140, 140, 140]);
  assert.equal(result.scrollX, 420);
});
test('existing remainder columns retain their previous distribution without opt-in', () => {
  const result = layout(columns.map(({ uniTableEqualRemainder, ...column }) => column), 1000);
  assert.deepEqual(result.columns.map(c => c.width), [140, 720, 140]);
});
test('rule columns follow the reference order and optional columns remain available', () => {
  const input = ['name','code','tag_key','rule_type','severity','device_id','operator','threshold','action','cooldown_seconds'].map(dataIndex => ({ dataIndex, uniTableMarkerBadgeColumn: dataIndex === 'rule_type' }));
  const result = alignIotTableColumns(input, 'rules');
  assert.deepEqual(result.filter(c => c.defaultShow).map(c => c.dataIndex), ['code','tag_key','name','rule_type','severity','device_id','operator','threshold','action']);
  assert.equal(result.find(c => c.dataIndex === 'rule_type').width, 100);
  assert.equal(result.find(c => c.dataIndex === 'rule_type').uniTableMarkerBadgeColumn, false);
  assert.equal(result.find(c => c.dataIndex === 'cooldown_seconds').defaultShow, false);
});
