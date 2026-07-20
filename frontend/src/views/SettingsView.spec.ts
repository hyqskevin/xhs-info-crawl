import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage } from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'

import SettingsView from './SettingsView.vue'

const mocks = vi.hoisted(() => ({
  settings: vi.fn().mockImplementation((kind: string) => Promise.resolve({ data: { data: kind === 'cities'
    ? [{ id: 1, name: '宁波', code: 'nb', keywords: ['周末活动', '展览'], recent_filter: '一周内', enabled: true }]
    : [] } })),
  createSetting: vi.fn(),
  updateSetting: vi.fn(),
  deleteSetting: vi.fn(),
  downloadBloggerTemplate: vi.fn(),
  importBloggers: vi.fn(),
  testOpenCLI: vi.fn(),
}))
vi.mock('@/api/client', () => ({ api: mocks }))

afterEach(() => { document.body.innerHTML = ''; vi.clearAllMocks() })

describe('SettingsView', () => {
  it('shows city keywords and recent filter without exposing internal code', async () => {
    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(mocks.settings).toHaveBeenCalledWith('cities')
    expect(wrapper.text()).toContain('宁波')
    expect(wrapper.text()).toContain('周末活动')
    expect(wrapper.text()).toContain('一周内')
    expect(wrapper.text()).toContain('编辑')
    expect(wrapper.text()).not.toContain('城市代码')
    expect(wrapper.text()).not.toContain('关键词配置')
  })

  it('opens one city form containing keywords and supported XHS time ranges', async () => {
    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text().includes('新增城市'))!.trigger('click')
    await flushPromises()

    expect(document.body.textContent).toContain('新增城市')
    expect(document.body.textContent).toContain('关键词')
    expect(document.body.textContent).toContain('抓取时间范围')
    expect(document.body.textContent).not.toContain('城市代码')
  })

  it('shows a separate loading icon while testing OpenCLI', async () => {
    let resolveTest!: (value: unknown) => void
    mocks.testOpenCLI.mockImplementationOnce(() => new Promise((resolve) => { resolveTest = resolve }))
    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()
    const button = wrapper.findAll('button').find((item) => item.text().includes('测试 OpenCLI'))!

    await button.trigger('click')
    expect(button.attributes('disabled')).toBeDefined()
    expect(wrapper.find('.opencli-testing-icon.is-loading').exists()).toBe(true)

    resolveTest({ data: { data: { logged_in: true } } })
    await flushPromises()
    expect(wrapper.find('.opencli-testing-icon').exists()).toBe(false)
  })

  it('submits a blogger without platform_user_id and profile_url', async () => {
    mocks.createSetting.mockResolvedValue({ data: { data: { id: 99, username: 'xhs_user', city_codes: ['nb'], enabled: true } } })
    mocks.settings.mockImplementation((kind: string) => Promise.resolve({ data: { data: kind === 'cities'
      ? [{ id: 1, name: '宁波', code: 'nb', keywords: [], recent_filter: '一周内', enabled: true }]
      : [] } }))

    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()
    // 切到博主 tab
    await wrapper.findAll('input[type="radio"]').find((r) => r.attributes('value') === 'bloggers')!.trigger('click')
    await wrapper.findAll('button').find((b) => b.text().includes('新增博主'))!.trigger('click')
    await flushPromises()

    // 输入博主名称，留空 xhs_id 和 profile_url
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
    // platform_user_id 字段不存在或为空
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

    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()
    await wrapper.findAll('input[type="radio"]').find((r) => r.attributes('value') === 'bloggers')!.trigger('click')
    await flushPromises()

    const text = document.body.textContent || ''
    expect(text).toContain('博主A')
    expect(text).toContain('博主B')
    // 博主 A 的两个城市标签都应出现
    expect(text).toContain('宁波')
    expect(text).toContain('上海')
    expect(text).toContain('未关联')  // 博主 B 没绑城市
  })

  it('shows template download and batch import only on blogger tab', async () => {
    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(wrapper.text()).not.toContain('下载模板')
    expect(wrapper.text()).not.toContain('批量导入')

    await wrapper.findAll('input[type="radio"]').find((radio) => radio.attributes('value') === 'bloggers')!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('下载模板')
    expect(wrapper.text()).toContain('批量导入')
  })

  it('uploads one blogger file with loading and refreshes after success', async () => {
    let resolveImport!: (value: unknown) => void
    mocks.importBloggers.mockImplementationOnce(() => new Promise((resolve) => { resolveImport = resolve }))
    const success = vi.spyOn(ElMessage, 'success')
    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()
    await wrapper.findAll('input[type="radio"]').find((radio) => radio.attributes('value') === 'bloggers')!.trigger('click')
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
    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()
    await wrapper.findAll('input[type="radio"]').find((radio) => radio.attributes('value') === 'bloggers')!.trigger('click')
    await flushPromises()

    await wrapper.findComponent({ name: 'ElUpload' }).props('onChange')({ raw: new File(['bad'], 'bloggers.csv') })
    await flushPromises()

    expect(error).toHaveBeenCalledWith('第3行：不存在城市：杭州')
  })
})
