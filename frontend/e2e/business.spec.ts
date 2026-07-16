import { expect, test } from '@playwright/test'

const response = (data: unknown) => ({ code: 200, message: 'success', data })

test('TC-UI-007 登录成功并进入仪表盘', async ({ page }) => {
  await page.route('**/api/v1/auth/login', (route) => route.fulfill({ json: response({ access_token: 'token' }) }))
  await page.route('**/api/v1/health', (route) => route.fulfill({ json: response({ status: 'ok', database: 'sqlite' }) }))
  await page.goto('/login')
  await page.getByPlaceholder('密码').fill('admin123')
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await expect.poll(() => page.evaluate(() => localStorage.getItem('token'))).toBe('token')
})

test.describe('已登录业务流程', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('token', 'e2e-token'))
  })

  test('TC-UI-008 新增活动', async ({ page }) => {
    let created = false
    await page.route('**/api/v1/activities**', async (route) => {
      if (route.request().method() === 'POST') {
        created = true
        return route.fulfill({ json: response({ id: 1 }) })
      }
      return route.fulfill({ json: { ...response({ items: [] }), pagination: { total: 0 } } })
    })
    await page.goto('/activities')
    await page.getByRole('button', { name: '新增活动' }).click()
    await page.getByLabel('名称').fill('周末艺术展')
    await page.locator('.el-form-item').filter({ hasText: '时间' }).locator('input').first().fill('2026-07-18 10:00:00')
    await page.getByLabel('地点').fill('上海展览中心')
    await page.getByRole('button', { name: '保存' }).click()
    await expect.poll(() => created).toBe(true)
    await expect(page.getByText('保存成功')).toBeVisible()
  })

  test('TC-UI-009 筛选并查看活动详情', async ({ page }) => {
    let filtered = false
    const activity = { id: 1, name: '上海周末展览', city_code: 'shanghai', start_time: '2026-07-18T10:00:00Z', location: '静安', price: '免费', type: '展览', source_url: '', summary: '活动详情', status: 'RAW' }
    await page.route('**/api/v1/activities**', async (route) => {
      const url = new URL(route.request().url())
      if (/\/activities\/1$/.test(url.pathname)) return route.fulfill({ json: response(activity) })
      filtered = url.searchParams.get('city') === 'shanghai'
      return route.fulfill({ json: { ...response({ items: [activity] }), pagination: { total: 1 } } })
    })
    await page.goto('/activities')
    await page.getByRole('textbox', { name: '城市代码' }).fill('shanghai')
    await page.getByRole('button', { name: '筛选' }).click()
    await expect.poll(() => filtered).toBe(true)
    await page.getByRole('button', { name: '详情' }).click()
    await expect(page.getByRole('heading', { name: '活动详情' })).toBeVisible()
    await expect(page.getByRole('cell', { name: '活动详情' })).toBeVisible()
  })

  test('TC-UI-010 提交抓取任务并查看登录提示', async ({ page }) => {
    let submitted = false
    await page.route('**/api/v1/tasks**', async (route) => {
      if (route.request().method() === 'POST') {
        submitted = true
        return route.fulfill({ json: response({ id: 1, status: 'PENDING' }) })
      }
      return route.fulfill({ json: response({ items: [] }) })
    })
    await page.goto('/tasks')
    await expect(page.getByText('任务会先检查 Chrome 小红书登录态；未登录时自动暂停')).toBeVisible()
    await page.getByRole('button', { name: '开始抓取' }).click()
    await expect.poll(() => submitted).toBe(true)
    await expect(page.getByText('任务已提交')).toBeVisible()
  })

  test('TC-UI-011 合并重复活动', async ({ page }) => {
    let merged = false
    await page.route('**/api/v1/activities/*', (route) => route.fulfill({ json: response({ id: 10, name: '活动', start_time: '2026-07-18T10:00:00Z', location: '静安' }) }))
    await page.route('**/api/v1/duplicates**', async (route) => {
      if (route.request().method() === 'POST') {
        merged = true
        return route.fulfill({ json: response({ status: 'MERGED' }) })
      }
      return route.fulfill({ json: response({ items: [{ id: 1, activity_a_id: 10, activity_b_id: 11, similarity: 0.92, matched_fields: 'name,time' }] }) })
    })
    await page.goto('/duplicates')
    await page.getByRole('button', { name: '保留 A' }).click()
    await expect.poll(() => merged).toBe(true)
    await expect(page.getByText('合并完成')).toBeVisible()
  })

  test('TC-UI-012 生成并预览周报', async ({ page }) => {
    let generated = false
    await page.route('**/api/v1/reports**', async (route) => {
      const url = new URL(route.request().url())
      if (route.request().method() === 'POST') {
        generated = true
        return route.fulfill({ json: response({ id: 1 }) })
      }
      if (/\/reports\/1$/.test(url.pathname)) return route.fulfill({ json: response({ content: '# 上海周末活动' }) })
      return route.fulfill({ json: response([{ id: 1, week: '2026-W29', cities: 'shanghai', activity_count: 2, status: 'GENERATED' }]) })
    })
    await page.goto('/reports')
    await page.getByRole('button', { name: '生成周报' }).click()
    await expect.poll(() => generated).toBe(true)
    await page.getByRole('button', { name: '预览' }).click()
    await expect(page.getByText('# 上海周末活动')).toBeVisible()
  })

  test('TC-UI-013 新增城市并测试 OpenCLI', async ({ page }) => {
    let cityCreated = false
    await page.route('**/api/v1/settings/**', async (route) => {
      const request = route.request()
      if (request.url().endsWith('/opencli/test')) return route.fulfill({ json: response({ logged_in: true }) })
      if (request.method() === 'POST') {
        cityCreated = true
        return route.fulfill({ json: response({ id: 1 }) })
      }
      return route.fulfill({ json: response([]) })
    })
    await page.goto('/settings')
    await page.getByRole('button', { name: '新增' }).click()
    await page.getByLabel('城市名称').fill('上海')
    await page.getByLabel('城市代码').fill('shanghai')
    await page.getByRole('button', { name: '保存' }).click()
    await expect.poll(() => cityCreated).toBe(true)
    await page.getByRole('button', { name: '测试 OpenCLI' }).click()
    await expect(page.getByText('OpenCLI 登录与连接正常')).toBeVisible()
  })
})
