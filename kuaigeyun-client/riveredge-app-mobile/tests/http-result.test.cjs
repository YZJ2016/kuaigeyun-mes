const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('../../../riveredge-frontend/node_modules/typescript');

function setup() {
  const file=path.resolve(__dirname,'../shared/api/http.uts');
  assert.ok(fs.existsSync(file),'http module is missing');
  let counter=0;
  const requests=[];
  let responder=null;
  const context=vm.createContext({exports:{},
    API_ORIGIN:'https://example.test',readAppEntryOrigin:()=>'',
    getTenantId:()=>'1',getToken:()=>'token',clearToken:()=>{},
    clientChannel:()=>'mobile_h5',createIdempotencyKey:()=> 'gen-'+(++counter),
    UTSJSONObject:class{},
    uni:{request:o=>{requests.push(o);responder(o);}},
  });
  const text=fs.readFileSync(file,'utf8').replace(/import[\s\S]*?from ['"][^'"]+['"]/g,'');
  vm.runInContext(ts.transpileModule(text,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}}).outputText,context);
  const ok=(res)=>{responder=o=>o.success(res);};
  const netfail=()=>{responder=o=>o.fail({errMsg:'timeout'});};
  return {run:s=>vm.runInContext(s,context),requests,ok,netfail,ctx:context};
}

test('network failure is result-unknown, not a definite failure',async()=>{
  const s=setup();s.netfail();
  const err=await s.run("exports.apiPost('/apps/x/write',{a:1})").then(()=>null,e=>e);
  const ErrCls=s.run('exports.ApiRequestError');
  assert.ok(err instanceof ErrCls);
  assert.equal(s.run('exports.ApiRequestError.prototype instanceof Error'),true);
  assert.equal(err.resultUnknown,true);
  assert.equal(err.status,0);
  assert.equal(err.message,'网络连接失败');
  assert.equal(s.run('exports.apiResultUnknown')(err),true);
});
test('explicit error statuses are definite failures with status and message',async()=>{
  const s=setup();s.ok({statusCode:422,data:JSON.stringify({detail:'数量无效'}),header:{}});
  const err=await s.run("exports.apiPost('/apps/x/write',{a:1})").then(()=>null,e=>e);
  assert.equal(err.resultUnknown,false);
  assert.equal(err.status,422);
  assert.equal(err.message,'数量无效');
  assert.equal(s.run('exports.apiResultUnknown')(err),false);
});
test('statusCode 0 delivered via success callback is result-unknown, not a refusal',async()=>{
  const s=setup();s.ok({statusCode:0,data:null,header:{}});
  const err=await s.run("exports.apiPost('/apps/x/write',{a:1})").then(()=>null,e=>e);
  assert.equal(err.status,0);
  assert.equal(err.resultUnknown,true);
  assert.equal(s.run('exports.apiResultUnknown')(err),true);
});
test('2xx with an unreadable body is result-unknown',async()=>{
  const s=setup();s.ok({statusCode:200,data:'<<<not json',header:{}});
  const err=await s.run("exports.apiPost('/apps/x/write',{a:1})").then(()=>null,e=>e);
  assert.equal(err.status,200);
  assert.equal(err.resultUnknown,true);
});
test('envelope success:false rejection is a definite failure',async()=>{
  const s=setup();s.ok({statusCode:200,data:JSON.stringify({success:false,message:'业务拒绝'}),header:{}});
  const err=await s.run("exports.apiPost('/apps/x/write',{a:1})").then(()=>null,e=>e);
  assert.equal(err.resultUnknown,false);
  assert.equal(err.message,'业务拒绝');
});
test('callers may supply the persisted operation key as Idempotency-Key',async()=>{
  const s=setup();s.ok({statusCode:200,data:JSON.stringify({success:true,data:{id:5}}),header:{'x-idempotency-replay':'1'}});
  const out=await s.run("exports.apiRequestWithOperationKey('POST','/apps/x/write',null,{a:1},'mob-op-fixed-1')");
  assert.equal(s.requests[0].header['Idempotency-Key'],'mob-op-fixed-1');
  assert.equal(JSON.stringify(out.data),JSON.stringify({id:5}));
  assert.equal(out.replayed,true);
  assert.equal(out.status,200);
  assert.equal(out.bodyPresent,true);
});
test('2xx with a missing or empty body still resolves but is flagged bodyPresent false',async()=>{
  const s=setup();s.ok({statusCode:200,data:'',header:{}});
  const out=await s.run("exports.apiRequestWithOperationKey('POST','/apps/x/write',null,{a:1},'mob-op-e1')");
  assert.equal(out.status,200);
  assert.equal(out.bodyPresent,false);
  assert.equal(out.data,'');
  const s2=setup();s2.ok({statusCode:204,data:null,header:{}});
  const out2=await s2.run("exports.apiRequestWithOperationKey('POST','/apps/x/write',null,{a:1},'mob-op-e2')");
  assert.equal(out2.bodyPresent,false);
  assert.equal(out2.data,null);
  // 普通读取调用方不受影响：仍按 data 返回。
  const s3=setup();s3.ok({statusCode:200,data:'',header:{}});
  const data=await s3.run("exports.apiGet('/apps/x/read',null)");
  assert.equal(data,'');
});
test('existing callers without a key still get a fresh Idempotency-Key',async()=>{
  const s=setup();s.ok({statusCode:200,data:JSON.stringify({success:true,data:{id:5}}),header:{}});
  await s.run("exports.apiPost('/apps/x/write',{a:1})");
  assert.equal(s.requests[0].header['Idempotency-Key'],'gen-1');
  const data=await s.run("exports.apiRequest('GET','/apps/x/read',null,null)");
  assert.equal(JSON.stringify(data),JSON.stringify({id:5}));
});
test('401 still clears the token and is a definite rejection',async()=>{
  const s=setup();let cleared=false;s.ctx.clearToken=()=>{cleared=true;};
  s.ok({statusCode:401,data:JSON.stringify({detail:'登录过期'}),header:{}});
  const err=await s.run("exports.apiPost('/apps/x/write',{a:1})").then(()=>null,e=>e);
  assert.equal(cleared,true);
  assert.equal(err.status,401);
  assert.equal(err.resultUnknown,false);
});
