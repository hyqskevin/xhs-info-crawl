import { expect, test } from '@playwright/test'

/**
 * 海报生成端到端流程（真浏览器）。
 *
 * 前置：
 * - 后端 dev API 跑起来在 http://127.0.0.1:8000
 * - 前端 dev 服务（Playwright webServer）跑起来
 * - 系统已装 playwright chromium（playwright install）
 * - 配置中心 → 海报模板 已至少 1 个手工模板（橙橙风格）
 *
 * 关联 TC-PW-E2E-{001..003}
 */
const ADMIN = { username: 'admin', password: 'Admin@123' }

async function login(page) {
  await page.goto('/login')
  await page.locator('input[placeholder*="用"]').fill(ADMIN.username)
  await page.locator('input[type="password"]').fill(ADMIN.password)
  await page.locator('button').filter({ hasText: '登录' }).click()
  await expect(page.locator('text=仪表盘')).toBeVisible()
}

test.describe('海报 wizard end-to-end', () => {
  test('TC-PW-E2E-001 海报制作 nav 进入列表页', async ({ page }) => {
    await login(page)
    await page.getByRole('link', { name: /海报制作/ }).click()
    await expect(page).toHaveURL(/\/posters/)
    await expect(page.getByText('海报任务列表')).toBeVisible()
  })

  test('TC-PW-E2E-002 新建海报 - 走完 6 步', async ({ page }) => {
    await login(page)
    await page.getByRole('link', { name: /海报制作/ }).click()
    await page.getByText('新建海报').first().click()
    await expect(page).toHaveURL(/\/posters\/new/)
    // 步骤 1：第一个候选勾选 + 下一步
    await page.waitForSelector('table')
    const checkboxes = page.locator('input[type="checkbox"]')
    if (await checkboxes.count() > 0) {
      await checkboxes.first().check()
    }
    await page.getByText('下一步').first().click()
    // 步骤 2：选择第一个模板
    const selectBtn = page.getByText('选择').first()
    if (await selectBtn.count() > 0) {
      await selectBtn.click()
    }
    await page.getByText('下一步').first().click()
    // 步骤 3：填充
    const inputs = page.locator('input[placeholder*="时间"], input[placeholder*="地点"], input[placeholder*="费用"]')
    if (await inputs.count() >= 3) {
      await inputs.nth(0).fill('7.4 16:00-17:00')
      await inputs.nth(1).fill('宁波万象汇L1')
      await inputs.nth(2).fill('免费')
    }
    await page.getByText('下一步').first().click()
    // 步骤 4：HTML
    await page.getByText('下一步').first().click()
    // 步骤 5：保存并预览
    await page.getByText('保存并预览').first().click()
    // 等 Iframe 出现
    await page.waitForSelector('iframe.preview-frame', { timeout: 10_000 })
    await expect(page.locator('iframe.preview-frame')).toBeVisible()
  })

  test('TC-PW-E2E-003 渲染为 PNG：触发 POST /render', async ({ page }) => {
    // 拦截 render 请求
    const reqPromise = page.waitForRequest(req => /\/api\/v1\/poster-tasks\/\d+\/render/.test(req.url()))
    await login(page)
    await page.getByRole('link', { name: /海报制作/ }).click()
    await page.getByText('新建海报').first().click()

    // 简化：mock 后面 → 选第一项 → 下一步 → 下一步 → 下一步 → 下一步 → 渲染为 PNG
    await page.waitForSelector('table')
    const checkboxes = page.locator('input[type="checkbox"]')
    if (await checkboxes.count() > 0) {
      await checkboxes.first().check()
    }
    await page.getByText('下一步').first().click()
    const selectBtn = page.getByText('选择').first()
    if (await selectBtn.count() > 0) {
      await selectBtn.click()
    }
    await page.getByText('下一步').first().click()
    await page.getByText('下一步').first().click()
    await page.getByText('下一步').first().click()
    await page.getByText('保存并预览').first().click()
    await page.waitForSelector('iframe.preview-frame', { timeout: 10_000 })
    // 点 "渲染为 PNG"
    const render = page.getByText('渲染为 PNG').first()
    if (await render.count() > 0) {
      await render.click()
      const req = await reqPromise
      expect(req.url()).toMatch(/\/render$/)
    } else {
      // skip if template not seeded
      test.skip(true, '没有模板，跳过')
    }
  })
})
