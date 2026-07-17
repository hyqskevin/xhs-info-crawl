import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('token', 'e2e-token'))
  await page.route('**/api/v1/health', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 200, message: 'success', data: { status: 'ok', database: 'sqlite' } }),
    })
  })
  await page.route('**/api/v1/dashboard/summary**', (route) => route.fulfill({ json: { data: { last_task: null } } }))
  await page.route('**/api/v1/activities**', (route) => route.fulfill({ json: { data: { items: [] }, pagination: { total: 0 } } }))
  await page.route('**/api/v1/duplicates**', (route) => route.fulfill({ json: { data: { items: [] } } }))
  await page.route('**/api/v1/tasks**', (route) => route.fulfill({ json: { data: { items: [] } } }))
  await page.route('**/api/v1/reports**', (route) => route.fulfill({ json: { data: [] } }))
  await page.route('**/api/v1/settings/**', (route) => route.fulfill({ json: { data: [] } }))
})

test('dashboard renders service state without emoji icons', async ({ page }) => {
  await page.goto('/dashboard')
  await expect(page.getByRole('heading', { name: '小红书本地活动信息抓取系统' })).toBeVisible()
  await expect(page.getByText('服务运行正常')).toBeVisible()
  await expect(page.getByText('SQLite', { exact: true })).toBeVisible()
  const source = await page.locator('body').innerText()
  expect(source).not.toMatch(/[😀-🙏🌀-🫿]/u)
})

for (const item of [
  { label: '活动管理', path: '/activities' },
  { label: '去重审核', path: '/duplicates' },
  { label: '任务日志', path: '/tasks' },
  { label: '周报管理', path: '/reports' },
  { label: '配置中心', path: '/settings' },
]) {
  test(`menu button ${item.label} navigates to ${item.path}`, async ({ page }) => {
    await page.goto('/dashboard')
    await page.getByRole('menuitem', { name: item.label }).click()
    await expect(page).toHaveURL(new RegExp(`${item.path}$`))
    await expect(page.getByRole('heading', { name: item.label })).toBeVisible()
  })
}
