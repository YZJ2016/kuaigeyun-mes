const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('../../../riveredge-frontend/node_modules/typescript');

function setup() {
  const file=path.resolve(__dirname,'../shared/api/submission-recovery.uts');
  assert.ok(fs.existsSync(file),'submission recovery module is missing');
  let tenant='1',user=7,origin='https://example.test/api/v1',counter=0,broken=false;
  const storage=new Map();
  const sent=[];
  let responder=()=>Promise.resolve({data:{id:1},replayed:false,status:200,bodyPresent:true});
  class ApiRequestError extends Error{constructor(m){super(m);this.status=0;this.resultUnknown=false;}}
  const context=vm.createContext({exports:{},apiBase:()=>origin,getTenantId:()=>tenant,
    readSessionUserId:()=>user,getToken:()=> 'secret-token-not-for-storage',
    createIdempotencyKey:()=> String(++counter),
    ApiRequestError,apiResultUnknown:e=>e!=null&&e.resultUnknown===true,
    apiRequestWithOperationKey:(m,p,q,b,k)=>{sent.push({m,p,q,b,k});return responder(m,p,q,b,k);},
    uni:{getStorageSync:k=>storage.get(k),setStorageSync:(k,v)=>{if(broken)throw Error('disk full');storage.set(k,v);},
      removeStorageSync:k=>storage.delete(k),getStorageInfoSync:()=>({keys:[...storage.keys()]})},
  });
  const text=fs.readFileSync(file,'utf8').replace(/import[\s\S]*?from ['"][^'"]+['"]/g,'');
  vm.runInContext(ts.transpileModule(text,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}}).outputText,context);
  const fail=(status,unknown,msg)=>{responder=()=>{const e=new ApiRequestError(msg||'failed');e.status=status;e.resultUnknown=!!unknown;return Promise.reject(e);};};
  return {run:s=>vm.runInContext(s,context),storage,sent,switchTenant:v=>{tenant=v;},switchUser:v=>{user=v;},
    switchOrigin:v=>{origin=v;},breakStorage:()=>{broken=true;},
    respond:o=>{responder=()=>Promise.resolve(o);},fail,
    reject:e=>{responder=()=>Promise.reject(e);},
    // Resolves to the rejection message (or '' on success) without host/realm quirks.
    msg:async s=>await vm.runInContext('Promise.resolve().then(()=>'+s+').then(()=>"",e=>e.message)',context)};
}
const prepare="exports.prepareSubmission('report','POST','/apps/kuaizhizao/reporting/quick',null,{reported_at:'2026-10-06T01:00:00Z',quantity:2})";
const submit="exports.submitRecoverable('report','POST','/apps/kuaizhizao/reporting/quick',null,{reported_at:'2026-10-06T01:00:00Z',quantity:2})";

test('persisted snapshot retains its key and original timestamp across reload',()=>{
  const s=setup();const first=s.run(prepare);
  const saved=s.run("exports.readPendingSubmission('report')");
  assert.equal(saved.operationKey,first.operationKey);
  assert.equal(JSON.parse(saved.bodyText).reported_at,'2026-10-06T01:00:00Z');
  assert.ok(first.operationKey.startsWith('mob-op-'));
  assert.throws(()=>s.run(prepare),/恢复/);
});
test('storage failure does not produce a usable submission operation',()=>{
  const s=setup();s.breakStorage();assert.throws(()=>s.run(prepare));
  assert.equal(s.storage.size,0);
});
test('pending submissions are isolated by user tenant and API origin',()=>{
  const s=setup();s.run(prepare);
  s.switchUser(8);assert.equal(s.run("exports.readPendingSubmission('report')"),null);
  s.switchUser(7);s.switchTenant('2');assert.equal(s.run("exports.readPendingSubmission('report')"),null);
  s.switchTenant('1');s.switchOrigin('https://other.test/api/v1');assert.equal(s.run("exports.readPendingSubmission('report')"),null);
  s.switchOrigin('https://example.test/api/v1');assert.notEqual(s.run("exports.readPendingSubmission('report')"),null);
});
test('late success clears only its original operation and does not clear a different account',()=>{
  const s=setup();s.run('const old = '+prepare);
  s.switchUser(8);s.run('const current = '+prepare);
  s.run('exports.completeSubmission(old)');
  assert.equal(s.run("exports.readPendingSubmission('report').operationKey"),s.run('current.operationKey'));
  s.switchUser(7);assert.equal(s.run("exports.readPendingSubmission('report')"),null);
});
test('snapshots contain no authorization material and invalid identity cannot create one',()=>{
  const s=setup();s.run(prepare);
  assert.ok(!JSON.stringify([...s.storage.values()]).includes('secret-token'));
  s.switchUser(0);assert.throws(()=>s.run(prepare),/账号/);
});
test('submitRecoverable applies, sends the snapshot key, and clears pending state',async()=>{
  const s=setup();
  const out=await s.run(submit);
  assert.equal(out.state,'applied');
  assert.equal(out.data.id,1);
  assert.equal(s.sent.length,1);
  assert.ok(s.sent[0].k.startsWith('mob-op-'));
  assert.equal(s.sent[0].m,'POST');
  assert.equal(JSON.stringify(s.sent[0].b),JSON.stringify({reported_at:'2026-10-06T01:00:00Z',quantity:2}));
  assert.equal(s.storage.size,0);
});
test('submitRecoverable rejects when a pending snapshot exists and sends nothing',async()=>{
  const s=setup();s.run(prepare);
  assert.match(await s.msg(submit),/恢复/);
  assert.equal(s.sent.length,0);
});
test('result unknown keeps the snapshot and recover resends the identical request and key',async()=>{
  const s=setup();s.fail(0,true,'网络连接失败');
  const out=await s.run(submit);
  assert.equal(out.state,'unknown');
  assert.equal(out.message,'网络连接失败');
  assert.equal(s.storage.size,1);
  const key=out.snapshot.operationKey;
  s.respond({data:{id:9},replayed:true,status:200,bodyPresent:true});
  const rec=await s.run("exports.recoverSubmission('"+key+"')");
  assert.equal(rec.state,'applied');
  assert.equal(rec.replayed,true);
  assert.equal(rec.data.id,9);
  assert.equal(s.sent.length,2);
  assert.equal(s.sent[1].k,key);
  assert.equal(s.sent[1].m,'POST');
  assert.equal(s.sent[1].p,'/apps/kuaizhizao/reporting/quick');
  assert.equal(s.sent[1].q,null);
  assert.equal(JSON.stringify(s.sent[1].b),JSON.stringify({reported_at:'2026-10-06T01:00:00Z',quantity:2}));
  assert.equal(s.storage.size,0);
});
test('explicit rejection clears pending state and is safe to retry',async()=>{
  const s=setup();s.fail(422,false,'校验失败');
  const out=await s.run(submit);
  assert.equal(out.state,'rejected');
  assert.equal(out.httpStatus,422);
  assert.equal(out.message,'校验失败');
  assert.equal(s.storage.size,0);
});
test('auth expiry and conflict keep the snapshot for reconciliation',async()=>{
  const s=setup();s.fail(401,false,'未授权');
  let out=await s.run(submit);
  assert.equal(out.state,'rejected');
  assert.equal(s.storage.size,1);
  const s2=setup();s2.fail(409,false,'同一操作标识不能提交不同内容');
  out=await s2.run(submit);
  assert.equal(out.state,'rejected');
  assert.equal(out.httpStatus,409);
  assert.equal(s2.storage.size,1);
});
test('listPendingSubmissions returns only current scope and recoverSubmission requires the key',async()=>{
  const s=setup();s.run(prepare);
  s.run("exports.prepareSubmission('qc','POST','/quality',null,{a:1})");
  const keys=s.run("exports.listPendingSubmissions()").map(x=>x.action).sort();
  assert.equal(JSON.stringify(keys),JSON.stringify(['qc','report']));
  s.switchUser(8);
  assert.equal(s.run('exports.listPendingSubmissions()').length,0);
  assert.match(await s.msg("exports.recoverSubmission('mob-op-1')"),/没有该待恢复/);
});
test('recoverSubmission resends the snapshot of a different account only under that scope',async()=>{
  const s=setup();
  const first=s.run(prepare);
  s.switchUser(8);
  assert.match(await s.msg("exports.recoverSubmission('"+first.operationKey+"')"),/没有该待恢复/);
  s.switchUser(7);
  const rec=await s.run("exports.recoverSubmission('"+first.operationKey+"')");
  assert.equal(rec.state,'applied');
  assert.equal(s.sent[0].k,first.operationKey);
});
test('corrupted snapshot blocks resubmission and never reaches the network',async()=>{
  const s=setup();s.run(prepare);
  const key=[...s.storage.keys()][0];
  s.storage.set(key,'{"version":1,"broken":true}');
  assert.throws(()=>s.run("exports.readPendingSubmission('report')"),/核对/);
  assert.match(await s.msg(submit),/核对/);
  assert.equal(s.sent.length,0);
});
test('HTTP 5xx is result-unknown and keeps the snapshot',async()=>{
  const s=setup();s.fail(500,false,'Internal Server Error');
  const out=await s.run(submit);
  assert.equal(out.state,'unknown');
  assert.equal(out.httpStatus,500);
  assert.match(out.message,/500/);
  assert.match(out.message,/未知/);
  assert.equal(s.storage.size,1);
  const s2=setup();s2.fail(502,false,'Bad Gateway');
  const out2=await s2.run(submit);
  assert.equal(out2.state,'unknown');
  assert.equal(s2.storage.size,1);
});
test('2xx with an empty body is result-unknown in the durable path and keeps the snapshot',async()=>{
  const s=setup();s.respond({data:null,replayed:false,status:200,bodyPresent:false});
  const out=await s.run(submit);
  assert.equal(out.state,'unknown');
  assert.equal(out.httpStatus,200);
  assert.match(out.message,/未知|空/);
  assert.equal(s.storage.size,1);
  const key=out.snapshot.operationKey;
  s.respond({data:{id:9},replayed:true,status:200,bodyPresent:true});
  const rec=await s.run("exports.recoverSubmission('"+key+"')");
  assert.equal(rec.state,'applied');
  assert.equal(rec.replayed,true);
  assert.equal(s.storage.size,0);
});
test('corrupted records are surfaced by listCorruptSubmissions for manual reconciliation',async()=>{
  const s=setup();s.run(prepare);
  const key=[...s.storage.keys()][0];
  // JSON 可解但快照校验失败：operationKey 仍可尽力捞出用于对照。
  s.storage.set(key,JSON.stringify({version:1,storageKey:key,scope:'other-scope',action:'report',operationKey:'mob-op-dead',method:'POST',path:'/p',queryText:'null',bodyText:'null'}));
  const corrupt=s.run('exports.listCorruptSubmissions()');
  assert.equal(corrupt.length,1);
  assert.equal(corrupt[0].storageKey,key);
  assert.equal(corrupt[0].action,'report');
  assert.equal(corrupt[0].operationKey,'mob-op-dead');
  // 可重发列表不含它，但按残存 operationKey 恢复会得到"损坏需核对"而非"没有记录"。
  assert.equal(s.run('exports.listPendingSubmissions()').length,0);
  assert.match(await s.msg("exports.recoverSubmission('mob-op-dead')"),/核对/);
  // 完全不可解析的内容也露面，operationKey 为空。
  const s2=setup();s2.run(prepare);
  const key2=[...s2.storage.keys()][0];
  s2.storage.set(key2,'{not json');
  const c2=s2.run('exports.listCorruptSubmissions()');
  assert.equal(c2.length,1);
  assert.equal(c2[0].action,'report');
  assert.equal(c2[0].operationKey,'');
  assert.match(await s2.msg("exports.recoverSubmission('mob-op-1')"),/没有该待恢复/);
});
test('nested user.id satisfies the session scope like readCurrentUser',()=>{
  const file=path.resolve(__dirname,'../shared/api/session.uts');
  const store=new Map();
  class UtsObj{
    constructor(m){this.m=m||{};}
    getNumber(k){const v=this.m[k];return typeof v=='number'?v:null;}
    getString(k){const v=this.m[k];return typeof v=='string'?v:null;}
    getJSON(k){const v=this.m[k];if(v instanceof UtsObj)return v;return v!=null&&typeof v=='object'&&!Array.isArray(v)?new UtsObj(v):null;}
  }
  const context=vm.createContext({exports:{},UTSJSONObject:UtsObj,
    asJsonObject:raw=>{if(raw==null)return null;if(raw instanceof UtsObj)return raw;
      if(typeof raw=='string'){try{const p=JSON.parse(raw);return p!=null&&typeof p=='object'&&!Array.isArray(p)?new UtsObj(p):null;}catch(e){return null;}}
      return null;},
    uni:{getStorageSync:k=>store.get(k),setStorageSync:(k,v)=>store.set(k,v),removeStorageSync:k=>store.delete(k)}});
  const text=fs.readFileSync(file,'utf8').replace(/import[\s\S]*?from ['"][^'"]+['"]/g,'');
  vm.runInContext(ts.transpileModule(text,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}}).outputText,context);
  store.set('user_info',JSON.stringify({user:{id:9,full_name:'N'}}));
  assert.equal(vm.runInContext('exports.readSessionUserId()',context),9);
  store.set('user_info',JSON.stringify({id:4}));
  assert.equal(vm.runInContext('exports.readSessionUserId()',context),4);
  store.set('user_info',JSON.stringify({user:{}}));
  assert.equal(vm.runInContext('exports.readSessionUserId()',context),0);
});
test('unserializable snapshot content throws before persisting or sending',async()=>{
  const s=setup();
  assert.throws(()=>s.run("exports.prepareSubmission('bad','POST','/p',null,undefined)"),/序列化/);
  assert.equal(s.storage.size,0);
  assert.equal(s.sent.length,0);
});
test('non-ApiRequestError rejections keep the snapshot as result-unknown',async()=>{
  const s=setup();s.reject(s.run('new Error("local boom")'));
  const out=await s.run(submit);
  assert.equal(out.state,'unknown');
  assert.equal(out.httpStatus,0);
  assert.equal(out.message,'local boom');
  assert.equal(s.storage.size,1);
  const s2=setup();s2.reject('plain string');
  const out2=await s2.run(submit);
  assert.equal(out2.state,'unknown');
  assert.equal(s2.storage.size,1);
});
