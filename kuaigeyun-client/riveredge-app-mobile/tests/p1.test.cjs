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

test('url tenant id hides the organization block until a name is known',async()=>{
  let id='', name='';
  const run=runPage('shell/login/flow.uts',{
    loginConnected:()=>true, readMobileEntryDomain:()=>'', readBrowserPath:()=>'', findEntryByRoute:()=>null,
    readBrowserQuery:()=>'', acquireLoginCode:async()=>({connected:true,code:''}), getToken:()=>'',
    getTenantId:()=>id, setTenantId:value=>{id=value;}, getTenantName:()=>name, setTenantName:value=>{name=value;},
  });
  const hidden=await run('bootLogin({tenant_id:"1"})');
  assert.equal(hidden.hideOrg,true);
  assert.equal(id,'1');
  name='星环精密';
  const shown=await run('bootLogin({tenant_id:"1"})');
  assert.equal(shown.hideOrg,false);
  assert.equal(name,'星环精密');
  const switched=await run('bootLogin({tenant_id:"2"})');
  assert.equal(switched.hideOrg,true);
  assert.equal(name,'');
});

test('home todo shows the entry name under the title',()=>{
  const cell={uid:'faults',key:'faults',route:'/equipment/faults',missing:false,label:'报修维修'};
  const run=runPage('shell/workbench/index.uvue',{
    readSessionName:()=>'',getTenantName:()=>'',scopeTitle:s=>s,readRecentRoutes:()=>[],
  });
  run('applyHome('+JSON.stringify([{scope:'equipment',sections:[{cells:[cell]}],errorText:'',badgeNote:'',showBadge:true,pendingCount:2,pendingText:'2 条待处理',overdueCount:0,overdueText:''}])+')');
  assert.equal(run('todos.value.length'),1);
  assert.equal(run('todos.value[0].title'),'待处理故障');
  assert.equal(run('todos.value[0].subtitle'),'报修维修');
});

test('home section title is 今日待办',()=>{
  const source=fs.readFileSync(path.join(root,'shell/workbench/index.uvue'),'utf8');
  assert.match(source,/<text class="home-section">今日待办<\/text>/);
});

test('home today todos use the reporting list total and inspection summary',async()=>{
  const calls=[];
  const reporting={uid:'r',key:'reporting-approve',route:'/mes/reporting-approve',missing:false,label:'报工审核'};
  const hub={uid:'q',key:'quality-hub',route:'/quality',missing:false,label:'待检验'};
  const picking={uid:'p',key:'pickings',route:'/wms/pickings',missing:false,label:'生产领料'};
  const faults={uid:'f',key:'faults',route:'/equipment/faults',missing:false,label:'报修维修'};
  const reminders={uid:'m',key:'maintenance-reminders',route:'/equipment/maintenance-reminders',missing:false,label:'维护提醒'};
  const blocks=[
    {scope:'workshop',sections:[{cells:[reporting]}],errorText:'',badgeNote:'',showBadge:false,pendingCount:0,overdueCount:0,pendingText:'',overdueText:''},
    {scope:'warehouse',sections:[{cells:[picking]}],errorText:'',badgeNote:'',showBadge:false,pendingCount:0,overdueCount:0,pendingText:'',overdueText:''},
    {scope:'quality',sections:[{cells:[hub]}],errorText:'',badgeNote:'',showBadge:false,pendingCount:0,overdueCount:0,pendingText:'',overdueText:''},
    {scope:'equipment',sections:[{cells:[faults,reminders]}],errorText:'',badgeNote:'',showBadge:true,pendingCount:2,pendingText:'2',overdueCount:1,overdueText:'1'},
  ];
  const run=runPage('shell/workbench/index.uvue',{
    readSessionName:()=>'',getTenantName:()=>'',scopeTitle:s=>s,readRecentRoutes:()=>[],
    getToken:()=>'token',takePendingEntry:()=>'',
    loadWorkbench:async()=>blocks,
    request:options=>{
      calls.push(options);
      if(String(options.path).includes('/reporting')) return Promise.resolve({success:true,data:[{id:1}],total:4});
      return Promise.resolve({pending_incoming:1,pending_process:2,pending_finished:0,pending_oqc:3});
    },
  });
  await run('refresh()');
  assert.deepEqual(calls.map(call=>call.path),[
    '/api/v1/apps/kuaizhizao/reporting',
    '/api/v1/apps/kuaizhizao/quality/inspection-center-summary',
  ]);
  assert.equal(calls[0].query.status,'pending');
  assert.equal(calls[0].query.limit,'1');
  assert.equal(run('todos.value.map(todo => todo.title).join(",")'),'待审报工,待检验,待处理故障,逾期保养');
  assert.equal(run('todos.value[0].subtitle'),'报工审核');
  assert.equal(run('todos.value[0].countText'),'4');
  assert.equal(run('todos.value[0].route'),'/mes/reporting-approve');
  assert.equal(run('todos.value[1].subtitle'),'待检验');
  assert.equal(run('todos.value[1].countText'),'6');
  assert.equal(run('todos.value[1].route'),'/quality');
  assert.equal(run('todos.value[2].subtitle'),'报修维修');
  assert.equal(run('todos.value[3].subtitle'),'维护提醒');
});

test('home today todos stay visible when the known count is zero',()=>{
  const reporting={uid:'r',key:'reporting-approve',route:'/mes/reporting-approve',missing:false,label:'报工审核'};
  const hub={uid:'q',key:'quality-hub',route:'/quality',missing:false,label:'待检验'};
  const faults={uid:'f',key:'faults',route:'/equipment/faults',missing:false,label:'报修维修'};
  const reminders={uid:'m',key:'maintenance-reminders',route:'/equipment/maintenance-reminders',missing:false,label:'维护提醒'};
  const run=runPage('shell/workbench/index.uvue',{
    readSessionName:()=>'',getTenantName:()=>'',scopeTitle:s=>s,readRecentRoutes:()=>[],
  });
  const blocks=[
    {scope:'workshop',sections:[{cells:[reporting]}],errorText:'',badgeNote:'',showBadge:false,pendingCount:0,overdueCount:0,pendingText:'',overdueText:''},
    {scope:'quality',sections:[{cells:[hub]}],errorText:'',badgeNote:'',showBadge:false,pendingCount:0,overdueCount:0,pendingText:'',overdueText:''},
    {scope:'equipment',sections:[{cells:[faults,reminders]}],errorText:'',badgeNote:'',showBadge:true,pendingCount:0,pendingText:'0',overdueCount:0,overdueText:'0'},
  ];
  const measured=[{key:'reporting-approve',count:0,failed:false},{key:'quality-hub',count:0,failed:false}];
  run('applyHome('+JSON.stringify(blocks)+','+JSON.stringify(measured)+')');
  assert.equal(run('todos.value.map(todo => todo.title).join(",")'),'待审报工,待检验,待处理故障,逾期保养');
  assert.equal(run('todos.value.every(todo => todo.countText === "0" && todo.tone === "neutral")'),true);
  assert.equal(run('todoEmptyText.value'),'');
});

test('home today todos do not invent a count when the matching total is missing',async()=>{
  const reporting={uid:'r',key:'reporting-approve',route:'/mes/reporting-approve',missing:false,label:'报工审核'};
  const hub={uid:'q',key:'quality-hub',route:'/quality',missing:false,label:'待检验'};
  const blocks=[
    {scope:'workshop',sections:[{cells:[reporting]}],errorText:'',badgeNote:'',showBadge:false,pendingCount:0,overdueCount:0,pendingText:'',overdueText:''},
    {scope:'quality',sections:[{cells:[hub]}],errorText:'',badgeNote:'',showBadge:false,pendingCount:0,overdueCount:0,pendingText:'',overdueText:''},
  ];
  const run=runPage('shell/workbench/index.uvue',{
    readSessionName:()=>'',getTenantName:()=>'',scopeTitle:s=>s,readRecentRoutes:()=>[],
    getToken:()=>'token',takePendingEntry:()=>'',
    loadWorkbench:async()=>blocks,
    request:options=>{
      if(String(options.path).includes('/reporting')) return Promise.resolve({data:[{id:1},{id:2}]});
      return Promise.reject(new Error('汇总失败'));
    },
  });
  await run('refresh()');
  assert.equal(run('todos.value.length'),0);
  assert.match(run('homeWarnings.value.join(" ")'),/待处理数量未能读取/);
  const hidden={...reporting,missing:true};
  run('applyHome('+JSON.stringify([{scope:'workshop',sections:[{cells:[hidden]}],errorText:'',badgeNote:'',showBadge:false,pendingCount:0,overdueCount:0,pendingText:'',overdueText:''}])+','+JSON.stringify([{key:'reporting-approve',count:9,failed:false}])+')');
  assert.equal(run('todos.value.length'),0);
});

test('home recent entries are filtered by the current available navigation',()=>{
  const cell={uid:'1',key:'incoming',route:'/quality/incoming',missing:false,label:'来料检验'};
  const run=runPage('shell/workbench/index.uvue',{
    readSessionName:()=>'',getTenantName:()=>'',scopeTitle:s=>s,
    readRecentRoutes:()=>['/removed','/quality/incoming'],
  });
  run('applyHome('+JSON.stringify([{scope:'quality',sections:[{cells:[cell]}],errorText:'',badgeNote:'',showBadge:false,pendingCount:0,overdueCount:0,pendingText:'',overdueText:''}])+')');
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
      assert.equal(run('loadMode.value'),'initial');
      assert.equal(run('listLoaded.value'),true);
    assert.equal(calls[0].query.keyword,'WO');
    assert.equal(calls[0].query.status,'released');
    assert.equal(calls[0].query.skip,0);
    assert.equal(calls[0].query.limit,20);
    if(page==='my-work-orders') assert.equal(calls[0].query.assigned_worker_id,1);
    run("keyword.value='unapplied'");
      await run('loadMore()');
      assert.equal(run('loadMode.value'),'more');
    assert.equal(calls[1].query.skip,1);
    assert.equal(calls[1].query.keyword,'WO');
    fail=true;await run('loadMore()');
      assert.equal(run('rows.value.length'),2);
      await run('refreshList()');
      assert.equal(run('loadMode.value'),'refresh');
    run('listScrollTop.value=480;openDetail(0);closeDetail()');
    assert.equal(run('scrollTop.value'),480);
    assert.equal(run('status.value'),'released');
  });
}

test('entered list stays loading until the current response and drops a stale one', async () => {
  let first; let second; let calls = 0;
  const run = runPage('features/workshop/reporting-history/index.uvue', {
    readCurrentUser: () => ({ id: 1, name: '张工' }),
    request: () => {
      calls += 1;
      if (calls === 1) return new Promise(resolve => { first = resolve; });
      return new Promise(resolve => { second = resolve; });
    },
  });
  const older = run('load()');
  assert.equal(run('loading.value'), true);
  const newer = run('load()');
  assert.equal(run('loading.value'), true);
  first({ data: [{ work_order_code: 'OLD' }] });
  await older;
  assert.equal(run('loading.value'), true);
  assert.equal(run('rows.value.length'), 0);
  second({ data: [{ work_order_code: 'NEW' }] });
  await newer;
  assert.equal(run('loading.value'), false);
  assert.equal(run('rows.value.length'), 1);
  assert.equal(run('rows.value[0].work_order_code'), 'NEW');
});

test('failed list load ends loading and keeps rows already on the page', async () => {
  const run = runPage('features/workshop/reporting-history/index.uvue', {
    readCurrentUser: () => ({ id: 1, name: '张工' }),
    request: () => Promise.reject(new Error('断网')),
  });
  run('rows.value=[{work_order_code:"KEEP"}]');
  await run('load()');
  assert.equal(run('loading.value'), false);
  assert.equal(run('errorTextValue.value'), '断网');
  assert.equal(run('rows.value.length'), 1);
  assert.equal(run('rows.value[0].work_order_code'), 'KEEP');
});

test('equipment repair list shows loading and ignores an older response', async () => {
  let first; let second; let calls = 0;
  const run = runPage('features/equipment/repairs/index.uvue', {
    joinParts: parts => parts.filter(Boolean).join(' '),
    readError: err => err.message,
    request: () => {
      calls += 1;
      if (calls === 1) return new Promise(resolve => { first = resolve; });
      return new Promise(resolve => { second = resolve; });
    },
  });
  run('rows.value=[{rowKey:"keep",title:"旧维修"}]');
  const older = run('loadList()');
  assert.equal(run('loading.value'), true);
  assert.equal(run('rows.value[0].title'), '旧维修');
  const newer = run('loadList()');
  first([{ repair_no: 'OLD', uuid: 'old', status: '已完成' }]);
  await older;
  assert.equal(run('rows.value[0].title'), '旧维修');
  assert.equal(run('loading.value'), true);
  second([{ repair_no: 'NEW', uuid: 'new', status: '已完成' }]);
  await newer;
  assert.equal(run('loading.value'), false);
  assert.equal(run('rows.value[0].title'), 'NEW');
  const failed = runPage('features/equipment/repairs/index.uvue', {
    joinParts: parts => parts.filter(Boolean).join(' '),
    readError: err => err.message,
    request: () => Promise.reject(new Error('维修列表失败')),
  });
  failed('rows.value=[{title:"仍在"}]');
  await failed('loadList()');
  assert.equal(failed('loading.value'), false);
  assert.equal(failed('errorText.value'), '维修列表失败');
  assert.equal(failed('rows.value[0].title'), '仍在');
});

test('app shell refresh ends after failure and does not apply an older scope list', async () => {
  let first; let second; let calls = 0;
  const run = runPage('shell/apps/index.uvue', {
    getToken: () => 'token',
    loadWorkbench: () => {
      calls += 1;
      if (calls === 1) return new Promise(resolve => { first = resolve; });
      return new Promise(resolve => { second = resolve; });
    },
  });
  const older = run('refresh()');
  assert.equal(run('loading.value'), true);
  const newer = run('refresh()');
  first([{ scope: 'old', sections: [] }]);
  await older;
  assert.equal(run('loading.value'), true);
  assert.equal(run('scopes.value.length'), 0);
  second([]);
  await newer;
  assert.equal(run('loading.value'), false);
  assert.equal(run('empty.value'), true);
  const failed = runPage('shell/apps/index.uvue', {
    getToken: () => 'token',
  });
  failed('loadWorkbench = () => Promise.reject(new Error("入口失败"))');
  await failed('refresh()');
  assert.equal(failed('loading.value'), false);
  assert.equal(failed('errorText.value'), '入口失败');
  assert.equal(failed('scopes.value.length'), 0);
});

test('home starts scopes concurrently and retains individual failures',async()=>{
  const pending=[];
  const run=runPage('shell/workbench/load.uts',{
    getToken:()=> 'token',getTenantId:()=> 't1',installedPackages:()=>['a','b'],packageScope:p=>p,
    packageBadge:()=>null,apiGet:(url,q)=>new Promise((resolve,reject)=>pending.push({resolve,reject})),
  });
  const result=run('loadWorkbench()');
  assert.equal(pending.length,2);
  pending[0].reject(new Error('offline'));pending[1].resolve([]);
  const blocks=await result;
  assert.equal(blocks.length,1);assert.equal(blocks[0].scope,'a');
});
