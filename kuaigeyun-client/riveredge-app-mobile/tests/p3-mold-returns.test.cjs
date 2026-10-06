const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('../../../riveredge-frontend/node_modules/typescript');
const root=path.resolve(__dirname,'..');
function script(extra={}) {
  const text=fs.readFileSync(path.join(root,'features/mold/mold-returns/index.uvue'),'utf8');
  const source=text.match(/<script setup lang="uts">([\s\S]*?)<\/script>/)[1];
  const ctx=vm.createContext({exports:{},ref:v=>({value:v}),computed:f=>({get value(){return f();}}),
    defineProps:()=>({}),defineEmits:()=>()=>{},defineOptions(){},watch(){},
    onShow(){},onMounted(){},onLoad(){},nextTick:f=>f(),
    UTSJSONObject:class {set(k,v){this[k]=v;}},
    DocLine:class {},
    MOLD_BORROWS_OUTSTANDING:'/borrows/outstanding',MOLD_RETURNS:'/returns',MOLD_RETURN_USAGE_PREVIEW:'/returns/usage-preview',
    withQuery:(p,q)=>p+'?'+q,isDateText:()=>true,todayDate:()=>'2026-10-06',
    joinParts:a=>a.filter(s=>s!='').join(' '),
    putText:(body,key,value)=>{const t=value.trim();if(t!=''){body.set(key,t);}},
    errorText:e=>e.message,
    fieldNumber:(o,k)=>o!=null&&o[k]!=null?Number(o[k]):0,
    fieldInt:(o,k)=>Math.floor(o!=null&&o[k]!=null?Number(o[k]):0),
    fieldText:(o,k)=>o!=null&&o[k]!=null?String(o[k]).trim():'',
    asJsonObject:o=>o!=null&&typeof o=='object'&&!Array.isArray(o)?o:null,
    readRows:p=>{if(p==null){return [];}if(Array.isArray(p)){return p;}if(p.items!=null){return p.items;}const d=p.data;if(d!=null&&typeof d=='object'&&d.items!=null){return d.items;}return [];},
    apiGet:async()=>({items:[],total:0}),apiPost:async()=>({}),
    ...extra});
  vm.runInContext(ts.transpileModule(source.replace(/import[\s\S]*?from ['"][^'"]+['"]/g,''),{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}}).outputText,ctx);
  return {run:e=>vm.runInContext(e,ctx)};
}
function uniMock(modals,navs) {
  return {
    showModal:o=>modals.push(o),
    navigateBack:o=>{navs.push('back');if(o.success!=null){o.success();}},
    reLaunch:o=>navs.push(o.url),
  };
}
function uniFailNavMock(modals,navs) {
  return {
    showModal:o=>modals.push(o),
    navigateBack:o=>{navs.push('back');if(o.fail!=null){o.fail();}},
    reLaunch:o=>{navs.push(o.url);if(o.fail!=null){o.fail();}},
  };
}
test('outstanding borrows commit skip only on success and retry the same page',async()=>{
  const calls=[];let fail=true;
  const page=script({
    apiGet:url=>{calls.push(url);return fail?Promise.reject(new Error('网络失败')):Promise.resolve({items:[{id:51,mold_id:7,document_no:'MB51',mold_name:'模A'}],total:80});},
  });
  page.run("borrowOptions.value=[{id:1,moldId:2,label:'A'}];borrowSkip.value=0;borrowTotal.value=80;loadSettled.value=true");
  await page.run('loadOutstanding(false)');
  assert.match(calls[0],/outstanding\?skip=50&limit=50/);
  assert.equal(page.run('borrowSkip.value'),0);
  assert.equal(page.run('borrowOptions.value.length'),1);
  assert.equal(page.run('listError.value'),'网络失败');
  assert.equal(page.run('borrowMode.value'),'more');
  fail=false;
  await page.run('loadOutstanding(false)');
  assert.match(calls[1],/skip=50&limit=50/);
  assert.equal(page.run('borrowSkip.value'),50);
  assert.equal(page.run('borrowOptions.value.length'),2);
  assert.equal(page.run('borrowTotal.value'),80);
  assert.equal(page.run('borrowOptions.value[1].label'),'MB51 - 模A');
});
test('outstanding load-more stays locked while loading, submitting or previewing',async()=>{
  const calls=[];
  const page=script({apiGet:url=>{calls.push(url);return Promise.resolve({items:[],total:80});}});
  page.run('loading.value=true;loadMoreBorrows()');assert.equal(calls.length,0);
  page.run('loading.value=false;submitting.value=true;loadMoreBorrows()');assert.equal(calls.length,0);
  page.run('submitting.value=false;previewPending.value=true;loadMoreBorrows()');assert.equal(calls.length,0);
  await page.run('previewPending.value=false;loadOutstanding(false)');
  assert.match(calls[0],/skip=50&limit=50/);
});
test('refresh clears a selection that vanished and keeps one still outstanding',async()=>{
  const calls=[];
  const page=script({
    apiGet:url=>{calls.push(url);return Promise.resolve({items:[{id:2,mold_id:22,document_no:'MB2',mold_name:'M2'}],total:1});},
  });
  page.run("borrowId.value=9;moldId.value=99;chosenBorrow.value='MB9';usageCount.value='3'");
  await page.run('loadOutstanding(true)');
  assert.match(calls[0],/outstanding\?skip=0&limit=50/);
  assert.equal(page.run('borrowId.value'),0);
  assert.equal(page.run('moldId.value'),0);
  assert.equal(page.run('chosenBorrow.value'),'');
  assert.equal(page.run('hint.value'),'所选领用已不存在');
  page.run("hint.value='';borrowId.value=2;moldId.value=22;chosenBorrow.value='MB2'");
  await page.run('loadOutstanding(true)');
  assert.equal(page.run('borrowId.value'),2);
  assert.equal(page.run('chosenBorrow.value'),'MB2');
});
test('createReturn resets the selection and keeps its success text over refresh failures',async()=>{
  const calls=[];const posts=[];
  const page=script({
    apiPost:async(url,body)=>{posts.push(body);return {document_no:'MR1'};},
    apiGet:url=>{calls.push(url);return Promise.reject(new Error('刷新失败'));},
  });
  page.run("borrowId.value=5;moldId.value=55;chosenBorrow.value='MB5';usageCount.value='4';remark.value='note';returnDate.value='2026-10-06'");
  await page.run('createReturn()');
  assert.equal(posts.length,1);
  assert.equal(posts[0].borrow_id,5);
  assert.equal(page.run('borrowId.value'),0);
  assert.equal(page.run('moldId.value'),0);
  assert.equal(page.run('chosenBorrow.value'),'');
  assert.equal(page.run('usageCount.value'),'1');
  assert.equal(page.run('remark.value'),'');
  assert.equal(page.run('hint.value'),'已创建 MR1');
  assert.equal(page.run('listError.value'),'刷新失败');
  await page.run('createReturn()');
  assert.equal(posts.length,1);
  assert.equal(page.run('hint.value'),'请选择领用单');
});
test('leave guard confirms dirty input and a cancelled leave preserves all input',()=>{
  const modals=[];const navs=[];let backHook=null;
  const page=script({onBackPress:cb=>{backHook=cb;},uni:uniMock(modals,navs)});
  assert.equal(page.run('leaveGuarded.value'),false);
  assert.equal(backHook({from:'backbutton'}),false);
  page.run('leaveBack()');assert.equal(modals.length,0);
  page.run("chosenBorrow.value='MB1';usageCount.value='3';remark.value='note'");
  assert.equal(page.run('leaveGuarded.value'),true);
  page.run('leaveBack()');assert.equal(modals.length,1);
  page.run('leaveBack()');assert.equal(modals.length,1);
  assert.equal(modals[0].title,'离开确认');
  assert.equal(modals[0].content,'当前内容尚未提交，离开后已填写的内容将丢失。');
  assert.equal(modals[0].confirmText,'确认离开');
  assert.equal(modals[0].cancelText,'继续填写');
  modals[0].success({confirm:false});
  assert.equal(navs.length,0);
  assert.equal(page.run('chosenBorrow.value'),'MB1');
  assert.equal(page.run('usageCount.value'),'3');
  assert.equal(page.run('remark.value'),'note');
  assert.equal(backHook({from:'backbutton'}),true);
  assert.equal(modals.length,2);
  modals[1].success({confirm:true});
  assert.deepEqual(navs,['back']);
  assert.equal(backHook({from:'backbutton'}),false);
});
test('leave guard blocks submit and preview without a modal',()=>{
  const modals=[];const navs=[];let backHook=null;
  const page=script({onBackPress:cb=>{backHook=cb;},uni:uniMock(modals,navs)});
  page.run('submitting.value=true');
  assert.equal(page.run('leaveGuarded.value'),true);
  assert.equal(backHook({from:'backbutton'}),true);
  assert.equal(modals.length,0);
  assert.equal(page.run('hint.value'),'提交或读取进行中，请等待完成后再离开');
  assert.equal(navs.length,0);
  page.run("submitting.value=false;previewPending.value=true;hint.value=''");
  page.run('leaveHome()');
  assert.equal(modals.length,0);
  assert.equal(page.run('hint.value'),'提交或读取进行中，请等待完成后再离开');
  page.run("previewPending.value=false;hint.value='';remark.value='x'");
  assert.equal(page.run('leaveGuarded.value'),true);
  page.run("remark.value='';usageCount.value='5'");
  assert.equal(page.run('leaveGuarded.value'),true);
});
test('confirming leave through home-link navigates back to the workbench',()=>{
  const modals=[];const navs=[];
  const page=script({onBackPress(){},uni:uniMock(modals,navs)});
  page.run("chosenBorrow.value='MB1'");
  page.run('leaveHome()');
  assert.equal(modals.length,1);
  modals[0].success({confirm:true});
  assert.deepEqual(navs,['/shell/workbench/index']);
});
test('return records keep the keyword, page with skip and reset on a new search',async()=>{
  const calls=[];
  const page=script({
    apiGet:url=>{calls.push(url);return Promise.resolve({items:[{document_no:'MR'+calls.length,mold_code:'MC',mold_name:'M',return_date:'2026-10-01',usage_count:3,status:'已审核'}],total:60});},
  });
  page.run("listKeyword.value='MR1';loadSettled.value=true");
  await page.run('loadList(true)');
  assert.match(calls[0],/returns\?keyword=MR1&skip=0&limit=50/);
  assert.equal(page.run('listTotal.value'),60);
  await page.run('loadList(false)');
  assert.match(calls[1],/keyword=MR1&skip=50&limit=50/);
  assert.equal(page.run('rows.value.length'),2);
  assert.equal(page.run('listSkip.value'),50);
});
test('record load-more uses the committed keyword until the next query',async()=>{
  const calls=[];
  const page=script({
    apiGet:url=>{calls.push(url);return Promise.resolve({items:[{document_no:'MR'+calls.length,mold_code:'MC',mold_name:'M',return_date:'2026-10-01',usage_count:3,status:'已审核'}],total:60});},
  });
  page.run("listKeyword.value='MR1'");
  await page.run('loadList(true)');
  assert.match(calls[0],/keyword=MR1&skip=0&limit=50/);
  page.run("listKeyword.value='MR2'");
  await page.run('loadList(false)');
  assert.match(calls[1],/keyword=MR1&skip=50&limit=50/);
  assert.equal(page.run('activeListKeyword.value'),'MR1');
  await page.run('loadList(true)');
  assert.match(calls[2],/keyword=MR2&skip=0&limit=50/);
  assert.equal(page.run('activeListKeyword.value'),'MR2');
});
test('a failed record query does not commit its keyword',async()=>{
  const calls=[];let fail=false;
  const page=script({
    apiGet:url=>{calls.push(url);return fail?Promise.reject(new Error('网络失败')):Promise.resolve({items:[],total:60});},
  });
  page.run("listKeyword.value='MR1'");
  await page.run('loadList(true)');
  assert.equal(page.run('activeListKeyword.value'),'MR1');
  fail=true;
  page.run("listKeyword.value='MR2'");
  await page.run('loadList(true)');
  assert.equal(page.run('listError.value'),'网络失败');
  assert.equal(page.run('activeListKeyword.value'),'MR1');
});
test('a preview that outlives its selection still clears previewPending',async()=>{
  let resolvePreview=null;
  const page=script({
    apiGet:url=>{
      if(url.indexOf('usage-preview')>=0){return new Promise(r=>{resolvePreview=r;});}
      return Promise.resolve({items:[{id:2,mold_id:22,document_no:'MB2',mold_name:'M2'}],total:1});
    },
  });
  page.run("borrowOptions.value=[{id:9,moldId:90,label:'MB9'}]");
  const p=page.run('chooseBorrow(0)');
  assert.equal(page.run('previewPending.value'),true);
  await page.run('loadOutstanding(true)');
  assert.equal(page.run('borrowId.value'),0);
  assert.equal(page.run('previewPending.value'),true);
  resolvePreview({usage_count:5,mold_id:91});
  await p;
  assert.equal(page.run('previewPending.value'),false);
  assert.equal(page.run('usageCount.value'),'1');
  assert.equal(page.run('moldId.value'),0);
  assert.equal(page.run('hint.value'),'所选领用已不存在');
});
test('a preview rejection after the selection clears keeps the newer hint',async()=>{
  let rejectPreview=null;
  const page=script({
    apiGet:url=>{
      if(url.indexOf('usage-preview')>=0){return new Promise((_r,j)=>{rejectPreview=j;});}
      return Promise.resolve({items:[],total:0});
    },
  });
  page.run("borrowOptions.value=[{id:9,moldId:90,label:'MB9'}]");
  const p=page.run('chooseBorrow(0)');
  assert.equal(page.run('previewPending.value'),true);
  await page.run('loadOutstanding(true)');
  assert.equal(page.run('borrowId.value'),0);
  rejectPreview(new Error('读取失败'));
  await p;
  assert.equal(page.run('previewPending.value'),false);
  assert.equal(page.run('hint.value'),'所选领用已不存在');
});
test('a failed navigation re-arms the leave buttons instead of wedging them',()=>{
  const modals=[];const navs=[];
  const page=script({onBackPress(){},uni:uniFailNavMock(modals,navs)});
  page.run("chosenBorrow.value='MB1'");
  page.run('leaveBack()');
  assert.equal(modals.length,1);
  modals[0].success({confirm:true});
  assert.deepEqual(navs,['back']);
  assert.equal(page.run('leaveGuarded.value'),true);
  page.run('leaveBack()');
  assert.equal(modals.length,2);
  modals[1].success({confirm:false});
  page.run('leaveHome()');
  assert.equal(modals.length,3);
  modals[2].success({confirm:true});
  assert.deepEqual(navs,['back','/shell/workbench/index']);
  assert.equal(page.run('leaveGuarded.value'),true);
});
test('a confirmed leave releases the guard and onShow re-arms a surviving page',()=>{
  const modals=[];const navs=[];let showHook=null;
  const page=script({onShow:cb=>{showHook=cb;},onBackPress(){},uni:uniMock(modals,navs),apiGet:async()=>({items:[],total:0})});
  page.run("chosenBorrow.value='MB1'");
  page.run('leaveBack()');
  modals[0].success({confirm:true});
  assert.deepEqual(navs,['back']);
  assert.equal(page.run('leaveGuarded.value'),false);
  page.run('leaveBack()');
  assert.equal(modals.length,1);
  showHook();
  assert.equal(page.run('leaveGuarded.value'),true);
  page.run('leaveBack()');
  assert.equal(modals.length,2);
});
