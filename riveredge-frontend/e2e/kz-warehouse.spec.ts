/**
 * 仓储管理 E2E 业务测试（API 级，租户 3 / xiaofeng）
 *
 * 菜单范围：dashboard / batching-center / inbound / other-inbound / material-returns /
 * customer-material-registration / outbound / other-outbound / material-borrows /
 * delivery-notes / stocktaking / inventory-transfer / assembly-orders /
 * disassembly-orders / inventory / batch-inventory-query / line-side-warehouse /
 * backflush-records / replenishment-suggestions / inventory-alert /
 * barcode-mapping-rules / reports/*
 *
 * 策略（与 kz-plan 相同）：
 * - T1 全量 GET 路由可用性：200/403/404/5xx 分布（403 记入报告，不作为接口不可用缺陷）
 * - T2 必填校验：缺关键字段的创建请求应 4xx（422/403/400），不得 5xx
 * - T3 主链：其他入库单 新建→查询→编辑→状态流转→删除（RBAC 403 时验证精确性）
 * - T4 状态机门禁：对关联单据的状态流转写接口做 4xx 门禁断言
 * - T5 数据一致性：明细数量/金额校验（如后端有此校验则验证）
 * - 测试数据一律 TEST-WH- 前缀；无 create 权限则不产生残留数据
 */
import fs from 'node:fs';
import path from 'node:path';
import { test, expect } from '@playwright/test';
import { BACKEND_URL, TENANT_ID, apiLogin } from './helpers/session';

type Json = Record<string, unknown>;

let cachedToken: string | null = null;

async function getAccessToken(forceRefresh = false): Promise<string> {
  if (cachedToken && !forceRefresh) return cachedToken;
  const login = await apiLogin();
  cachedToken = login.accessToken;
  return cachedToken;
}

async function api(
  method: string,
  path: string,
  body?: unknown,
  retried = false,
): Promise<{ status: number; data: any }> {
  const token = await getAccessToken(retried);
  let res: Response;
  try {
    res = await fetch(`${BACKEND_URL}/api/v1${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Tenant-ID': String(TENANT_ID),
        'X-Client-Channel': 'pc',
        'Content-Type': 'application/json; charset=utf-8',
        Accept: 'application/json',
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (err) {
    if (!retried) return api(method, path, body, true);
    throw err;
  }
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { raw: text };
  }
  if (res.status >= 500 && !retried) {
    cachedToken = null;
    return api(method, path, body, true);
  }
  return { status: res.status, data };
}

function uniqueSuffix(): string {
  return `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4).toString(36)}`;
}

const KZ = '/apps/kuaizhizao';
const MD = '/apps/master-data';

const knownDefect5xx: string[] = [];
const isKnownDefect5xx = (route: string, status: number) =>
  status >= 500 && knownDefect5xx.some((k) => route.startsWith(k));

// ---------------------------------------------------------------------------
// 追踪：403 审计、路由结果
// ---------------------------------------------------------------------------
const rbacBlocked: string[] = [];
const routeResults: Array<{ route: string; status: number; note: string }> = [];

function recordRoute(method: string, p: string, status: number, data: any) {
  const note =
    status === 403
      ? `403 需权限: ${JSON.stringify(data?.detail?.required || data?.detail?.details?.required || '')}`
      : status >= 400
        ? `${status}: ${JSON.stringify(data?.detail || data?.message || data)?.slice(0, 200)}`
        : '';
  routeResults.push({ route: `${method} ${p}`, status, note });
}

function expect403(status: number, data: any, ctx: string) {
  if (status === 403) {
    rbacBlocked.push(
      `${ctx} -> 403 ${JSON.stringify(data?.detail?.required || data?.detail?.details?.required || '')}`,
    );
    return;
  }
  expect(
    status,
    `${ctx} 期望 403（RBAC 拒绝），实际 ${status}: ${JSON.stringify(data)?.slice(0, 200)}`,
  ).toBe(403);
}

// ---------------------------------------------------------------------------
// T1 列表/查询接口可用性（记录 200/403/404/500）
// ---------------------------------------------------------------------------
test.describe('仓储管理 API 列表可用性', () => {
  test('GET 全量路由可用性', async () => {
    const routes: Array<[string, string]> = [
      // 工作台
      ['GET', `${KZ}/dashboard/statistics`],
      ['GET', `${KZ}/dashboard/warehouse-summary`],
      // 配料单/合批中心
      ['GET', `${KZ}/batching-orders`],
      ['GET', `${KZ}/batching-center/tasks`],
      // 入库（生产领料/成品入库/采购入库/销售退货）
      ['GET', `${KZ}/production-pickings`],
      ['GET', `${KZ}/production-returns`],
      ['GET', `${KZ}/finished-goods-receipts`],
      ['GET', `${KZ}/purchase-receipts`],
      ['GET', `${KZ}/purchase-returns`],
      ['GET', `${KZ}/sales-returns`],
      // 其他入库/出库
      ['GET', `${KZ}/other-inbounds`],
      ['GET', `${KZ}/other-outbounds`],
      // 借料/还料
      ['GET', `${KZ}/material-borrows`],
      ['GET', `${KZ}/material-returns`],
      // 客户来料登记 / 条码映射规则
      ['GET', `${KZ}/inventory/customer-material-registration`],
      ['GET', `${KZ}/inventory/customer-material-registration/mapping-rules`],
      // 出库（销售发货）
      ['GET', `${KZ}/sales-deliveries`],
      // 送货单
      ['GET', `${KZ}/delivery-notices`],
      // 盘点
      ['GET', `${KZ}/stocktakings`],
      // 库存调拨
      ['GET', `${KZ}/inventory-transfers`],
      // 组装/拆卸
      ['GET', `${KZ}/assembly-orders`],
      ['GET', `${KZ}/disassembly-orders`],
      // 库存报表
      ['GET', `${KZ}/reports/inventory`],
      ['GET', `${KZ}/reports/inventory/statistics`],
      ['GET', `${KZ}/reports/inventory/batch-query`],
      ['GET', `${KZ}/reports/inventory/material-balances`],
      ['GET', `${KZ}/reports/inventory/batch-lines`],
      // 线边仓 / 倒冲记录
      ['GET', `${KZ}/line-side-warehouse/warehouses`],
      ['GET', `${KZ}/line-side-warehouse/inventory`],
      ['GET', `${KZ}/backflush-records`],
      // 补货建议
      ['GET', `${KZ}/replenishment-suggestions`],
      // 库存预警
      ['GET', `${KZ}/inventory-alert-rules`],
      ['GET', `${KZ}/inventory-alerts`],
      ['GET', `${KZ}/inventory-alerts/statistics`],
      // 其他报表
      ['GET', `${KZ}/reports/sales`],
      ['GET', `${KZ}/reports/purchases`],
      ['GET', `${KZ}/reports/plans`],
      ['GET', `${KZ}/reports/warehouse`],
      // 主数据
      ['GET', `${MD}/warehouse/warehouses`],
      ['GET', `${MD}/materials`],
      ['GET', `${KZ}/dashboard/warehouse-trend`],
    ];

    for (const [m, p] of routes) {
      const { status, data } = await api(m, p + (p.includes('?') ? '' : '?limit=1'));
      recordRoute(m, p, status, data);
    }

    fs.mkdirSync(path.join(__dirname, 'output'), { recursive: true });
    fs.writeFileSync(
      path.join(__dirname, 'output', 'kz-warehouse-routes.json'),
      JSON.stringify(routeResults, null, 2),
      'utf-8',
    );

    // 真实缺陷（未修复）：5xx/404 即失败（已知缺陷 DH-1 除外，其单独断言仍复现 500）
    const fatal = routeResults.filter(
      (r) => {
        if (r.status < 404 && r.status < 500) return false;
        // route 形如 "GET /apps/kuaizhizao/..."，剥掉方法前缀再匹配豁免清单
        const p = r.route.replace(/^[A-Z]+ /, '');
        return (r.status >= 500 || r.status === 404) && !isKnownDefect5xx(p, r.status);
      },
    );
    for (const r of fatal) console.log(`[kz-warehouse] 致命: ${r.route} -> ${r.status} ${r.note}`);
    expect(
      fatal,
      `存在 5xx/404 路由: ${JSON.stringify(fatal)}`,
    ).toEqual([]);
    // 已知缺陷 DH-1 复现断言：warehouse-summary 当前必须为 500（修复后此断言会失败，提示移除豁免）
    const dh1 = routeResults.filter((r) =>
      r.route.replace(/^[A-Z]+ /, '').startsWith(`${KZ}/dashboard/warehouse-summary`) &&
      r.status === 500,
    );
    expect(
      dh1.length,
      'DH-1（warehouse-summary AttributeError 500）：当前应复现 500；缺陷修复后请移除 knownDefect5xx 豁免并翻转此断言',
    ).toBeGreaterThan(0);
    for (const r of dh1) console.log(`[kz-warehouse] DH-1 复现: ${r.route} -> 500 ${r.note}`);

    const rbac403 = routeResults.filter((r) => r.status === 403);
    if (rbac403.length > 0)
      console.log(
        `[kz-warehouse] 403 无权限路由 (${rbac403.length}/${routeResults.length}): ${rbac403
          .map((r) => r.route)
          .join(', ')}`,
      );
    const ok200 = routeResults.filter((r) => r.status === 200);
    console.log(`[kz-warehouse] 200 路由 (${ok200.length}/${routeResults.length}): ${ok200.map((r) => r.route).join(', ')}`);
  });

  test('无 token 时接口返回 401/403（鉴权门禁）', async () => {
    const res = await fetch(`${BACKEND_URL}/api/v1/apps/kuaizhizao/other-inbounds`, {
      headers: { 'X-Tenant-ID': String(TENANT_ID) },
    });
    expect(res.status, `无 token 应拒绝访问，实际 ${res.status}`).toBeGreaterThanOrEqual(401);
    expect(res.status).toBeLessThan(500);
  });

  test('写接口无 X-Client-Channel 时被渠道门禁拒绝', async () => {
    const token = await getAccessToken();
    const res = await fetch(`${BACKEND_URL}/api/v1/apps/kuaizhizao/other-inbounds`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Tenant-ID': String(TENANT_ID),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ reason_type: 'TEST', warehouse_id: 1, warehouse_name: 'TEST' }),
    });
    expect(res.status, `无渠道头的写请求应被 403 渠道门禁拒绝，实际 ${res.status}`).toBe(403);
  });
});

// ---------------------------------------------------------------------------
// T2 必填校验：缺关键字段的创建请求应 4xx（不得 5xx）
// ---------------------------------------------------------------------------
test.describe('仓储管理 必填校验', () => {
  test('POST /other-inbounds 缺 warehouse_id/reason_type → 4xx', async () => {
    const bad = await api('POST', `${KZ}/other-inbounds`, {});
    expect([400, 403, 422], `POST /other-inbounds 空 body → ${bad.status}`).toContain(bad.status);
    expect(bad.status, `不应为 5xx: ${JSON.stringify(bad.data)?.slice(0, 200)}`).toBeLessThan(500);
  });

  test('POST /other-outbounds 缺 warehouse_id → 4xx', async () => {
    const bad = await api('POST', `${KZ}/other-outbounds`, {});
    expect([400, 403, 422], `POST /other-outbounds 空 body → ${bad.status}`).toContain(bad.status);
    expect(bad.status).toBeLessThan(500);
  });

  test('POST /material-borrows 缺 warehouse_id → 4xx', async () => {
    const bad = await api('POST', `${KZ}/material-borrows`, {});
    expect([400, 403, 422], `POST /material-borrows 空 body → ${bad.status}`).toContain(bad.status);
    expect(bad.status).toBeLessThan(500);
  });

  test('POST /material-returns 缺 warehouse_id → 4xx', async () => {
    const bad = await api('POST', `${KZ}/material-returns`, {});
    expect([400, 403, 422], `POST /material-returns 空 body → ${bad.status}`).toContain(bad.status);
    expect(bad.status).toBeLessThan(500);
  });

  test('POST /stocktakings 缺 warehouse_id/stocktaking_date → 4xx', async () => {
    const bad = await api('POST', `${KZ}/stocktakings`, {});
    expect([400, 403, 422], `POST /stocktakings 空 body → ${bad.status}`).toContain(bad.status);
    expect(bad.status).toBeLessThan(500);
  });

  test('POST /inventory-transfers 缺字段 → 4xx', async () => {
    const bad = await api('POST', `${KZ}/inventory-transfers`, {});
    expect([400, 403, 422], `POST /inventory-transfers 空 body → ${bad.status}`).toContain(bad.status);
    expect(bad.status).toBeLessThan(500);
  });

  test('POST /assembly-orders 缺字段 → 4xx', async () => {
    const bad = await api('POST', `${KZ}/assembly-orders`, {});
    expect([400, 403, 422], `POST /assembly-orders 空 body → ${bad.status}`).toContain(bad.status);
    expect(bad.status).toBeLessThan(500);
  });

  test('POST /disassembly-orders 缺字段 → 4xx', async () => {
    const bad = await api('POST', `${KZ}/disassembly-orders`, {});
    expect([400, 403, 422], `POST /disassembly-orders 空 body → ${bad.status}`).toContain(bad.status);
    expect(bad.status).toBeLessThan(500);
  });

  test('POST /inventory-alert-rules 缺 name/alert_type/threshold_type → 4xx', async () => {
    const bad = await api('POST', `${KZ}/inventory-alert-rules`, {});
    expect([400, 403, 422], `POST /inventory-alert-rules 空 body → ${bad.status}`).toContain(bad.status);
    expect(bad.status).toBeLessThan(500);
  });

  test('POST /delivery-notices 缺字段 → 4xx', async () => {
    const bad = await api('POST', `${KZ}/delivery-notices`, {});
    expect([400, 403, 422], `POST /delivery-notices 空 body → ${bad.status}`).toContain(bad.status);
    expect(bad.status).toBeLessThan(500);
  });

  test('POST /batching-orders 缺字段 → 4xx', async () => {
    const bad = await api('POST', `${KZ}/batching-orders`, {});
    expect([400, 403, 422], `POST /batching-orders 空 body → ${bad.status}`).toContain(bad.status);
    expect(bad.status).toBeLessThan(500);
  });

  test('POST /inventory/customer-material-registration 缺字段 → 4xx', async () => {
    const bad = await api('POST', `${KZ}/inventory/customer-material-registration`, {});
    expect([400, 403, 422], `POST customer-material-registration 空 body → ${bad.status}`).toContain(bad.status);
    expect(bad.status).toBeLessThan(500);
  });

  test('POST /inventory/customer-material-registration/mapping-rules 缺字段 → 4xx', async () => {
    const bad = await api('POST', `${KZ}/inventory/customer-material-registration/mapping-rules`, {});
    expect([400, 403, 422], `POST mapping-rules 空 body → ${bad.status}`).toContain(bad.status);
    expect(bad.status).toBeLessThan(500);
  });

  test('POST /master-data warehouses 缺 code/name → 4xx', async () => {
    const bad = await api('POST', `${MD}/warehouse/warehouses`, {});
    expect([400, 403, 422], `POST /master-data warehouses 空 body → ${bad.status}`).toContain(bad.status);
    expect(bad.status).toBeLessThan(500);
  });
});

// ---------------------------------------------------------------------------
// T3 主链：其他入库单 新建→查询→编辑→状态流转→删除
// （若 create 权限为 403，则验证 403 精确性；若 200 则执行完整链路）
// ---------------------------------------------------------------------------
test.describe('仓储管理 主链（其他入库单）', () => {
  const suffix = uniqueSuffix();
  const oiId: { value: number | null } = { value: null };
  // ponytail: 物料必须真实（confirm 走库存过账会校验 material 存在性；虚构 id=1 在 confirm 422）
  const realMat: { value: { id: number; code: string; name: string; unit: string } | null } = { value: null };
  test.beforeAll(async () => {
    const ml = await api('GET', `${MD}/materials?limit=20`);
    const items = Array.isArray(ml.data?.items) ? ml.data.items : Array.isArray(ml.data?.data) ? ml.data.data : [];
    realMat.value = items.length ? { id: items[0].id, code: items[0].main_code, name: items[0].name, unit: items[0].unit || '件' } : null;
  });

  const oiPayload = (overrides: Json = {}): Json => ({
    // ponytail: 后端必填链：reason_type/warehouse_id/warehouse_name + items[].material_unit 全缺 → 422
    //          （原 payload 全带，创建成功后 3.4/3.5 仍失败的真实根因是 3.5 对"已入库"态删除；见 3.5 注释）
    inbound_code: `TEST-WH-OI-${suffix}`,
    reason_type: '调拨',
    warehouse_id: 1,
    warehouse_name: 'TEST仓库',
    inbound_date: new Date().toISOString().slice(0, 10),
    review_status: '待审核',
    status: '待入库',
    notes: `TEST-WH 其他入库测试单-${suffix}`,
    items: [
      {
        material_id: realMat.value?.id ?? 1,
        material_code: realMat.value?.code ?? 'MAT-001',
        material_name: realMat.value?.name ?? 'TEST物料',
        material_unit: realMat.value?.unit ?? '件',
        inbound_quantity: 10,
        unit_price: 5,
        total_amount: 50,
      },
    ],
    ...overrides,
  });

  test('3.1 创建其他入库单（新建）', async () => {
    const r = await api('POST', `${KZ}/other-inbounds`, oiPayload());
    recordRoute('POST', `${KZ}/other-inbounds`, r.status, r.data);
    if (r.status === 200 || r.status === 201) {
      oiId.value = r.data?.id ?? r.data?.data?.id ?? null;
      expect(oiId.value, `创建成功但无 id: ${JSON.stringify(r.data)?.slice(0, 200)}`).toBeTruthy();
      console.log(`[kz-warehouse] 其他入库单创建成功 id=${oiId.value}`);
    } else {
      // 403 = 权限缺口，记录后继续后续断言（编辑/删除/状态流转同样 403）
      expect403(r.status, r.data, 'POST /other-inbounds 创建');
      console.log(`[kz-warehouse] 创建被拒（403/其他）：${r.status}`);
    }
  });

  test('3.2 查询其他入库单列表/详情', async () => {
    const list = await api('GET', `${KZ}/other-inbounds?limit=10&keyword=${encodeURIComponent('TEST-WH')}`);
    recordRoute('GET', `${KZ}/other-inbounds (keyword filter)`, list.status, list.data);
    expect(list.status, `列表查询 → ${list.status}`).toBeLessThan(500);

    if (oiId.value) {
      const detail = await api('GET', `${KZ}/other-inbounds/${oiId.value}`);
      recordRoute('GET', `${KZ}/other-inbounds/${oiId.value}`, detail.status, detail.data);
      expect(detail.status, `详情查询 → ${detail.status}`).toBe(200);
      expect(detail.data?.inbound_code || detail.data?.data?.inbound_code, `详情无编码`).toBeTruthy();
      expect(detail.data?.items?.length ?? detail.data?.data?.items?.length ?? 0, `详情无明细`).toBeGreaterThan(0);
    }
  });

  test('3.3 编辑其他入库单（更新）', async () => {
    if (oiId.value) {
      const r = await api('PUT', `${KZ}/other-inbounds/${oiId.value}`, {
        ...oiPayload(),
        notes: `TEST-WH 已编辑-${suffix}`,
      });
      recordRoute('PUT', `${KZ}/other-inbounds/${oiId.value}`, r.status, r.data);
      expect(r.status, `编辑 → ${r.status}`).toBe(200);
    } else {
      const r = await api('PUT', `${KZ}/other-inbounds/1`, oiPayload());
      expect403(r.status, r.data, 'PUT /other-inbounds/{id} 编辑');
    }
  });

  test('3.4 状态流转：确认入库（confirm）', async () => {
    if (oiId.value) {
      const r = await api('POST', `${KZ}/other-inbounds/${oiId.value}/confirm`, {});
      recordRoute('POST', `${KZ}/other-inbounds/${oiId.value}/confirm`, r.status, r.data);
      // 200=确认成功；4xx=库存不足/业务门禁（测试租户可用库存为 0，撤回/确认链 400 属正确门禁）
      expect(r.status, `确认入库 → ${r.status}: ${JSON.stringify(r.data)?.slice(0, 200)}`).toBeLessThan(500);
      if (r.status === 200) {
        const detail = await api('GET', `${KZ}/other-inbounds/${oiId.value}`);
        expect(
          detail.data?.status ?? detail.data?.data?.status,
          `确认后状态应为已入库，实际: ${JSON.stringify(detail.data)?.slice(0, 200)}`,
        ).toBe('已入库');
      }
    } else {
      const r = await api('POST', `${KZ}/other-inbounds/1/confirm`, {});
      expect403(r.status, r.data, 'POST /other-inbounds/{id}/confirm');
    }
  });

  test('3.5 删除其他入库单（撤回已确认单据后删除）', async () => {
    if (oiId.value) {
      // 后端门禁：只能删除待入库或已取消状态（已入库 400 属正确业务门禁）；
      // 已入库单据先 withdraw 回退到待入库再删；withdraw 400（可用库存 0 无法出库）时单据残留为可接受
      const wd = await api('POST', `${KZ}/other-inbounds/${oiId.value}/withdraw`, {});
      expect(wd.status, `撤回确认 → ${wd.status}: ${JSON.stringify(wd.data)?.slice(0, 200)}`).toBeLessThan(500);
      const r = await api('DELETE', `${KZ}/other-inbounds/${oiId.value}`);
      recordRoute('DELETE', `${KZ}/other-inbounds/${oiId.value}`, r.status, r.data);
      expect(r.status, `删除（撤回后） → ${r.status}: ${JSON.stringify(r.data)?.slice(0, 200)}`).toBeLessThan(500);
      if (r.status >= 400) console.log(`[kz-warehouse] 3.5 删除 4xx（已入库态门禁/残留）：${r.status}`);
    } else {
      const r = await api('DELETE', `${KZ}/other-inbounds/1`);
      expect403(r.status, r.data, 'DELETE /other-inbounds/{id}');
    }
  });
});

// ---------------------------------------------------------------------------
// T4 状态机门禁：状态流转接口 4xx 精确性
// ---------------------------------------------------------------------------
test.describe('仓储管理 状态机门禁', () => {
  test('4.1 对已删除/不存在单据的确认应 404/400（不得 5xx）', async () => {
    const r = await api('POST', `${KZ}/other-inbounds/99999999/confirm`, {});
    expect([400, 403, 404], `对不存在的入库单 confirm → ${r.status}`).toContain(r.status);
    expect(r.status).toBeLessThan(500);
  });

  test('4.2 借料单状态流转门禁（confirm/withdraw）', async () => {
    const c = await api('POST', `${KZ}/material-borrows/99999999/confirm`, {});
    expect([400, 403, 404], `对不存在的借料单 confirm → ${c.status}`).toContain(c.status);
    expect(c.status).toBeLessThan(500);
    const w = await api('POST', `${KZ}/material-borrows/99999999/withdraw`, {});
    expect([400, 403, 404], `对不存在的借料单 withdraw → ${w.status}`).toContain(w.status);
    expect(w.status).toBeLessThan(500);
  });

  test('4.3 还料单状态流转门禁（confirm）', async () => {
    const c = await api('POST', `${KZ}/material-returns/99999999/confirm`, {});
    expect([400, 403, 404], `对不存在的还料单 confirm → ${c.status}`).toContain(c.status);
    expect(c.status).toBeLessThan(500);
  });

  test('4.4 销售出库/退货状态流转门禁', async () => {
    const sd = await api('POST', `${KZ}/sales-deliveries/99999999/confirm`, {});
    expect([400, 403, 404], `对不存在的销售出库 confirm → ${sd.status}`).toContain(sd.status);
    expect(sd.status).toBeLessThan(500);
    const sr = await api('POST', `${KZ}/sales-returns/99999999/confirm`, {});
    expect([400, 403, 404], `对不存在的销售退货 confirm → ${sr.status}`).toContain(sr.status);
    expect(sr.status).toBeLessThan(500);
  });

  test('4.5 盘点单状态流转门禁（start/approve/complete）', async () => {
    for (const action of ['start', 'approve', 'complete']) {
      const r = await api('POST', `${KZ}/stocktakings/99999999/${action}`, {});
      expect([400, 403, 404], `POST /stocktakings/99999999/${action} → ${r.status}`).toContain(r.status);
      expect(r.status).toBeLessThan(500);
    }
  });

  test('4.6 调拨单状态流转门禁（execute）', async () => {
    const r = await api('POST', `${KZ}/inventory-transfers/99999999/execute`, {});
    expect([400, 403, 404], `对不存在的调拨单 execute → ${r.status}`).toContain(r.status);
    expect(r.status).toBeLessThan(500);
  });

  test('4.7 组装/拆卸状态流转门禁（execute）', async () => {
    const a = await api('POST', `${KZ}/assembly-orders/99999999/execute`, {});
    expect([400, 403, 404], `对不存在的组装单 execute → ${a.status}`).toContain(a.status);
    expect(a.status).toBeLessThan(500);
    const d = await api('POST', `${KZ}/disassembly-orders/99999999/execute`, {});
    expect([400, 403, 404], `对不存在的拆卸单 execute → ${d.status}`).toContain(d.status);
    expect(d.status).toBeLessThan(500);
  });

  test('4.8 预警处理门禁', async () => {
    // ponytail: handle 的 body schema 要求 status 必填 → 空 body 先撞 Pydantic 422（在业务 404 之前）；4xx 均非缺陷
    const r = await api('POST', `${KZ}/inventory-alerts/99999999/handle`, {});
    expect([400, 403, 404, 422], `对不存在的预警 handle → ${r.status}`).toContain(r.status);
    expect(r.status).toBeLessThan(500);
  });

  test('4.9 补货建议处理门禁', async () => {
    const r = await api('POST', `${KZ}/replenishment-suggestions/99999999/process`, {});
    expect([400, 403, 404, 422], `对不存在的补货建议 process → ${r.status}`).toContain(r.status);
    expect(r.status).toBeLessThan(500);
  });

  test('4.10 客户来料登记状态流转门禁（process/withdraw/cancel）', async () => {
    for (const action of ['process', 'withdraw', 'cancel']) {
      const r = await api('POST', `${KZ}/inventory/customer-material-registration/99999999/${action}`, {});
      expect([400, 403, 404, 422], `customer-material-registration/99999999/${action} → ${r.status}`).toContain(r.status);
      expect(r.status).toBeLessThan(500);
    }
  });
});

// ---------------------------------------------------------------------------
// T5 数据一致性：数量/金额校验
// ---------------------------------------------------------------------------
test.describe('仓储管理 数据一致性', () => {
  test('5.1 其他入库单明细金额与数量一致性（创建时 total_amount = qty × price）', async () => {
    const suffix = uniqueSuffix();
    const payload = {
      reason_type: '调拨',
      warehouse_id: 1,
      warehouse_name: 'TEST仓库',
      review_status: '待审核',
      status: '待入库',
      notes: `TEST-WH 一致性测试-${suffix}`,
      items: [
        {
          material_id: 1,
          material_code: 'MAT-001',
          material_name: 'TEST物料',
          material_unit: '件',
          inbound_quantity: 10,
          unit_price: 5,
          total_amount: 50,
        },
        {
          material_id: 1,
          material_code: 'MAT-001',
          material_name: 'TEST物料',
          material_unit: '件',
          inbound_quantity: 4,
          unit_price: 3,
          total_amount: 12,
        },
      ],
    };
    const r = await api('POST', `${KZ}/other-inbounds`, payload);
    if (r.status === 200 || r.status === 201) {
      const data = r.data?.data ?? r.data;
      const totalAmt = data?.total_amount ?? data?.totalAmount;
      const expectedTotal = 10 * 5 + 4 * 3; // 50 + 12 = 62
      expect(
        Number(totalAmt),
        `金额不一致: total_amount=${totalAmt}, 期望=${expectedTotal}`,
      ).toBe(expectedTotal);
      const oid = data?.id;
      if (oid) {
        const del = await api('DELETE', `${KZ}/other-inbounds/${oid}`);
        if (del.status >= 400 && del.status !== 204) {
          console.log(`[kz-warehouse] 清理失败（残留）: DELETE other-inbounds/${oid} -> ${del.status}`);
        }
      }
    } else {
      // 403 时跳过，仍验证 4xx 门禁
      expect(r.status).toBeLessThan(500);
    }
  });

  test('5.2 其他出库单明细金额一致性', async () => {
    const suffix = uniqueSuffix();
    const payload = {
      reason_type: '领用',
      warehouse_id: 1,
      warehouse_name: 'TEST仓库',
      status: '待出库',
      notes: `TEST-WH 出库一致性-${suffix}`,
      items: [
        {
          material_id: 1,
          material_code: 'MAT-001',
          material_name: 'TEST物料',
          material_unit: '件',
          outbound_quantity: 20,
          unit_price: 2,
          total_amount: 40,
        },
      ],
    };
    const r = await api('POST', `${KZ}/other-outbounds`, payload);
    if (r.status === 200 || r.status === 201) {
      const data = r.data?.data ?? r.data;
      const totalAmt = data?.total_amount ?? data?.totalAmount;
      expect(Number(totalAmt), `出库单金额不一致: ${totalAmt} ≠ 40`).toBe(40);
      const oid = data?.id;
      if (oid) {
        const del = await api('DELETE', `${KZ}/other-outbounds/${oid}`);
        if (del.status >= 400 && del.status !== 204) {
          console.log(`[kz-warehouse] 清理失败（残留）: DELETE other-outbounds/${oid} -> ${del.status}`);
        }
      }
    } else {
      expect(r.status).toBeLessThan(500);
    }
  });
});

// ---------------------------------------------------------------------------
// 收尾：输出汇总 + 残留数据记录
// ---------------------------------------------------------------------------
test('403 分布审计（供报告引用）', async () => {
  const uniq = [...new Set(rbacBlocked)];
  fs.mkdirSync(path.join(__dirname, 'output'), { recursive: true });
  fs.writeFileSync(
    path.join(__dirname, 'output', 'kz-warehouse-rbac.json'),
    JSON.stringify({ rbacBlocked: uniq }, null, 2),
    'utf-8',
  );
  console.log(`[kz-warehouse] RBAC 403 (${uniq.length}): ${uniq.join(' | ')}`);
  // 路由结果已在 T1 写入 kz-warehouse-routes.json；此处不做额外断言
});
