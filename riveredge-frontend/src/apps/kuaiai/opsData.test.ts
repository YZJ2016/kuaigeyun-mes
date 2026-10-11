/**
 * spec 184 纯函数单测（node:test）。
 * 运行：node --experimental-strip-types --test src/apps/kuaiai/opsData.test.ts
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  auditStatusTone,
  capabilityLabel,
  fillMissingDays,
  siteTodayISO,
} from './opsData.ts';

test('fillMissingDays补齐缺失日期为0并保持连续升序', () => {
  const out = fillMissingDays(
    [
      { day: '2026-10-09', count: 3 },
      { day: '2026-10-11', count: 1 },
    ],
    7,
    '2026-10-11',
  );
  assert.deepEqual(out, [
    { day: '2026-10-05', count: 0 },
    { day: '2026-10-06', count: 0 },
    { day: '2026-10-07', count: 0 },
    { day: '2026-10-08', count: 0 },
    { day: '2026-10-09', count: 3 },
    { day: '2026-10-10', count: 0 },
    { day: '2026-10-11', count: 1 },
  ]);
});

test('fillMissingDays空输入生成全0序列', () => {
  const out = fillMissingDays([], 3, '2026-10-11');
  assert.equal(out.length, 3);
  assert.equal(out[0].day, '2026-10-09');
  assert.equal(out[2].day, '2026-10-11');
  assert.ok(out.every((d) => d.count === 0));
});

test('fillMissingDays跨月边界', () => {
  const out = fillMissingDays([{ day: '2026-09-30', count: 5 }], 3, '2026-10-02');
  assert.deepEqual(out.map((d) => d.day), [
    '2026-09-30',
    '2026-10-01',
    '2026-10-02',
  ]);
  assert.equal(out[0].count, 5);
});

test('fillMissingDays忽略非法day并入同日出多行计数', () => {
  const out = fillMissingDays(
    [
      { day: 'bad', count: 99 },
      { day: '2026-10-11', count: 2 },
      { day: '2026-10-11', count: 1 },
    ],
    1,
    '2026-10-11',
  );
  assert.deepEqual(out, [{ day: '2026-10-11', count: 3 }]);
});

test('fillMissingDays默认endDay取站点当日(Asia/Shanghai)', () => {
  const today = siteTodayISO(new Date('2026-10-10T16:30:00Z'));
  assert.equal(today, '2026-10-11'); // UTC 16:30 = 上海次日 00:30
  const out = fillMissingDays(null, 2, today);
  assert.equal(out[out.length - 1].day, '2026-10-11');
});

test('capabilityLabel: null/空/unknown → 未分类', () => {
  assert.equal(capabilityLabel(null), '未分类');
  assert.equal(capabilityLabel(undefined), '未分类');
  assert.equal(capabilityLabel(''), '未分类');
  assert.equal(capabilityLabel('   '), '未分类');
  assert.equal(capabilityLabel('unknown'), '未分类');
  assert.equal(capabilityLabel('Unknown'), '未分类');
  assert.equal(capabilityLabel('chat'), 'chat');
  assert.equal(capabilityLabel('  draft '), 'draft');
});

test('auditStatusTone: 2xx/4xx/5xx/空值分档', () => {
  assert.equal(auditStatusTone(200), 'success');
  assert.equal(auditStatusTone(299), 'success');
  assert.equal(auditStatusTone(404), 'warning');
  assert.equal(auditStatusTone(403), 'warning');
  assert.equal(auditStatusTone(500), 'error');
  assert.equal(auditStatusTone(503), 'error');
  assert.equal(auditStatusTone(null), 'default');
  assert.equal(auditStatusTone(0), 'default');
  assert.equal(auditStatusTone(302), 'default');
});
