/**
 * 登录页 UI 验证：表单登录（默认 xiaofeng @ 测试，无同名歧义），成功后离开 /login。
 */
import { test, expect } from '@playwright/test';
import { USERNAME, PASSWORD, TENANT_DISPLAY_NAME, TENANT_ID } from './helpers/session';

/** 多组织同名同密时的手机号后四位（仅当弹窗出现时使用） */
const PHONE_LAST4 = process.env.E2E_PHONE_LAST4 || '';

test.describe('登录', () => {
  test('表单登录成功并跳转', async ({ page }) => {
    await page.goto(`/login?tenant_id=${TENANT_ID}`);
    await page.waitForSelector('form');

    await page.locator('input[autocomplete="username"]').fill(USERNAME);
    await page.locator('input[autocomplete="current-password"]').fill(PASSWORD);
    await page.locator('button[type="submit"]').click();

    // 若触发同名同密核验
    const phoneInput = page.getByPlaceholder('手机号后四位');
    if (PHONE_LAST4 && (await phoneInput.isVisible({ timeout: 3_000 }).catch(() => false))) {
      await phoneInput.fill(PHONE_LAST4);
      await page.getByRole('button', { name: /确\s*认/ }).click();
    }

    // 多组织选择（若出现）
    const tenantOption = page.locator(`text=${TENANT_DISPLAY_NAME}`).first();
    await tenantOption.click({ timeout: 5_000 }).catch(() => undefined);

    await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 45_000 });
    expect(page.url()).not.toContain('/login');

    const token = await page.evaluate(() => localStorage.getItem('token'));
    expect(token).toBeTruthy();
  });

  test('错误密码提示失败且停留在登录页', async ({ page }) => {
    await page.goto('/login');
    await page.waitForSelector('form');

    await page.locator('input[autocomplete="username"]').fill(USERNAME);
    await page.locator('input[autocomplete="current-password"]').fill('wrong-password-1');
    await page.locator('button[type="submit"]').click();

    await page.waitForTimeout(3000);
    expect(new URL(page.url()).pathname).toBe('/login');
    const token = await page.evaluate(() => localStorage.getItem('token'));
    expect(token).toBeFalsy();
  });
});
