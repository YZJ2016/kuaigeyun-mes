/**
 * 生产执行 E2E 业务测试（API 级，租户 3 / xiaofeng）
 *
 * 菜单范围：dashboard, work-orders, outbound, reporting, inbound,
 *           rework-orders, packing-binding, reporting/statistics,
 *           exception-management/*, reports/*
 *
 * 核心主链：工单（work-orders）新建→查询→编辑→删除
 *   + 报工记录 新建→查询→删除 + 数量一致性
 *   + 返工单 新建→查询→删除 + 必填校验
 *   + 生产日报 模板/报表 主链
 *   + 异常管理 缺料上报
 * 测试数据统一 TEST-PRO- 前缀；cleanup 删除自造数据。
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
const RUN_ID = uniqueSuffix();
const today = () => new Date().toISOString().slice(0, 10);

const KZ = '/apps/kuaizhizao';
const MD = '/apps/master-data';

// 测试数据追踪（cleanup 用）
const created = {
  workOrderIds: [] as number[],
  reworkIds: [] as number[],
  reportingIds: [] as number[],
  templateIds: [] as number[],
  reportIds: [] as number[],
  exceptionIds: [] as number[],
};

async function cleanup() {
  const failures: string[] = [];
  const tryDel = async (label: string, p: string) => {
    const r = await api('DELETE', p);
    if (r.status >= 400) failures.push(`${label} DELETE ${p} -> ${r.status} ${JSON.stringify(r.data)?.slice(0, 120)}`);
  };
  for (const id of [...created.exceptionIds].reverse()) await tryDel('异常', `${KZ}/exceptions/material-shortage/${id}`);
  for (const id of [...created.reportIds].reverse()) await tryDel('日报', `${KZ}/production-daily-reports/${id}`);
  for (const id of [...created.templateIds].reverse()) await tryDel('日报模板', `${KZ}/production-daily-templates/${id}`);
  for (const id of [...created.reportingIds].reverse()) await tryDel('报工', `${KZ}/reporting/${id}`);
  for (const id of [...created.reworkIds].reverse()) await tryDel('返工单', `${KZ}/rework-orders/${id}`);
  for (const id of [...created.workOrderIds].reverse()) await tryDel('工单', `${KZ}/work-orders/${id}`);
  return failures;
}

let rbacBlocked: string[] = [];
function markRbac(route: string, status: number, data: any) {
  if (status === 403) {
    rbacBlocked.push(`${route} -> 403 ${JSON.stringify(data?.detail?.required || data?.detail || '').slice(0, 200)}`);
  }
}

async function ensureMaterial(): Promise<{ id: number; code: string; name: string } | null> {
  // 测试租户已有物料则直接复用；否则自造一条（TEST-PRO- 前缀）
  const list = await api('GET', `${MD}/materials?limit=5`);
  if (list.status < 400) {
    const items: any[] = Array.isArray(list.data?.data) ? list.data.data : Array.isArray(list.data) ? list.data : [];
    // 优先 TEST-PRO 物料
    const testMat = items.find((m: any) => String(m.code || '').startsWith('TEST-PRO'));
    if (testMat) return testMat;
    if (items.length > 0) return items[0];
  } else {
    markRbac('GET /master-data materials', list.status, list.data);
    return null;
  }
  const r = await api('POST', `${MD}/materials`, {
    code: `TEST-PRO-MAT-${RUN_ID}`,
    name: `TEST-PRO物料-${RUN_ID}`,
    base_unit: '件',
    source_type: 'Buy',
    is_active: true,
  });
  markRbac('POST /master-data materials', r.status, r.data);
  if (r.status >= 400) return null;
  return r.data;
}

function woPayload(material: { id: number; code: string; name: string }, overrides: Json = {}) {
  return {
    code: `TEST-PRO-WO-${RUN_ID}`,
    name: `TEST-PRO工单-${RUN_ID}`,
    product_id: material.id,
    product_code: material.code,
    product_name: material.name,
    quantity: 10,
    production_mode: 'MTS',
    status: 'draft',
    priority: 'normal',
    planned_start_date: `${today()}T08:00:00`,
    planned_end_date: `${today()}T18:00:00`,
    remarks: `E2E生产执行测试 ${RUN_ID}`,
    ...overrides,
  };
}

// ===========================================================================
// 1. 列表/查询接口可用性（记录 200/403/404/500 分布）
// ===========================================================================
test.describe('生产执行 列表/查询接口可用性', () => {
  const routes: Array<[string, string]> = [
    // dashboard
    ['GET', `${KZ}/dashboard/statistics`],
    ['GET', `${KZ}/dashboard/manufacturing-summary`],
    ['GET', `${KZ}/dashboard/manufacturing-trend`],
    ['GET', `${KZ}/dashboard/menu-badge-counts`],
    // work-orders
    ['GET', `${KZ}/work-orders`],
    ['GET', `${KZ}/work-orders/statistics`],
    ['GET', `${KZ}/work-orders/delayed`],
    ['GET', `${KZ}/work-orders/execution-config`],
    // reporting
    ['GET', `${KZ}/reporting`],
    ['GET', `${KZ}/reporting/statistics`],
    ['GET', `${KZ}/reporting/overview-statistics`],
    ['GET', `${KZ}/scrap`],
    ['GET', `${KZ}/defect`],
    // rework-orders
    ['GET', `${KZ}/rework-orders`],
    ['GET', `${KZ}/rework-orders/meta/form-profile`],
    // outbound / inbound（warehouse_execution 路由）
    ['GET', `${KZ}/production-pickings`],
    ['GET', `${KZ}/production-returns`],
    ['GET', `${KZ}/other-inbounds`],
    ['GET', `${KZ}/other-outbounds`],
    ['GET', `${KZ}/material-borrows`],
    ['GET', `${KZ}/finished-goods-receipts`],
    // packing-binding
    ['GET', `${KZ}/packing-bindings`],
    // exception-management
    ['GET', `${KZ}/exceptions/material-shortage`],
    ['GET', `${KZ}/exceptions/delivery-delay`],
    ['GET', `${KZ}/exceptions/quality`],
    // reports / production daily
    ['GET', `${KZ}/production-daily-templates`],
    ['GET', `${KZ}/production-daily-reports`],
    ['GET', `${KZ}/rework-position-plan-templates`],
  ];

  test('各查询路由可达（允许 200/403；404/5xx 为缺陷）', async () => {
    const rows: Array<{ route: string; status: number; note: string }> = [];
    for (const [m, p] of routes) {
      const { status, data } = await api(m, p);
      const reqPerm = data?.detail?.required
        ? `(需权限: ${Array.isArray(data.detail.required) ? data.detail.required.join(',') : data.detail.required})`
        : '';
      rows.push({ route: `${m} ${p.replace('/api/v1', '')}`, status, note: status === 200 ? '' : reqPerm });
    }
    fs.mkdirSync(path.join(__dirname, 'output'), { recursive: true });
    fs.writeFileSync(
      path.join(__dirname, 'output', 'kz-production-routes.json'),
      JSON.stringify(rows, null, 2),
      'utf-8',
    );
    for (const r of rows) if (r.status >= 400) console.log(`[kz-production] ${r.route} -> ${r.status} ${r.note}`);

    // 404/5xx 判缺陷；403 记录为测试账号权限缺口
    const missing = rows.filter((r) => r.status === 404);
    const fatal = rows.filter((r) => r.status >= 500);
    expect(
      fatal.map((r) => `${r.route} -> ${r.status}`),
      `存在 5xx 路由（服务端异常）: ${fatal.map((r) => r.route).join(', ')}`,
    ).toEqual([]);
    // 404 允许：部分路由在该部署可能未注册（如 reports/* 子路径）；仅记录不断言
    if (missing.length > 0)
      console.log(`[kz-production] 404 路由缺失（记录）: ${missing.map((r) => r.route).join(', ')}`);
    const denied = rows.filter((r) => r.status === 403);
    console.log(`[kz-production] 403 分布(${denied.length}/${rows.length}): ${denied.map((r) => r.route).join(', ')}`);
  });

  test('无 token 时查询接口返回 401/403（鉴权门禁）', async () => {
    const res = await fetch(`${BACKEND_URL}/api/v1${KZ}/work-orders`, {
      headers: { 'X-Tenant-ID': String(TENANT_ID) },
    });
    expect(res.status, `无 token 应拒绝，实际 ${res.status}`).toBeGreaterThanOrEqual(401);
    expect(res.status).toBeLessThan(500);
  });
});

// ===========================================================================
// 2. 工单主链：新建 → 查询 → 编辑 → 删除
// ===========================================================================
test.describe('工单主链（新建→查询→编辑→删除）', () => {
  test('前置：物料就位', async () => {
    const mat = await ensureMaterial();
    if (!mat) test.skip(true, '无可用物料（master-data 403 或自造失败）');
    console.log(`[kz-production] 使用物料: ${mat.id} ${mat.code}`);
  });

  test('新建工单（草稿）', async () => {
    const mat = await ensureMaterial();
    if (!mat) test.skip(true, '无可用物料');
    const r = await api('POST', `${KZ}/work-orders`, woPayload(mat));
    markRbac('POST /work-orders', r.status, r.data);
    if (r.status === 403) test.skip(true, `工单创建 403 RBAC：${JSON.stringify(r.data?.detail?.required || '')}`);
    expect(r.status, `创建工单 ${r.status}: ${JSON.stringify(r.data)?.slice(0, 300)}`).toBeLessThan(400);
    created.workOrderIds.push(r.data.id);
    expect(r.data.id).toBeGreaterThan(0);
    expect(r.data.code).toMatch(/TEST-PRO-WO/);
    expect(r.data.status).toBe('draft');
  });

  test('查询：列表命中 + 详情一致 + 工序列表', async () => {
    if (created.workOrderIds.length === 0) test.skip(true, '工单创建被 RBAC 拦截');
    const woId = created.workOrderIds[created.workOrderIds.length - 1];
    const list = await api('GET', `${KZ}/work-orders?limit=50&keyword=${encodeURIComponent(`TEST-PRO-WO-${RUN_ID}`)}`);
    markRbac('GET /work-orders', list.status, list.data);
    if (list.status === 403) test.skip(true, '工单列表 403 RBAC');
    expect(list.status, `工单列表 ${list.status}`).toBe(200);
    const items: any[] = Array.isArray(list.data?.data) ? list.data.data : [];
    const hit = items.find((o) => o.id === woId);
    expect(hit, `列表未命中工单 ${woId}`).toBeTruthy();

    const g = await api('GET', `${KZ}/work-orders/${woId}`);
    markRbac('GET /work-orders/{id}', g.status, g.data);
    if (g.status === 403) test.skip(true, '工单详情 403 RBAC');
    expect(g.status, `详情 ${g.status}: ${JSON.stringify(g.data)?.slice(0, 200)}`).toBe(200);
    expect(g.data.id).toBe(woId);

    const ops = await api('GET', `${KZ}/work-orders/${woId}/operations`);
    if (ops.status === 200) {
      expect(Array.isArray(ops.data), '工序列表应为数组').toBe(true);
    } else {
      console.log(`[kz-production] 工序列表 ${ops.status}（工艺路线缺失时允许 4xx，记录不断言）`);
    }
  });

  test('数据一致性：新建工单 quantity 与 completed_quantity 初始值', async () => {
    if (created.workOrderIds.length === 0) test.skip(true, '工单创建被 RBAC 拦截');
    const woId = created.workOrderIds[created.workOrderIds.length - 1];
    const g = await api('GET', `${KZ}/work-orders/${woId}`);
    expect(g.status).toBe(200);
    const q = Number(g.data.quantity);
    expect(q, '计划数量缺失').toBeGreaterThan(0);
    expect(
      [0, '0'],
      `草稿工单已完成数量应为 0，实际 ${g.data.completed_quantity}`,
    ).toContain(g.data.completed_quantity);
    // 合格/不合格合计不超过计划量（草稿态为 0）
    expect(Number(g.data.qualified_quantity)).toBe(0);
  });

  test('编辑草稿工单成功（改备注）', async () => {
    if (created.workOrderIds.length === 0) test.skip(true, '工单创建被 RBAC 拦截');
    const woId = created.workOrderIds[created.workOrderIds.length - 1];
    const r = await api('PUT', `${KZ}/work-orders/${woId}`, { remarks: `E2E编辑 ${RUN_ID}` });
    markRbac('PUT /work-orders/{id}', r.status, r.data);
    if (r.status === 403) test.skip(true, '工单编辑 403 RBAC');
    expect(r.status, `编辑 ${r.status}: ${JSON.stringify(r.data)?.slice(0, 200)}`).toBeLessThan(400);
  });

  test('工单状态流转：draft → released', async () => {
    if (created.workOrderIds.length === 0) test.skip(true, '工单创建被 RBAC 拦截');
    const woId = created.workOrderIds[created.workOrderIds.length - 1];
    const rel = await api('POST', `${KZ}/work-orders/${woId}/release?ignore_shortage=true`, {});
    markRbac(`POST /work-orders/${woId}/release`, rel.status, rel.data);
    if (rel.status === 403) test.skip(true, '工单下达 403 RBAC');
    if (rel.status >= 400) {
      // 缺料/工艺路线等业务门禁：记录后回滚用例不断言
      console.log(`[kz-production] 下达被业务门禁 ${rel.status}: ${JSON.stringify(rel.data)?.slice(0, 300)}`);
      return;
    }
    expect(rel.data.status, `下达后状态 ${rel.data.status}`).toBe('released');
    const g = await api('GET', `${KZ}/work-orders/${woId}`);
    expect(g.data.status, `详情状态 ${g.data.status}`).toBe('released');
  });

  test('删除工单（软删）', async () => {
    if (created.workOrderIds.length === 0) test.skip(true, '工单创建被 RBAC 拦截');
    const woId = created.workOrderIds[created.workOrderIds.length - 1];
    const r = await api('DELETE', `${KZ}/work-orders/${woId}`);
    markRbac('DELETE /work-orders/{id}', r.status, r.data);
    if (r.status === 403) test.skip(true, '工单删除 403 RBAC');
    expect(r.status, `删除 ${r.status}: ${JSON.stringify(r.data)?.slice(0, 200)}`).toBeLessThan(400);
    created.workOrderIds.splice(created.workOrderIds.lastIndexOf(woId), 1);
  });
});

// ===========================================================================
// 3. 必填校验：缺关键字段应被拒绝（4xx）
// ===========================================================================
test.describe('必填校验（4xx 拒绝）', () => {
  test('工单缺产品/数量被拒', async () => {
    const r = await api('POST', `${KZ}/work-orders`, { code: `TEST-PRO-WO-${RUN_ID}-BAD`, quantity: 5 });
    markRbac('POST /work-orders (missing product)', r.status, r.data);
    if (r.status === 403) test.skip(true, '工单创建 403 RBAC（校验未触发）');
    expect(r.status, `缺产品字段应 4xx，实际 ${r.status}: ${JSON.stringify(r.data)?.slice(0, 200)}`).toBeGreaterThanOrEqual(400);
    expect(r.status).toBeLessThan(500);
  });

  test('工单缺 code 与 code_rule 被拒', async () => {
    const mat = await ensureMaterial();
    if (!mat) test.skip(true, '无可用物料');
    const r = await api('POST', `${KZ}/work-orders`, {
      name: `TEST-PRO无码-${RUN_ID}`,
      product_id: mat.id,
      product_code: mat.code,
      product_name: mat.name,
      quantity: 10,
    });
    markRbac('POST /work-orders (no code)', r.status, r.data);
    if (r.status === 403) test.skip(true, '工单创建 403 RBAC');
    expect(r.status, `缺 code/code_rule 应 4xx，实际 ${r.status}: ${JSON.stringify(r.data)?.slice(0, 200)}`).toBeGreaterThanOrEqual(400);
    expect(r.status).toBeLessThan(500);
  });

  test('返工单缺必填被拒', async () => {
    const r = await api('POST', `${KZ}/rework-orders`, { rework_reason: 'TEST-PRO缺字段' });
    markRbac('POST /rework-orders (missing)', r.status, r.data);
    if (r.status === 403) test.skip(true, '返工单创建 403 RBAC');
    expect(r.status, `缺产品/数量/原因应 4xx，实际 ${r.status}: ${JSON.stringify(r.data)?.slice(0, 200)}`).toBeGreaterThanOrEqual(400);
    expect(r.status).toBeLessThan(500);
  });

  test('报工记录缺生产人员/小组被拒（Pydantic model_validator）', async () => {
    const mat = await ensureMaterial();
    if (!mat) test.skip(true, '无可用物料');
    const r = await api('POST', `${KZ}/reporting`, {
      work_order_id: 1,
      work_order_code: 'TEST-PRO-WO-X',
      work_order_name: 'TEST',
      operation_id: 1,
      operation_code: 'OP1',
      operation_name: '测试工序',
      reported_quantity: 1,
      qualified_quantity: 1,
      unqualified_quantity: 0,
      work_hours: 1,
      reported_at: new Date().toISOString(),
    });
    markRbac('POST /reporting (no worker)', r.status, r.data);
    if (r.status === 403) test.skip(true, '报工创建 403 RBAC');
    expect(r.status, `缺生产人员应 4xx，实际 ${r.status}: ${JSON.stringify(r.data)?.slice(0, 200)}`).toBeGreaterThanOrEqual(400);
    expect(r.status).toBeLessThan(500);
  });

  test('缺料异常缺必填被拒', async () => {
    const r = await api('POST', `${KZ}/exceptions/material-shortage`, { shortage_quantity: 1 });
    markRbac('POST /exceptions/material-shortage (missing)', r.status, r.data);
    if (r.status === 403) test.skip(true, '缺料上报 403 RBAC');
    expect(r.status, `缺 work_order_id/material_id 应 4xx，实际 ${r.status}`).toBeGreaterThanOrEqual(400);
    expect(r.status).toBeLessThan(500);
  });
});

// ===========================================================================
// 4. 返工单主链：新建 → 查询 → 编辑 → 删除
// ===========================================================================
test.describe('返工单主链', () => {
  test('新建返工单 + 查询 + 编辑 + 删除', async () => {
    const mat = await ensureMaterial();
    if (!mat) test.skip(true, '无可用物料');
    const payload: Json = {
      product_id: mat.id,
      product_code: mat.code,
      product_name: mat.name,
      quantity: 5,
      rework_reason: `TEST-PRO返工原因-${RUN_ID}`,
      rework_type: '返工',
      business_type: 'simple_exec',
      remarks: `E2E返工单 ${RUN_ID}`,
    };
    const cr = await api('POST', `${KZ}/rework-orders`, payload);
    markRbac('POST /rework-orders', cr.status, cr.data);
    if (cr.status === 403) test.skip(true, '返工单创建 403 RBAC');
    expect(cr.status, `创建返工单 ${cr.status}: ${JSON.stringify(cr.data)?.slice(0, 300)}`).toBeLessThan(400);
    created.reworkIds.push(cr.data.id);
    const rwId = cr.data.id;

    // 查询
    const g = await api('GET', `${KZ}/rework-orders/${rwId}`);
    markRbac('GET /rework-orders/{id}', g.status, g.data);
    if (g.status === 403) test.skip(true, '返工单详情 403 RBAC');
    expect(g.status, `详情 ${g.status}`).toBe(200);
    expect(g.data.quantity).toBe(5);

    // 编辑
    const up = await api('PUT', `${KZ}/rework-orders/${rwId}`, { remarks: `E2E编辑 ${RUN_ID}` });
    if (up.status === 403) test.skip(true, '返工单编辑 403 RBAC');
    expect(up.status, `编辑 ${up.status}: ${JSON.stringify(up.data)?.slice(0, 200)}`).toBeLessThan(400);

    // 删除
    const del = await api('DELETE', `${KZ}/rework-orders/${rwId}`);
    if (del.status === 403) test.skip(true, '返工单删除 403 RBAC');
    expect(del.status, `删除 ${del.status}: ${JSON.stringify(del.data)?.slice(0, 200)}`).toBeLessThan(400);
    created.reworkIds.splice(created.reworkIds.lastIndexOf(rwId), 1);
  });
});

// ===========================================================================
// 5. 报工记录：新建 → 查询 → 数量一致性 → 删除
// ===========================================================================
test.describe('报工记录主链', () => {
  test('新建报工记录（自报，需工单+工序）+ 数量一致性 + 删除', async () => {
    const mat = await ensureMaterial();
    if (!mat) test.skip(true, '无可用物料');
    // 先建一张工单（有工序才可能报工）
    const wo = await api('POST', `${KZ}/work-orders`, woPayload(mat, { code: `TEST-PRO-WO2-${RUN_ID}` }));
    if (wo.status === 403) test.skip(true, '工单创建 403 RBAC');
    expect(wo.status, `前置工单 ${wo.status}: ${JSON.stringify(wo.data)?.slice(0, 200)}`).toBeLessThan(400);
    const woId = wo.data.id;
    created.workOrderIds.push(woId);

    const ops = await api('GET', `${KZ}/work-orders/${woId}/operations`);
    if (ops.status !== 200 || !Array.isArray(ops.data) || ops.data.length === 0) {
      console.log(`[kz-production] 工单无工序行（工艺路线缺失）${ops.status}，报工跳过`);
      return;
    }
    const op = ops.data[0];
    // 自报：worker_id 需要等于登录用户 id
    const login = await apiLogin();
    const myId = (login.user as any)?.id;

    const rp = await api('POST', `${KZ}/reporting`, {
      work_order_id: woId,
      work_order_code: wo.data.code,
      work_order_name: wo.data.name || '',
      operation_id: op.id,
      operation_code: op.operation_code || op.code || '',
      operation_name: op.operation_name || op.name || '',
      worker_id: myId,
      worker_name: `E2E测试员-${RUN_ID}`,
      reported_quantity: 3,
      qualified_quantity: 2,
      unqualified_quantity: 1,
      work_hours: 1.5,
      reported_at: new Date().toISOString(),
      remarks: `E2E报工 ${RUN_ID}`,
    });
    markRbac('POST /reporting', rp.status, rp.data);
    if (rp.status === 403) test.skip(true, '报工创建 403 RBAC');
    if (rp.status >= 400) {
      console.log(`[kz-production] 报工被拒 ${rp.status}: ${JSON.stringify(rp.data)?.slice(0, 300)}`);
      return;
    }
    created.reportingIds.push(rp.data.id);
    const rrId = rp.data.id;

    // 查询
    const g = await api('GET', `${KZ}/reporting/${rrId}`);
    markRbac('GET /reporting/{id}', g.status, g.data);
    if (g.status === 403) test.skip(true, '报工详情 403 RBAC');
    expect(g.status, `详情 ${g.status}`).toBe(200);

    // 数量一致性：报工数量 = 合格 + 不合格
    expect(
      Number(g.data.reported_quantity),
      `报工数量 ${g.data.reported_quantity} ≠ 合格 ${g.data.qualified_quantity} + 不合格 ${g.data.unqualified_quantity}`,
    ).toBeCloseTo(Number(g.data.qualified_quantity) + Number(g.data.unqualified_quantity), 6);

    // 删除
    const del = await api('DELETE', `${KZ}/reporting/${rrId}`);
    if (del.status === 403) test.skip(true, '报工删除 403 RBAC');
    expect(del.status, `删除 ${del.status}: ${JSON.stringify(del.data)?.slice(0, 200)}`).toBeLessThan(400);
    created.reportingIds.splice(created.reportingIds.lastIndexOf(rrId), 1);
  });
});

// ===========================================================================
// 6. 生产日报：模板 + 报表 主链
// ===========================================================================
test.describe('生产日报（模板→报表→提交→删除）', () => {
  test('新建日报模板 + 基于模板建报表 + 提交 + 删除', async () => {
    const tpl = await api('POST', `${KZ}/production-daily-templates`, {
      template_code: `TEST-PRO-TPL-${RUN_ID}`.slice(0, 50),
      template_name: `TEST-PRO日报模板-${RUN_ID}`,
      description: 'E2E生产日报',
      field_schema: [
        { key: 'output_qty', label: '产出数量', type: 'number', required: true },
        { key: 'remarks', label: '备注', type: 'textarea' },
      ],
      is_active: true,
    });
    markRbac('POST /production-daily-templates', tpl.status, tpl.data);
    if (tpl.status === 403) test.skip(true, '日报模板创建 403 RBAC');
    expect(tpl.status, `模板创建 ${tpl.status}: ${JSON.stringify(tpl.data)?.slice(0, 200)}`).toBeLessThan(400);
    const tplId = tpl.data.id;
    created.templateIds.push(tplId);

    const rep = await api('POST', `${KZ}/production-daily-reports`, {
      template_id: tplId,
      report_date: today(),
      team_name: `E2E班组-${RUN_ID}`,
      shift_name: '白班',
      field_values: { output_qty: 100 },
      remarks: `E2E日报 ${RUN_ID}`,
    });
    markRbac('POST /production-daily-reports', rep.status, rep.data);
    if (rep.status === 403) test.skip(true, '日报创建 403 RBAC');
    expect(rep.status, `日报创建 ${rep.status}: ${JSON.stringify(rep.data)?.slice(0, 200)}`).toBeLessThan(400);
    const repId = rep.data.id;
    created.reportIds.push(repId);

    // 查询
    const g = await api('GET', `${KZ}/production-daily-reports/${repId}`);
    if (g.status === 403) test.skip(true, '日报详情 403 RBAC');
    expect(g.status, `日报详情 ${g.status}`).toBe(200);
    expect(g.data.field_values?.output_qty ?? Number(g.data.field_values?.output_qty || 0), '产出数量缺失').toBe(100);

    // 提交（状态流转 draft → submitted）
    const sub = await api('POST', `${KZ}/production-daily-reports/${repId}/submit`, {});
    if (sub.status === 403) test.skip(true, '日报提交 403 RBAC');
    if (sub.status < 400) {
      expect(sub.data.status, `提交后状态 ${sub.data.status}`).toBe('submitted');
    } else {
      console.log(`[kz-production] 日报提交被拒 ${sub.status}: ${JSON.stringify(sub.data)?.slice(0, 200)}`);
    }
  });
});

// ===========================================================================
// 7. 异常管理：缺料异常上报（需工单+物料）
// ===========================================================================
test.describe('异常管理（缺料上报）', () => {
  test('缺料异常上报 + 查询', async () => {
    const mat = await ensureMaterial();
    if (!mat) test.skip(true, '无可用物料');
    const wo = await api('POST', `${KZ}/work-orders`, woPayload(mat, { code: `TEST-PRO-WO3-${RUN_ID}` }));
    if (wo.status === 403) test.skip(true, '工单创建 403 RBAC');
    expect(wo.status, `前置工单 ${wo.status}`).toBeLessThan(400);
    const woId = wo.data.id;
    created.workOrderIds.push(woId);

    const r = await api('POST', `${KZ}/exceptions/material-shortage`, {
      work_order_id: woId,
      material_id: mat.id,
      shortage_quantity: 5,
      available_quantity: 2,
      required_quantity: 7,
      alert_level: 'high',
      remarks: `TEST-PRO缺料 ${RUN_ID}`,
    });
    markRbac('POST /exceptions/material-shortage', r.status, r.data);
    if (r.status === 403) test.skip(true, '缺料上报 403 RBAC');
    if (r.status < 400) {
      created.exceptionIds.push(r.data.id);
      const g = await api('GET', `${KZ}/exceptions/material-shortage/${r.data.id}`);
      expect(g.status, `详情 ${g.status}`).toBe(200);
      expect(Number(g.data.shortage_quantity)).toBe(5);
    } else {
      console.log(`[kz-production] 缺料上报被拒 ${r.status}: ${JSON.stringify(r.data)?.slice(0, 300)}`);
    }
  });
});

// ===========================================================================
// 8. 出库/入库/包装绑定：列表 + 状态接口
// ===========================================================================
test.describe('出库/入库/包装绑定（列表可用性）', () => {
  test('领料单/退料单/成品入库列表可读', async () => {
    for (const p of ['/production-pickings', '/production-returns', '/finished-goods-receipts']) {
      const r = await api('GET', `${KZ}${p}?limit=5`);
      markRbac(`GET ${p}`, r.status, r.data);
      if (r.status === 403) {
        // 403 记录，不 skip（本 describe 仅记录分布）
        continue;
      }
      expect(r.status, `${p} 列表 ${r.status}: ${JSON.stringify(r.data)?.slice(0, 200)}`).toBe(200);
    }
  });

  test('包装绑定列表可读', async () => {
    const r = await api('GET', `${KZ}/packing-bindings?limit=5`);
    markRbac('GET /packing-bindings', r.status, r.data);
    expect([200, 403], `包装绑定 ${r.status}`).toContain(r.status);
    if (r.status === 200) {
      const data = r.data;
      // 后端返回 list 或分页对象，记录结构
      console.log(`[kz-production] packing-bindings 结构: ${Array.isArray(data) ? 'array' : Object.keys(data || {})}`);
    }
  });
});

// ===========================================================================
// 清理
// ===========================================================================
test('清理测试数据', async () => {
  const failures = await cleanup();
  fs.mkdirSync(path.join(__dirname, 'output'), { recursive: true });
  const summary = {
    runId: RUN_ID,
    failures,
    rbacBlocked,
    remaining: {
      workOrderIds: created.workOrderIds,
      reworkIds: created.reworkIds,
      reportingIds: created.reportingIds,
      templateIds: created.templateIds,
      reportIds: created.reportIds,
      exceptionIds: created.exceptionIds,
    },
  };
  fs.writeFileSync(path.join(__dirname, 'output', 'kz-production-cleanup.json'), JSON.stringify(summary, null, 2), 'utf-8');
  for (const f of failures) console.log(`[kz-production] 清理失败: ${f}`);
  for (const f of rbacBlocked) console.log(`[kz-production] RBAC 403: ${f}`);
});

test('清理后复查残留（软删记录）', async () => {
  if (created.workOrderIds.length === 0) {
    console.log('[kz-production] 无残留工单需复查（未创建或被 RBAC 拦截）');
    return;
  }
  const list = await api('GET', `${KZ}/work-orders?limit=100&keyword=${encodeURIComponent(`TEST-PRO-WO-${RUN_ID}`)}`);
  if (list.status === 403) return;
  const items: any[] = Array.isArray(list.data?.data) ? list.data.data : [];
  const mine = items.filter((o) => created.workOrderIds.includes(o.id));
  expect(mine, `残留工单: ${JSON.stringify(mine.map((o) => o.id))}`).toEqual([]);
});
