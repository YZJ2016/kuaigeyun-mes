const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('../../../riveredge-frontend/node_modules/typescript');
const root=path.resolve(__dirname,'..');
const FILE='features/workshop/scan-report/index.uvue';
function script(extra={}) {
  const text=fs.readFileSync(path.join(root,FILE),'utf8');
  const source=text.match(/<script setup lang="uts">([\s\S]*?)<\/script>/)[1];
  const ctx=vm.createContext({exports:{},ref:v=>({value:v}),computed:f=>({get value(){return f();}}),
    watch(){},onShow(){},onMounted(){},onLoad(){},onBackPress(){},nextTick:f=>f(),
    UTSJSONObject:class {set(k,v){this[k]=v;}},...extra});
  vm.runInContext(ts.transpileModule(source.replace(/import[\s\S]*?from ['"][^'"]+['"]/g,''),{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}}).outputText,ctx);
  return {run:e=>vm.runInContext(e,ctx)};
}
function mocks(opt={}) {
  const state={outcome:opt.outcome||{state:'applied',data:{},replayed:false,httpStatus:200,message:'',snapshot:{operationKey:'mob-op-1',bodyText:'{}'}},
    pending:opt.pending||null,recoverOutcome:opt.recoverOutcome||{state:'applied',data:{},replayed:true,httpStatus:200,message:'',snapshot:{operationKey:'mob-op-1',bodyText:'{}'}}};
  const calls={submit:[],recover:[],toast:[],nav:[]};
  const uni=opt.uni||{showModal(){},navigateBack(){},reLaunch(){},showToast(){}};
  const extra={
    request:async()=>({}),
    submitRecoverable:async(action,method,p,query,body)=>{
      calls.submit.push({action,method,path:p,query,body});
      if(opt.submitThrows) throw new Error(opt.submitThrows);
      return state.outcome;
    },
    recoverSubmission:async(key)=>{calls.recover.push(key);if(opt.recoverThrows) throw new Error(opt.recoverThrows);return state.recoverOutcome;},
    readPendingSubmission:()=>state.pending,
    SUBMISSION_APPLIED:'applied',SUBMISSION_REJECTED:'rejected',SUBMISSION_UNKNOWN:'unknown',
    scan:async()=>'',scanRaw:()=>'',nowIso:()=>'2026-10-06T01:00:00Z',toast:t=>calls.toast.push(t),
    readWorkOrderRows:()=>[],readRows:()=>[],
    readCurrentUser:()=>({id:1,name:'张三'}),
    navigateToPage:u=>calls.nav.push(u),
    fieldText:(o,k)=>o==null?'':o[k]==null?'':(''+o[k]).trim(),
    fieldNumber:(o,k)=>o==null?0:Math.floor(Number(o[k])||0),
    errorText:e=>e==null?'请求失败':(e.message||'请求失败'),
    firstText:(o,ks)=>{for(const k of ks){const v=o==null?'':o[k]==null?'':''+o[k];if(v.length>0)return v;}return '';},
    uni,
  };
  return {extra,calls,state};
}
function fillForm(page) {
  page.run("selectedOrder.value={id:5,code:'WO-1',name:'订单A'};operations.value=[{operation_id:9,operation_code:'OP10',operation_name:'组装'}];selectedOperationIndex.value=0");
}
test('scan-report guards leave only with unsaved input or while submitting',()=>{
  const modals=[],calls=[];
  const uni={showModal:o=>modals.push(o),navigateBack:()=>calls.push('back'),reLaunch:o=>calls.push(o.url),showToast(){}};
  let backHandler=null;
  const {extra}=mocks({uni});
  const page=script({...extra,onBackPress:f=>{backHandler=f;}});
  assert.equal(page.run('needsGuard.value'),false);
  assert.equal(backHandler(),false);assert.equal(modals.length,0);
  page.run("reportedQuantity.value='3'");
  assert.equal(page.run('needsGuard.value'),true);
  assert.equal(backHandler(),true);
  assert.equal(modals.length,1);assert.equal(modals[0].title,'离开确认');
  assert.equal(modals[0].content,'当前内容尚未提交，离开后已填写的内容将丢失。');
  assert.equal(modals[0].confirmText,'确认离开');assert.equal(modals[0].cancelText,'继续填写');
  modals[0].success({confirm:false});assert.equal(calls.length,0);
  page.run('leaveHome()');assert.equal(modals.length,2);
  modals[1].success({confirm:true});assert.deepEqual(calls,['/shell/workbench/index']);
  const page2=script({...mocks({uni:{showModal:o=>modals.push(o),navigateBack:()=>calls.push('back'),reLaunch(){},showToast(){}}}).extra});
  page2.run("manualCode.value='WO-9';leaveBack()");
  modals[2].success({confirm:true});assert.deepEqual(calls,['/shell/workbench/index','back']);
});
test('scan-report holds the leave guard while submitting and never confirms away',()=>{
  const modals=[];
  const uni={showModal:o=>modals.push(o),navigateBack(){},reLaunch(){},showToast(){}};
  let backHandler=null;
  const {extra}=mocks({uni});
  const page=script({...extra,onBackPress:f=>{backHandler=f;}});
  page.run("submitting.value=true");
  assert.equal(page.run('needsGuard.value'),true);
  assert.equal(backHandler(),true);assert.equal(modals.length,0);
  assert.equal(page.run('errorTextValue.value'),'提交或读取进行中，请等待完成后再离开');
  page.run('leaveHome()');assert.equal(modals.length,0);
});
test('scan-report sends the snapshot once via submitRecoverable and clears dirty state on applied',async()=>{
  const {extra,calls}=mocks();
  const page=script(extra);
  fillForm(page);
  page.run("reportedQuantity.value='10';unqualifiedQuantity.value='2';workHours.value='1.5'");
  await page.run('submitReport()');
  assert.equal(calls.submit.length,1);
  assert.equal(calls.submit[0].action,'scan-report');assert.equal(calls.submit[0].method,'POST');
  assert.equal(calls.submit[0].path,'/apps/kuaizhizao/reporting/quick');assert.equal(calls.submit[0].query,null);
  assert.equal(calls.submit[0].body.reported_at,'2026-10-06T01:00:00Z');
  assert.equal(calls.submit[0].body.qualified_quantity,8);assert.equal(calls.submit[0].body.worker_id,1);
  assert.match(page.run('successText.value'),/WO-1 · OP10 组装 · 合格 8 · 不合格 2 · 工时 1.5 小时/);
  assert.equal(page.run('selectedOrder.value'),null);
  assert.equal(page.run('needsGuard.value'),false);
  assert.deepEqual(calls.toast,['报工已提交']);
});
test('scan-report rejected outcome shows the message and stays retryable without pending state',async()=>{
  const {extra,calls,state}=mocks({outcome:{state:'rejected',data:null,replayed:false,httpStatus:422,message:'校验失败',snapshot:{operationKey:'mob-op-2',bodyText:'{}'}}});
  const page=script(extra);
  fillForm(page);
  page.run("reportedQuantity.value='10';unqualifiedQuantity.value='2';workHours.value='1.5'");
  await page.run('submitReport()');
  assert.equal(calls.submit.length,1);
  assert.equal(page.run('errorTextValue.value'),'校验失败');
  assert.equal(page.run('pendingKey.value'),'');
  assert.equal(page.run('submitting.value'),false);
  assert.equal(page.run('reportedQuantity.value'),'10');
});
test('scan-report unknown outcome never auto-resends and recover replays the snapshot key',async()=>{
  const bodyText=JSON.stringify({work_order_code:'WO-1',operation_code:'OP10',operation_name:'组装',qualified_quantity:8,unqualified_quantity:2,work_hours:1.5});
  const {extra,calls,state}=mocks({outcome:{state:'unknown',data:null,replayed:false,httpStatus:0,message:'网络连接失败',snapshot:{operationKey:'mob-op-9',bodyText}},
    recoverOutcome:{state:'applied',data:{},replayed:true,httpStatus:200,message:'',snapshot:{operationKey:'mob-op-9',bodyText}}});
  const page=script(extra);
  fillForm(page);
  page.run("reportedQuantity.value='10';unqualifiedQuantity.value='2';workHours.value='1.5'");
  await page.run('submitReport()');
  assert.equal(calls.submit.length,1,'no automatic resend after unknown');
  assert.equal(page.run('pendingKey.value'),'mob-op-9');
  assert.match(page.run('errorTextValue.value'),/结果未知/);
  assert.equal(page.run('submitting.value'),false);
  state.pending={operationKey:'mob-op-9'};
  await page.run('recoverPending()');
  assert.deepEqual(calls.recover,['mob-op-9']);
  assert.match(page.run('successText.value'),/WO-1 · OP10 组装 · 合格 8/);
  assert.equal(page.run('pendingKey.value'),'');
  assert.equal(page.run('needsGuard.value'),false);
});
test('scan-report blocks a second submit while a pending snapshot exists',async()=>{
  const {extra,calls,state}=mocks({submitThrows:'此操作仍有待恢复的提交，请先恢复原操作'});
  state.pending={operationKey:'mob-op-3'};
  const page=script(extra);
  fillForm(page);
  page.run("reportedQuantity.value='10';unqualifiedQuantity.value='2';workHours.value='1.5'");
  await page.run('submitReport()');
  assert.equal(calls.submit.length,1);
  assert.match(page.run('errorTextValue.value'),/待恢复/);
  assert.equal(page.run('pendingKey.value'),'mob-op-3');
  assert.equal(page.run('submitting.value'),false);
});
test('scan-report surfaces pending recovery on show',()=>{
  const {extra,state}=mocks();
  state.pending={operationKey:'mob-op-7'};
  let showHandler=null;
  const page=script({...extra,onShow:f=>{showHandler=f;}});
  showHandler();
  assert.equal(page.run('pendingKey.value'),'mob-op-7');
});
test('scan-report scrolls to the first invalid field and summarizes the error',async()=>{
  const {extra,calls}=mocks();
  const page=script(extra);
  fillForm(page);
  await page.run('submitReport()');
  assert.equal(calls.submit.length,0);
  assert.equal(page.run('scrollTarget.value'),'report-field-reported');
  assert.equal(page.run('reportedError.value'),'请填写有效的非负报工数量');
  assert.match(page.run('formError.value'),/报工数量/);
  page.run("reportedQuantity.value='5'");
  await page.run('submitReport()');
  assert.equal(page.run('scrollTarget.value'),'report-field-unqualified');
  page.run("unqualifiedQuantity.value='9';workHours.value='1'");
  await page.run('submitReport()');
  assert.equal(page.run('scrollTarget.value'),'report-field-unqualified');
  assert.equal(page.run('unqualifiedError.value'),'不合格数量不能大于报工数量');
  page.run("unqualifiedQuantity.value='9';workHours.value=''");
  await page.run('submitReport()');
  assert.equal(page.run('scrollTarget.value'),'report-field-hours');
  assert.equal(calls.submit.length,0);
});
