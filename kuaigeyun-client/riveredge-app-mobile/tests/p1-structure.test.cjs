// Source checks only; these do not substitute for the UTS/native compiler.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('../../../riveredge-frontend/node_modules/typescript');
const root = path.resolve(__dirname, '..');
const files = [
  'shared/ui/load-feedback.uvue',
  'features/workshop/exceptions/index.uvue', 'shared/ui/action-card.uvue',
  'shell/login/index.uvue', 'shell/account/index.uvue', 'shared/ui/home-link.uvue', 'shared/ui/choice-button.uvue',
  ...['detail','line-rebinds','maintenance-executions','maintenance-reminders','repairs','scan'].map(p=>'features/equipment/'+p+'/index.uvue'),
  ...['mold-borrows','mold-reminders','mold-scan'].map(p=>'features/mold/'+p+'/index.uvue'),
  ...['nonconforming','quality-hub'].map(p=>'features/quality/'+p+'/index.uvue'),
  ...['exception-report','packing-binding','reporting-approve','work-order-assign'].map(p=>'features/workshop/'+p+'/index.uvue'),
  'shell/account/edit.uvue', 'shell/account/password.uvue', 'shell/tenant/index.uvue',
  'shell/apps/index.uvue', 'shared/ui/action-button.uvue', 'shared/ui/selection-row.uvue',
  'shared/ui/date-field.uvue', 'shared/ui/date.uts', 'shared/ui/navigate.uts', 'shared/ui/status-badge.uvue',
  'features/mold/http.uts', ...['mold-repairs','mold-maintenances','mold-returns'].map(p=>'features/mold/'+p+'/index.uvue'),
  'shell/workbench/index.uvue', 'shell/workbench/load.uts', 'shell/workbench/recent.uts',
  'shell/registry/index.uts', 'shared/api/session.uts',
  ...['scan-report','my-work-orders','work-orders'].map(p=>'features/workshop/'+p+'/index.uvue'),
  ...['spot-checks','spot-check-conduct','route-patrols','faults'].map(p=>'features/equipment/'+p+'/index.uvue'),
  'features/equipment/selection.uts', 'features/equipment/components/master-picker.uvue',
  'features/warehouse/board.uvue', 'features/warehouse/payload.uts',
  'features/quality/components/inspection-board.uvue',
  ...['incoming','process-scan','finished','oqc'].map(p=>'features/quality/'+p+'/index.uvue'),
];
test('P1/P2 source syntax, relative imports and template tags remain valid',()=>{
  for (const file of files) {
    const source=fs.readFileSync(path.join(root,file),'utf8');
    const script=file.endsWith('.uts')?source:source.match(/<script setup lang="uts">([\s\S]*?)<\/script>/)[1];
    const output=ts.transpileModule(script,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS},reportDiagnostics:true});
    assert.deepEqual((output.diagnostics??[]).filter(d=>d.category===ts.DiagnosticCategory.Error).map(d=>d.messageText),[],file);
    for (const match of script.matchAll(/from\s+['"](\.[^'"]+)['"]/g)) {
      assert.ok(fs.existsSync(path.resolve(root,path.dirname(file),match[1])),file+': '+match[1]);
    }
    if(!file.endsWith('.uvue')) continue;
    const template=source.match(/<template>([\s\S]*?)<\/template>/)[1];
    for (const match of template.matchAll(/:(?:label|disabled|busy|selected|key|value)="([^"]*)"/g)) {
      const parsed=ts.createSourceFile('binding.ts','const binding = ('+match[1]+');',ts.ScriptTarget.ES2020,true);
      assert.deepEqual(parsed.parseDiagnostics.map(d=>d.messageText),[],file+': '+match[0]);
    }
    const stack=[];
    for(const match of template.matchAll(/<(\/?)([\w-]+)((?:"[^"]*"|'[^']*'|[^'">])*)>/g)) {
      const [,closing,tag,attrs]=match;
      if(closing) assert.equal(stack.pop(),tag,file+': '+tag);
      else if(!attrs.trim().endsWith('/')) stack.push(tag);
    }
    assert.equal(stack.length,0,file+': unclosed tags');
  }
});
