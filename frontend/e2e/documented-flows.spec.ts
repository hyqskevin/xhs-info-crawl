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
const note = {
  id: 1,
  title: '上海周末展览推文',
  city_code: 'shanghai',
  published_at: '2026-07-18T09:00:00Z',
  created_at: '2026-07-18T09:00:00Z',
  activity_count: 1,
  review_status: 'PENDING',
}
const noteDetail = {
  ...note,
  content: '页面正文',
  source_url: 'https://example.com/note/1',
  activities: [activity],
  images: [],
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
    await page.route('**/api/v1/notes**', (route) => route.fulfill({ json: { ...response({ items: [] }), pagination: { total: 0 } } }))
    await page.goto('/activities')
    await expect(page.getByRole('button', { name: '新增活动' })).toHaveCount(0)
    await expect(page.getByText('发布时间')).toBeVisible()
  })

  test('在推文详情中编辑识别活动', async ({ page }) => {
    let updated: Record<string, unknown> | undefined
    await page.route('**/api/v1/notes**', (route) => {
      const pathname = new URL(route.request().url()).pathname
      if (pathname.endsWith('/notes/1')) return route.fulfill({ json: response(noteDetail) })
      return route.fulfill({ json: { ...response({ items: [note] }), pagination: { total: 1 } } })
    })
    await page.route('**/api/v1/activities/1', async (route) => {
      if (route.request().method() === 'PUT') {
        updated = route.request().postDataJSON()
        return route.fulfill({ json: response({ ...activity, ...updated }) })
      }
      return route.fulfill({ json: response(activity) })
    })
    await page.goto('/activities')
    await page.getByRole('button', { name: '详情' }).click()
    await page.getByRole('button', { name: '编辑' }).click()
    await page.getByLabel('名称').fill('上海周末展览（已审核）')
    await page.getByRole('button', { name: '保存' }).click()
    expect(updated?.name).toBe('上海周末展览（已审核）')
  })

  test('子活动删除先取消不请求，再确认执行', async ({ page }) => {
    let deletes = 0
    await page.route('**/api/v1/notes**', (route) => {
      const pathname = new URL(route.request().url()).pathname
      if (pathname.endsWith('/notes/1')) return route.fulfill({ json: response(noteDetail) })
      return route.fulfill({ json: { ...response({ items: [note] }), pagination: { total: 1 } } })
    })
    await page.route('**/api/v1/activities/1', async (route) => {
      if (route.request().method() === 'DELETE') { deletes += 1; return route.fulfill({ json: response({ id: 1 }) }) }
      return route.fulfill({ json: response(activity) })
    })
    await page.goto('/activities')
    await page.getByRole('button', { name: '详情' }).click()
    await page.getByRole('button', { name: '删除', exact: true }).click()
    await page.getByRole('button', { name: '取消' }).click()
    expect(deletes).toBe(0)
    await page.getByRole('button', { name: '删除', exact: true }).click()
    await page.getByRole('button', { name: '确定' }).click()
    await expect.poll(() => deletes).toBe(1)
  })

  test('分页点击下一页请求 page=2', async ({ page }) => {
    const pages: string[] = []
    await page.route('**/api/v1/notes**', (route) => {
      pages.push(new URL(route.request().url()).searchParams.get('page') || '1')
      return route.fulfill({ json: { ...response({ items: [note] }), pagination: { total: 21 } } })
    })
    await page.goto('/activities')
    await page.getByRole('button', { name: '下一页' }).click()
    await expect.poll(() => pages).toContain('2')
  })

  test('勾选多篇推文后批量删除', async ({ page }) => {
    let ids: number[] = []
    const second = { ...note, id: 2, title: '上海周末市集推文' }
    await page.route('**/api/v1/notes**', async (route) => {
      if (route.request().method() === 'DELETE') {
        ids = route.request().postDataJSON().ids
        return route.fulfill({ json: response({ deleted_count: ids.length }) })
      }
      return route.fulfill({ json: { ...response({ items: [note, second] }), pagination: { total: 2 } } })
    })
    await page.goto('/activities')
    await page.locator('.el-table__header .el-checkbox').click()
    await page.getByRole('button', { name: '批量删除' }).click()
    await page.getByRole('button', { name: '确定' }).click()
    await expect.poll(() => ids).toEqual([1, 2])
    await expect(page.getByText('已删除 2 篇推文')).toBeVisible()
  })

  test('宽版活动详情在表格下展示来源页面图片并支持预览', async ({ page }) => {
    const detail = { ...noteDetail, title: '宁波活动图集', images: [{ id: 11 }, { id: 12 }] }
    await page.route('**/api/v1/notes**', (route) => {
      const pathname = new URL(route.request().url()).pathname
      if (pathname.endsWith('/notes/1')) return route.fulfill({ json: response(detail) })
      return route.fulfill({ json: { ...response({ items: [note] }), pagination: { total: 1 } } })
    })
    await page.route('**/api/v1/notes/1/images/**', (route) => route.fulfill({ body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64'), contentType: 'image/png' }))
    await page.goto('/activities')
    await page.getByRole('button', { name: '详情' }).click()

    await expect(page.locator('.el-drawer')).toHaveCSS('width', /70%|[7-9][0-9]{2}px/)
    await expect(page.getByText('宁波活动图集')).toBeVisible()
    await expect(page.getByRole('heading', { name: '来源页面图片' })).toBeVisible()
    await expect(page.locator('.source-image-grid .el-image')).toHaveCount(2)
    await page.locator('.source-image-grid .el-image').first().click()
    await expect(page.locator('.el-image-viewer__wrapper')).toBeVisible()
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

  test('仪表盘确认后安全停止运行任务并展示跳过计数', async ({ page }) => {
    let stopped = false
    const runningTask = { id: 4, status: 'RUNNING', total_notes: 20, downloaded_notes: 8, ocr_notes: 7, extracted_notes: 5, success_notes: 5, failed_notes: 1, skipped_notes: 4, current_stage: 'OCR', current_note: '周末活动', progress_percent: 50, error_message: null }
    await page.route('**/api/v1/dashboard/summary**', (route) => route.fulfill({ json: response({ last_task: runningTask }) }))
    await page.route('**/api/v1/tasks/4/stop', (route) => {
      stopped = true
      return route.fulfill({ status: 202, json: response({ ...runningTask, status: 'STOP_REQUESTED' }) })
    })
    await page.goto('/dashboard')
    await expect(page.getByText('已跳过').locator('..').getByText('4')).toBeVisible()
    await page.getByRole('button', { name: '停止抓取' }).click()
    await page.getByRole('button', { name: '确定' }).click()
    await expect.poll(() => stopped).toBe(true)
    await expect(page.getByText('已请求安全停止')).toBeVisible()
  })

  test('已停止任务可以按原任务继续抓取', async ({ page }) => {
    let restarted = false
    const stoppedTask = { id: 4, status: 'STOPPED', total_notes: 20, downloaded_notes: 8, ocr_notes: 7, extracted_notes: 5, success_notes: 5, failed_notes: 0, skipped_notes: 4, current_stage: null, current_note: null, progress_percent: 45, error_message: null }
    await page.route('**/api/v1/dashboard/summary**', (route) => route.fulfill({ json: response({ last_task: stoppedTask }) }))
    await page.route('**/api/v1/tasks/4/restart', (route) => {
      restarted = true
      return route.fulfill({ status: 202, json: response({ ...stoppedTask, status: 'PENDING' }) })
    })
    await page.goto('/dashboard')
    await expect(page.getByText('已停止')).toBeVisible()
    await page.getByRole('button', { name: '继续抓取' }).click()
    await expect.poll(() => restarted).toBe(true)
  })

  test('等待登录任务可打开 Chrome 登录页并检测登录后继续', async ({ page }) => {
    let opened = false
    let restarted = false
    const pausedTask = { id: 4, status: 'PAUSED', total_notes: 102, downloaded_notes: 19, ocr_notes: 19, extracted_notes: 19, success_notes: 19, failed_notes: 0, skipped_notes: 0, skipped_activities: 3, current_stage: 'DOWNLOADING', current_note: '活动笔记', progress_percent: 18.6, error_message: '请在 Chrome 登录小红书后重试' }
    await page.route('**/api/v1/dashboard/summary**', (route) => route.fulfill({ json: response({ last_task: pausedTask }) }))
    await page.route('**/api/v1/settings/opencli/open-login', (route) => {
      opened = true
      return route.fulfill({ json: response({ url: 'https://www.xiaohongshu.com/explore' }) })
    })
    await page.route('**/api/v1/tasks/4/restart', (route) => {
      restarted = true
      return route.fulfill({ status: 202, json: response({ ...pausedTask, status: 'PENDING' }) })
    })

    await page.goto('/dashboard')
    await expect(page.getByText('活动已跳过').locator('..').getByText('3')).toBeVisible()
    await page.getByRole('button', { name: '打开小红书登录' }).click()
    await expect.poll(() => opened).toBe(true)
    await expect(page.getByText('已打开 Chrome 小红书登录页')).toBeVisible()
    await page.getByRole('button', { name: '检测登录并继续' }).click()
    await expect.poll(() => restarted).toBe(true)
    await expect(page.getByText('登录状态正常，任务已继续抓取')).toBeVisible()
  })
})

test.describe('TC-UI-011 推文去重完整流程', () => {
  test.beforeEach(async ({ page }) => authenticated(page))

  test('双栏展示两篇推文的标题、发布时间和活动数', async ({ page }) => {
    await page.route('**/api/v1/notes/10', (route) => route.fulfill({ json: response({ ...note, id: 10, title: '推文 A' }) }))
    await page.route('**/api/v1/notes/11', (route) => route.fulfill({ json: response({ ...note, id: 11, title: '推文 B', activity_count: 2 }) }))
    await page.route('**/api/v1/duplicates**', (route) => route.fulfill({ json: response({ items: [{ id: 1, note_a_id: 10, note_b_id: 11, similarity: 0.92, matched_fields: 'city,published_at' }] }) }))
    await page.goto('/duplicates')
    await expect(page.getByRole('cell', { name: /推文 A 2026/ })).toBeVisible()
    await expect(page.getByRole('cell', { name: /推文 B 2026/ })).toBeVisible()
    await expect(page.getByText('识别活动 1 条')).toBeVisible()
    await expect(page.getByText('识别活动 2 条')).toBeVisible()
  })

  test('保留 B 与忽略分别调用正确接口', async ({ page }) => {
    const calls: string[] = []
    await page.route('**/api/v1/duplicates**', async (route) => {
      if (route.request().method() === 'POST') { calls.push(`${route.request().url()}:${route.request().postData() || ''}`); return route.fulfill({ json: response({}) }) }
      return route.fulfill({ json: response({ items: [{ id: 1, note_a_id: 10, note_b_id: 11, similarity: 0.92, matched_fields: 'city,published_at' }] }) })
    })
    await page.route('**/api/v1/notes/*', (route) => route.fulfill({ json: response(note) }))
    await page.goto('/duplicates')
    await page.getByRole('button', { name: '保留 B' }).click()
    await expect.poll(() => calls.some((x) => x.includes('/merge') && x.includes('"keep":"b"'))).toBe(true)
    await page.getByRole('button', { name: '更多' }).click()
    await page.getByRole('menuitem', { name: '不是重复' }).click()
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

  test('下载模板并批量导入博主后刷新列表', async ({ page }) => {
    let imported = false
    await page.route('**/api/v1/settings/cities**', (route) => route.fulfill({ json: response([
      { id: 1, name: '宁波', code: 'nb', keywords: [], recent_filter: '一周内', enabled: true },
    ]) }))
    await page.route('**/api/v1/settings/bloggers**', async (route) => {
      const pathname = new URL(route.request().url()).pathname
      if (pathname.endsWith('/import-template')) {
        return route.fulfill({
          body: 'template',
          headers: { 'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'content-disposition': 'attachment; filename="blogger-import-template.xlsx"' },
        })
      }
      if (pathname.endsWith('/import') && route.request().method() === 'POST') {
        imported = true
        expect(new URL(route.request().url()).searchParams.get('filename')).toBe('bloggers.csv')
        return route.fulfill({ status: 201, json: response({ created: 1, updated: 0, total: 1 }) })
      }
      return route.fulfill({ json: response(imported ? [
        { id: 8, username: '批量博主', profile_url: '', city_codes: ['nb'], enabled: true },
      ] : []) })
    })
    await page.goto('/settings')
    await page.getByText('博主白名单').click()

    const download = page.waitForEvent('download')
    await page.getByRole('button', { name: '下载模板' }).click()
    expect((await download).suggestedFilename()).toBe('blogger-import-template.xlsx')

    await page.locator('input[type="file"]').setInputFiles({
      name: 'bloggers.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from('博主名称,小红书用户ID,主页地址,关联城市,启用\n批量博主,,,宁波,是\n'),
    })
    await expect(page.getByText('导入成功：新增 1，更新 0')).toBeVisible()
    await expect(page.getByText('批量博主')).toBeVisible()
  })
})
