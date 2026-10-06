const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('../../../riveredge-frontend/node_modules/typescript');
const root=path.resolve(__dirname,'..');
function script(file,props={},extra={}) {
  const text=fs.readFileSync(path.join(root,file),'utf8');
  const source=file.endsWith('.uts')?text:text.match(/<script setup lang="uts">([\s\S]*?)<\/script>/)[1];
  const events=[];
  const ctx=vm.createContext({exports:{},ref:v=>({value:v}),computed:f=>({get value(){return f();}}),defineProps:()=>props,
    defineEmits:()=> (...args)=>events.push(args),defineOptions(){},watch(){},onShow(){},onMounted(){},onLoad(){},
    UTSJSONObject:class {set(k,v){this[k]=v;}},...extra});
  vm.runInContext(ts.transpileModule(source.replace(/import[\s\S]*?from ['"][^'"]+['"]/g,''),{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}}).outputText,ctx);
  return {run:e=>vm.runInContext(e,ctx),events};
}
test('date field emits only a valid selected date and respects disabled state',()=>{
  const util=script('shared/ui/date.uts');
  const props={modelValue:'',disabled:false,required:false};
  const page=script('shared/ui/date-field.uvue',props,{isDateText:s=>util.run('exports.isDateText('+JSON.stringify(s)+')'),todayDate:()=> '2026-10-06'});
  page.run("onChange({detail:{value:'2026-02-30'}})");assert.equal(page.events.length,0);
  page.run("onChange({detail:{value:'2026-10-07'}})");assert.deepEqual(page.events[0],['update:modelValue','2026-10-07']);
  props.disabled=true;page.run("onChange({detail:{value:'2026-10-08'}});clearDate()");assert.equal(page.events.length,1);
  props.disabled=false;page.run('clearDate()');assert.deepEqual(page.events[1],['update:modelValue','']);
});
test('shared actions and selections reject busy and disabled activation',()=>{
  for(const file of ['action-button','selection-row']) {
    const props={disabled:true,busy:false};const page=script('shared/ui/'+file+'.uvue',props);
    page.run('activate()');assert.equal(page.events.length,0);
    props.disabled=false;props.busy=true;page.run('activate()');assert.equal(page.events.length,0);
    props.busy=false;page.run('activate()');assert.equal(page.events.length,1);
  }
});
test('compact choice blocks disabled activation without changing selected state',()=>{
  const props={disabled:true,selected:true,label:'合格'};
  const page=script('shared/ui/choice-button.uvue',props);
  page.run('activate()');assert.equal(page.events.length,0);
  props.disabled=false;page.run('activate()');assert.deepEqual(page.events[0],['choose']);
  assert.equal(props.selected,true);
});
test('slotted action cards block disabled activation',()=>{
  const props={disabled:true,variant:'card'};
  const page=script('shared/ui/action-card.uvue',props);
  page.run('activate()');assert.equal(page.events.length,0);
  props.disabled=false;page.run('activate()');assert.deepEqual(page.events[0],['press']);
});
test('loading feedback suppresses short requests and cleans timers on restart and unmount',()=>{
  const props={active:false,mode:'refresh',label:''};let update,unmount,id=0;
  const timers=new Map();
  const page=script('shared/ui/load-feedback.uvue',props,{
    watch:(getter,callback)=>{update=callback;callback(getter());},onUnmounted:callback=>{unmount=callback;},
    setTimeout:(callback,delay)=>{const key=++id;timers.set(key,{callback:()=>{timers.delete(key);callback();},delay});return key;},clearTimeout:key=>timers.delete(key),
  });
  props.active=true;update(true);assert.equal(page.run('visible.value'),false);assert.equal(timers.size,2);
  props.active=false;update(false);assert.equal(timers.size,0);assert.equal(page.run('visible.value'),false);
  props.active=true;update(true);const shown=[...timers.values()].find(t=>t.delay===160);shown.callback();
  assert.equal(page.run('visible.value'),true);
  [...timers.values()].find(t=>t.delay===8000).callback();assert.equal(page.run('slow.value'),true);
  props.active=false;update(false);assert.equal(page.run('slow.value'),false);
  props.active=true;update(true);assert.equal(timers.size,2);unmount();assert.equal(timers.size,0);
});
test('warehouse pagination remains locked while refreshing or submitting',()=>{
  const page=script('features/warehouse/board.uvue',{kind:'inventory-query'});
  page.run('loading.value=true;loadMore()');assert.equal(page.run('page.value'),1);assert.equal(page.run('skip.value'),0);
  page.run('loading.value=false;busy.value=true;loadMore()');assert.equal(page.run('page.value'),1);assert.equal(page.run('skip.value'),0);
});
test('equipment fault detail reports waiting and unlocks after failure without duplicate requests',async()=>{
  let reject;const calls=[];
  const page=script('features/equipment/faults/index.uvue',{}, {
    request:o=>{calls.push(o);return new Promise((resolve,no)=>{reject=no;});},readError:e=>e.message,
  });
  const pending=page.run("openFault('fault-1')");assert.equal(page.run('detailLoading.value'),true);
  await page.run("openFault('fault-2')");assert.equal(calls.length,1);
  assert.equal(calls[0].method,'GET');assert.match(calls[0].url,/equipment-faults\/fault-1$/);
  reject(new Error('网络失败'));await pending;
  assert.equal(page.run('detailLoading.value'),false);assert.equal(page.run('errorText.value'),'网络失败');
});
test('registered pages and their local components have no clickable text or view controls',()=>{
  const pages=JSON.parse(fs.readFileSync(path.join(root,'pages.json'),'utf8')).pages;
  const visited=new Set();
  function inspect(file) {
    if(visited.has(file)||file.includes(path.sep+'uni_modules'+path.sep))return;
    visited.add(file);const source=fs.readFileSync(file,'utf8');
    const template=source.match(/<template>([\s\S]*?)<\/template>/)[1];
    assert.doesNotMatch(template,/<(?:view|text)\b(?:"[^"]*"|[^">])*@click=/,file);
    for (const match of source.matchAll(/from\s+['"](\.[^'"]+\.uvue)['"]/g)) inspect(path.resolve(path.dirname(file),match[1]));
  }
  for(const page of pages)inspect(path.join(root,page.path+'.uvue'));
  assert.equal(pages.length,51);
});
test('login freezes organization selection and prevents competing authentication',async()=>{
  const chosen=[],calls=[];let finish;
  const page=script('shell/login/index.uvue',{}, {
    chooseTenant:id=>chosen.push(id),setTenantName(){},
    loginWithPassword:async(name,password)=>{calls.push([name,password]);return new Promise(resolve=>{finish=resolve;});},
    searchTenants:async()=>{throw new Error('unexpected search');},
    uni:{reLaunch(){}},
  });
  page.run("tenants.value=[{tenantId:'7',tenantName:'车间',tenantDomain:'shop'}];username.value='operator';passwordText.value='password';searching.value=true");
  await page.run('onPasswordLogin()');assert.equal(calls.length,0);
  page.run('onChoose(0)');assert.equal(chosen.length,0);
  page.run('searching.value=false;onChoose(0)');assert.deepEqual(chosen,['7']);
  const pending=page.run('onPasswordLogin()');
  page.run('onChoose(0)');await page.run('onSearch()');await page.run('onPasswordLogin()');
  assert.equal(chosen.length,1);assert.equal(calls.length,1);
  finish('账号或密码错误');await pending;
  assert.equal(page.run('loggingIn.value'),false);assert.equal(page.run('message.value'),'账号或密码错误');
});
test('quality choices retain clearable single and multi selection and lock during upload',()=>{
  const page=script('features/quality/components/inspection-board.uvue');
  page.run("steps.value=[{options:[{value:'A'},{value:'B'}],value:'',multiSelected:[],judgment:'',photos:[]}]");
  page.run('pickOption(0,0)');assert.equal(page.run('steps.value[0].value'),'A');
  page.run('pickOption(0,0)');assert.equal(page.run('steps.value[0].value'),'');
  page.run('toggleOption(0,0);toggleOption(0,1);toggleOption(0,0)');
  assert.deepEqual(Array.from(page.run('steps.value[0].multiSelected')),['B']);
  page.run("uploadingCount.value=1;pickOption(0,1);toggleOption(0,1);pickLegacy(0,'fail');toggleNa(0);pickOverall('fail')");
  assert.equal(page.run('steps.value[0].value'),'');assert.equal(page.run('steps.value[0].judgment'),'');
  assert.deepEqual(Array.from(page.run('steps.value[0].multiSelected')),['B']);
  assert.equal(page.run('overallJudgment.value'),'');
  page.run("uploadingCount.value=0;submitting.value=true;pickResult('不合格')");
  assert.equal(page.run('inspectionResult.value'),'合格');
});
test('navigation retains home interception and return behavior',()=>{
  const calls=[];const props={title:'',holdHome:true};
  const page=script('shared/ui/home-link.uvue',props,{
    getCurrentPages:()=>[{route:'features/quality/incoming/index',getPageStyle:()=>({getString:()=> '来料检验'})}],
    uni:{navigateBack:()=>calls.push('back'),reLaunch:o=>calls.push(o.url)},
  });
  assert.equal(page.run('barTitle.value'),'来料检验');assert.equal(page.run('showActions.value'),true);
  page.run('onHome()');assert.deepEqual(page.events[0],['home']);assert.equal(calls.length,0);
  props.holdHome=false;page.run('onHome();onBack()');assert.deepEqual(calls,['/shell/workbench/index','back']);
});
test('account actions keep confirmation and cancellation makes no request',()=>{
  const modals=[],requests=[],routes=[];
  const page=script('shell/account/index.uvue',{}, {
    apiPost:(url)=>requests.push(url),
    uni:{showModal:o=>modals.push(o),navigateTo:o=>routes.push(o.url)},
  });
  page.run('openEdit();openPassword();askUnbind();askLogout()');
  assert.deepEqual(routes,['/shell/account/edit','/shell/account/password']);
  assert.equal(modals.length,2);assert.equal(modals[0].title,'解除绑定');assert.equal(modals[1].title,'退出登录');
  modals[0].success({confirm:false});modals[1].success({confirm:false});assert.equal(requests.length,0);
});
test('mold borrowing keeps optional dates and blocks duplicate submission',async()=>{
  const calls=[];let finish;
  const util=script('shared/ui/date.uts');
  const page=script('features/mold/mold-borrows/index.uvue',{}, {
    isDateText:s=>util.run('exports.isDateText('+JSON.stringify(s)+')'),
    putText:(body,key,value)=>{if(value.trim())body.set(key,value.trim());},
    apiPost:(url,body)=>{calls.push({url,body});return new Promise(resolve=>{finish=resolve;});},
    apiGetRows:async()=>[],withQuery:(p,q)=>p+'?'+q,
    MOLD_BORROWS:'/api/v1/apps/kuaizhizao/mold-borrows',
    errorText:e=>e.message,fieldText:(o,k)=>o[k]??'',joinParts:a=>a.join(' '),
  });
  page.run("moldId.value=9;borrowDate.value='2026-02-30'");await page.run('createBorrow()');
  assert.equal(calls.length,0);
  page.run("borrowDate.value='2026-10-06';expectedReturnDate.value='';borrowerName.value='操作人'");
  const first=page.run('createBorrow()');await page.run('createBorrow()');
  assert.equal(calls.length,1);assert.equal(page.run('submitting.value'),true);
  assert.equal(calls[0].body.mold_id,9);assert.equal(calls[0].body.borrow_date,'2026-10-06');
  assert.equal(calls[0].body.borrower_name,'操作人');assert.equal('expected_return_date' in calls[0].body,false);
  finish({document_no:'B1'});await first;assert.equal(page.run('submitting.value'),false);
});
test('equipment date fields preserve optional models and busy guards',()=>{
  for (const [page,model] of [['spot-checks','checkDateText'],['spot-check-conduct','checkDateText'],['route-patrols','patrolDateText']]) {
    const source=fs.readFileSync(path.join(root,'features/equipment/'+page+'/index.uvue'),'utf8');
    const field=source.match(new RegExp('<date-field[^>]*v-model="'+model+'"[^>]*>'))[0];
    assert.match(field,/:disabled="loading \|\| busy"/);assert.doesNotMatch(field,/\brequired\b/);
    assert.match(source,new RegExp('const '+model+" = ref\\(''\\)"));
  }
});
test('shared date validation covers leap years and malformed dates',()=>{
  const page=script('shared/ui/date.uts');
  for(const value of ['2024-02-29','2000-02-29','2026-10-06']) assert.equal(page.run('exports.isDateText('+JSON.stringify(value)+')'),true,value);
  for(const value of ['1900-02-29','2026-02-29','2026-04-31','0000-01-01','2026-13-01','2026-01-00','2026-1-01']) assert.equal(page.run('exports.isDateText('+JSON.stringify(value)+')'),false,value);
});

test('mold repair preserves the existing free-text urgency and payload contract',async()=>{
  const calls=[];
  const page=script('features/mold/mold-repairs/index.uvue',{}, {
    isDateText:()=>true,toPcLines:()=>[],
    putText:(body,key,value)=>{if(value.trim())body.set(key,value.trim());},
    apiPost:async (url,body)=>{calls.push({url,body});return {document_no:'R1'};},
    apiGetRows:async()=>[],withQuery:(p,q)=>p+'?'+q,
    MOLD_REPAIRS:'/api/v1/apps/kuaizhizao/mold-repairs',
    errorText:e=>e.message,fieldText:(o,k)=>o[k]??'',joinParts:a=>a.join(' '),
  });
  page.run("moldId.value=7;urgency.value='x'.repeat(33)");await page.run('createRepair()');
  assert.equal(calls.length,0);assert.match(page.run('hint.value'),/32/);
  page.run("urgency.value='现场加急';repairDate.value='2026-10-06';submitting.value=true");await page.run('createRepair()');
  assert.equal(calls.length,0);
  page.run('submitting.value=false');await page.run('createRepair()');
  assert.equal(calls.length,1);assert.equal(calls[0].body.mold_id,7);
  assert.equal(calls[0].body.urgency,'现场加急');assert.equal(calls[0].body.repair_date,'2026-10-06');
});

test('badge retains explicit zero and uses the installed uni-ui x implementation',()=>{
  const text=fs.readFileSync(path.join(root,'shared/ui/status-badge.uvue'),'utf8');
  assert.ok(text.includes(':always-wrap-with-content="true"'));
  assert.ok(text.includes('uni_modules/uni-badge-view/'));
  const page=script('shared/ui/status-badge.uvue',{value:'0',tone:'danger'});
  assert.match(page.run('badgeStyle.value'),/#991B1B/);
});

test('quality list settlement ignores superseded responses and retains rows during refresh',async()=>{
  const pending=[];
  const page=script('features/quality/components/inspection-board.uvue',{listPath:'/quality',customTable:''},{request:()=>new Promise((resolve,reject)=>pending.push({resolve,reject})),readRows:v=>v,errorText:()=> '读取失败'});
  const first=page.run('loadList()');const second=page.run('loadList()');
  pending[0].resolve([{id:1}]);await first;
  assert.equal(page.run('loading.value'),true);assert.equal(page.run('loadSettled.value'),false);
  pending[1].resolve([{id:2}]);await second;
  assert.equal(page.run('loading.value'),false);assert.equal(page.run('loadSettled.value'),true);
  const refresh=page.run('loadList()');assert.equal(page.run('rows.value[0].id'),2);
  pending[2].reject(new Error('network'));await refresh;
  assert.equal(page.run('loading.value'),false);assert.equal(page.run('errorTextValue.value'),'读取失败');
});
test('inspection text inputs freeze during upload and submission',()=>{
  const page=script('features/quality/components/inspection-board.uvue');
  page.run("steps.value=[{value:'old'}];customFields.value=[{value:'old'}];qualifiedText.value='5';notes.value='old'");
  for(const lock of ['uploadingCount.value=1','uploadingCount.value=0;submitting.value=true']) {
    page.run(lock+";onQualifiedInput({detail:{value:'9'}});onNotesInput({detail:{value:'new'}});onStepInput(0,{detail:{value:'new'}});onCustomInput(0,{detail:{value:'new'}})");
    assert.equal(page.run('qualifiedText.value'),'5');assert.equal(page.run('notes.value'),'old');
    assert.equal(page.run('steps.value[0].value'),'old');assert.equal(page.run('customFields.value[0].value'),'old');
  }
  page.run("submitting.value=false;onNotesInput({detail:{value:'new'}})");assert.equal(page.run('notes.value'),'new');
});
test('disposition submission locks edits and back navigation, then unlocks after failure',async()=>{
  let reject;const calls=[];
  const page=script('features/quality/nonconforming/index.uvue',{}, {onBackPress(){},fieldNumber:(row,key)=>row[key]||0,fieldText:(row,key)=>row[key]||'',errorText:()=> '处置失败',request:args=>{calls.push(args);return new Promise((resolve,r)=>{reject=r;});}});
  page.run("rows.value=[{id:8,status:'draft'}];selectedIndex.value=0;disposeIndex.value=6;disposeNote.value='原备注'");
  const submit=page.run('submitDispose()');
  assert.equal(page.run('disposing.value'),true);
  page.run("closeRow();onDisposeNote({detail:{value:'改备注'}});pickDispose(0)");await page.run('submitDispose()');await page.run('loadLedger()');
  assert.equal(calls.length,1);assert.equal(calls[0].method,'PUT');assert.equal(calls[0].path,'/api/v1/apps/kuaizhizao/nonconforming-ledger/8/disposition');
  assert.equal(calls[0].data.remarks,'原备注');assert.equal(page.run('selectedIndex.value'),0);assert.equal(page.run('disposeNote.value'),'原备注');
  reject(new Error('network'));await submit;
  assert.equal(page.run('loading.value'),false);assert.equal(page.run('disposing.value'),false);assert.equal(page.run('errorTextValue.value'),'处置失败');
  page.run('closeRow()');assert.equal(page.run('selectedIndex.value'),-1);
});
test('successful disposition closes details and waits for ledger refresh',async()=>{
  const pending=[];const calls=[];
  const page=script('features/quality/nonconforming/index.uvue',{}, {onBackPress(){},fieldNumber:(row,key)=>row[key]||0,fieldText:(row,key)=>row[key]||'',readRows:v=>v,errorText:()=> '失败',request:args=>{calls.push(args);return new Promise(resolve=>pending.push(resolve));}});
  page.run("rows.value=[{id:8,status:'draft'}];selectedIndex.value=0;disposeIndex.value=3");
  const submit=page.run('submitDispose()');pending[0]({});await new Promise(resolve=>setImmediate(resolve));
  assert.equal(page.run('selectedIndex.value'),-1);assert.equal(page.run('disposing.value'),false);assert.equal(page.run('loading.value'),true);
  assert.equal(calls[1].method,'GET');assert.equal(calls[1].path,'/api/v1/apps/kuaizhizao/nonconforming-ledger');
  pending[1]([{id:8,status:'processed'}]);await submit;
  assert.equal(page.run('loading.value'),false);assert.equal(page.run('rows.value[0].status'),'processed');assert.equal(page.run('loadSettled.value'),true);
});
