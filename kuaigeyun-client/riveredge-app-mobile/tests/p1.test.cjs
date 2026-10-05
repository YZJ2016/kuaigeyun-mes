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
test('report rejects invalid numeric suffixes, infinity and negatives',()=>{
  const run=runPage('features/workshop/scan-report/index.uvue');
  for(const bad of ['12abc','Infinity','-1','1e999','']) {
    assert.equal(run(`requiredNumber(${JSON.stringify(bad)}, '报工数量')`),null,bad);
  }
  assert.equal(run("requiredNumber('0', '不合格数量')"),0);
  assert.equal(run("requiredNumber('12.5', '工时')"),12.5);
});

test('recent entries isolate accounts and organizations and move repeats to front',()=>{
  let tenant='t1',user=1;const storage={};
  const run=runPage('shell/workbench/recent.uts',{
    getTenantId:()=>tenant,readSessionUserId:()=>user,
    uni:{getStorageSync:k=>storage[k],setStorageSync:(k,v)=>storage[k]=v},
  });
  run("exports.rememberRoute('/mes');exports.rememberRoute('/quality');exports.rememberRoute('/mes')");
  assert.deepEqual(Array.from(run('exports.readRecentRoutes()')),['/mes','/quality']);
  tenant='t2';assert.equal(run('exports.readRecentRoutes().length'),0);
  tenant='t1';user=2;assert.equal(run('exports.readRecentRoutes().length'),0);
  user=0;run("exports.rememberRoute('/hidden')");assert.equal(Object.keys(storage).length,1);
});

test('equipment selector uses binding IDs and paginated existing masters',async()=>{
  const calls=[];
  const run=runPage('features/equipment/selection.uts',{
    request:async o=>{calls.push(o);return o.path.includes('bindings')?[{scheme_id:7}]:{id:7,name:'日常点检'};},
  });
  const items=await run('exports.loadBoundSchemes(4)');
  assert.equal(calls[0].query.equipment_id,4);assert.equal(calls[0].query.scheme_type,'spot_check');
  assert.equal(calls[1].path,'/api/v1/apps/kuaizhizao/equipment-inspection-schemes/7');
  assert.equal(items[0].id,7);
  await run("exports.searchChoices('route','线路',20)");
  assert.equal(calls[2].query.skip,20);assert.equal(calls[2].query.keyword,'线路');
});

test('warehouse serial edits preserve line IDs and normalize the existing payload format',()=>{
  const run=runPage('features/warehouse/board.uvue',{serialList:s=>s.split(/[，,\n]/).map(x=>x.trim()).filter(Boolean)});
  run("lines.value=[{itemId:9,serialText:' A，B\\nC '}];serialInput.value=' D ';addSerial(0);removeSerial(0,1)");
  assert.equal(run('lines.value[0].itemId'),9);
  assert.equal(run('lines.value[0].serialText'),'A,C,D');
});

test('quality leaving requires confirmation and is blocked during uploads',()=>{
  const modals=[];
  const run=runPage('features/quality/components/inspection-board.uvue',{
    uni:{showModal:o=>modals.push(o)},
  });
  run('conducting.value=true;uploadingCount.value=1;closeConduct()');
  assert.equal(modals.length,0);assert.equal(run('conducting.value'),true);
  run('uploadingCount.value=0;closeConduct()');
  assert.equal(modals.length,1);assert.equal(run('conducting.value'),true);
  modals[0].success({confirm:false});assert.equal(run('conducting.value'),true);
  run('closeConduct()');modals[1].success({confirm:true});assert.equal(run('conducting.value'),false);
});

test('home recent entries are filtered by the current available navigation',()=>{
  const cell={uid:'1',key:'incoming',route:'/quality/incoming',missing:false,label:'来料检验'};
  const run=runPage('shell/workbench/index.uvue',{
    readSessionName:()=>'',getTenantName:()=>'',scopeTitle:s=>s,
    readRecentRoutes:()=>['/removed','/quality/incoming'],
  });
  run('applyHome('+JSON.stringify([{scope:'quality',sections:[{cells:[cell]}],errorText:'',badgeNote:'',showBadge:false,pendingCount:0,overdueCount:0}])+')');
  assert.equal(run('frequent.value.length'),1);
  assert.equal(run('frequent.value[0].route'),cell.route);
});

test('quality missing steps select the execution section and first missing item',async()=>{
  const run=runPage('features/quality/components/inspection-board.uvue',{nextTick:fn=>fn()});
  run("currentId.value=1;currentQty.value='1';qualifiedText.value='1';steps.value=[{legacy:true,judgment:'',name:'外观'}];activeStage.value=2");
  await run('submitConduct()');
  assert.equal(run('activeStage.value'),1);
  assert.equal(run('scrollTarget.value'),'quality-step-0');
});

test('changing equipment discards an old binding response',async()=>{
  let resolve;let invalidate;
  const props={kind:'scheme',equipmentId:'4',disabled:false};
  const run=runPage('features/equipment/components/master-picker.uvue',{
    defineProps:()=>props,watch:(_getter,callback)=>invalidate=callback,
    loadBoundSchemes:()=>new Promise(r=>resolve=r),
  });
  const pending=run('bound()');
  props.equipmentId='5';invalidate();resolve([{id:7,name:'旧设备方案'}]);await pending;
  assert.equal(run('rows.value.length'),0);
});
test('manual code uses the same resolution API and clears previous quantities',async()=>{
  const calls=[];
  const run=runPage('features/workshop/scan-report/index.uvue',{
    request: o=>{calls.push(o);return Promise.resolve([]);},readWorkOrderRows:()=>[],
  });
  run("manualCode.value=' WO7 ';reportedQuantity.value='8';workHours.value='2'");
  await run('resolveManual()');
  assert.equal(calls[0].path,'/api/v1/apps/kuaizhizao/work-orders/resolve-by-scan');
  assert.equal(calls[0].body.raw,'WO7');
  assert.equal(run('reportedQuantity.value'),'');
  assert.equal(run('workHours.value'),'');
});

for (const page of ['my-work-orders','work-orders']) {
  test(page+' paginates with active filters and retains rows on append failure',async()=>{
    const calls=[];let fail=false;
    const run=runPage('features/workshop/'+page+'/index.uvue',{
      request:o=>{calls.push(o);return fail?Promise.reject(new Error('offline')):Promise.resolve({data:[{id:calls.length}],total:3});},
      nextTick:fn=>fn(),
    });
    run("keyword.value=' WO ';status.value='released'");
    await run('search()');
    assert.equal(calls[0].query.keyword,'WO');
    assert.equal(calls[0].query.status,'released');
    assert.equal(calls[0].query.skip,0);
    assert.equal(calls[0].query.limit,20);
    if(page==='my-work-orders') assert.equal(calls[0].query.assigned_worker_id,1);
    run("keyword.value='unapplied'");
    await run('loadMore()');
    assert.equal(calls[1].query.skip,1);
    assert.equal(calls[1].query.keyword,'WO');
    fail=true;await run('loadMore()');
    assert.equal(run('rows.value.length'),2);
    run('listScrollTop.value=480;openDetail(0);closeDetail()');
    assert.equal(run('scrollTop.value'),480);
    assert.equal(run('status.value'),'released');
  });
}

test('home starts scopes concurrently and retains individual failures',async()=>{
  const pending=[];
  const run=runPage('shell/workbench/load.uts',{
    getToken:()=> 'token',installedPackages:()=>['a','b'],packageScope:p=>p,
    packageBadge:()=>null,apiGet:(url,q)=>new Promise((resolve,reject)=>pending.push({resolve,reject})),
  });
  const result=run('loadWorkbench()');
  assert.equal(pending.length,2);
  pending[0].reject(new Error('offline'));pending[1].resolve([]);
  const blocks=await result;
  assert.equal(blocks.length,1);assert.equal(blocks[0].scope,'a');
});
