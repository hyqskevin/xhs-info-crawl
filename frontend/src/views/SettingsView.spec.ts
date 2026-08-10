import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage, ElMessageBox } from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import SettingsView from './SettingsView.vue'

const { mockRoute, mockRouter } = vi.hoisted(() => ({
  mockRoute: {
    query: {} as Record<string, any>,
    path: '/settings',
    fullPath: '/settings',
    meta: { title: '配置中心' },
  },
  mockRouter: { push: vi.fn(), replace: vi.fn() },
}))
vi.mock('vue-router', () => ({
  useRoute: () => mockRoute,
  useRouter: () => mockRouter,
}))

const mocks = vi.hoisted(() => ({
  settings: vi.fn().mockImplementation((kind: string) => Promise.resolve({ data: { data: kind === 'cities'
    ? [{ id: 1, name: '宁波', code: 'nb', keywords: ['周末活动', '展览'], recent_filter: '一周内', enabled: true }]
    : [] } })),
  createSetting: vi.fn(),
  updateSetting: vi.fn(),
  deleteSetting: vi.fn(),
  downloadBloggerTemplate: vi.fn(),
  importBloggers: vi.fn(),
  xhsAccounts: vi.fn().mockResolvedValue({ data: { data: [
    { id: 1, name: '主账号', remark: '日常', session_name: 'main', enabled: true, priority: 1, login_status: 'logged_in' },
    { id: 2, name: '备用账号', remark: '', session_name: 'backup', enabled: false, priority: 2, login_status: 'logged_out' },
  ] } }),
  createXhsAccount: vi.fn().mockResolvedValue({ data: { data: { id: 99, name: '新账号', session_name: 'new', enabled: true, priority: 3 } } }),
  updateXhsAccount: vi.fn().mockResolvedValue({ data: { data: {} } }),
  deleteXhsAccount: vi.fn().mockResolvedValue({ data: { data: {} } }),
  checkXhsAccountLogin: vi.fn().mockResolvedValue({ data: { data: { id: 1, name: '主账号', remark: '日常', session_name: 'main', enabled: true, priority: 1, login_status: 'logged_in', logged_in: true, raw: { username: '小红' } } } }),
  keywordGroups: vi.fn().mockResolvedValue({ data: { data: { items: [] } } }),
  bloggerGroups: vi.fn().mockResolvedValue({ data: { data: { items: [] } } }),
  systemConfig: vi.fn().mockResolvedValue({ data: { data: {
    minimax_api_key: '', minimax_base_url: 'https://api.minimaxi.com/v1', minimax_model: 'MiniMax-M3',
    minimax_timeout_seconds: 180, ocr_enabled: false, ocr_language: 'ch', ocr_min_confidence: 0.5,
    pipeline_stage_max_retries: 2, pipeline_stage_retry_delay_seconds: 2,
    xhs_search_target_count: 50, xhs_search_scroll_max_rounds: 8, xhs_scroll_pixels: 800,
    xhs_scroll_stagnant_rounds: 2, search_limit: 50, weekly_search_limit: 500,
    consecutive_note_failure_limit: 3, activity_future_window_days: 60,
    opencli_bin: 'opencli',
  } } }),
  updateSystemConfig: vi.fn().mockResolvedValue({ data: { data: {} } }),
}))
vi.mock('@/api/client', () => ({ api: mocks }))

afterEach(() => { document.body.innerHTML = ''; vi.clearAllMocks() })
beforeEach(() => {
  mockRoute.query = {}
  mockRoute.path = '/settings'
  mockRoute.fullPath = '/settings'
})

describe('SettingsView', () => {
  it('defaults to cities tab when no query', async () => {
    mockRoute.query = {}
    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(mocks.settings).toHaveBeenCalledWith('cities')
    expect(wrapper.text()).toContain('新增城市')
    expect(wrapper.text()).not.toContain('下载模板')
    expect(wrapper.text()).not.toContain('批量导入')
  })

  it('reads tab from route query', async () => {
    mocks.settings.mockImplementation((kind: string) => Promise.resolve({ data: { data: kind === 'cities'
      ? [{ id: 1, name: '宁波', code: 'nb', keywords: [], recent_filter: '一周内', enabled: true }]
      : [{ id: 100, username: '博主A', profile_url: 'https://xhs/u/A', city_codes: ['nb'], enabled: true }] } }))
    mockRoute.query = { tab: 'bloggers' }

    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(mocks.settings).toHaveBeenCalledWith('bloggers')
    expect(wrapper.text()).toContain('博主A')
    expect(wrapper.text()).toContain('下载模板')
    expect(wrapper.text()).toContain('批量导入')
    expect(wrapper.text()).not.toContain('新增城市')
  })

  it('shows city recent filter without exposing internal code', async () => {
    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(mocks.settings).toHaveBeenCalledWith('cities')
    expect(wrapper.text()).toContain('宁波')
    expect(wrapper.text()).toContain('一周内')
    expect(wrapper.text()).toContain('编辑')
    expect(wrapper.text()).not.toContain('城市代码')
    expect(wrapper.text()).not.toContain('关键词配置')
  })

  it('opens one city form with supported XHS time ranges', async () => {
    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text().includes('新增城市'))!.trigger('click')
    await flushPromises()

    expect(document.body.textContent).toContain('新增城市')
    expect(document.body.textContent).toContain('抓取时间范围')
    expect(document.body.textContent).not.toContain('城市代码')
  })

  it('submits a blogger without platform_user_id and profile_url', async () => {
    mocks.createSetting.mockResolvedValue({ data: { data: { id: 99, username: 'xhs_user', city_codes: ['nb'], enabled: true } } })
    mocks.settings.mockImplementation((kind: string) => Promise.resolve({ data: { data: kind === 'cities'
      ? [{ id: 1, name: '宁波', code: 'nb', keywords: [], recent_filter: '一周内', enabled: true }]
      : [] } }))
    mockRoute.query = { tab: 'bloggers' }

    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增博主'))!.trigger('click')
    await flushPromises()

    const inputs = document.body.querySelectorAll('input')
    let usernameInput: HTMLInputElement | undefined
    for (const input of Array.from(inputs)) {
      const formItem = input.closest('.el-form-item')
      if (formItem?.textContent?.includes('博主名称')) {
        usernameInput = input as HTMLInputElement
        break
      }
    }
    usernameInput!.value = 'xhs_user'
    usernameInput!.dispatchEvent(new Event('input', { bubbles: true }))

    await wrapper.findAll('button').find((b) => b.text().trim() === '保存')!.trigger('click')
    await flushPromises()

    const call = mocks.createSetting.mock.calls.find((c) => c[0] === 'bloggers')!
    const payload = call[1]
    expect(payload.platform_user_id === '' || payload.platform_user_id == null).toBe(true)
    expect(payload.username).toBe('xhs_user')
    expect(payload.city_codes).toEqual([])
  })

  it('renders blogger list with city tag from city_codes array', async () => {
    mocks.settings.mockImplementation((kind: string) => Promise.resolve({ data: { data: kind === 'cities'
      ? [
          { id: 1, name: '宁波', code: 'nb', keywords: [], recent_filter: '一周内', enabled: true },
          { id: 2, name: '上海', code: 'city-99f1e469', keywords: [], recent_filter: '一周内', enabled: true },
        ]
      : [
          { id: 100, username: '博主A', profile_url: 'https://xhs/u/A', city_codes: ['nb', 'city-99f1e469'], enabled: true },
          { id: 101, username: '博主B', profile_url: 'https://xhs/u/B', city_codes: [], enabled: true },
        ] } }))
    mockRoute.query = { tab: 'bloggers' }

    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    const text = document.body.textContent || ''
    expect(text).toContain('博主A')
    expect(text).toContain('博主B')
    expect(text).toContain('宁波')
    expect(text).toContain('上海')
    expect(text).toContain('未关联')
  })

  it('shows template download and batch import only on blogger tab', async () => {
    mockRoute.query = { tab: 'bloggers' }
    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(wrapper.text()).toContain('下载模板')
    expect(wrapper.text()).toContain('批量导入')
  })

  it('uploads one blogger file with loading and refreshes after success', async () => {
    let resolveImport!: (value: unknown) => void
    mocks.importBloggers.mockImplementationOnce(() => new Promise((resolve) => { resolveImport = resolve }))
    const success = vi.spyOn(ElMessage, 'success')
    mockRoute.query = { tab: 'bloggers' }

    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()
    const upload = wrapper.findComponent({ name: 'ElUpload' })
    const file = new File(['content'], 'bloggers.xlsx')

    const importing = upload.props('onChange')({ raw: file })
    await wrapper.vm.$nextTick()

    expect(mocks.importBloggers).toHaveBeenCalledWith(file)
    expect(wrapper.findAll('button').find((button) => button.text().includes('批量导入'))!.classes()).toContain('is-loading')

    resolveImport({ data: { data: { created: 2, updated: 1, total: 3 } } })
    await importing
    await flushPromises()

    expect(success).toHaveBeenCalledWith('导入成功：新增 2，更新 1')
    expect(mocks.settings.mock.calls.filter((call) => call[0] === 'bloggers').length).toBeGreaterThanOrEqual(2)
  })

  it('shows the backend row error when batch import fails', async () => {
    mocks.importBloggers.mockRejectedValueOnce({ response: { data: { message: '第3行：不存在城市：杭州' } } })
    const error = vi.spyOn(ElMessage, 'error')
    mockRoute.query = { tab: 'bloggers' }

    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    await wrapper.findComponent({ name: 'ElUpload' }).props('onChange')({ raw: new File(['bad'], 'bloggers.csv') })
    await flushPromises()

    expect(error).toHaveBeenCalledWith('第3行：不存在城市：杭州')
  })

  it('shows system config tab with grouped sections', async () => {
    mockRoute.query = { tab: 'system-config' }
    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(mocks.systemConfig).toHaveBeenCalled()
    const text = document.body.textContent || ''
    expect(text).toContain('系统配置')
    expect(text).toContain('活动识别模型')
    expect(text).toContain('PaddleOCR')
    expect(text).toContain('单笔记流水线重试')
    expect(text).toContain('小红书滚动策略')
    expect(text).toContain('抓取工具')
    expect(text).toContain('opencli 路径')
    expect(text).toContain('抓取数量')
    expect(text).toContain('保存配置')
    expect(text).toContain('重置')
  })

  it('renders opencli_bin input and sends value on save', async () => {
    mockRoute.query = { tab: 'system-config' }
    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    const input = wrapper.find('input[placeholder="opencli"]')
    expect(input.exists()).toBe(true)
    await input.setValue('/Users/kevin_w/.nvm/versions/node/v22.18.0/bin/opencli')

    const saveButton = Array.from(document.body.querySelectorAll('button')).find((b) => b.textContent?.includes('保存配置'))!
    saveButton.dispatchEvent(new Event('click'))
    await flushPromises()

    expect(mocks.updateSystemConfig).toHaveBeenCalled()
    const payload = mocks.updateSystemConfig.mock.calls[0]?.[0] as Record<string, unknown>
    expect(payload.opencli_bin).toBe('/Users/kevin_w/.nvm/versions/node/v22.18.0/bin/opencli')
  })

  it('saves system config and shows success message', async () => {
    const success = vi.spyOn(ElMessage, 'success')
    mockRoute.query = { tab: 'system-config' }
    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    const saveButton = Array.from(document.body.querySelectorAll('button')).find((b) => b.textContent?.includes('保存配置'))!
    saveButton.dispatchEvent(new Event('click'))
    await flushPromises()

    expect(mocks.updateSystemConfig).toHaveBeenCalled()
    expect(success).toHaveBeenCalledWith('系统配置已保存，重启服务后生效')
    success.mockRestore()
  })

  it('hides add button on system config tab', async () => {
    mockRoute.query = { tab: 'system-config' }
    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(wrapper.text()).not.toContain('新增城市')
    expect(wrapper.text()).not.toContain('新增博主')
  })

  it('loads xhs-accounts tab and renders account table with name/remark/session/login/enabled/priority', async () => {
    mockRoute.query = { tab: 'xhs-accounts' }
    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(mocks.xhsAccounts).toHaveBeenCalled()
    const text = document.body.textContent || ''
    expect(text).toContain('主账号')
    expect(text).toContain('备用账号')
    expect(text).toContain('main')
    expect(text).toContain('backup')
    expect(text).toContain('检测登录')
    expect(text).toContain('新增账号')
  })

  it('shows login status tag for xhs accounts', async () => {
    mockRoute.query = { tab: 'xhs-accounts' }
    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    const text = document.body.textContent || ''
    // logged_in 显示「已登录」，logged_out 显示「未登录」
    expect(text).toContain('已登录')
    expect(text).toContain('未登录')
  })

  it('creates a new xhs account via api.createXhsAccount', async () => {
    const success = vi.spyOn(ElMessage, 'success')
    mockRoute.query = { tab: 'xhs-accounts' }
    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    await wrapper.findAll('button').find((b) => b.text().includes('新增账号'))!.trigger('click')
    await flushPromises()

    // 填写名称
    const inputs = document.body.querySelectorAll('input')
    let nameInput: HTMLInputElement | undefined
    for (const input of Array.from(inputs)) {
      const formItem = input.closest('.el-form-item')
      if (formItem?.textContent?.includes('账号名称')) {
        nameInput = input as HTMLInputElement
        break
      }
    }
    nameInput!.value = '新账号'
    nameInput!.dispatchEvent(new Event('input', { bubbles: true }))

    await wrapper.findAll('button').find((b) => b.text().trim() === '保存')!.trigger('click')
    await flushPromises()

    expect(mocks.createXhsAccount).toHaveBeenCalled()
    const payload = mocks.createXhsAccount.mock.calls[0][0]
    expect(payload.name).toBe('新账号')
    expect(success).toHaveBeenCalledWith('保存成功')
  })

  it('checks login status when clicking 检测登录 button', async () => {
    const success = vi.spyOn(ElMessage, 'success')
    mockRoute.query = { tab: 'xhs-accounts' }
    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    const checkButton = wrapper.findAll('button').find((b) => b.text().includes('检测登录'))!
    await checkButton.trigger('click')
    await flushPromises()

    expect(mocks.checkXhsAccountLogin).toHaveBeenCalled()
  })

  it('deletes an xhs account via api.deleteXhsAccount', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as any)
    mockRoute.query = { tab: 'xhs-accounts' }
    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    const deleteButton = wrapper.findAll('button').filter((b) => b.text().includes('删除'))[0]
    await deleteButton.trigger('click')
    await flushPromises()

    expect(mocks.deleteXhsAccount).toHaveBeenCalled()
  })
})
