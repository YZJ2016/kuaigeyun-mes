/**
 * 直接跑前端会话选择解析（不进 Vite 打包）。
 * node --experimental-strip-types scripts/check-chat-session-selection.mts
 */
import assert from 'node:assert/strict';
import {
  formatCatalogModelRef,
  parseSessionQueryId,
  resolveSessionModelId,
  sessionSelectionPayload,
} from '../src/apps/kuaiai/pages/chat/sessionSelection.ts';

const options = [
  { id: 5, model_name: 'deepseek-chat' },
  { id: 8, model_name: 'deepseek-chat' },
  { id: 9, model_name: 'qwen-plus' },
];

assert.equal(formatCatalogModelRef(5), '#id:5');
assert.equal(resolveSessionModelId('#id:5', options), 5);
assert.equal(resolveSessionModelId('  #id:9 ', options), 9);
assert.equal(resolveSessionModelId('#id:5', [{ id: 1, model_name: 'other' }]), undefined);
assert.equal(resolveSessionModelId('#id:', options), undefined);
assert.equal(resolveSessionModelId('#id:0', options), undefined);
assert.equal(resolveSessionModelId('#id:abc', options), undefined);
assert.equal(resolveSessionModelId('qwen-plus', options), 9);
assert.equal(resolveSessionModelId('deepseek-chat', options), undefined);
assert.equal(resolveSessionModelId('missing', options), undefined);
assert.equal(resolveSessionModelId(null, options), undefined);
assert.equal(resolveSessionModelId('', options), undefined);

assert.equal(parseSessionQueryId('12'), 12);
assert.equal(parseSessionQueryId(''), null);
assert.equal(parseSessionQueryId(null), null);
assert.equal(parseSessionQueryId('0'), null);
assert.equal(parseSessionQueryId('01'), null);
assert.equal(parseSessionQueryId('1.5'), null);
assert.equal(parseSessionQueryId('abc'), null);

assert.deepEqual(sessionSelectionPayload(3, 5), { agent_id: 3, model: null });
assert.deepEqual(sessionSelectionPayload(undefined, 5), {
  agent_id: null,
  model: '#id:5',
});
assert.deepEqual(sessionSelectionPayload(undefined, undefined), {});

console.log('sessionSelection ok');
