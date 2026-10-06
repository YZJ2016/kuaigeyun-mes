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
  const ctx=vm.createContext({exports:{},ref:v=>({value:v}),computed:f=>({get value(){return f();}}),defineProps:()=>props,
    defineEmits:()=> (...args)=>[],defineOptions(){},watch(){},onShow(){},onMounted(){},onLoad(){},nextTick:f=>f(),
    UTSJSONObject:class {set(k,v){this[k]=v;}},...extra});
  vm.runInContext(ts.transpileModule(source.replace(/import[\s\S]*?from ['"][^'"]+['"]/g,''),{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}}).outputText,ctx);
  return {run:e=>vm.runInContext(e,ctx)};
}
function boardMocks(calls,sizes) {
  return {
    listPath:()=>'/list',listQuery:(kind,skip,page,keyword)=>({skip,page,keyword}),
    apiGet:async(url,query)=>{calls.push(query);const n=sizes==null?1:sizes[calls.length-1]||0;return {items:new Array(n).fill({id:calls.length}),total:200};},
    readCards:raw=>raw.items,readTotal:raw=>raw.total,errorText:e=>e.message,
  };
}
test('warehouse load more reuses the committed keyword after the input drifts',async()=>{
  const calls=[];
  const page=script('features/warehouse/board.uvue',{kind:'inventory-query'},boardMocks(calls));
  await page.run("keyword.value='AAA';loadList(true)");
  assert.equal(calls[0].keyword,'AAA');
  page.run("keyword.value='BBB';loadMore()");await new Promise(r=>setImmediate(r));
  assert.equal(calls[1].keyword,'AAA');assert.equal(calls[1].page,2);
  assert.equal(page.run('activeKeyword.value'),'AAA');
  page.run("keyword.value='CCC';loadList(true)");await new Promise(r=>setImmediate(r));
  assert.equal(calls[2].keyword,'CCC');assert.equal(calls[2].page,1);
  page.run('loadMore()');await new Promise(r=>setImmediate(r));
  assert.equal(calls[3].keyword,'CCC');
});
test('warehouse skip append follows the loaded batch size and self-heals after a short page',async()=>{
  const calls=[];
  const page=script('features/warehouse/board.uvue',{kind:'pickings'},boardMocks(calls,[45,10,10]));
  await page.run('loadList(true)');
  assert.equal(calls[0].skip,0);assert.equal(page.run('cards.value.length'),45);
  page.run('loadMore()');await new Promise(r=>setImmediate(r));
  assert.equal(calls[1].skip,45);assert.equal(page.run('cards.value.length'),55);
  page.run('loadMore()');await new Promise(r=>setImmediate(r));
  assert.equal(calls[2].skip,55);assert.equal(page.run('skip.value'),55);
});
test('warehouse leave guard asks once, keeps edits on cancel and releases navigation on confirm',()=>{
  const modals=[],navs=[],backs=[];
  const page=script('features/warehouse/board.uvue',{kind:'pickings'},{
    ...boardMocks([]),onBackPress:cb=>backs.push(cb),
    uni:{showModal:o=>modals.push(o),navigateBack:o=>navs.push('back'),reLaunch:o=>navs.push(o.url)},
  });
  assert.equal(backs.length,1);
  assert.equal(page.run('needsGuard.value'),false);
  assert.equal(backs[0]({from:'backbutton'}),false);
  page.run("selectedId.value=7;editingLineIndex.value=0;serialInput.value='SN-1'");
  assert.equal(page.run('needsGuard.value'),true);
  assert.equal(backs[0]({from:'backbutton'}),true);
  assert.equal(modals.length,1);assert.equal(navs.length,0);
  assert.equal(modals[0].title,'离开确认');assert.equal(modals[0].content,'当前内容尚未提交，离开后已填写的内容将丢失。');
  assert.equal(modals[0].confirmText,'确认离开');assert.equal(modals[0].cancelText,'继续填写');
  modals[0].success({confirm:false});
  assert.equal(navs.length,0);assert.equal(page.run('serialInput.value'),'SN-1');
  page.run('leaveBack()');assert.equal(modals.length,2);
  modals[1].success({confirm:true});assert.deepEqual(navs,['back']);
  assert.equal(page.run('needsGuard.value'),false);
  assert.equal(backs[0]({from:'backbutton'}),false);
  page.run("leaving.value=false;busy.value=true");
  assert.equal(backs[0]({from:'backbutton'}),true);assert.equal(modals.length,2);
  assert.equal(page.run('hint.value'),'提交或读取进行中，请等待完成后再离开');
  page.run("leaving.value=false;busy.value=false;editingHeader.value=true");
  page.run('leaveHome()');assert.equal(modals.length,3);
  modals[2].success({confirm:true});
  assert.deepEqual(navs,['back','/shell/workbench/index']);
});
function faultMocks(modals,navs,backs) {
  return {
    onBackPress:cb=>backs.push(cb),
    request:o=>Promise.resolve({items:[],total:0}),
    readRows:raw=>raw.items==null?[]:raw.items,
    fieldText:(o,k)=>o==null?'':o[k]==null?'':''+o[k],
    asJsonObject:o=>o==null||typeof o!='object'?null:o,
    fieldInt:(o,k)=>o==null?0:Math.floor(o[k]||0),
    joinParts:a=>a.filter(s=>s.length>0).join(' '),
    readError:e=>e.message,
    uni:{showModal:o=>modals.push(o),navigateBack:o=>navs.push('back'),reLaunch:o=>navs.push(o.url)},
  };
}
test('equipment faults leave guard tracks filled fields and releases only on confirm',()=>{
  const modals=[],navs=[],backs=[];
  const page=script('features/equipment/faults/index.uvue',{},faultMocks(modals,navs,backs));
  assert.equal(backs.length,1);
  assert.equal(page.run('needsGuard.value'),false);
  assert.equal(backs[0]({from:'backbutton'}),false);
  page.run("faultDescriptionText.value='皮带异响'");
  assert.equal(page.run('needsGuard.value'),true);
  assert.equal(backs[0]({from:'navigateBack'}),true);
  assert.equal(modals.length,1);assert.equal(navs.length,0);
  assert.equal(modals[0].title,'离开确认');assert.equal(modals[0].content,'当前内容尚未提交，离开后已填写的内容将丢失。');
  modals[0].success({confirm:false});
  assert.equal(page.run('faultDescriptionText.value'),'皮带异响');assert.equal(navs.length,0);
  page.run('leaveBack()');assert.equal(modals.length,2);
  modals[1].success({confirm:true});assert.deepEqual(navs,['back']);
  assert.equal(page.run('needsGuard.value'),false);
  assert.equal(backs[0]({from:'backbutton'}),false);
  page.run("leaving.value=false;faultDescriptionText.value=''");
  assert.equal(page.run('needsGuard.value'),false);
  page.run("equipmentUuidText.value='eq-1'");assert.equal(page.run('needsGuard.value'),true);
  page.run("equipmentUuidText.value='';busy.value=true");
  assert.equal(backs[0]({from:'backbutton'}),true);assert.equal(modals.length,2);
  assert.equal(page.run('formError.value'),'提交或读取进行中，请等待完成后再离开');
});
test('warehouse stock-taking counts and remarks are guarded edits',()=>{
  const page=script('features/warehouse/board.uvue',{kind:'stocktaking'},{
    ...boardMocks([]),
    uni:{showModal:()=>{},navigateBack:()=>{},reLaunch:()=>{}},
  });
  page.run("selectedId.value=9;lines.value=[{actualQuantityText:'',remarks:''}]");
  assert.equal(page.run('needsGuard.value'),false);
  page.run("lines.value[0].actualQuantityText='12'");
  assert.equal(page.run('needsGuard.value'),true);
  page.run("lines.value[0].actualQuantityText='';lines.value[0].remarks='复盘'");
  assert.equal(page.run('needsGuard.value'),true);
});
test('warehouse alert notes and status changes are guarded against the loaded baseline',()=>{
  const page=script('features/warehouse/board.uvue',{kind:'inventory-alerts'},{
    ...boardMocks([]),
    uni:{showModal:()=>{},navigateBack:()=>{},reLaunch:()=>{}},
  });
  page.run('selectedId.value=5');
  assert.equal(page.run('needsGuard.value'),false);
  page.run("alertStatus.value='resolved'");
  assert.equal(page.run('needsGuard.value'),true);
  page.run("alertStatus.value=alertStatusBaseline.value;alertNotes.value='  已通知'");
  assert.equal(page.run('needsGuard.value'),true);
  page.run("alertNotes.value=''");
  assert.equal(page.run('needsGuard.value'),false);
});
test('warehouse confirm leave re-arms the guard when navigation fails',()=>{
  const modals=[],navOpts=[];
  const page=script('features/warehouse/board.uvue',{kind:'pickings'},{
    ...boardMocks([]),
    uni:{showModal:o=>modals.push(o),navigateBack:o=>navOpts.push(o),reLaunch:o=>navOpts.push(o)},
  });
  page.run("selectedId.value=7;serialInput.value='SN-1'");
  page.run('leaveBack()');
  modals[0].success({confirm:true});
  assert.equal(page.run('leaving.value'),true);
  assert.equal(page.run('needsGuard.value'),false);
  navOpts[0].fail();
  assert.equal(page.run('leaving.value'),false);
  assert.equal(page.run('needsGuard.value'),true);
});
test('warehouse board mirrors guard-state to the wrapper and confirm releases it before navigating',()=>{
  const emits=[],watches=[],modals=[],navOpts=[];
  const page=script('features/warehouse/board.uvue',{kind:'pickings',backRequest:0},{
    ...boardMocks([]),
    defineEmits:()=>(...args)=>emits.push(args),
    watch:(src,cb)=>watches.push(cb),
    uni:{showModal:o=>modals.push(o),navigateBack:o=>navOpts.push(o),reLaunch:o=>navOpts.push(o)},
  });
  page.run("selectedId.value=7;serialInput.value='SN-1'");
  watches.forEach(cb=>cb());
  assert.ok(emits.some(e=>e[0]=='guard-state'&&e[1]==true));
  assert.equal(modals.length,1);
  assert.equal(modals[0].title,'离开确认');
  modals[0].success({confirm:true});
  assert.equal(page.run('leaving.value'),true);
  assert.equal(navOpts.length,1);
  assert.equal(emits[emits.length-1][0],'guard-state');
  assert.equal(emits[emits.length-1][1],false);
});
test('warehouse wrapper pages hoist the back guard through guard-state and back-request',()=>{
  const dir=path.join(root,'features/warehouse');
  const kinds=fs.readdirSync(dir).filter(name=>fs.existsSync(path.join(dir,name,'index.uvue')));
  assert.equal(kinds.length,12);
  for(const kind of kinds){
    const source=fs.readFileSync(path.join(dir,kind,'index.uvue'),'utf8');
    assert.ok(source.includes(':back-request="backRequest"'),kind);
    assert.ok(source.includes(':show-request="showRequest"'),kind);
    assert.ok(source.includes('@guard-state="onGuardState"'),kind);
    assert.ok(source.includes('backRequest.value += 1'),kind);
    assert.ok(source.includes('onBackPress'),kind);
  }
});
test('equipment faults re-arms the leave guard after failed navigation and on show',()=>{
  const modals=[],navOpts=[],backs=[],shows=[];
  const page=script('features/equipment/faults/index.uvue',{},{
    ...faultMocks(modals,[],backs),
    onShow:cb=>shows.push(cb),
    uni:{showModal:o=>modals.push(o),navigateBack:o=>navOpts.push(o),reLaunch:o=>navOpts.push(o)},
  });
  page.run("faultDescriptionText.value='x'");
  page.run('leaveBack()');
  modals[0].success({confirm:true});
  assert.equal(page.run('leaving.value'),true);
  navOpts[0].fail();
  assert.equal(page.run('leaving.value'),false);
  assert.equal(page.run('needsGuard.value'),true);
  page.run('leaving.value=true');
  shows[0]();
  assert.equal(page.run('leaving.value'),false);
});
