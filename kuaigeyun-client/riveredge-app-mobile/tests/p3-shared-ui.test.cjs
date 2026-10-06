// 说明：role/aria-* 断言均为源码断言（表达意图）；编译后属性是否真实落到原生元素需在 HBuilderX 构建中验证。
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
function navStubs(calls,statusBarHeight) {
  const uni={navigateBack:()=>calls.push('navigateBack'),reLaunch:o=>calls.push(o.url)};
  if(statusBarHeight!=null) uni.getWindowInfo=()=>({statusBarHeight});
  return {getCurrentPages:()=>[{route:'features/quality/incoming/index',getPageStyle:()=>({getString:()=> '来料检验'})}],uni};
}
test('home-link intercepts 返回 only while holdBack is set',()=>{
  const calls=[];const props={title:'',holdBack:true};
  const page=script('shared/ui/home-link.uvue',props,navStubs(calls));
  page.run('onBack()');assert.deepEqual(page.events,[['back']]);assert.equal(calls.length,0);
  props.holdBack=false;page.run('onBack()');assert.deepEqual(calls,['navigateBack']);assert.equal(page.events.length,1);
});
test('home-link still intercepts 首页 via holdHome and navigates by default',()=>{
  const calls=[];const props={title:'',holdHome:true};
  const page=script('shared/ui/home-link.uvue',props,navStubs(calls));
  page.run('onHome()');assert.deepEqual(page.events,[['home']]);assert.equal(calls.length,0);
  props.holdHome=false;page.run('onHome()');assert.deepEqual(calls,['/shell/workbench/index']);
});
test('home-link pads the nav by the reported status bar height and stays flat otherwise',()=>{
  const page=script('shared/ui/home-link.uvue',{title:''},navStubs([],24));
  assert.equal(page.run('navInsetTop.value'),24);
  const plain=script('shared/ui/home-link.uvue',{title:''},navStubs([]));
  assert.equal(plain.run('navInsetTop.value'),0);
  const source=fs.readFileSync(path.join(root,'shared/ui/home-link.uvue'),'utf8');
  assert.match(source,/navInsetTop \+ 'px'/);assert.match(source,/class="nav-inset"/);
});
test('shared buttons bind accessible name, role and state semantics on the button element',()=>{
  for(const file of ['shared/ui/action-button.uvue','shared/ui/choice-button.uvue']) {
    const source=fs.readFileSync(path.join(root,file),'utf8');
    const button=source.match(/<button\b[\s\S]*?\{\{/)[0];
    assert.match(button,/role="button"/,file);
    assert.match(button,/:aria-label="accessibilityLabel\.length > 0 \? accessibilityLabel : label"/,file);
    assert.match(source,/accessibilityLabel: \{ type: String, default: '' \}/,file);
  }
  const action=fs.readFileSync(path.join(root,'shared/ui/action-button.uvue'),'utf8');
  assert.match(action,/:aria-busy="busy"/);assert.match(action,/:aria-disabled="disabled \|\| busy"/);
  const choice=fs.readFileSync(path.join(root,'shared/ui/choice-button.uvue'),'utf8');
  assert.match(choice,/:aria-pressed="selected"/);assert.match(choice,/:aria-disabled="disabled"/);
});
test('choice-button keeps the choose contract alongside pressed-state semantics',()=>{
  const props={disabled:false,selected:true,label:'合格',accessibilityLabel:'检验结果：合格'};
  const page=script('shared/ui/choice-button.uvue',props);
  page.run('activate()');assert.deepEqual(page.events,[['choose']]);
  props.disabled=true;page.run('activate()');assert.equal(page.events.length,1);
});
test('action-button keeps the press contract with accessibilityLabel set',()=>{
  const props={label:'保存',accessibilityLabel:'保存表单',busy:false,disabled:false};
  const page=script('shared/ui/action-button.uvue',props);
  page.run('activate()');assert.deepEqual(page.events,[['press']]);
  props.busy=true;page.run('activate()');assert.equal(page.events.length,1);
});
test('action-card binds role, accessible name and disabled state on the slotted button',()=>{
  const source=fs.readFileSync(path.join(root,'shared/ui/action-card.uvue'),'utf8');
  const button=source.match(/<button\b[\s\S]*?<slot/)[0];
  assert.match(button,/role="button"/);
  assert.match(button,/:aria-label="accessibilityLabel"/);
  assert.match(button,/:aria-disabled="disabled"/);
  assert.match(source,/accessibilityLabel: \{ type: String, default: '' \}/);
  const props={disabled:false,variant:'card',accessibilityLabel:'打开工单'};
  const page=script('shared/ui/action-card.uvue',props);
  page.run('activate()');assert.deepEqual(page.events,[['press']]);
  props.disabled=true;page.run('activate()');assert.equal(page.events.length,1);
});
test('selection-row binds pressed state and accessible name with label fallback',()=>{
  const source=fs.readFileSync(path.join(root,'shared/ui/selection-row.uvue'),'utf8');
  const button=source.match(/<button\b[\s\S]*?@click/)[0];
  assert.match(button,/role="button"/);
  assert.match(button,/:aria-label="accessibilityLabel\.length > 0 \? accessibilityLabel : label"/);
  assert.match(button,/:aria-pressed="selected"/);
  assert.match(button,/:aria-disabled="disabled \|\| busy"/);
  assert.match(button,/:aria-busy="busy"/);
  assert.match(source,/accessibilityLabel: \{ type: String, default: '' \}/);
  const props={label:'借用工装',selected:false,disabled:false,busy:false,accessibilityLabel:'选择借用工装'};
  const page=script('shared/ui/selection-row.uvue',props);
  page.run('activate()');assert.deepEqual(page.events,[['choose']]);
  props.busy=true;page.run('activate()');assert.equal(page.events.length,1);
});
test('scroll-into-view targets resolve to ids inside the same file',()=>{
  const scan=fs.readFileSync(path.join(root,'features/workshop/scan-report/index.uvue'),'utf8');
  for(const id of ['report-field-reported','report-field-unqualified','report-field-hours']) {
    assert.ok(scan.includes('id="'+id+'"'),'scan-report missing id '+id);
  }
  const board=fs.readFileSync(path.join(root,'features/quality/components/inspection-board.uvue'),'utf8');
  assert.match(board,/:id="'quality-step-' \+ index"/);
  assert.match(board,/scrollTarget\.value = 'quality-step-' \+ /);
});
