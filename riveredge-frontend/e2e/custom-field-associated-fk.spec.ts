/**
 * 关联对象源字段（外键 / 手工追加）回归
 *
 * 层级：
 * 1) API：system-link-fields / associated-lookup / 字段 CRUD（异常与契约）
 * 2) UI：自定义字段管理页可选主物料；BOM 新建弹窗不因关联字段崩溃
 *
 * 运行：
 *   cd riveredge-frontend
 *   $env:E2E_USERNAME='e2e_cf_fk'; $env:E2E_PASSWORD='…'; $env:E2E_TENANT_ID='1'
 *   npx playwright test -c e2e/playwright.cf-fk.config.ts
 */
import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { STORAGE_STATE_PATH } from './helpers/session';
import {
  apiGetRaw,
  apiSendRaw,
  associatedLookup,
  createAssociatedObjectField,
  deleteCustomField,
  fetchOneActiveMaterial,
  listSystemLinkFields,
  listSystemSourceFields,
  type CustomFieldDto,
} from './helpers/customFieldApi';

const BOM_TABLE = 'master_data_boms';
const MATERIAL_TABLE = 'master_data_materials';
const SALES_ORDER_TABLE = 'apps_kuaizhizao_sales_orders';
const PURCHASE_ORDER_TABLE = 'apps_kuaizhizao_purchase_orders';
const CF_ADMIN_PATH = '/system/custom-fields';
const BOM_PAGE_PATH = '/apps/master-data/process/engineering-bom';
/** 会消费 system-link-fields / associated-lookup 的业务表抽样 */
const LINK_FIELD_TABLES = [
  BOM_TABLE,
  MATERIAL_TABLE,
  SALES_ORDER_TABLE,
  PURCHASE_ORDER_TABLE,
  'master_data_factory_workshops',
] as const;

test.use({ storageState: STORAGE_STATE_PATH });

function uniqueCode(prefix: string): string {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`;
}

async function readToken(page: import('@playwright/test').Page): Promise<string> {
  const token = await page.evaluate(() => localStorage.getItem('token'));
  expect(token, '登录态 token 缺失').toBeTruthy();
  return token!;
}

test.describe('自定义字段 · 关联对象外键源', () => {
  test.describe.configure({ mode: 'serial' });

  let createdField: CustomFieldDto | null = null;

  test.afterEach(async ({ page }) => {
    if (!createdField?.uuid) return;
    try {
      const token = await readToken(page);
      await deleteCustomField(token, createdField.uuid);
    } catch (error) {
      console.warn('[cleanup] delete custom field failed', error);
    } finally {
      createdField = null;
    }
  });

  test('API：BOM 表 system-link-fields 含 materialId，且不含在纯标量清单中混丢', async ({
    page,
  }) => {
    await page.goto('/');
    const token = await readToken(page);

    const links = await listSystemLinkFields(token, BOM_TABLE);
    const scalars = await listSystemSourceFields(token, BOM_TABLE);

    const materialLink = links.find((item) => item.name === 'materialId');
    expect(materialLink, '外键清单应含主物料 materialId').toBeTruthy();

    const materialAsScalar = scalars.find((item) => item.name === 'materialId');
    expect(materialAsScalar, 'materialId 不应出现在纯标量源字段清单').toBeFalsy();
  });

  test('API：按物料 id 匹配可 lookup base_unit；错误匹配返回空值不 500', async ({ page }) => {
    await page.goto('/');
    const token = await readToken(page);
    const material = await fetchOneActiveMaterial(token);

    const ok = await associatedLookup(token, {
      table: MATERIAL_TABLE,
      matchField: 'id',
      matchValue: material.id,
      returnField: 'base_unit',
    });
    expect(ok.value == null || typeof ok.value === 'string' || typeof ok.value === 'number').toBe(
      true,
    );
    if (material.base_unit || material.baseUnit) {
      expect(String(ok.value)).toBe(String(material.base_unit || material.baseUnit));
    }

    const miss = await associatedLookup(token, {
      table: MATERIAL_TABLE,
      matchField: 'id',
      matchValue: -1,
      returnField: 'base_unit',
    });
    expect(miss.value).toBeNull();
  });

  test('API：可创建 BOM 关联对象字段（源=materialId），再删除', async ({ page }) => {
    await page.goto('/');
    const token = await readToken(page);
    const code = uniqueCode('e2e_bom_unit');

    createdField = await createAssociatedObjectField(token, {
      tableName: BOM_TABLE,
      code,
      name: `E2E主物料单位_${code}`,
      sourceField: 'materialId',
      associatedTable: MATERIAL_TABLE,
      matchField: 'id',
      returnField: 'base_unit',
      displayMode: 'display',
    });
    expect(createdField.uuid).toBeTruthy();
    expect(createdField.config?.sourceField).toBe('materialId');
    expect(createdField.config?.matchField).toBe('id');

    await deleteCustomField(token, createdField.uuid);
    createdField = null;
  });

  test('API：手工追加源字段可创建（不在 link 清单内）', async ({ page }) => {
    await page.goto('/');
    const token = await readToken(page);
    const code = uniqueCode('e2e_manual_src');
    const manualSource = `manualFk_${Date.now().toString(36)}`;

    createdField = await createAssociatedObjectField(token, {
      tableName: BOM_TABLE,
      code,
      name: `E2E手工源_${code}`,
      sourceField: manualSource,
      associatedTable: MATERIAL_TABLE,
      matchField: 'id',
      returnField: 'code',
      displayMode: 'display',
    });
    expect(createdField.config?.sourceField).toBe(manualSource);

    await deleteCustomField(token, createdField.uuid);
    createdField = null;
  });

  test('API：异常契约 — 未知表/未注册关联表/缺源字段不 500', async ({ page }) => {
    await page.goto('/');
    const token = await readToken(page);

    const unknownLinks = await apiGetRaw(
      token,
      `/core/custom-fields/system-link-fields/${encodeURIComponent('not_a_real_table_zzz')}`,
    );
    expect(unknownLinks.status, unknownLinks.body).toBeLessThan(500);
    if (unknownLinks.status === 200) {
      expect(JSON.parse(unknownLinks.body)).toEqual([]);
    }

    const unregisteredLookup = await apiGetRaw(
      token,
      `/core/custom-fields/associated-lookup?${new URLSearchParams({
        table: 'not_registered_table_zzz',
        match_field: 'id',
        match_value: '1',
        return_field: 'name',
      }).toString()}`,
    );
    expect(unregisteredLookup.status, unregisteredLookup.body).toBeLessThan(500);
    if (unregisteredLookup.status === 200) {
      const parsed = JSON.parse(unregisteredLookup.body) as { value: unknown };
      expect(parsed.value).toBeNull();
    }

    const badMatchRaw = await apiGetRaw(
      token,
      `/core/custom-fields/associated-lookup?${new URLSearchParams({
        table: MATERIAL_TABLE,
        match_field: 'definitely_not_a_column',
        match_value: 'x',
        return_field: 'base_unit',
      }).toString()}`,
    );
    expect(badMatchRaw.status, badMatchRaw.body).toBeLessThan(500);
    if (badMatchRaw.status === 200) {
      expect(JSON.parse(badMatchRaw.body).value).toBeNull();
    }

    const unregisteredOptions = await apiGetRaw(
      token,
      `/core/custom-fields/associated-options?${new URLSearchParams({
        table: 'not_registered_table_zzz',
        limit: '10',
      }).toString()}`,
    );
    expect(unregisteredOptions.status, unregisteredOptions.body).toBeGreaterThanOrEqual(400);
    expect(unregisteredOptions.status).toBeLessThan(500);

    const incompleteXlookup = await apiSendRaw(token, '/core/custom-fields', 'POST', {
      name: 'E2E缺源字段',
      code: uniqueCode('e2e_nosrc'),
      table_name: BOM_TABLE,
      field_type: 'associated_object',
      label: 'E2E缺源字段',
      is_required: false,
      is_searchable: false,
      is_sortable: false,
      sort_order: 0,
      is_active: true,
      config: {
        associatedTable: MATERIAL_TABLE,
        matchField: 'id',
        returnField: 'base_unit',
        displayMode: 'display',
      },
    });
    expect(incompleteXlookup.status, incompleteXlookup.body).toBeGreaterThanOrEqual(400);
    expect(incompleteXlookup.status).toBeLessThan(500);
    expect(incompleteXlookup.body).toMatch(/源字段|matchField|associatedField|display/);
  });

  test('API：抽样业务表 system-link-fields 可调用且外键不进纯标量清单', async ({ page }) => {
    await page.goto('/');
    const token = await readToken(page);

    for (const table of LINK_FIELD_TABLES) {
      const linksRaw = await apiGetRaw(
        token,
        `/core/custom-fields/system-link-fields/${encodeURIComponent(table)}`,
      );
      expect(linksRaw.status, `${table} link-fields ${linksRaw.body}`).toBe(200);
      const links = JSON.parse(linksRaw.body) as Array<{ name: string }>;
      expect(Array.isArray(links)).toBe(true);

      const scalarsRaw = await apiGetRaw(
        token,
        `/core/custom-fields/system-fields/${encodeURIComponent(table)}`,
      );
      expect(scalarsRaw.status, `${table} system-fields ${scalarsRaw.body}`).toBe(200);
      const scalars = JSON.parse(scalarsRaw.body) as Array<{ name: string }>;
      const scalarNames = new Set(scalars.map((item) => item.name));
      for (const link of links) {
        expect(
          scalarNames.has(link.name),
          `${table}: 外键 ${link.name} 不应混入纯标量清单`,
        ).toBeFalsy();
      }
    }
  });

  test('UI：自定义字段管理页可选主物料源字段；BOM 新建弹窗加载不崩溃', async ({ page }) => {
    const pageErrors: string[] = [];
    page.on('pageerror', (error) => pageErrors.push(String(error)));

    await page.goto('/');
    const token = await readToken(page);
    const code = uniqueCode('e2e_ui_unit');

    createdField = await createAssociatedObjectField(token, {
      tableName: BOM_TABLE,
      code,
      name: `E2E界面单位_${code}`,
      sourceField: 'materialId',
      associatedTable: MATERIAL_TABLE,
      matchField: 'id',
      returnField: 'base_unit',
      displayMode: 'display',
    });

    // —— 管理页：左侧选 BOM，列表可见字段 ——
    await page.goto(CF_ADMIN_PATH);
    await expect(page.getByText('物料清单BOM').or(page.getByText('BOM')).first()).toBeVisible({
      timeout: 30_000,
    });
    const bomPageItem = page.getByText('物料清单BOM', { exact: false }).first();
    await bomPageItem.click();
    await expect(page.getByText(createdField.name).first()).toBeVisible({ timeout: 20_000 });

    // —— BOM 页：打开新建，确认自定义字段标签出现且无 pageerror ——
    await page.goto(BOM_PAGE_PATH);
    const createBtn = page.getByRole('button', { name: /新建/ }).first();
    await expect(createBtn).toBeVisible({ timeout: 30_000 });
    await createBtn.click();

    const modal = page.getByRole('dialog').first();
    await expect(modal).toBeVisible({ timeout: 20_000 });
    await expect(modal.getByText(createdField.name, { exact: false }).first()).toBeVisible({
      timeout: 20_000,
    });

    // 选主物料后应触发 associated-lookup（不固定睡眠，等网络）
    const material = await fetchOneActiveMaterial(token);
    const lookupWait = page.waitForResponse(
      (res) =>
        res.url().includes('/core/custom-fields/associated-lookup') &&
        res.request().method() === 'GET',
      { timeout: 30_000 },
    ).catch(() => null);

    const materialSelect = modal.getByRole('combobox').filter({ hasText: /主物料|物料/ }).first();
    const materialFallback = modal.locator('.ant-select').filter({ hasText: /主物料|请选择/ }).first();
    if (await materialSelect.isVisible().catch(() => false)) {
      await materialSelect.click();
    } else {
      await materialFallback.click();
    }
    const searchBox = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden) input').first();
    if (await searchBox.isVisible().catch(() => false)) {
      await searchBox.fill(String(material.code || material.name || material.id));
    }
    const option = page
      .locator('.ant-select-item-option-content')
      .filter({ hasText: String(material.code || material.name || '') })
      .first();
    if (await option.isVisible({ timeout: 8_000 }).catch(() => false)) {
      await option.click();
      const lookupRes = await lookupWait;
      if (lookupRes) {
        expect(lookupRes.status(), 'associated-lookup 不应 5xx').toBeLessThan(500);
      }
    }

    expect(pageErrors, `BOM 弹窗不应抛未捕获异常: ${pageErrors.join('; ')}`).toEqual([]);

    await page.keyboard.press('Escape');
  });
});

test.afterAll(() => {
  const outDir = path.join(__dirname, 'output');
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(
    path.join(outDir, 'custom-field-associated-fk-meta.json'),
    JSON.stringify({ at: new Date().toISOString(), storageState: STORAGE_STATE_PATH }, null, 2),
  );
});
