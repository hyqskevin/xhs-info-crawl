import { expect, test } from '@playwright/test'

const response = (data: unknown) => ({ code: 200, message: 'success', data })

test('TC-UI-007 登录成功并进入仪表盘', async ({ page }) => {
  await page.route('**/api/v1/auth/login', (route) => route.fulfill({ json: response({ access_token: 'token' }) }))
  await page.route('**/api/v1/health', (route) => route.fulfill({ json: response({ status: 'ok', database: 'sqlite' }) }))
  await page.route('**/api/v1/settings/cities**', (route) => route.fulfill({ json: response([]) }))
  await page.route('**/api/v1/settings/bloggers**', (route) => route.fulfill({ json: response([]) }))
  await page.route('**/api/v1/dashboard/summary**', (route) => route.fulfill({ json: response({ last_task: null }) }))
  await page.goto('/login')
  await page.getByPlaceholder('密码').fill('admin123')
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await expect.poll(() => page.evaluate(() => localStorage.getItem('token'))).toBe('token')
})

test.describe('已登录业务流程', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('token', 'e2e-token'))
    await page.route('**/api/v1/settings/cities**', (route) => route.fulfill({ json: response([{ id: 1, name: '上海', code: 'shanghai', keywords: ['周末活动'], recent_filter: '一周内', enabled: true }]) }))
    await page.route('**/api/v1/settings/bloggers**', (route) => route.fulfill({ json: response([{ id: 9, username: '活动博主', city_code: 'shanghai', enabled: true }]) }))
    await page.route('**/api/v1/dashboard/summary**', (route) => route.fulfill({ json: response({ last_task: null }) }))
  })

  test('TC-UI-008 活动只来自抓取且支持按时间筛选', async ({ page }) => {
    let query = ''
    await page.route('**/api/v1/notes**', async (route) => {
      query = route.request().url()
      return route.fulfill({ json: { ...response({ items: [] }), pagination: { total: 0 } } })
    })
    await page.goto('/activities')
    await expect(page.getByRole('button', { name: '新增活动' })).toHaveCount(0)
    const dateInputs = page.locator('.el-date-editor input')
    await dateInputs.nth(0).fill('2026-07-18')
    await dateInputs.nth(1).fill('2026-07-20')
    await page.getByRole('button', { name: '筛选' }).click()
    await expect.poll(() => new URL(query).searchParams.get('start_date')).toBe('2026-07-18')
    expect(new URL(query).searchParams.get('end_date')).toBe('2026-07-20')
  })

  test('TC-UI-009 筛选并查看活动详情', async ({ page }) => {
    let filtered = false
    const note = { id: 1, title: '上海周末展览推文', city_code: 'shanghai', published_at: '2026-07-18T10:00:00Z', activity_count: 1, review_status: 'PENDING' }
    const detail = { ...note, content: '活动详情', source_url: 'https://www.xiaohongshu.com/explore/note-1', images: [], activities: [{ id: 10, name: '上海周末展览', location: '静安', status: 'RAW' }] }
    await page.route('**/api/v1/notes**', async (route) => {
      const url = new URL(route.request().url())
      if (/\/notes\/1$/.test(url.pathname)) return route.fulfill({ json: response(detail) })
      filtered = url.searchParams.get('city') === 'shanghai'
      return route.fulfill({ json: { ...response({ items: [note] }), pagination: { total: 1 } } })
    })
    await page.goto('/activities')
    await page.locator('.el-select').first().click()
    await page.getByRole('option', { name: '上海' }).click()
    await page.getByRole('button', { name: '筛选' }).click()
    await expect.poll(() => filtered).toBe(true)
    await page.getByRole('button', { name: '详情' }).click()
    await expect(page.getByRole('heading', { name: '推文详情' })).toBeVisible()
    await expect(page.getByText('活动详情', { exact: true })).toBeVisible()
    await expect(page.getByRole('cell', { name: '上海周末展览', exact: true })).toBeVisible()
  })

  test('TC-UI-009A 日期未知活动显示待确认', async ({ page }) => {
    const unknown = { id: 2, title: '日期未知活动推文', city_code: 'shanghai', published_at: null, created_at: null, activity_count: 1, review_status: 'PENDING' }
    await page.route('**/api/v1/notes**', (route) => route.fulfill({ json: { ...response({ items: [unknown] }), pagination: { total: 1 } } }))
    await page.goto('/activities')
    await expect(page.getByRole('row', { name: /日期未知活动推文/ })).toContainText('待确认')
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
    await page.goto('/dashboard')
    await page.locator('.crawl-card .el-select').nth(1).click()
    await page.getByRole('option', { name: '周末活动' }).click()
    await expect(page.getByText('任务启动前会检查 Chrome 小红书登录状态')).toBeVisible()
    await page.getByRole('button', { name: '开始抓取' }).click()
    await expect.poll(() => submitted).toBe(true)
    await expect(page.getByText('任务已提交')).toBeVisible()
  })

  test('TC-UI-011 合并重复活动', async ({ page }) => {
    let merged = false
    await page.route('**/api/v1/notes/*', (route) => {
      const id = Number(new URL(route.request().url()).pathname.split('/').pop())
      return route.fulfill({ json: response({ id, title: `推文 ${id}`, published_at: '2026-07-18T10:00:00Z', activity_count: 1 }) })
    })
    await page.route('**/api/v1/duplicates**', async (route) => {
      if (route.request().method() === 'POST') {
        merged = true
        return route.fulfill({ json: response({ status: 'MERGED' }) })
      }
      return route.fulfill({ json: response({ items: [{ id: 1, note_a_id: 10, note_b_id: 11, similarity: 0.92, matched_fields: 'title,published_at' }] }) })
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
      return route.fulfill({ json: response([{ id: 1, week: '2026-W29', cities: ['shanghai'], activity_count: 2, status: 'GENERATED' }]) })
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
    await page.getByRole('button', { name: '新增城市' }).click()
    await page.getByLabel('城市名称').fill('上海')
    const keyword = page.getByRole('textbox', { name: '关键词' })
    await keyword.fill('周末活动')
    await keyword.press('Enter')
    await page.getByRole('button', { name: '保存' }).click()
    await expect.poll(() => cityCreated).toBe(true)
    await page.getByRole('button', { name: '测试 OpenCLI' }).click()
    await expect(page.getByText('OpenCLI 登录与连接正常')).toBeVisible()
  })

  test('TC-UI-014 批量删除当前页活动', async ({ page }) => {
    let deletedIds: number[] = []
    const items = [1, 2].map((id) => ({ id, title: `推文 ${id}`, city_code: 'shanghai', published_at: '2026-07-18T10:00:00Z', activity_count: 1, review_status: 'PENDING' }))
    await page.route('**/api/v1/notes**', async (route) => {
      if (route.request().method() === 'DELETE') {
        deletedIds = route.request().postDataJSON().ids
        return route.fulfill({ json: response({ deleted_count: deletedIds.length }) })
      }
      return route.fulfill({ json: { ...response({ items }), pagination: { total: 2 } } })
    })
    await page.goto('/activities')
    await page.locator('.el-table__header .el-checkbox').click()
    await page.getByRole('button', { name: '批量删除' }).click()
    await page.getByRole('button', { name: '确定' }).click()
    await expect.poll(() => deletedIds).toEqual([1, 2])
  })

  test('TC-UI-018 批量通过后生成单城市周报', async ({ page }) => {
    let approvedIds: number[] = []
    let reportPayload: { week: string; cities: string[] } | null = null
    const items = [1, 2].map((id) => ({ id, title: `推文 ${id}`, city_code: 'shanghai', published_at: '2026-07-18T10:00:00Z', activity_count: 1, review_status: 'PENDING' }))
    await page.route('**/api/v1/notes**', async (route) => {
      if (route.request().method() === 'POST' && route.request().url().endsWith('/batch/approve')) {
        approvedIds = route.request().postDataJSON().ids
        return route.fulfill({ json: response({ approved_ids: approvedIds, approved_count: approvedIds.length }) })
      }
      return route.fulfill({ json: { ...response({ items }), pagination: { total: 2 } } })
    })
    await page.route('**/api/v1/reports**', async (route) => {
      if (route.request().method() === 'POST') {
        reportPayload = route.request().postDataJSON()
        return route.fulfill({ json: response({ id: 8, week: reportPayload!.week, cities: reportPayload!.cities, activity_count: 2, status: 'draft' }) })
      }
      return route.fulfill({ json: response([]) })
    })

    await page.goto('/activities')
    await expect(page.getByRole('button', { name: '批量通过' })).toBeDisabled()
    await page.locator('.el-table__header .el-checkbox').click()
    await page.getByRole('button', { name: '批量通过' }).click()
    await page.getByRole('button', { name: '确定' }).click()
    await expect.poll(() => approvedIds).toEqual([1, 2])
    await expect(page.getByText('已通过 2 篇推文')).toBeVisible()

    await page.goto('/reports')
    await page.getByRole('button', { name: '生成周报' }).click()
    await expect.poll(() => reportPayload).not.toBeNull()
    expect(reportPayload!.cities).toEqual(['shanghai'])
    await expect(page.getByText('周报生成成功')).toBeVisible()
  })
})
