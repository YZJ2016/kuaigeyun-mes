// Source checks only; these do not substitute for the UTS/native compiler.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('../../../riveredge-frontend/node_modules/typescript');
const root = path.resolve(__dirname, '..');
const files = [
  'shell/workbench/index.uvue', 'shell/workbench/load.uts', 'shell/workbench/recent.uts',
  'shell/registry/index.uts', 'shared/api/session.uts',
  ...['scan-report','my-work-orders','work-orders'].map(p=>'features/workshop/'+p+'/index.uvue'),
  ...['spot-checks','spot-check-conduct','route-patrols','faults'].map(p=>'features/equipment/'+p+'/index.uvue'),
  'features/equipment/selection.uts', 'features/equipment/components/master-picker.uvue',
  'features/warehouse/board.uvue', 'features/warehouse/payload.uts',
  'features/quality/components/inspection-board.uvue',
  ...['incoming','process-scan','finished','oqc'].map(p=>'features/quality/'+p+'/index.uvue'),
];
test('P1 source syntax, relative imports and template tags remain valid',()=>{
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
    const stack=[];
    for(const match of template.matchAll(/<(\/?)([\w-]+)((?:"[^"]*"|'[^']*'|[^'">])*)>/g)) {
      const [,closing,tag,attrs]=match;
      if(closing) assert.equal(stack.pop(),tag,file+': '+tag);
      else if(!attrs.trim().endsWith('/')) stack.push(tag);
    }
    assert.equal(stack.length,0,file+': unclosed tags');
  }
});
