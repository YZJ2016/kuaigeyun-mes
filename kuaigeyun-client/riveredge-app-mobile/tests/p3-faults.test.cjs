const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('../../../riveredge-frontend/node_modules/typescript');
const root=path.resolve(__dirname,'..');
function script(extra={}) {
  const text=fs.readFileSync(path.join(root,'features/equipment/faults/index.uvue'),'utf8');
  const source=text.match(/<script setup lang="uts">([\s\S]*?)<\/script>/)[1];
  const ctx=vm.createContext({exports:{},ref:v=>({value:v}),computed:f=>({get value(){return f();}}),
    watch(){},onShow(){},onMounted(){},onLoad(){},nextTick:f=>f(),
    UTSJSONObject:class {set(k,v){this[k]=v;}},...extra});
  vm.runInContext(ts.transpileModule(source.replace(/import[\s\S]*?from ['"][^'"]+['"]/g,''),{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}}).outputText,ctx);
  return {run:e=>vm.runInContext(e,ctx)};
}
function mocks(calls,fail) {
  return {
    request:o=>{calls.push(o);return fail.value?Promise.reject(new Error('网络失败')):Promise.resolve({items:[{uuid:'f'+calls.length,fault_no:'F'+calls.length}],total:100});},
    readRows:raw=>raw.items==null?[]:raw.items,
    fieldText:(o,k)=>o==null?'':o[k]==null?'':''+o[k],
    asJsonObject:o=>o==null||typeof o!='object'?null:o,
    fieldInt:(o,k)=>o==null?0:Math.floor(o[k]||0),
    joinParts:a=>a.filter(s=>s.length>0).join(' '),
    readError:e=>e.message,
  };
}
test('equipment fault list paginates with skip and retries the failed page only',async()=>{
  const calls=[];const fail={value:true};
  const page=script(mocks(calls,fail));
  page.run("rows.value=[{rowKey:'a',faultUuid:'a',title:'t',detail:'d'}];total.value=100;loadSettled.value=true;skip.value=0");
  page.run('loadMore()');await new Promise(r=>setImmediate(r));
  assert.equal(calls[0].query.skip,50);assert.equal(calls[0].query.limit,50);
  assert.equal(page.run('rows.value.length'),1);assert.equal(page.run('skip.value'),0);
  assert.equal(page.run('errorText.value'),'网络失败');
  fail.value=false;page.run('loadMore()');await new Promise(r=>setImmediate(r));
  assert.equal(calls[1].query.skip,50);
  assert.equal(page.run('rows.value.length'),2);assert.equal(page.run('skip.value'),50);
  assert.equal(page.run('total.value'),100);assert.equal(page.run('loadMode.value'),'more');
});
test('equipment fault list resets on refresh and forwards the equipment filter',async()=>{
  const calls=[];const fail={value:false};
  const page=script(mocks(calls,fail));
  page.run("queryUuid.value='eq-1';skip.value=50;loadSettled.value=true");
  await page.run('reload()');
  assert.equal(calls[0].query.skip,0);assert.equal(calls[0].query.equipment_uuid,'eq-1');
  assert.equal(page.run('loadMode.value'),'refresh');assert.equal(page.run('skip.value'),0);
});
test('equipment fault pagination stays locked while loading or submitting',async()=>{
  const calls=[];const fail={value:false};
  const page=script(mocks(calls,fail));
  page.run('loading.value=true;loadMore()');assert.equal(calls.length,0);
  page.run('loading.value=false;busy.value=true;loadMore()');assert.equal(calls.length,0);
});
test('equipment fault complete marks each invalid field and scrolls to the first one',async()=>{
  const calls=[];const fail={value:false};
  const page=script(mocks(calls,fail));
  page.run("completeUuid.value='r1';repairResult.value='';faultCauseText.value='';repairContentText.value=''");
  await page.run('submitComplete()');
  assert.equal(calls.length,0);
  assert.equal(page.run('resultError.value'),'请选择维修结果');
  assert.equal(page.run('causeError.value'),'请填写故障原因');
  assert.equal(page.run('contentError.value'),'请填写维修内容');
  assert.equal(page.run('formError.value'),'请选择维修结果');
  assert.equal(page.run('scrollTarget.value'),'fault-field-result');
  page.run("repairResult.value='成功'");
  await page.run('submitComplete()');
  assert.equal(page.run('scrollTarget.value'),'fault-field-cause');
  page.run("faultCauseText.value='老化'");
  await page.run('submitComplete()');
  assert.equal(page.run('scrollTarget.value'),'fault-field-content');assert.equal(calls.length,0);
  page.run("repairContentText.value='更换轴承'");
  await page.run('submitComplete()');
  assert.equal(calls.length,2);assert.match(calls[0].url,/repairs\/r1\/complete$/);
  assert.equal(calls[0].data.fault_cause,'老化');assert.equal(calls[0].data.repair_result,'成功');
});
test('equipment fault create keeps values and flags the missing field',async()=>{
  const calls=[];const fail={value:false};
  const page=script(mocks(calls,fail));
  page.run("equipmentUuidText.value='';faultDescriptionText.value='描述文本'");
  await page.run('submitCreate()');
  assert.equal(calls.length,0);
  assert.equal(page.run('equipmentError.value'),'请选择故障设备');
  assert.equal(page.run('scrollTarget.value'),'fault-field-equipment');
  assert.equal(page.run('faultDescriptionText.value'),'描述文本');
  page.run("equipmentUuidText.value='eq-9';faultDescriptionText.value=''");
  await page.run('submitCreate()');
  assert.equal(page.run('descriptionError.value'),'请填写故障描述');
  assert.equal(page.run('scrollTarget.value'),'fault-field-description');assert.equal(calls.length,0);
});
test('equipment fault deep-link prefill is the leave-guard baseline rather than dirty input',()=>{
  const loads=[];const calls=[];const fail={value:false};
  const page=script({...mocks(calls,fail),onLoad:cb=>loads.push(cb)});
  loads[0]({uuid:'eq-1'});
  assert.equal(page.run('equipmentUuidText.value'),'eq-1');
  assert.equal(page.run('needsGuard.value'),false);
  page.run("equipmentUuidText.value='eq-2'");
  assert.equal(page.run('needsGuard.value'),true);
  page.run("equipmentUuidText.value='eq-1'");
  assert.equal(page.run('needsGuard.value'),false);
});
test('equipment fault field errors clear as the user retypes into them',()=>{
  const calls=[];const fail={value:false};
  const page=script(mocks(calls,fail));
  page.run("causeError.value='x';onFaultCause({detail:{value:'老化'}})");
  assert.equal(page.run('faultCauseText.value'),'老化');
  assert.equal(page.run('causeError.value'),'');
  page.run("contentError.value='x';onRepairContent({detail:{value:'更换轴承'}})");
  assert.equal(page.run('repairContentText.value'),'更换轴承');
  assert.equal(page.run('contentError.value'),'');
  page.run("descriptionError.value='x';onFaultDescription({detail:{value:'异响'}})");
  assert.equal(page.run('faultDescriptionText.value'),'异响');
  assert.equal(page.run('descriptionError.value'),'');
});
