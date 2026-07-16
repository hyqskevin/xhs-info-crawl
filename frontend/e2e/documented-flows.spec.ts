import { expect, test, type Page, type Route } from '@playwright/test'

const response = (data: unknown) => ({ code: 200, message: 'success', data })
const activity = {
  id: 1,
  name: '上海周末展览',
  city_code: 'shanghai',
  start_time: '2026-07-18T10:00:00Z',
  end_time: null,
  location: '静安艺术中心',
  price: '免费',
  type: '展览',
  source_url: 'https://example.com/note/1',
  summary: '活动详情',
  status: 'RAW',
}

async function authenticated(page: Page) {
  await page.addInitScript(() => localStorage.setItem('token', 'e2e-token'))
}

test.describe('TC-UI-007 登录完整流程', () => {
  test('未登录访问业务页面跳转登录页', async ({ page }) => {
    await page.goto('/activities')
    await expect(page).toHaveURL(/\/login$/)
  })

  test('空用户名或密码显示表单校验且不请求接口', async ({ page }) => {
    let requested = false
    await page.route('**/api/v1/auth/login', (route) => { requested = true; return route.abort() })
    await page.goto('/login')
    await page.getByPlaceholder('用户名').fill('')
    await page.getByRole('button', { name: '登录' }).click()
    await expect(page.getByText('请输入用户名和密码')).toBeVisible()
    expect(requested).toBe(false)
  })

  test('错误凭据显示错误提示', async ({ page }) => {
    await page.route('**/api/v1/auth/login', (route) => route.fulfill({ status: 401, json: { detail: '用户名或密码错误' } }))
    await page.goto('/login')
    await page.getByPlaceholder('密码').fill('wrong')
    await page.getByRole('button', { name: '登录' }).click()
    await expect(page.getByText('用户名或密码错误')).toBeVisible()
    await expect(page).toHaveURL(/\/login$/)
  })
})

test.describe('TC-UI-008/009 活动管理完整流程', () => {
  test.beforeEach(async ({ page }) => authenticated(page))

  test('新增活动缺少必填项时阻止提交', async ({ page }) => {
    let submitted = false
    await page.route('**/api/v1/activities**', async (route) => {
      if (route.request().method() === 'POST') submitted = true
      return route.fulfill({ json: { ...response({ items: [] }), pagination: { total: 0 } } })
    })
    await page.goto('/activities')
    await page.getByRole('button', { name: '新增活动' }).click()
    await page.getByRole('button', { name: '保存' }).click()
    await expect(page.getByText('请填写活动名称和开始时间')).toBeVisible()
    expect(submitted).toBe(false)
  })

  test('编辑活动并审核为 APPROVED', async ({ page }) => {
    let updated: Record<string, unknown> | undefined
    await page.route('**/api/v1/activities**', async (route) => {
      if (route.request().method() === 'PUT') {
        updated = route.request().postDataJSON()
        return route.fulfill({ json: response({ ...activity, ...updated }) })
      }
      return route.fulfill({ json: { ...response({ items: [activity] }), pagination: { total: 1 } } })
    })
    await page.goto('/activities')
    await page.getByRole('button', { name: '编辑' }).click()
    await page.getByLabel('名称').fill('上海周末展览（已审核）')
    await page.getByLabel('状态').click()
    await page.getByRole('option', { name: 'APPROVED' }).click()
    await page.getByRole('button', { name: '保存' }).click()
    await expect.poll(() => updated?.status).toBe('APPROVED')
    expect(updated?.name).toBe('上海周末展览（已审核）')
  })

  test('删除先取消不请求，再确认执行软删除', async ({ page }) => {
    let deletes = 0
    await page.route('**/api/v1/activities**', async (route) => {
      if (route.request().method() === 'DELETE') { deletes += 1; return route.fulfill({ json: response({ id: 1 }) }) }
      return route.fulfill({ json: { ...response({ items: [activity] }), pagination: { total: 1 } } })
    })
    await page.goto('/activities')
    await page.getByRole('button', { name: '删除' }).click()
    await page.getByRole('button', { name: '取消' }).click()
    expect(deletes).toBe(0)
    await page.getByRole('button', { name: '删除' }).click()
    await page.getByRole('button', { name: '确认' }).click()
    await expect.poll(() => deletes).toBe(1)
    await expect(page.getByText('已删除')).toBeVisible()
  })

  test('分页点击下一页请求 page=2', async ({ page }) => {
    const pages: string[] = []
    await page.route('**/api/v1/activities**', (route) => {
      pages.push(new URL(route.request().url()).searchParams.get('page') || '1')
      return route.fulfill({ json: { ...response({ items: [activity] }), pagination: { total: 21 } } })
    })
    await page.goto('/activities')
    await page.getByRole('button', { name: 'Go to next page' }).click()
    await expect.poll(() => pages).toContain('2')
  })
})

test.describe('TC-UI-010 任务完整流程', () => {
  test.beforeEach(async ({ page }) => authenticated(page))

  test('提交期间禁用按钮以防重复点击', async ({ page }) => {
    let resolveRequest: (() => void) | undefined
    let requests = 0
    await page.route('**/api/v1/tasks**', async (route) => {
      if (route.request().method() === 'POST') {
        requests += 1
        await new Promise<void>((resolve) => { resolveRequest = resolve })
        return route.fulfill({ json: response({ id: 1, status: 'PENDING' }) })
      }
      return route.fulfill({ json: response({ items: [] }) })
    })
    await page.goto('/tasks')
    const button = page.getByRole('button', { name: '开始抓取' })
    await button.click()
    await expect(button).toBeDisabled()
    await button.click({ force: true })
    expect(requests).toBe(1)
    resolveRequest?.()
  })

  test('显示暂停状态并打开任务日志', async ({ page }) => {
    const task = { id: 8, type: 'keyword', status: 'PAUSED', total_notes: 3, error_message: '请在 Chrome 登录小红书后重试' }
    await page.route('**/api/v1/tasks/8/logs', (route) => route.fulfill({ json: response([{ id: 1, level: 'ERROR', message: task.error_message, created_at: '2026-07-16T10:00:00Z' }]) }))
    await page.route('**/api/v1/tasks**', (route) => route.fulfill({ json: response({ items: [task] }) }))
    await page.goto('/tasks')
    await expect(page.getByText('PAUSED')).toBeVisible()
    await page.getByRole('button', { name: '日志' }).click()
    await expect(page.getByRole('heading', { name: '任务日志' })).toBeVisible()
    await expect(page.getByText(/请在 Chrome 登录小红书后重试/)).toBeVisible()
  })
})

test.describe('TC-UI-011 去重完整流程', () => {
  test.beforeEach(async ({ page }) => authenticated(page))

  test('双栏展示两个活动的名称、时间和地点', async ({ page }) => {
    await page.route('**/api/v1/activities/10', (route) => route.fulfill({ json: response({ ...activity, id: 10, name: '活动 A' }) }))
    await page.route('**/api/v1/activities/11', (route) => route.fulfill({ json: response({ ...activity, id: 11, name: '活动 B', location: '静安公园' }) }))
    await page.route('**/api/v1/duplicates**', (route) => route.fulfill({ json: response({ items: [{ id: 1, activity_a_id: 10, activity_b_id: 11, similarity: 0.92, matched_fields: 'city,date' }] }) }))
    await page.goto('/duplicates')
    await expect(page.getByRole('cell', { name: /活动 A 2026/ })).toBeVisible()
    await expect(page.getByRole('cell', { name: /活动 B 2026/ })).toBeVisible()
    await expect(page.getByText('静安艺术中心')).toBeVisible()
    await expect(page.getByText('静安公园')).toBeVisible()
  })

  test('保留 B 与忽略分别调用正确接口', async ({ page }) => {
    const calls: string[] = []
    await page.route('**/api/v1/duplicates**', async (route) => {
      if (route.request().method() === 'POST') { calls.push(`${route.request().url()}:${route.request().postData() || ''}`); return route.fulfill({ json: response({}) }) }
      return route.fulfill({ json: response({ items: [{ id: 1, activity_a_id: 10, activity_b_id: 11, similarity: 0.92, matched_fields: 'city,date' }] }) })
    })
    await page.route('**/api/v1/activities/*', (route) => route.fulfill({ json: response(activity) }))
    await page.goto('/duplicates')
    await page.getByRole('button', { name: '保留 B' }).click()
    await expect.poll(() => calls.some((x) => x.includes('/merge') && x.includes('"keep":"b"'))).toBe(true)
    await page.getByRole('button', { name: '不是重复' }).click()
    await expect.poll(() => calls.some((x) => x.includes('/ignore'))).toBe(true)
  })
})

test.describe('TC-UI-012 周报完整流程', () => {
  test.beforeEach(async ({ page }) => authenticated(page))

  test('Markdown 和 Excel 按钮打开正确下载地址', async ({ page }) => {
    const opened: string[] = []
    await page.addInitScript(() => { window.open = ((url?: string | URL) => { (window as any).__opened = [...((window as any).__opened || []), String(url)]; return null }) as typeof window.open })
    await page.route('**/api/v1/reports**', (route) => route.fulfill({ json: response([{ id: 3, week: '2026-W29', cities: 'shanghai', activity_count: 2, status: 'GENERATED' }]) }))
    await page.goto('/reports')
    await page.getByRole('button', { name: 'Markdown' }).click()
    await page.getByRole('button', { name: 'Excel' }).click()
    opened.push(...await page.evaluate(() => (window as any).__opened || []))
    expect(opened).toEqual(['/api/v1/reports/3/download?format=md', '/api/v1/reports/3/download?format=xlsx'])
  })
})

test.describe('TC-UI-013 配置中心完整流程', () => {
  test.beforeEach(async ({ page }) => authenticated(page))

  for (const config of [
    { tab: '关键词', labels: [['关键词', '周末活动'], ['城市代码', 'shanghai']], expected: 'keywords' },
    { tab: '博主', labels: [['用户 ID', 'user-1'], ['名称', '活动博主'], ['主页', 'https://example.com/u/1'], ['城市代码', 'shanghai']], expected: 'bloggers' },
  ]) {
    test(`新增${config.tab}配置`, async ({ page }) => {
      let posted = ''
      await page.route('**/api/v1/settings/**', async (route: Route) => {
        if (route.request().method() === 'POST') { posted = route.request().url(); return route.fulfill({ json: response({ id: 1 }) }) }
        return route.fulfill({ json: response([]) })
      })
      await page.goto('/settings')
      await page.getByRole('radio', { name: config.tab }).click()
      await page.getByRole('button', { name: '新增' }).click()
      for (const [label, value] of config.labels) await page.getByLabel(label).fill(value)
      await page.getByRole('button', { name: '保存' }).click()
      await expect.poll(() => posted).toContain(`/settings/${config.expected}`)
    })
  }

  test('删除配置并显示 OpenCLI 未登录提示', async ({ page }) => {
    let deleted = false
    await page.route('**/api/v1/settings/opencli/test', (route) => route.fulfill({ status: 401, json: { detail: 'AUTH_REQUIRED' } }))
    await page.route('**/api/v1/settings/cities**', async (route) => {
      if (route.request().method() === 'DELETE') { deleted = true; return route.fulfill({ json: response({ id: 1 }) }) }
      return route.fulfill({ json: response([{ id: 1, name: '上海', code: 'shanghai' }]) })
    })
    await page.goto('/settings')
    await page.getByRole('button', { name: '删除' }).click()
    await expect.poll(() => deleted).toBe(true)
    await page.getByRole('button', { name: '测试 OpenCLI' }).click()
    await expect(page.getByText('请在 Chrome 登录小红书')).toBeVisible()
  })
})
