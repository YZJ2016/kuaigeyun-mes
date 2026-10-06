const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('../../../riveredge-frontend/node_modules/typescript');
const root = path.resolve(__dirname, '..');
function runPage(file, extra = {}) {
  const source = fs.readFileSync(path.join(root, file), 'utf8');
  const script = file.endsWith('.uts') ? source : source.match(/<script setup lang="uts">([\s\S]*?)<\/script>/)[1];
  const globals = { exports: {}, ref: v => ({value:v}), computed: fn => ({get value(){return fn();}}),
    UTSJSONObject: class {set(k,v){this[k]=v;} getString(k){return this[k]??null;} getNumber(k){return this[k]??null;}},
    onLoad(){}, onShow(){}, onMounted(){}, onBackPress(){}, onBeforeUnmount(){}, defineOptions(){}, defineProps: () => ({}), watch(){}, defineEmits:()=>()=>{},
    fieldText: (row,k) => row?.[k] == null ? '' : String(row[k]), fieldNumber: (row,k) => Number(row?.[k]??0),
    fieldId: row => Number(row?.id??0), readRows: p => Array.isArray(p)?p:p?.data??p?.items??[],
    errorText: e=>e.message, firstText: (r,ks)=>ks.map(k=>r[k]).find(Boolean)??'',
    toast(){}, nowIso:()=> '2026-10-05T00:00:00Z', readCurrentUser:()=>({id:1,name:'张工'}),
    ...extra};
  const ctx = vm.createContext(globals);
  const output = ts.transpileModule(script.replace(/import[\s\S]*?from ['"][^'"]+['"]/g,''),
    {compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS},reportDiagnostics:true});
  assert.equal((output.diagnostics??[]).filter(d=>d.category===ts.DiagnosticCategory.Error).length,0, file);
  vm.runInContext(output.outputText,ctx);
  return expr=>vm.runInContext(expr,ctx);
}

test('reporting history pages with worker_id, commits skip on success and retries the same page', async () => {
  const calls = [];
  let fail = false;
  const run = runPage('features/workshop/reporting-history/index.uvue', {
    request: o => { calls.push(o); return fail ? Promise.reject(new Error('offline')) : Promise.resolve({data:[{id:calls.length}],total:3}); },
  });
  await run('load()');
  assert.equal(run('loadMode.value'),'initial');
  assert.equal(run('listLoaded.value'),true);
  assert.equal(calls[0].query.worker_id,1);
  assert.equal(calls[0].query.skip,0);
  assert.equal(calls[0].query.limit,20);
  assert.equal(run('total.value'),3);
  await run('refreshList()');
  assert.equal(run('loadMode.value'),'refresh');
  assert.equal(calls[1].query.skip,0);
  await run('loadMore()');
  assert.equal(run('loadMode.value'),'more');
  assert.equal(calls[2].query.skip,1);
  fail = true;
  await run('loadMore()');
  assert.equal(calls[3].query.skip,2);
  assert.equal(run('rows.value.length'),2);
  assert.equal(run('errorTextValue.value'),'offline');
  await run('retry()');
  assert.equal(calls[4].query.skip,2);
  assert.equal(run('rows.value.length'),2);
});

test('reporting history failure on first page keeps rows and retry reloads', async () => {
  const run = runPage('features/workshop/reporting-history/index.uvue', {
    request: () => Promise.reject(new Error('断网')),
  });
  run('rows.value=[{work_order_code:"KEEP"}]');
  await run('load()');
  assert.equal(run('loading.value'),false);
  assert.equal(run('errorTextValue.value'),'断网');
  assert.equal(run('rows.value[0].work_order_code'),'KEEP');
});

test('performance page sends period plus paging and reloads on month change', async () => {
  const calls = [];
  let watcher = null;
  let fail = false;
  const run = runPage('features/workshop/performance/index.uvue', {
    currentPeriod: () => '2026-02',
    watch: (g, cb) => { watcher = cb; },
    request: o => { calls.push(o); return fail ? Promise.reject(new Error('offline')) : Promise.resolve({items:[{id:calls.length}],total:3}); },
  });
  run('period.value=currentPeriod();pickedDate.value=period.value+"-01"');
  if (watcher) watcher('2026-02-01');
  await run('load()');
  assert.equal(calls[0].query.period,'2026-02');
  assert.equal(calls[0].query.employee_id,1);
  assert.equal(calls[0].query.skip,0);
  assert.equal(calls[0].query.limit,20);
  assert.equal(run('total.value'),3);
  await run('loadMore()');
  assert.equal(calls[1].query.skip,1);
  run('pickedDate.value="2026-01-15"');
  if (watcher) watcher('2026-01-15');
  for (let i=0;i<5;i++) await Promise.resolve();
  assert.equal(run('period.value'),'2026-01');
  assert.equal(calls[2].query.period,'2026-01');
  assert.equal(calls[2].query.skip,0);
  fail = true;
  await run('loadMore()');
  assert.equal(calls[3].query.skip,1);
  assert.equal(run('rows.value.length'),1);
  assert.equal(run('errorTextValue.value'),'offline');
  await run('retry()');
  assert.equal(calls[4].query.skip,1);
  assert.equal(run('rows.value.length'),1);
});
