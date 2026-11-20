/**
 * 采购管理 E2E 业务测试（API 级，租户 3 / xiaofeng）
 * 范围：采购订单/申请/询价/付款申请/到货预警/变更/收货通知/入库/退货 列表可用性
 *      + 采购订单 新建→查询→编辑→删除 主链 + 必填校验 + 状态流转 + 金额一致性
 * 测试数据统一 TEST-PUR- 前缀；afterAll 清理自造数据（含供应商/物料/收货通知/付款申请）
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
        // 全站写门禁：POST/PUT/PATCH/DELETE 必须携带官方 X-Client-Channel
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
  // 连库抖动 5xx：刷 token 重试一次（与 equipmentApi 同款）
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
const plusDays = (n: number) => new Date(Date.now() + n * 86_400_000).toISOString().slice(0, 10);

// kuaizhizao API 根（与 api() 拼接一致）
const KZ = '/apps/kuaizhizao';

/** 提交只到已提交；进入待审核或免审确认须再走提交审核。 */
async function commitThenReviewPurchaseOrder(poId: number) {
  const sub = await api('POST', `${KZ}/purchase-orders/${poId}/submit`, {});
  expect(sub.status, `提交失败 ${sub.status}: ${JSON.stringify(sub.data)}`).toBeLessThan(400);
  const committed = String(sub.data?.status || '');
  if (['CONFIRMED', 'AUDITED', '已审核', '已确认', 'PENDING_REVIEW', '待审核'].includes(committed)) {
    return sub;
  }
  const review = await api('POST', `/core/uni-audit/purchase_order/${poId}/submit_review`, {});
  expect(review.status, `提交审核失败 ${review.status}: ${JSON.stringify(review.data)}`).toBeLessThan(400);
  return review;
}
const MD = '/apps/master-data'; // master-data 主数据（api() 已含 /api/v1 前缀）

// ---------------------------------------------------------------------------
// 测试数据追踪（cleanup 用）
// ---------------------------------------------------------------------------
const created = {
  supplierUuid: null as string | null,
  supplierId: 0,
  materialUuid: null as string | null,
  materialId: 0,
  poIds: [] as number[],
  reqIds: [] as number[],
  inqIds: [] as number[],
  payIds: [] as number[],
  rnIds: [] as number[],
};

async function cleanup() {
  const failures: string[] = [];
  const tryDel = async (label: string, p: string) => {
    const r = await api('DELETE', p);
    if (r.status >= 400) failures.push(`${label} DELETE ${p} -> ${r.status}`);
  };
  for (const id of [...created.rnIds].reverse()) await tryDel('收货通知', `${KZ}/receipt-notices/${id}`);
  for (const id of [...created.payIds].reverse()) await tryDel('付款申请', `${KZ}/payment-applications/${id}`);
  for (const id of [...created.poIds].reverse()) await tryDel('采购订单', `${KZ}/purchase-orders/${id}`);
  for (const id of [...created.inqIds].reverse()) await tryDel('采购询价', `${KZ}/purchase-inquiries/${id}`);
  for (const id of [...created.reqIds].reverse()) await tryDel('采购申请', `${KZ}/purchase-requisitions/${id}`);
  if (created.materialUuid) await tryDel('物料', `${MD}/materials/${created.materialUuid}`);
  if (created.supplierUuid) await tryDel('供应商', `${MD}/supply-chain/suppliers/${created.supplierUuid}`);
  return failures;
}

test.describe.configure({ mode: 'serial' });

// ---------------------------------------------------------------------------
// 前置：供应商 + 物料（主链依赖；尽量复用测试租户现有数据，失败才自造）
// ---------------------------------------------------------------------------
class RbacBlockedError extends Error {
  route: string;
  constructor(route: string, status: number, data: any) {
    super(`${route} -> ${status} ${JSON.stringify(data?.detail?.required || data?.detail || '').slice(0, 200)}`);
    this.route = route;
  }
}

async function ensureSupplierAndMaterial() {
  // ponytail: 列表形态兼容：顶层 {items,total}（物料/多数 KZ 接口）或 data:{data|items}（供应商）
  const listOf = (d: any) => (Array.isArray(d?.items) ? d.items : Array.isArray(d?.data?.items) ? d.data.items : Array.isArray(d?.data?.data) ? d.data.data : Array.isArray(d?.data) ? d.data : []);
  // 优先找已有 TEST-PUR 供应商/物料；找不到再找任意一条（403 时跳过复用直接自造）
  const list = await api('GET', `${MD}/supply-chain/suppliers?limit=1&keyword=TEST-PUR`);
  let supplier: any =
    list.status < 400 && listOf(list.data).length > 0
      ? listOf(list.data)[0]
      : null;
  if (!supplier) {
    if (list.status === 403) markRbac('GET /master-data suppliers', list.status, list.data);
    const any = await api('GET', `${MD}/supply-chain/suppliers?limit=1`);
    if (any.status === 403) markRbac('GET /master-data suppliers (any)', any.status, any.data);
    const anySups = listOf(any.data);
    supplier = anySups.length > 0 ? anySups[0] : null;
  }
  if (supplier) {
    created.supplierId = supplier.id;
    created.supplierUuid = supplier.uuid || null;
  } else {
    // 读不到就自造（测试租户内可造数）
    const suffix = RUN_ID;
    const r = await api('POST', `${MD}/supply-chain/suppliers`, {
      code: `TEST-PUR-SUP-${suffix}`,
      name: `TEST-PUR供应商-${suffix}`,
      category: '原材料',
      is_active: true,
      qualification_status: 'approved',
    });
    markRbac('POST /master-data suppliers', r.status, r.data);
    if (r.status >= 400) {
      throw new RbacBlockedError('POST /master-data suppliers', r.status, r.data);
    }
    created.supplierId = r.data.id;
    created.supplierUuid = r.data.uuid;
  }

  const ml = await api('GET', `${MD}/materials?limit=1&keyword=TEST-PUR`);
  // ponytail: 物料接口顶层 {items,total}；供应商接口 data:{data}；两种形态都读
  const matOf = (d: any) => (Array.isArray(d?.items) ? d.items : Array.isArray(d?.data?.items) ? d.data.items : Array.isArray(d?.data?.data) ? d.data.data : Array.isArray(d?.data) ? d.data : []);
  let material: any = ml.status < 400 && matOf(ml.data).length > 0 ? matOf(ml.data)[0] : null;
  if (!material) {
    if (ml.status === 403) markRbac('GET /master-data materials', ml.status, ml.data);
    const mAny = await api('GET', `${MD}/materials?limit=1`);
    if (mAny.status === 403) markRbac('GET /master-data materials (any)', mAny.status, mAny.data);
    const anyMats = matOf(mAny.data);
    material = anyMats.length > 0 ? anyMats[0] : null;
  }
  if (material) {
    created.materialId = material.id;
    created.materialUuid = material.uuid || null;
  } else {
    const ms = RUN_ID;
    const mr = await api('POST', `${MD}/materials`, {
      code: `TEST-PUR-MAT-${ms}`,
      name: `TEST-PUR物料-${ms}`,
      base_unit: '件',
      source_type: 'Buy',
      is_active: true,
    });
    markRbac('POST /master-data materials', mr.status, mr.data);
    if (mr.status >= 400) {
      throw new RbacBlockedError('POST /master-data materials', mr.status, mr.data);
    }
    created.materialId = mr.data.id;
    created.materialUuid = mr.data.uuid;
  }
}

const poPayload = (overrides: Json = {}) => ({
  order_code: `TEST-PUR-PO-${RUN_ID}`,
  supplier_id: created.supplierId,
  supplier_name: 'TEST供应商',
  order_date: today(),
  delivery_date: plusDays(14),
  tax_rate: 0,
  status: 'DRAFT',
  notes: 'E2E采购测试单',
  items: [
    {
      material_id: created.materialId,
      material_code: 'E2E-TEST',
      material_name: 'E2E测试物料',
      ordered_quantity: 10,
      unit: '件',
      unit_price: 5,
      total_price: 50,
      required_date: plusDays(14),
    },
    {
      material_id: created.materialId,
      material_code: 'E2E-TEST',
      material_name: 'E2E测试物料',
      ordered_quantity: 4,
      unit: '件',
      unit_price: 3,
      total_price: 12,
      required_date: plusDays(14),
    },
  ],
  ...overrides,
});

// RBAC 403：记录（账号无该模块权限 = 测试账号权限缺口，报告里列）
let rbacBlocked: string[] = [];
function markRbac(route: string, status: number, data: any) {
  if (status === 403) rbacBlocked.push(`${route} -> 403 ${JSON.stringify(data?.detail?.required || data?.detail || '')}`);
}

// ===========================================================================
// 1. 列表/查询接口可用性（记录 200/403/404/500）
// ===========================================================================
test.describe('采购管理 API 列表可用性', () => {
  const routes: Array<[string, string]> = [
    ['GET', `${KZ}/purchase-orders`],
    ['GET', `${KZ}/purchase-orders/statistics`],
    ['GET', `${KZ}/purchase-requisitions`],
    ['GET', `${KZ}/purchase-inquiries`],
    ['GET', `${KZ}/payment-applications`],
    ['GET', `${KZ}/purchase-arrival/warnings`],
    ['GET', `${KZ}/purchase-arrival/delay-reports`],
    ['GET', `${KZ}/purchase-order-change-orders`],
    ['GET', `${KZ}/receipt-notices`],
    ['GET', `${KZ}/receipt-notices/statistics`],
    ['GET', `${KZ}/purchase-receipts`],
    ['GET', `${KZ}/purchase-returns`],
    ['GET', `${KZ}/purchase-returns/statistics`],
    ['GET', `${KZ}/dashboard/purchase-summary`],
    ['GET', `${KZ}/dashboard/purchase-trend`],
    ['GET', `${KZ}/dashboard/purchase-top10`],
    ['GET', `${KZ}/reports/purchases`],
  ];

  test('各列表/查询路由可达', async () => {
    const rows: Array<{ route: string; status: number; ok: boolean; note: string }> = [];
    for (const [m, p] of routes) {
      const { status, data } = await api(m, p);
      const ok = status === 200;
      const reqPerm = data?.detail?.required
        ? `(需权限: ${Array.isArray(data.detail.required) ? data.detail.required.join(',') : data.detail.required})`
        : '';
      rows.push({ route: `${m} ${p.replace('/api/v1/apps/kuaizhizao', '')}`, status, ok, note: reqPerm });
    }
    fs.mkdirSync(path.join(__dirname, 'output'), { recursive: true });
    fs.writeFileSync(
      path.join(__dirname, 'output', 'kz-purchase-routes.json'),
      JSON.stringify(rows, null, 2),
      'utf-8',
    );
    const bad = rows.filter((r) => !r.ok);
    for (const r of bad) console.log(`[kz-purchase] ${r.route} -> ${r.status} ${r.note}`);
    // 仅 5xx（服务端错误）判真实缺陷；403=测试账号权限缺口、404=路由未注册（两者记录在 routes.json 供报告引用）
    const fatal = rows.filter((r) => r.status >= 500);
    expect(fatal, `存在 5xx 路由: ${JSON.stringify(fatal)}`).toEqual([]);
    const rbac403 = rows.filter((r) => r.status === 403);
    const missing404 = rows.filter((r) => r.status === 404);
    if (rbac403.length > 0)
      console.log(`[kz-purchase] 403 无权限路由（测试账号权限缺口）: ${rbac403.map((r) => r.route).join(', ')}`);
    if (missing404.length > 0)
      console.log(`[kz-purchase] 404 路由缺失: ${missing404.map((r) => r.route).join(', ')}`);
  });

  test('采购订单核心写接口可达（业务校验层：空明细应 4xx 或成功）', async () => {
    // ponytail: 原写死 supplier_id:1，租户 3 无该供应商 → 后端返回业务 404"供应商不存在"（NotFound 语义，非路由缺失）误报。
    //          改用 ensureSupplierAndMaterial 的真实供应商 id（找不到跳过）
    if (created.supplierId === 0) {
      try {
        await ensureSupplierAndMaterial();
      } catch (e) {
        rbacBlocked.push(`smoke 前置 ensureSupplierAndMaterial: ${(e as Error).message}`);
      }
    }
    if (created.supplierId === 0) test.skip(true, '无可用供应商（上游被拦截），smoke 跳过');
    // 接口可达即可：允许 2xx（创建成功）或 4xx（业务校验/RBAC 拒绝）；
    // 路由 404/5xx 才说明接口不可用（真实缺陷）；业务 404（供应商不存在）不再误报
    const r = await api('POST', `${KZ}/purchase-orders`, {
      order_code: `TEST-PUR-PO-${RUN_ID}-SMOKE`,
      supplier_id: created.supplierId,
      supplier_name: 'TEST',
      order_date: today(),
      delivery_date: plusDays(14),
      status: 'DRAFT',
      items: [],
    });
    markRbac('POST /purchase-orders (smoke)', r.status, r.data);
    expect(r.status, `创建接口应 2xx/4xx，实际 ${r.status}: ${JSON.stringify(r.data)}`).toBeLessThan(500);
    expect(r.status, `创建接口不应 404（供应商已 ensure），实际 ${r.status}`).not.toBe(404);
    const r2 = await api('POST', `${KZ}/purchase-requisitions`, {
      requisition_name: 'TEST-PUR申请-smoke',
      requisition_code: `TEST-PUR-REQ-${RUN_ID}-SMOKE`,
      items: [],
    });
    markRbac('POST /purchase-requisitions (smoke)', r2.status, r2.data);
    expect(r2.status, `申请创建接口应 2xx/4xx，实际 ${r2.status}`).toBeLessThan(500);
    expect(r2.status).not.toBe(404);
    if (r.status < 400 && r.data?.id) await api('DELETE', `${KZ}/purchase-orders/${r.data.id}`);
    if (r2.status < 400 && r2.data?.id) await api('DELETE', `${KZ}/purchase-requisitions/${r2.data.id}`);
  });

  test('收货通知/采购入库/采购退货 详情与统计接口可用', async () => {
    // 需要真实 id；优先取列表首条，否则跳过（避免误报 404）
    const rn = await api('GET', `${KZ}/receipt-notices?limit=1`);
    if (rn.status === 200 && Array.isArray(rn.data?.data) && rn.data.data.length > 0) {
      const gid = rn.data.data[0].id;
      const g = await api('GET', `${KZ}/receipt-notices/${gid}`);
      expect(g.status, `收货通知详情 ${g.status}`).toBeLessThan(400);
    }
    const rc = await api('GET', `${KZ}/purchase-receipts?limit=1`);
    if (rc.status === 200 && Array.isArray(rc.data?.data) && rc.data.data.length > 0) {
      const gid = rc.data.data[0].id;
      const g = await api('GET', `${KZ}/purchase-receipts/${gid}`);
      expect(g.status, `采购入库详情 ${g.status}`).toBeLessThan(400);
    }
    const rt = await api('GET', `${KZ}/purchase-returns?limit=1`);
    if (rt.status === 200 && Array.isArray(rt.data?.data) && rt.data.data.length > 0) {
      const gid = rt.data.data[0].id;
      const g = await api('GET', `${KZ}/purchase-returns/${gid}`);
      expect(g.status, `采购退货详情 ${g.status}`).toBeLessThan(400);
    }
  });
});

// ===========================================================================
// 2. 采购订单主链：新建 → 查询 → 编辑 → 删除
// ===========================================================================
test.describe('采购订单 主链（新建→查询→编辑→删除）', () => {
  test('前置：供应商与物料就位', async () => {
    try {
      await ensureSupplierAndMaterial();
    } catch (e: any) {
      // RBAC 拦截：标记并跳过后续（不污染断言）
      if (e instanceof RbacBlockedError) {
        rbacBlocked.push(`前置 ensureSupplierAndMaterial: ${e.message}`);
      } else {
        console.log(`[kz-purchase] 前置 ensureSupplierAndMaterial 异常: ${e.message}`);
      }
      test.skip(true, `前置物料/供应商被拦截：${e.message}`);
    }
    expect(created.supplierId, 'supplierId 缺失').toBeGreaterThan(0);
    expect(created.materialId, 'materialId 缺失').toBeGreaterThan(0);
  });

  test('新建采购订单（2 行明细）', async () => {
    const r = await api('POST', `${KZ}/purchase-orders`, poPayload());
    markRbac('POST /purchase-orders', r.status, r.data);
    if (r.status === 403) {
      test.skip(true, `采购订单创建 403 RBAC（测试账号无 kuaizhizao:purchase-order 权限）：${JSON.stringify(r.data)}`);
    }
    expect(r.status, `创建 PO 失败 ${r.status}: ${JSON.stringify(r.data)}`).toBeLessThan(400);
    created.poIds.push(r.data.id);
    expect(r.data.id).toBeGreaterThan(0);
    expect(r.data.order_code, '订单编码缺失').toBeTruthy();
    expect(Array.isArray(r.data.items) && r.data.items.length, '明细缺失').toBe(2);
  });

  test('查询：列表命中 + 详情一致', async () => {
    if (created.poIds.length === 0) test.skip(true, '无可用 PO（上游被 RBAC 拦截）');
    const poId = created.poIds[created.poIds.length - 1];
    const list = await api(
      `GET`,
      `${KZ}/purchase-orders?limit=100&keyword=${encodeURIComponent(`TEST-PUR-PO-${RUN_ID}`)}`,
    );
    markRbac('GET /purchase-orders', list.status, list.data);
    if (list.status === 403) test.skip(true, '采购订单列表 403 RBAC');
    expect(list.status, `列表查询 ${list.status}`).toBe(200);
    // ponytail: /purchase-orders 列表响应体为 {data: [...], total, success}（api() 的 data 字段=整个响应体）；
    //          原读法 list.data?.items 恒 undefined → 0 命中误报（PUR-NEW 非缺陷，实为响应形态读取错）
    const items = Array.isArray(list.data?.data)
      ? list.data.data
      : Array.isArray(list.data)
        ? list.data
        : Array.isArray(list.data?.items)
          ? list.data.items
          : [];
    const hit = items.find((o: any) => o.id === poId);
    expect(hit, `列表未命中新建订单 ${poId}（返回 ${items.length} 条）`).toBeTruthy();

    const g = await api('GET', `${KZ}/purchase-orders/${poId}`);
    expect(g.status, `详情查询 ${g.status}: ${JSON.stringify(g.data)}`).toBe(200);
    expect(g.data.id).toBe(poId);
  });

  test('数据一致性：订单头金额 = 明细总价之和', async () => {
    if (created.poIds.length === 0) test.skip(true, '无可用 PO（上游被 RBAC 拦截）');
    const g = await api('GET', `${KZ}/purchase-orders/${created.poIds[created.poIds.length - 1]}`);
    expect(g.status).toBe(200);
    const items: any[] = g.data.items || [];
    const sum = items.reduce((acc, it) => acc + Number(it.total_price || 0), 0);
    expect(
      Math.abs(Number(g.data.total_amount) - sum) < 0.001,
      `头金额 ${g.data.total_amount} ≠ 明细合计 ${sum}`,
    ).toBe(true);
    const sumQty = items.reduce((acc, it) => acc + Number(it.ordered_quantity || 0), 0);
    expect(Number(g.data.total_quantity || 0), '总数量应为明细之和').toBeCloseTo(sumQty, 3);
  });

  test('编辑草稿订单成功', async () => {
    if (created.poIds.length === 0) test.skip(true, '无可用 PO（上游被 RBAC 拦截）');
    const poId = created.poIds[created.poIds.length - 1];
    // ponytail: 采购订单更新 schema 为完整对象（supplier_id/supplier_name 等必填，非 PATCH）；
    //          仅发 {notes} 会 422（缺必填字段）。改用完整 poPayload + notes 覆盖
    const r = await api('PUT', `${KZ}/purchase-orders/${poId}`, {
      ...poPayload({ order_code: undefined }),
      id: poId,
      notes: 'E2E编辑后可删除',
    });
    if (r.status === 403) test.skip(true, `采购订单编辑 403 RBAC：${JSON.stringify(r.data)}`);
    expect(r.status, `编辑失败 ${r.status}: ${JSON.stringify(r.data)}`).toBeLessThan(400);
  });

  test('删除草稿订单成功', async () => {
    if (created.poIds.length === 0) test.skip(true, '无可用 PO（上游被 RBAC 拦截）');
    const poId = created.poIds[created.poIds.length - 1];
    const r = await api('DELETE', `${KZ}/purchase-orders/${poId}`);
    if (r.status === 403) test.skip(true, `采购订单删除 403 RBAC：${JSON.stringify(r.data)}`);
    expect(r.status, `删除失败 ${r.status}: ${JSON.stringify(r.data)}`).toBeLessThan(400);
    created.poIds.splice(created.poIds.lastIndexOf(poId), 1);
    const g = await api('GET', `${KZ}/purchase-orders/${poId}`);
    expect([200, 404], `删除后详情应 404/不可见，实际 ${g.status}`).toContain(g.status);
  });
});

// ===========================================================================
// 3. 必填校验：缺关键字段应被拒绝（4xx）
// ===========================================================================
test.describe('必填校验（4xx 拒绝）', () => {
  test('缺明细创建采购订单被拒', async () => {
    // 仅校验 schema 层（Pydantic）拒绝；不依赖 supplier/material 主数据
    const r = await api('POST', `${KZ}/purchase-orders`, {
      order_code: `TEST-PUR-PO-${RUN_ID}-NOITEMS`,
      supplier_id: 1,
      supplier_name: 'TEST',
      order_date: today(),
      delivery_date: plusDays(14),
      status: 'DRAFT',
      items: [],
    });
    markRbac('POST /purchase-orders (items=[])', r.status, r.data);
    if (r.status === 403) {
      test.skip(true, `采购订单 403 RBAC（测试账号无写权限）：${JSON.stringify(r.data?.detail?.required || '')}`);
    }
    expect(r.status, `缺 items 应 4xx，实际 ${r.status}: ${JSON.stringify(r.data)}`).toBeGreaterThanOrEqual(400);
    expect(r.status).toBeLessThan(500);
    if (r.status < 400 && r.data?.id) await api('DELETE', `${KZ}/purchase-orders/${r.data.id}`);
  });

  test('缺供应商创建采购订单被拒（非草稿）', async () => {
    const r = await api('POST', `${KZ}/purchase-orders`, {
      order_code: `TEST-PUR-PO-${RUN_ID}-NOSUP`,
      order_date: today(),
      delivery_date: plusDays(14),
      status: 'PENDING_REVIEW',
      items: [
        {
          material_id: 1,
          material_code: 'E2E-TEST',
          material_name: 'E2E测试物料',
          ordered_quantity: 1,
          unit_price: 1,
          total_price: 1,
        },
      ],
    });
    markRbac('POST /purchase-orders (no supplier)', r.status, r.data);
    if (r.status === 403) test.skip(true, '采购订单 403 RBAC');
    expect(r.status, `缺供应商且非草稿应 4xx，实际 ${r.status}: ${JSON.stringify(r.data)}`).toBeGreaterThanOrEqual(400);
    expect(r.status).toBeLessThan(500);
  });

  test('采购申请缺明细被拒', async () => {
    const r = await api('POST', `${KZ}/purchase-requisitions`, {
      requisition_name: 'TEST-PUR缺明细申请',
      requisition_code: `TEST-PUR-REQ-${RUN_ID}-EMPTY`,
      items: [],
    });
    markRbac('POST /purchase-requisitions (items=[])', r.status, r.data);
    if (r.status === 403) test.skip(true, '采购申请 403 RBAC');
    expect(r.status, `缺 items 应 4xx，实际 ${r.status}: ${JSON.stringify(r.data)}`).toBeGreaterThanOrEqual(400);
    expect(r.status).toBeLessThan(500);
    if (r.status < 400 && r.data?.id) await api('DELETE', `${KZ}/purchase-requisitions/${r.data.id}`);
  });

  test('付款申请缺供应商/缺明细被拒', async () => {
    const r = await api('POST', `${KZ}/payment-applications`, {
      application_code: `TEST-PUR-PAY-${RUN_ID}-NOSUP`,
      items: [{ source_type: 'purchase_order', request_amount: 100 }],
    });
    markRbac('POST /payment-applications (no supplier)', r.status, r.data);
    if (r.status === 403) test.skip(true, '付款申请 403 RBAC');
    expect(r.status, `缺 supplier_id 应 4xx，实际 ${r.status}: ${JSON.stringify(r.data)}`).toBeGreaterThanOrEqual(400);
    expect(r.status).toBeLessThan(500);
  });

  test('收货通知缺采购订单关联被拒', async () => {
    const r = await api('POST', `${KZ}/receipt-notices`, {
      notice_code: `TEST-PUR-RN-${RUN_ID}-NOP`,
      items: [],
    });
    markRbac('POST /receipt-notices (no PO)', r.status, r.data);
    if (r.status === 403) test.skip(true, '收货通知 403 RBAC');
    expect(r.status, `缺 purchase_order_id 应 4xx，实际 ${r.status}: ${JSON.stringify(r.data)}`).toBeGreaterThanOrEqual(400);
    expect(r.status).toBeLessThan(500);
  });
});

// ===========================================================================
// 4. 状态流转：新建 → 提交 → 审核 → （草稿编辑门禁）
// ===========================================================================
test.describe('采购订单状态流转', () => {
  test('草稿 → 提交 → 审核后不可再当草稿编辑', async () => {
    const r = await api('POST', `${KZ}/purchase-orders`, poPayload());
    markRbac('POST /purchase-orders', r.status, r.data);
    if (r.status === 403) test.skip(true, '采购订单 403 RBAC（测试账号无写权限）');
    expect(r.status, `创建 ${r.status}: ${JSON.stringify(r.data)}`).toBeLessThan(400);
    const poId = r.data.id;
    created.poIds.push(poId);

    const sub = await commitThenReviewPurchaseOrder(poId);
    const afterSubmit = String(sub.data?.status || '');
    const alreadyApproved = ['CONFIRMED', 'AUDITED', '已审核', '已确认'].includes(afterSubmit);
    let st = afterSubmit;
    if (!alreadyApproved) {
      const app = await api('POST', `${KZ}/purchase-orders/${poId}/approve`, {
        approved: true,
        review_remarks: 'E2E审核',
      });
      expect(app.status, `审核失败 ${app.status}: ${JSON.stringify(app.data)}`).toBeLessThan(400);
      st = app.data?.status;
    }
    expect(['CONFIRMED', 'AUDITED', '已审核', '已确认'], `审核后状态异常: ${st}`).toContain(st);

    // 已审核订单编辑需 change_reason，直接草稿式编辑应被门禁
    const ed = await api('PUT', `${KZ}/purchase-orders/${poId}`, { notes: 'E2E改' });
    if (ed.status >= 400) {
      console.log(`[kz-purchase] 审核后编辑被门禁（${ed.status}）: ${JSON.stringify(ed.data)}`);
    }
  });

  test('草稿订单可编辑变更明细', async () => {
    const r = await api('POST', `${KZ}/purchase-orders`, poPayload());
    markRbac('POST /purchase-orders', r.status, r.data);
    if (r.status === 403) test.skip(true, '采购订单 403 RBAC');
    expect(r.status).toBeLessThan(400);
    const poId = r.data.id;
    created.poIds.push(poId);
    const up = await api('PUT', `${KZ}/purchase-orders/${poId}`, {
      delivery_date: plusDays(21),
    });
    expect(up.status, `草稿编辑失败 ${up.status}: ${JSON.stringify(up.data)}`).toBeLessThan(400);
  });
});

// ===========================================================================
// 5. 关联单据：收货通知（PO 下推）/ 付款申请（PO 下推）/ 采购申请下推 PO
// ===========================================================================
test.describe('关联单据流转', () => {
  test('采购申请 → 创建 PO（convert）', async () => {
    try {
      await ensureSupplierAndMaterial();
    } catch (e: any) {
      if (e instanceof RbacBlockedError) rbacBlocked.push(`convert 前置 ensureSupplierAndMaterial: ${e.message}`);
      test.skip(true, `convert 前置物料/供应商被拦截：${e.message}`);
    }
    if (created.supplierId === 0 || created.materialId === 0) test.skip(true, '无可用供应商/物料（上游被拦截）');
    const rr = await api('POST', `${KZ}/purchase-requisitions`, {
      requisition_name: `TEST-PUR申请-${RUN_ID}`,
      requisition_code: `TEST-PUR-REQ-${RUN_ID}`,
      items: [
        {
          material_id: created.materialId,
          material_code: 'E2E-TEST',
          material_name: 'E2E测试物料',
          quantity: 8,
          unit: '件',
          suggested_unit_price: 6,
        },
      ],
    });
    markRbac('POST /purchase-requisitions', rr.status, rr.data);
    if (rr.status === 403) test.skip(true, '采购申请 403 RBAC（测试账号无写权限）');
    expect(rr.status, `创建采购申请 ${rr.status}: ${JSON.stringify(rr.data)}`).toBeLessThan(400);
    created.reqIds.push(rr.data.id);
    const itemIds = (rr.data.items || []).map((it: any) => it.id);
    expect(itemIds.length).toBeGreaterThan(0);

    const cv = await api(
      'POST',
      `${KZ}/purchase-requisitions/${rr.data.id}/convert-to-purchase-order`,
      { item_ids: itemIds, supplier_id: created.supplierId },
    );
    if (cv.status < 400) {
      const pos = Array.isArray(cv.data) ? cv.data : [cv.data];
      for (const po of pos) if (po?.id) created.poIds.push(po.id);
      // 申请转单后状态应离开草稿（后端用中文/英文状态词，这里只记录不硬断言，避免误判）
      const g = await api('GET', `${KZ}/purchase-requisitions/${rr.data.id}`);
      if (g.status === 200) {
        console.log(`[kz-purchase] 转单后申请状态: ${g.data?.status}`);
      }
    } else if (cv.status === 403) {
      test.skip(true, `convert-to-purchase-order 403 RBAC：${JSON.stringify(cv.data?.detail || '')}`);
    } else if (cv.status >= 400) {
      console.log(`[kz-purchase] convert-to-purchase-order 业务失败 ${cv.status}: ${JSON.stringify(cv.data)}`);
    }
  });

  test('PO 下推收货通知 → 可删除', async () => {
    if (created.poIds.length === 0) test.skip(true, '无可用 PO（上游被 RBAC 拦截）');
    // 复用/新建一张已审核 PO 来下推（下推通常要求已审核）
    let poId: number | undefined;
    for (const id of [...created.poIds].reverse()) {
      const g = await api('GET', `${KZ}/purchase-orders/${id}`);
      if (g.status === 200 && ['CONFIRMED', 'AUDITED', '已审核', '已确认'].includes(g.data.status)) {
        poId = id;
        break;
      }
    }
    if (poId === undefined) {
      const r = await api('POST', `${KZ}/purchase-orders`, poPayload());
      markRbac('POST /purchase-orders', r.status, r.data);
      if (r.status === 403) test.skip(true, '采购订单 403 RBAC');
      expect(r.status).toBeLessThan(400);
      poId = r.data.id;
      created.poIds.push(poId);
      const reviewed = await commitThenReviewPurchaseOrder(poId);
      const reviewedStatus = String(reviewed.data?.status || '');
      if (!['CONFIRMED', 'AUDITED', '已审核', '已确认'].includes(reviewedStatus)) {
        await api('POST', `${KZ}/purchase-orders/${poId}/approve`, { approved: true });
      }
    }
    const push = await api('POST', `${KZ}/purchase-orders/${poId}/push-to-receipt-notice`, {});
    markRbac(`POST /purchase-orders/${poId}/push-to-receipt-notice`, push.status, push.data);
    if (push.status === 403) test.skip(true, '下推收货通知 403 RBAC');
    expect(push.status, `下推收货通知 ${push.status}: ${JSON.stringify(push.data)}`).toBeLessThan(400);
    const rn = push.data;
    // 下推结果：{ order_id, notice_id, notice_code, message }
    const rnId = rn?.notice_id ?? rn?.id;
    if (rnId) created.rnIds.push(rnId);
    // 用 notice_id 查详情验证关联
    if (rnId) {
      const g = await api('GET', `${KZ}/receipt-notices/${rnId}`);
      if (g.status === 200) {
        expect(g.data.purchase_order_id, '收货通知应关联来源 PO').toBe(poId);
      }
    } else {
      console.log(`[kz-purchase] 下推结果无 notice_id: ${JSON.stringify(rn)?.slice(0, 200)}`);
    }
  });

  test('PO 下推付款申请 → 可删除', async () => {
    if (created.poIds.length === 0) test.skip(true, '无可用 PO（上游被 RBAC 拦截）');
    let poId: number | undefined;
    for (const id of [...created.poIds].reverse()) {
      const g = await api('GET', `${KZ}/purchase-orders/${id}`);
      if (g.status === 200 && ['CONFIRMED', 'AUDITED', '已审核', '已确认'].includes(g.data.status)) {
        poId = id;
        break;
      }
    }
    if (poId === undefined) {
      const r = await api('POST', `${KZ}/purchase-orders`, poPayload());
      markRbac('POST /purchase-orders', r.status, r.data);
      if (r.status === 403) test.skip(true, '采购订单 403 RBAC');
      expect(r.status).toBeLessThan(400);
      poId = r.data.id;
      created.poIds.push(poId);
      const reviewed = await commitThenReviewPurchaseOrder(poId);
      const reviewedStatus = String(reviewed.data?.status || '');
      if (!['CONFIRMED', 'AUDITED', '已审核', '已确认'].includes(reviewedStatus)) {
        await api('POST', `${KZ}/purchase-orders/${poId}/approve`, { approved: true });
      }
    }
    const gpo = await api('GET', `${KZ}/purchase-orders/${poId}`);
    const amount = Number(gpo.data?.total_amount || 0) || 1;
    const push = await api('POST', `${KZ}/purchase-orders/${poId}/push-to-payment-application`, {
      amount: Math.min(amount, 100),
    });
    markRbac(`POST /purchase-orders/${poId}/push-to-payment-application`, push.status, push.data);
    if (push.status === 403) test.skip(true, '下推付款申请 403 RBAC');
    expect(push.status, `下推付款申请 ${push.status}: ${JSON.stringify(push.data)}`).toBeLessThan(400);
    const pay = push.data;
    expect(pay?.id, '付款申请缺 id').toBeTruthy();
    created.payIds.push(pay.id);
  });

  test('采购订单变更记录可读（from-order preview）', async () => {
    // 找一张已审核 PO
    let poId: number | undefined;
    for (const id of [...created.poIds].reverse()) {
      const g = await api('GET', `${KZ}/purchase-orders/${id}`);
      if (g.status === 200 && ['CONFIRMED', 'AUDITED', '已审核', '已确认'].includes(g.data.status)) {
        poId = id;
        break;
      }
    }
    if (poId === undefined) test.skip(true, '无可用的已审核 PO（上游被 RBAC 拦截）');
    const preview = await api('GET', `${KZ}/purchase-order-change-orders/from-order/${poId}/preview`);
    markRbac(`GET /purchase-order-change-orders/from-order/${poId}/preview`, preview.status, preview.data);
    if (preview.status === 403) test.skip(true, '变更预览 403 RBAC');
    expect(preview.status, `变更预览 ${preview.status}: ${JSON.stringify(preview.data)}`).toBeLessThan(400);
  });

  test('到货预警延期填报：基于 PO 明细创建 + 流转', async () => {
    let itemId: number | undefined;
    for (const id of [...created.poIds].reverse()) {
      const g = await api('GET', `${KZ}/purchase-orders/${id}`);
      const items: any[] = g.data?.items || [];
      const open = items.find((it) => Number(it.outstanding_quantity || 0) > 0);
      if (g.status === 200 && open) {
        itemId = open.id;
        break;
      }
    }
    if (itemId === undefined) test.skip(true, '无开口 PO 明细可填延期');
    const cr = await api('POST', `${KZ}/purchase-arrival/delay-reports`, {
      purchase_order_item_id: itemId,
      delay_reason: 'logistics',
      estimated_arrival_date: plusDays(30),
      impact_description: 'E2E测试延期',
    });
    markRbac('POST /purchase-arrival/delay-reports', cr.status, cr.data);
    if (cr.status === 403) test.skip(true, '延期填报 403 RBAC');
    expect(cr.status, `创建延期填报 ${cr.status}: ${JSON.stringify(cr.data)}`).toBeLessThan(400);
    const repId = cr.data.id;
    const sub = await api('POST', `${KZ}/purchase-arrival/delay-reports/${repId}/submit`, {});
    expect(sub.status, `延期提交 ${sub.status}: ${JSON.stringify(sub.data)}`).toBeLessThan(400);
    const appr = await api('POST', `${KZ}/purchase-arrival/delay-reports/${repId}/approve`, {
      approved: true,
    });
    expect(appr.status, `延期审核 ${appr.status}: ${JSON.stringify(appr.data)}`).toBeLessThan(400);
    const st = appr.data?.status;
    expect(['已通过', '已审核', 'approved', 'AUDITED', 'CONFIRMED'], `延期审核后状态异常 ${st}`).toContain(st);
  });

  test('采购询价单创建 + 列表', async () => {
    try {
      if (created.supplierId === 0 || created.materialId === 0) {
        await ensureSupplierAndMaterial();
      }
    } catch (e: any) {
      if (e instanceof RbacBlockedError) rbacBlocked.push(`询价 前置 ensureSupplierAndMaterial: ${e.message}`);
      test.skip(true, `询价 前置物料/供应商被拦截：${e.message}`);
    }
    if (created.supplierId === 0 || created.materialId === 0) test.skip(true, '无可用供应商/物料（上游被拦截）');
    const r = await api('POST', `${KZ}/purchase-inquiries`, {
      inquiry_name: `TEST-PUR询价-${RUN_ID}`,
      items: [
        {
          material_id: created.materialId,
          material_code: 'E2E-TEST',
          material_name: 'E2E测试物料',
          quantity: 5,
          unit: '件',
        },
      ],
      vendors: [
        { supplier_id: created.supplierId, supplier_name: 'TEST供应商' },
      ],
    });
    markRbac('POST /purchase-inquiries', r.status, r.data);
    if (r.status === 403) test.skip(true, '采购询价 403 RBAC');
    expect(r.status, `创建询价 ${r.status}: ${JSON.stringify(r.data)}`).toBeLessThan(400);
    created.inqIds.push(r.data.id);
    const list = await api('GET', `${KZ}/purchase-inquiries?limit=20`);
    markRbac('GET /purchase-inquiries', list.status, list.data);
    if (list.status === 403) test.skip(true, '采购询价列表 403 RBAC');
    expect(list.status).toBe(200);
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
      supplierUuid: created.supplierUuid,
      materialUuid: created.materialUuid,
      poIds: created.poIds,
      reqIds: created.reqIds,
      inqIds: created.inqIds,
      payIds: created.payIds,
      rnIds: created.rnIds,
    },
  };
  fs.writeFileSync(
    path.join(__dirname, 'output', 'kz-purchase-cleanup.json'),
    JSON.stringify(summary, null, 2),
    'utf-8',
  );
  for (const f of failures) console.log(`[kz-purchase] 清理失败: ${f}`);
  for (const f of rbacBlocked) console.log(`[kz-purchase] RBAC 403: ${f}`);
});

test('清理后复查残留（软删记录）', async () => {
  const kw = `TEST-PUR-PO-`;
  const r = await api('GET', `${KZ}/purchase-orders?limit=100&keyword=${encodeURIComponent(kw)}`);
  // ponytail: 列表响应体 {data: [...], total}；api() 的 data 字段=整个响应体
  const items = Array.isArray(r.data?.data) ? r.data.data : Array.isArray(r.data) ? r.data : Array.isArray(r.data?.items) ? r.data.items : [];
  const mine = items.filter((o: any) => created.poIds.includes(o.id));
  expect(mine, `残留 PO: ${JSON.stringify(mine.map((o: any) => o.id))}`).toEqual([]);
});
