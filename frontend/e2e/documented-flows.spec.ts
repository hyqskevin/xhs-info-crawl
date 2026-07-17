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
  test.beforeEach(async ({ page }) => {
    await authenticated(page)
    await page.route('**/api/v1/settings/cities**', (route) => route.fulfill({ json: response([{ id: 1, name: '上海', code: 'shanghai', enabled: true }]) }))
  })

  test('不提供手工新增活动入口', async ({ page }) => {
    await page.route('**/api/v1/activities**', (route) => route.fulfill({ json: { ...response({ items: [] }), pagination: { total: 0 } } }))
    await page.goto('/activities')
    await expect(page.getByRole('button', { name: '新增活动' })).toHaveCount(0)
    await expect(page.getByText('活动时间')).toBeVisible()
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
    await page.getByRole('button', { name: '编辑审核' }).click()
    await page.getByLabel('名称').fill('上海周末展览（已审核）')
    await page.locator('.el-form-item').filter({ hasText: '审核状态' }).locator('.el-select').click()
    await page.getByRole('option', { name: '已通过' }).click()
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
    await page.getByRole('button', { name: '删除', exact: true }).click()
    await page.getByRole('button', { name: '取消' }).click()
    expect(deletes).toBe(0)
    await page.getByRole('button', { name: '删除', exact: true }).click()
    await page.getByRole('button', { name: '确定' }).click()
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
    await page.getByRole('button', { name: '下一页' }).click()
    await expect.poll(() => pages).toContain('2')
  })

  test('勾选多条活动后批量删除', async ({ page }) => {
    let ids: number[] = []
    const second = { ...activity, id: 2, name: '上海周末市集' }
    await page.route('**/api/v1/activities**', async (route) => {
      if (route.request().method() === 'DELETE') {
        ids = route.request().postDataJSON().ids
        return route.fulfill({ json: response({ deleted_count: ids.length }) })
      }
      return route.fulfill({ json: { ...response({ items: [activity, second] }), pagination: { total: 2 } } })
    })
    await page.goto('/activities')
    await page.locator('.el-table__header .el-checkbox').click()
    await page.getByRole('button', { name: '批量删除' }).click()
    await page.getByRole('button', { name: '确定' }).click()
    await expect.poll(() => ids).toEqual([1, 2])
    await expect(page.getByText('已删除 2 条活动')).toBeVisible()
  })
})

test.describe('TC-UI-010 任务完整流程', () => {
  test.beforeEach(async ({ page }) => {
    await authenticated(page)
    await page.route('**/api/v1/settings/cities**', (route) => route.fulfill({ json: response([{ id: 1, name: '上海', code: 'shanghai', keywords: ['周末活动'], recent_filter: '一周内', enabled: true }]) }))
    await page.route('**/api/v1/settings/bloggers**', (route) => route.fulfill({ json: response([]) }))
    await page.route('**/api/v1/dashboard/summary**', (route) => route.fulfill({ json: response({ last_task: null }) }))
  })

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
    await page.goto('/dashboard')
    await page.locator('.crawl-card .el-select').nth(1).click()
    await page.getByRole('option', { name: '周末活动' }).click()
    const button = page.getByRole('button', { name: '开始抓取' })
    await button.click()
    await expect(button).toBeDisabled()
    await button.click({ force: true })
    expect(requests).toBe(1)
    resolveRequest?.()
    await expect(button).toBeEnabled()
  })

  test('显示暂停状态并打开任务日志', async ({ page }) => {
    const task = { id: 8, type: 'keyword', status: 'PAUSED', total_notes: 3, error_message: '请在 Chrome 登录小红书后重试' }
    await page.route('**/api/v1/tasks/8/logs', (route) => route.fulfill({ json: response([{ id: 1, level: 'ERROR', message: task.error_message, created_at: '2026-07-16T10:00:00Z' }]) }))
    await page.route('**/api/v1/tasks**', (route) => route.fulfill({ json: response({ items: [task] }) }))
    await page.goto('/tasks')
    await expect(page.getByText('等待登录')).toBeVisible()
    await page.getByRole('button', { name: '日志' }).click()
    await expect(page.locator('.el-drawer__title', { hasText: '任务日志' })).toBeVisible()
    await expect(page.getByText(/请在 Chrome 登录小红书后重试/)).toBeVisible()
  })

  test('仪表盘展示细化进度并可继续失败任务', async ({ page }) => {
    let restarted = false
    const failedTask = { id: 4, status: 'FAILED', total_notes: 113, downloaded_notes: 8, ocr_notes: 7, extracted_notes: 5, failed_notes: 1, current_stage: null, current_note: null, progress_percent: 4, error_message: '单条笔记解析失败' }
    await page.route('**/api/v1/dashboard/summary**', (route) => route.fulfill({ json: response({ last_task: failedTask }) }))
    await page.route('**/api/v1/tasks/4/restart', async (route) => {
      restarted = true
      return route.fulfill({ status: 202, json: response({ ...failedTask, status: 'PENDING' }) })
    })
    await page.goto('/dashboard')
    await expect(page.getByText('已下载').locator('..').getByText('8')).toBeVisible()
    await expect(page.getByText('OCR 完成').locator('..').getByText('7')).toBeVisible()
    await page.getByRole('button', { name: '继续抓取' }).click()
    await expect.poll(() => restarted).toBe(true)
    await expect(page.getByText('任务已继续抓取')).toBeVisible()
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
  test.beforeEach(async ({ page }) => {
    await authenticated(page)
    await page.route('**/api/v1/settings/cities**', (route) => route.fulfill({ json: response([{ id: 1, name: '上海', code: 'shanghai', enabled: true }]) }))
  })

  test('单城市周报使用周选择器且 Markdown 和 Excel 可下载', async ({ page }) => {
    const downloaded: string[] = []
    await page.route('**/api/v1/reports**', (route) => route.fulfill({ json: response([{ id: 3, week: '2026-W29', cities: ['shanghai'], activity_count: 2, status: 'GENERATED' }]) }))
    await page.route('**/api/v1/reports/3/download**', (route) => {
      downloaded.push(new URL(route.request().url()).searchParams.get('format') || '')
      return route.fulfill({ body: 'report', headers: { 'content-type': 'application/octet-stream', 'content-disposition': 'attachment; filename="report.md"' } })
    })
    await page.goto('/reports')
    await expect(page.getByLabel('周次')).toBeVisible()
    await expect(page.getByRole('combobox', { name: '城市' })).toBeVisible()
    await page.getByRole('button', { name: 'Markdown' }).click()
    await page.getByRole('button', { name: 'Excel' }).click()
    await expect.poll(() => downloaded).toEqual(['md', 'xlsx'])
  })
})

test.describe('TC-UI-013 配置中心完整流程', () => {
  test.beforeEach(async ({ page }) => authenticated(page))

  test('新增城市时同时保存关键词和时间范围', async ({ page }) => {
    let payload: Record<string, unknown> | undefined
    await page.route('**/api/v1/settings/**', async (route: Route) => {
      if (route.request().method() === 'POST') { payload = route.request().postDataJSON(); return route.fulfill({ json: response({ id: 1 }) }) }
      return route.fulfill({ json: response([]) })
    })
    await page.goto('/settings')
    await page.getByRole('button', { name: '新增城市' }).click()
    await page.getByLabel('城市名称').fill('宁波')
    const keyword = page.getByRole('textbox', { name: '关键词' })
    await keyword.fill('周末活动')
    await keyword.press('Enter')
    await page.getByRole('button', { name: '保存' }).click()
    await expect.poll(() => payload?.name).toBe('宁波')
    expect(payload?.keywords).toEqual(['周末活动'])
    expect(payload?.recent_filter).toBe('一周内')
    expect(payload).not.toHaveProperty('code')
  })

  test('编辑城市配置', async ({ page }) => {
    let updated = false
    await page.route('**/api/v1/settings/cities**', async (route) => {
      if (route.request().method() === 'PUT') { updated = true; return route.fulfill({ json: response({}) }) }
      return route.fulfill({ json: response([{ id: 1, name: '宁波', code: 'nb', keywords: ['活动'], recent_filter: '一周内', enabled: true }]) })
    })
    await page.goto('/settings')
    await page.getByRole('button', { name: '编辑' }).click()
    await page.getByLabel('城市名称').fill('宁波市')
    await page.getByRole('button', { name: '保存' }).click()
    await expect.poll(() => updated).toBe(true)
  })

  test('删除配置并显示 OpenCLI 未登录提示', async ({ page }) => {
    let deleted = false
    await page.route('**/api/v1/settings/opencli/test', (route) => route.fulfill({ status: 401, json: { detail: 'AUTH_REQUIRED' } }))
    await page.route('**/api/v1/settings/cities**', async (route) => {
      if (route.request().method() === 'DELETE') { deleted = true; return route.fulfill({ json: response({ id: 1 }) }) }
      return route.fulfill({ json: response([{ id: 1, name: '上海', code: 'shanghai', keywords: ['活动'], recent_filter: '一周内', enabled: true }]) })
    })
    await page.goto('/settings')
    await page.getByRole('button', { name: '删除' }).click()
    await page.getByRole('button', { name: '确定' }).click()
    await expect.poll(() => deleted).toBe(true)
    await page.getByRole('button', { name: '测试 OpenCLI' }).click()
    await expect(page.getByText('请在 Chrome 登录小红书')).toBeVisible()
  })

  test('OpenCLI 测试请求期间显示独立旋转图标，结束后显示 Toast', async ({ page }) => {
    let release: (() => void) | undefined
    await page.route('**/api/v1/settings/opencli/test', async (route) => {
      await new Promise<void>((resolve) => { release = resolve })
      return route.fulfill({ json: response({ logged_in: true }) })
    })
    await page.route('**/api/v1/settings/cities**', (route) => route.fulfill({ json: response([]) }))
    await page.goto('/settings')
    await page.getByRole('button', { name: '测试 OpenCLI' }).click()
    await expect(page.getByLabel('OpenCLI 测试中')).toBeVisible()
    release?.()
    await expect(page.getByLabel('OpenCLI 测试中')).toHaveCount(0)
    await expect(page.getByText('OpenCLI 登录与连接正常')).toBeVisible()
  })
})
