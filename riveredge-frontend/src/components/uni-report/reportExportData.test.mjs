import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fetchAllReportRows, selectReportExportRows, buildReportCsv, buildReportHtml } from './reportExportData.ts';

test('all export reads every page with the same filters, starting at zero', async () => {
  const calls = [];
  const rows = await fetchAllReportRows(async (filters) => {
    calls.push(filters);
    return { data: filters.offset === 0 ? [{ value: 1 }, { value: 2 }] : [{ value: 3 }], total: 3 };
  }, { status: 'ready', offset: 40, limit: 20 }, 2);
  assert.deepEqual(rows.map((r) => r.value), [1, 2, 3]);
  assert.deepEqual(calls, [{ status: 'ready', limit: 2, offset: 0 }, { status: 'ready', limit: 2, offset: 2 }]);
});

test('all export fails instead of silently downloading a partial report', async () => {
  await assert.rejects(fetchAllReportRows(async ({ offset }) => ({ data: offset ? [] : [{ a: 1 }], total: 2 }), {}, 1));
});

test('selected export uses the configured row key and empty selection exports nothing', () => {
  const rows = [{ uuid: 'a', value: 1 }, { uuid: 'b', value: 2 }];
  assert.deepEqual(selectReportExportRows('selected', ['b'], rows, 'uuid'), [rows[1]]);
  assert.deepEqual(selectReportExportRows('selected', [], rows, 'uuid'), []);
  assert.deepEqual(selectReportExportRows('currentPage', [], rows, 'uuid'), rows);
});

test('CSV quotes commas, quotes and CR/LF; HTML escapes report and cell markup', () => {
  assert.equal(buildReportCsv(['名称'], ['name'], [{ name: 'a,"b"\r\nc' }]), '\ufeff名称\r\n"a,""b""\r\nc"');
  const html = buildReportHtml('<报表>', ['<名称>'], ['name'], [{ name: '<script>alert(1)</script>' }]);
  assert.ok(html.includes('&lt;报表&gt;'));
  assert.ok(html.includes('&lt;script&gt;'));
  assert.ok(!html.includes('<script>'));
});
